"""Tests for LibrusClient and LibrusApi (HTTP is mocked with requests-mock)."""

import asyncio
from itertools import pairwise
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from librus_apix import urls
from librus_apix.client import Client, Token
from librus_apix.exceptions import (
    AuthorizationError,
    MaintananceError,
    ParseError,
    TokenError,
)
import pytest
import requests
from requests.cookies import MockRequest, MockResponse
import requests_mock as rm

from custom_components.librus_apix.api import LibrusApi, LibrusClient
from custom_components.librus_apix.const import BACKOFF_START, REQUEST_TIMEOUT
from custom_components.librus_apix.exceptions import (
    LibrusAuthError,
    LibrusConnectionError,
    LibrusParseError,
    LibrusUnavailableError,
)
from custom_components.librus_apix.request_queue import RequestQueue

USERNAME = "jan.kowalski"
PASSWORD = "S3cret-Pass!"
SESSION_ID = "L01~session-id-value"
SESSION_ID_2 = "second-session-id-value"
NO_ACCESS_PAGE = '<html><body><h2 class="inside">Brak dostępu</h2></body></html>'
LOGIN_URL = f"{urls.API_URL}/OAuth/Authorization"


def _info(client: Client) -> str:
    """Read one page, like the library parsers do."""
    return client.get(client.INFO_URL).text


