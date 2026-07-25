"""Environment-backed bot configuration."""

from dataclasses import dataclass
from os import environ


class ConfigurationError(RuntimeError):
    """Raised when bot configuration is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    token: str
    backend_base_url: str
    api_timeout: float
    default_language: str

    @classmethod
    def from_env(cls) -> "Settings":
        token = environ.get("BOT_TOKEN", "").strip()
        base_url = environ.get("BOT_BACKEND_BASE_URL", "").strip()
        if not token:
            raise ConfigurationError("BOT_TOKEN is required")
        if not base_url:
            raise ConfigurationError("BOT_BACKEND_BASE_URL is required")
        try:
            timeout = float(environ.get("BOT_API_TIMEOUT", "5"))
        except ValueError as exc:
            raise ConfigurationError("BOT_API_TIMEOUT must be a number") from exc
        if timeout <= 0:
            raise ConfigurationError("BOT_API_TIMEOUT must be greater than zero")

        default_language = environ.get("BOT_DEFAULT_LANGUAGE", "en").strip().lower()
        if default_language not in {"en", "ru"}:
            raise ConfigurationError("BOT_DEFAULT_LANGUAGE must be 'en' or 'ru'")
        return cls(token, base_url.rstrip("/"), timeout, default_language)
