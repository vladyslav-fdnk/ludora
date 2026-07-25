"""Controlled backend API failures."""


class APIError(Exception):
    """Base class for failures safe for handlers to classify."""


class BackendUnavailable(APIError):
    """The backend could not be reached."""


class BackendTimeout(APIError):
    """The backend did not respond before the configured timeout."""


class InvalidResponse(APIError):
    """The backend returned malformed or contract-incompatible data."""


class ProductNotFound(APIError):
    """The requested product is unavailable."""


class UnexpectedAPIStatus(APIError):
    """The backend returned an unexpected HTTP status."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"Unexpected backend status: {status_code}")


class AuthenticationFailed(APIError):
    """Telegram synchronization was rejected by the backend."""


class AuthenticationRequired(APIError):
    """Stored authentication is missing or can no longer be refreshed."""


class MissingTelegramUser(APIError):
    """Telegram did not provide a usable sender identity."""