@pytest.fixture
def login(requests_mock: rm.Mocker, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Mock the Librus login; return the login POST matcher.

    requests-mock builds responses without an original HTTP response, so requests
    does not copy Set-Cookie headers into the session jar. Do that step here.
    """
    extract = requests.sessions.extract_cookies_to_jar

    def extract_with_mock_headers(jar: Any, request: Any, response: Any) -> None:
        extract(jar, request, response)
        jar.extract_cookies(MockResponse(response.headers), MockRequest(request))

    monkeypatch.setattr(
        requests.sessions, "extract_cookies_to_jar", extract_with_mock_headers
    )
    requests_mock.get(urls.API_URL, text="")
    requests_mock.get(f"{urls.BASE_URL}/loguj/portalRodzina", text="")
    requests_mock.get(
        f"{LOGIN_URL}/2FA",
        text="",
        headers={"Set-Cookie": f"SDZIENNIKSID={SESSION_ID_2}"},
    )
    return requests_mock.post(
        LOGIN_URL,
        json={"status": "ok"},
        headers={"Set-Cookie": f"DZIENNIKSID={SESSION_ID}"},
    )


@pytest.fixture
def api(hass: HomeAssistant) -> LibrusApi:
    """Return an API for the real server URLs with no request gap."""
    return LibrusApi(hass, USERNAME, PASSWORD, queue=RequestQueue(hass, gap=0))


async def test_clients_do_not_share_cookies(
    hass: HomeAssistant, requests_mock: rm.Mocker
) -> None:
    """Each client has its own cookie jar and session."""
    # The library default: one cookie jar object for all clients.
    assert Client(Token()).cookies is Client(Token()).cookies

    first, second = LibrusClient(), LibrusClient()
    assert first.cookies is not second.cookies
    assert first._session is not second._session

    requests_mock.get(urls.INFO_URL, text="ok")
    first.token = Token(API_Key="first1:first2")
    second.token = Token(API_Key="second1:second2")
    await hass.async_add_executor_job(first.get, first.INFO_URL)
    await hass.async_add_executor_job(second.get, second.INFO_URL)

    cookie = requests_mock.last_request.headers["Cookie"]
    assert "DZIENNIKSID=second1" in cookie
    assert "first" not in cookie


async def test_base_url_override() -> None:
    """A base URL moves all Synergia pages; the login server stays."""
    client = LibrusClient("http://librus-mock-a:8000/")

    assert client.BASE_URL == "http://librus-mock-a:8000"
    assert client.GRADES_URL == "http://librus-mock-a:8000/przegladaj_oceny/uczen"
    assert client.SCHEDULE_URL == "http://librus-mock-a:8000/terminarz/"
    assert client.API_URL == urls.API_URL


async def test_requests_have_a_timeout(
    hass: HomeAssistant, requests_mock: rm.Mocker
) -> None:
    """Every request is sent with the default timeout."""
    requests_mock.get(urls.INFO_URL, text="ok")
    requests_mock.post(urls.GRADES_URL, text="ok")
    requests_mock.post(urls.GATEWAY_API_SUBJECTS, json={})
    client = LibrusClient()
    client.token = Token(API_Key="a:b")

    await hass.async_add_executor_job(client.get, client.INFO_URL)
    assert requests_mock.last_request.timeout == REQUEST_TIMEOUT
    await hass.async_add_executor_job(client.post, client.GRADES_URL, {"a": "1"})
    assert requests_mock.last_request.timeout == REQUEST_TIMEOUT
    await hass.async_add_executor_job(client.post_json, urls.GATEWAY_API_SUBJECTS)
    assert requests_mock.last_request.timeout == REQUEST_TIMEOUT
    assert requests_mock.last_request.json() == {}


async def test_two_entries_run_one_at_a_time_with_gap(
    hass: HomeAssistant, requests_mock: rm.Mocker
) -> None:
    """Requests of two entries never overlap and keep the gap."""
    spans: list[tuple[float, float]] = []

    def page(request: Any, context: Any) -> str:
        start = time.monotonic()
        time.sleep(0.05)
        spans.append((start, time.monotonic()))
        return "ok"

    requests_mock.get("http://mock-a/informacja", text=page)
    requests_mock.get("http://mock-b/informacja", text=page)
    queue = RequestQueue(hass, gap=0.2)
    entry_a = LibrusApi(hass, "a", "x", base_url="http://mock-a", queue=queue)
    entry_b = LibrusApi(hass, "b", "y", base_url="http://mock-b", queue=queue)

    await asyncio.gather(
        *(entry.async_call(_info) for entry in (entry_a, entry_b, entry_a, entry_b))
    )

    assert len(spans) == 4
    for (_, end), (start, _) in pairwise(sorted(spans)):
        assert start - end >= 0.19


async def test_mock_mode_skips_login(
    hass: HomeAssistant, requests_mock: rm.Mocker
) -> None:
    """With a base URL no login request is made."""
    requests_mock.get("http://librus-mock-a:8000/informacja", text="ok")
    api = LibrusApi(
        hass, "a", "b", base_url="http://librus-mock-a:8000", queue=RequestQueue(hass)
    )

    assert await api.async_call(_info) == "ok"
    assert requests_mock.call_count == 1
    assert "DZIENNIKSID=mock" in requests_mock.last_request.headers["Cookie"]


async def test_login_sends_credentials_once(
    requests_mock: rm.Mocker, login: Any, api: LibrusApi
) -> None:
    """The first call logs in, later calls reuse the session."""
    requests_mock.get(urls.INFO_URL, text="ok")

    assert await api.async_call(_info) == "ok"
    assert await api.async_call(_info) == "ok"

    assert login.call_count == 1
    assert f"login={USERNAME}" in login.last_request.text
    assert f"DZIENNIKSID={SESSION_ID}" in requests_mock.last_request.headers["Cookie"]


async def test_expired_session_logs_in_again_once(
    requests_mock: rm.Mocker, login: Any, api: LibrusApi
) -> None:
    """An expired session triggers one new login and a retry."""
    requests_mock.get(
        urls.INFO_URL, [{"text": "ok"}, {"text": NO_ACCESS_PAGE}, {"text": "fresh"}]
    )

    assert await api.async_call(_info) == "ok"
    assert await api.async_call(_info) == "fresh"
    assert login.call_count == 2


async def test_redirect_to_login_page_is_an_expired_session(
    requests_mock: rm.Mocker, login: Any, api: LibrusApi
) -> None:
    """A redirect to the login page counts as an expired session."""
    login_page = f"{urls.BASE_URL}/loguj"
    requests_mock.get(login_page, text="login form")
    requests_mock.get(
        urls.INFO_URL,
        [
            {"text": "ok"},
            {"status_code": 302, "headers": {"Location": login_page}},
            {"text": "fresh"},
        ],
    )

    assert await api.async_call(_info) == "ok"
    assert await api.async_call(_info) == "fresh"
    assert login.call_count == 2


async def test_library_token_error_logs_in_again(login: Any, api: LibrusApi) -> None:
    """TokenError and a failed OAuth refresh from the library trigger a new login."""
    errors = iter([None, TokenError("Malformed or expired token."), None])
    errors_2 = iter([AuthorizationError("Error while refreshing oauth token"), None])

    def func(client: Client, source: Any) -> str:
        if err := next(source):
            raise err
        return "ok"

    assert await api.async_call(func, errors) == "ok"
    assert await api.async_call(func, errors) == "ok"
    assert await api.async_call(func, errors_2) == "ok"
    assert login.call_count == 3


async def test_session_rejected_again_after_new_login(
    requests_mock: rm.Mocker, login: Any, api: LibrusApi
) -> None:
    """A second rejection after the new login raises LibrusAuthError."""
    requests_mock.get(urls.INFO_URL, [{"text": "ok"}, {"text": NO_ACCESS_PAGE}])

    assert await api.async_call(_info) == "ok"
    with pytest.raises(LibrusAuthError):
        await api.async_call(_info)
    assert login.call_count == 2


async def test_session_rejected_right_after_first_login(
    requests_mock: rm.Mocker, login: Any, api: LibrusApi
) -> None:
    """No second login when the first one was just made."""
    requests_mock.get(urls.INFO_URL, text=NO_ACCESS_PAGE)

    with pytest.raises(LibrusAuthError):
        await api.async_call(_info)
    assert login.call_count == 1


async def test_wrong_password(
    requests_mock: rm.Mocker, login: Any, api: LibrusApi
) -> None:
    """A login error reply raises LibrusAuthError, also with HTTP 403."""
    requests_mock.post(
        LOGIN_URL,
        status_code=403,
        json={"status": "error", "errors": [{"message": "Nieprawidłowy login"}]},
    )

    with pytest.raises(LibrusAuthError, match="Nieprawidłowy login"):
        await api.async_login()


@pytest.mark.parametrize("status", [403, 429, 500, 502, 503])
async def test_refused_requests_back_off(
    requests_mock: rm.Mocker, login: Any, api: LibrusApi, status: int
) -> None:
    """HTTP 403, 429 and 5xx raise LibrusUnavailableError with a backoff delay."""
    requests_mock.get(urls.INFO_URL, status_code=status, text="<html>busy</html>")

    with pytest.raises(LibrusUnavailableError) as exc:
        await api.async_call(_info)
    assert not exc.value.maintenance
    assert exc.value.retry_after == BACKOFF_START


async def test_retry_after_header(
    requests_mock: rm.Mocker, login: Any, api: LibrusApi
) -> None:
    """The server's Retry-After sets a longer backoff."""
    requests_mock.get(
        urls.INFO_URL, status_code=429, headers={"Retry-After": "900"}, text=""
    )

    with pytest.raises(LibrusUnavailableError) as exc:
        await api.async_call(_info)
    assert exc.value.retry_after == 900


async def test_maintenance_on_login(
    requests_mock: rm.Mocker, login: Any, api: LibrusApi
) -> None:
    """The maintenance reply of the API raises a maintenance error."""
    requests_mock.get(
        urls.API_URL,
        status_code=503,
        json={"Message": [{"description": "Przerwa techniczna"}]},
    )

    with pytest.raises(LibrusUnavailableError) as exc:
        await api.async_login()
    assert exc.value.maintenance
    assert exc.value.retry_after == BACKOFF_START
    assert login.call_count == 0


async def test_library_maintenance_error(login: Any, api: LibrusApi) -> None:
    """MaintananceError from the library is a maintenance backoff."""

    def func(client: Client) -> None:
        raise MaintananceError("maintenance")

    with pytest.raises(LibrusUnavailableError) as exc:
        await api.async_call(func)
    assert exc.value.maintenance
    assert exc.value.retry_after == BACKOFF_START


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ParseError("Error in parsing grades"), LibrusParseError),
        (KeyError("Attendances"), LibrusParseError),
        (requests.JSONDecodeError("Expecting value", "<html>", 0), LibrusParseError),
        (requests.ConnectionError("down"), LibrusConnectionError),
        (requests.Timeout("slow"), LibrusConnectionError),
    ],
)
async def test_errors_are_mapped(
    login: Any, api: LibrusApi, error: Exception, expected: type[Exception]
) -> None:
    """Library and requests errors become our exceptions."""

    def func(client: Client) -> None:
        raise error

    with pytest.raises(expected):
        await api.async_call(func)


async def test_no_secrets_in_logs(
    requests_mock: rm.Mocker,
    login: Any,
    api: LibrusApi,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Login, new login, rejection and backoff never log credentials or cookies."""
    caplog.set_level(logging.DEBUG)
    requests_mock.get(urls.INFO_URL, [{"text": "ok"}, {"text": NO_ACCESS_PAGE}])

    await api.async_call(_info)
    with pytest.raises(LibrusAuthError):
        await api.async_call(_info)
    requests_mock.get(urls.INFO_URL, status_code=503, text="")
    with pytest.raises(LibrusUnavailableError):
        await api.async_call(_info)

    assert "Logged in to synergia.librus.pl" in caplog.text
    for secret in (USERNAME, PASSWORD, SESSION_ID, SESSION_ID_2):
        assert secret not in caplog.text
