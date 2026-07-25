import asyncio
from typing import Protocol

from .models import AuthTokens


class TokenStorage(Protocol):
    async def get(self, telegram_id: int) -> AuthTokens | None: ...

    async def set(self, telegram_id: int, tokens: AuthTokens) -> None: ...

    async def delete(self, telegram_id: int) -> None: ...


class InMemoryTokenStorage:
    """Process-local token storage; intentionally replaceable in a later stage."""

    def __init__(self) -> None:
        self._tokens: dict[int, AuthTokens] = {}
        self._lock = asyncio.Lock()

    async def get(self, telegram_id: int) -> AuthTokens | None:
        async with self._lock:
            return self._tokens.get(telegram_id)

    async def set(self, telegram_id: int, tokens: AuthTokens) -> None:
        async with self._lock:
            self._tokens[telegram_id] = tokens

    async def delete(self, telegram_id: int) -> None:
        async with self._lock:
            self._tokens.pop(telegram_id, None)
