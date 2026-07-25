from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.api.exceptions import InvalidResponse


@dataclass(frozen=True, slots=True)
class TelegramIdentity:
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None

    @classmethod
    def from_user(cls, user: Any) -> "TelegramIdentity":
        if user is None:
            raise ValueError("Telegram user information is missing")
        telegram_id = getattr(user, "id", None)
        if isinstance(telegram_id, bool) or not isinstance(telegram_id, int) or telegram_id <= 0:
            raise ValueError("Telegram user id is invalid")
        return cls(
            telegram_id=telegram_id,
            username=getattr(user, "username", None),
            first_name=getattr(user, "first_name", None),
            last_name=getattr(user, "last_name", None),
            language_code=getattr(user, "language_code", None),
        )

    def as_payload(self) -> dict[str, int | str | None]:
        return {
            "telegram_id": self.telegram_id,
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "language_code": self.language_code,
        }


@dataclass(frozen=True, slots=True)
class AuthTokens:
    access: str
    refresh: str


@dataclass(frozen=True, slots=True)
class BackendUser:
    email: str
    first_name: str
    last_name: str
    telegram_username: str
    telegram_language_code: str
    date_joined: datetime

    @classmethod
    def from_mapping(cls, value: Any) -> "BackendUser":
        if not isinstance(value, dict):
            raise InvalidResponse("User must be an object")
        strings = {}
        for field in (
            "email",
            "first_name",
            "last_name",
            "telegram_username",
            "telegram_language_code",
        ):
            item = value.get(field)
            if not isinstance(item, str):
                raise InvalidResponse(f"User {field} is invalid")
            strings[field] = item
        try:
            date_joined = datetime.fromisoformat(value["date_joined"].replace("Z", "+00:00"))
        except (KeyError, AttributeError, TypeError, ValueError) as exc:
            raise InvalidResponse("User registration date is invalid") from exc
        return cls(date_joined=date_joined, **strings)


@dataclass(frozen=True, slots=True)
class AuthResult:
    tokens: AuthTokens
    user: BackendUser

    @classmethod
    def from_mapping(cls, value: Any) -> "AuthResult":
        if not isinstance(value, dict):
            raise InvalidResponse("Authentication response must be an object")
        access = value.get("access")
        refresh = value.get("refresh")
        if not isinstance(access, str) or not access:
            raise InvalidResponse("Access token is invalid")
        if not isinstance(refresh, str) or not refresh:
            raise InvalidResponse("Refresh token is invalid")
        return cls(
            tokens=AuthTokens(access=access, refresh=refresh),
            user=BackendUser.from_mapping(value.get("user")),
        )
