"""Access to Librus Synergia through the librus-apix library.

LibrusClient fixes library defects in our own code (the library stays unmodified):
- each client gets its own cookie jar and session (the library default jar is one
  object shared by all clients, so two students would share cookies),
- every request has a timeout and waits for the shared request gap,
- refused requests (HTTP 403, 429, 5xx) raise LibrusUnavailableError,
- expired sessions are detected on every page and raise the library TokenError,
- an optional base URL points all Synergia pages to another server (the mock).

LibrusApi runs library calls for one account through the shared request queue,
logs in again at most once per call and maps all errors to our exceptions.
"""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
import inspect
import logging
import re
from typing import Any
from urllib.parse import urlsplit

from homeassistant.core import HomeAssistant
import requests
from requests.cookies import RequestsCookieJar

from librus_apix import urls
from librus_apix.client import Client, Token
from librus_apix.exceptions import (
    ArgumentError,
    AuthorizationError,
    DateError,
    MaintananceError,
    ParseError,
    TokenError,
    TokenKeyError,
)

from .const import REQUEST_TIMEOUT
from .exceptions import (
    LibrusAuthError,
    LibrusConnectionError,
    LibrusError,
    LibrusParseError,
    LibrusSessionExpiredError,
    LibrusUnavailableError,
)
from .request_queue import RequestQueue, async_get_request_queue

_LOGGER = logging.getLogger(__name__)

# Mock mode skips the login (it uses hard-coded Librus URLs); the mock ignores cookies.
MOCK_TOKEN = "mock:mock"

# Synergia shows "Brak dostępu" (no access) or the login page for an expired session.
_NO_ACCESS = re.compile('class="inside"[^>]*>\\s*Brak dostępu'.encode())
_LOGIN_PATH = "/loguj"

type Throttle = Callable[[], AbstractContextManager[None]]


def _url_overrides(base_url: str) -> dict[str, str]:
    """Return the Client URL arguments with the Synergia base URL replaced."""
    return {
        param.name: base_url + param.default.removeprefix(urls.BASE_URL)
        for param in inspect.signature(Client.__init__).parameters.values()
        if isinstance(param.default, str) and param.default.startswith(urls.BASE_URL)
    }


def _short(err: Exception) -> str:
    """Return a short error text (library messages can contain whole pages)."""
    return str(err)[:200] or type(err).__name__


def _request_error(err: requests.RequestException) -> str:
    """Server and cause only, e.g. "no connection to host:8000 (NameResolutionError)".

    The full requests/urllib3 text repeats the URL and the whole retry chain.
    """
    url = err.request.url if err.request is not None else None
    host = (urlsplit(url).netloc if url else "") or "Librus"
    if isinstance(err, requests.Timeout):
        return f"no answer from {host} ({type(err).__name__})"
    if isinstance(err, requests.ConnectionError):
        cause = err.args[0] if err.args else err
        # MaxRetryError keeps the real cause in .reason.
        cause = getattr(cause, "reason", None) or cause
        name = (
            type(cause).__name__ if isinstance(cause, Exception) else "ConnectionError"
        )
        return f"no connection to {host} ({name})"
    return f"request to {host} failed ({type(err).__name__})"


def _check_status(response: requests.Response, *args: Any, **kwargs: Any) -> None:
    """Session response hook: raise when the server refuses service."""
    status = response.status_code
    if status not in (403, 429) and status < 500:
        return
    try:
        body = response.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and body.get("status") == "error":
        # Login error reply (for example a wrong password): the library reads it.
        return
    if status == 503 and isinstance(body, dict) and "Message" in body:
        raise LibrusUnavailableError("Librus is in maintenance", maintenance=True)
    retry_after = response.headers.get("Retry-After", "")
    raise LibrusUnavailableError(
        f"Librus refused the request (HTTP {status})",
        retry_after=float(retry_after) if retry_after.isdigit() else None,
    )


class _LibrusSession(requests.Session):
    """Session with a default timeout, the request gap and status checks."""

    def __init__(self, throttle: Throttle) -> None:
        super().__init__()
        self._throttle = throttle
        self.hooks["response"].append(_check_status)

    def request(self, method: str, url: str, *args: Any, **kwargs: Any) -> Any:
        """Send one request (redirects included) after the request gap."""
        if kwargs.get("timeout") is None:
            kwargs["timeout"] = REQUEST_TIMEOUT
        with self._throttle():
            return super().request(method, url, *args, **kwargs)


