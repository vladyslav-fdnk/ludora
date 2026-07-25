from typing import Any

from app.api import BackendClient
from app.api.exceptions import AuthenticationRequired, MissingTelegramUser

from .models import AuthResult, BackendUser, TelegramIdentity
from .storage import TokenStorage


class TelegramAuthService:
    def __init__(self, client: BackendClient, storage: TokenStorage) -> None:
        self._client = client
        self._storage = storage

    async def synchronize(self, telegram_user: Any) -> AuthResult:
        identity = self._identity(telegram_user)
        result = await self._client.authenticate_telegram(identity)
        await self._storage.set(identity.telegram_id, result.tokens)
        return result

    async def ensure_authenticated(self, telegram_user: Any) -> TelegramIdentity:
        identity = self._identity(telegram_user)
        if await self._storage.get(identity.telegram_id) is None:
            await self.synchronize(telegram_user)
        return identity

    async def get_profile(self, telegram_user: Any) -> BackendUser:
        identity = await self.ensure_authenticated(telegram_user)
        try:
            return await self._client.get_profile(identity.telegram_id)
        except AuthenticationRequired:
            # A missing/expired refresh token requires a fresh Telegram sync.
            await self.synchronize(telegram_user)
            return await self._client.get_profile(identity.telegram_id)

    @staticmethod
    def _identity(telegram_user: Any) -> TelegramIdentity:
        try:
            return TelegramIdentity.from_user(telegram_user)
        except ValueError as exc:
            raise MissingTelegramUser from exc
