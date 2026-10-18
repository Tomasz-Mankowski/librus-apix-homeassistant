"""Errors raised by the Librus client layer."""


class LibrusError(Exception):
    """Base class for Librus errors."""


class LibrusAuthError(LibrusError):
    """Login rejected, or the session is rejected again right after a login."""


class LibrusConnectionError(LibrusError):
    """Network error or timeout."""


class LibrusParseError(LibrusError):
    """A page or response could not be parsed."""


class LibrusSessionExpiredError(LibrusError):
    """The session cookies are no longer accepted. Handled by logging in again."""


class LibrusUnavailableError(LibrusError):
    """The server refuses service (HTTP 403, 429, 5xx) or is in maintenance.

    ``retry_after`` holds the server's Retry-After hint when raised by the client,
    and the backoff delay in seconds once it leaves the request queue.
    """

    def __init__(
        self,
        message: str,
        *,
        maintenance: bool = False,
        retry_after: float | None = None,
    ) -> None:
        """Store the maintenance flag and the delay."""
        super().__init__(message)
        self.maintenance = maintenance
        self.retry_after = retry_after