class LibrusClient(Client):
    """librus-apix Client with the fixes listed in the module docstring."""

    def __init__(
        self, base_url: str | None = None, throttle: Throttle = nullcontext
    ) -> None:
        """Create a client with no token. ``base_url`` replaces the Synergia URL."""
        overrides = _url_overrides(base_url.rstrip("/")) if base_url else {}
        super().__init__(Token(), extra_cookies=RequestsCookieJar(), **overrides)
        self._session = _LibrusSession(throttle)
        self._headers = {**self._session.headers, **urls.HEADERS}

    def get(self, url: str) -> requests.Response:
        """GET a page."""
        return self._send("GET", url)

    def post(self, url: str, data: dict[str, str]) -> requests.Response:
        """POST a form."""
        return self._send("POST", url, data=data)

    def post_json(self, url: str, data: dict | None = None) -> requests.Response:
        """POST a JSON body (gateway API)."""
        return self._send(
            "POST", url, json=data or {}, headers={"Content-Type": "application/json"}
        )

    def _send(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        """Send with the session cookies, keeping the connection open."""
        self.cookies.update(self.token.access_cookies())
        # The library's own calls (login, OAuth refresh) replace these; restore them.
        self._session.headers = self._headers
        self._session.cookies = self.cookies
        response = self._session.request(method, url, proxies=self.proxy, **kwargs)
        if urlsplit(response.url).path.startswith(_LOGIN_PATH) or _NO_ACCESS.search(
            response.content
        ):
            raise TokenError("Session expired")
        return response


@contextmanager
def _mapped_errors(auth_error: type[LibrusError]) -> Iterator[None]:
    """Turn library and requests errors into our exceptions.

    ``auth_error`` replaces AuthorizationError: LibrusAuthError for the login,
    LibrusSessionExpiredError for data calls (a failed OAuth refresh means the
    session expired, so a new login can fix it).
    """
    try:
        yield
    except LibrusError:
        raise
    except TokenError as err:
        raise LibrusSessionExpiredError(_short(err)) from err
    except (AuthorizationError, TokenKeyError) as err:
        raise auth_error(_short(err)) from err
    except MaintananceError as err:
        raise LibrusUnavailableError(
            f"Librus is in maintenance: {_short(err)}", maintenance=True
        ) from err
    except requests.JSONDecodeError as err:
        raise LibrusParseError(f"Unexpected response: {_short(err)}") from err
    except requests.RequestException as err:
        raise LibrusConnectionError(_request_error(err)) from err
    except (
        ParseError,
        DateError,
        ArgumentError,
        AttributeError,
        IndexError,
        KeyError,
        TypeError,
        ValueError,
    ) as err:
        raise LibrusParseError(_short(err)) from err


class LibrusApi:
    """Async access to one Librus account through the shared request queue."""

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        base_url: str | None = None,
        queue: RequestQueue | None = None,
    ) -> None:
        """Prepare the client. ``base_url`` selects mock mode (no login)."""
        self._username = username
        self._password = password
        self._mock = base_url is not None
        self._queue = queue or async_get_request_queue(hass)
        self.client = LibrusClient(base_url, self._queue.request_slot)
        self._host = urlsplit(self.client.BASE_URL).netloc
        self._logged_in = False

    async def async_login(self) -> None:
        """Log in. Raises LibrusAuthError for wrong credentials."""
        self._logged_in = False
        await self._queue.async_run(self._host, self._login)
        self._logged_in = True
        _LOGGER.debug("Logged in to %s", self._host)

    async def async_call[T](self, func: Callable[..., T], *args: Any) -> T:
        """Return ``func(client, *args)``; log in first or again (once) if needed."""
        fresh_login = not self._logged_in
        if fresh_login:
            await self.async_login()
        try:
            return await self._queue.async_run(self._host, self._call, func, *args)
        except LibrusSessionExpiredError as err:
            if fresh_login:
                self._logged_in = False
                raise LibrusAuthError("Session rejected right after login") from err
        _LOGGER.debug("Session expired on %s, logging in again", self._host)
        await self.async_login()
        try:
            return await self._queue.async_run(self._host, self._call, func, *args)
        except LibrusSessionExpiredError as err:
            self._logged_in = False
            raise LibrusAuthError("Session rejected right after login") from err

    def diagnostics(self) -> dict[str, Any]:
        """Connection state for diagnostics (no credentials, no cookies)."""
        return {"host": self._host, "mock": self._mock, "logged_in": self._logged_in}

    def close(self) -> None:
        """Close the HTTP session (executor)."""
        self.client._session.close()

    def _login(self) -> None:
        """Get new session cookies (executor)."""
        if self._mock:
            self.client.token = Token(API_Key=MOCK_TOKEN)
            return
        with _mapped_errors(LibrusAuthError):
            self.client.get_token(self._username, self._password)

    def _call[T](self, func: Callable[..., T], *args: Any) -> T:
        """Run one library call (executor)."""
        with _mapped_errors(LibrusSessionExpiredError):
            return func(self.client, *args)
