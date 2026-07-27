from typing import Any

from app.api import BackendClient
from app.api.exceptions import AuthenticationRequired, MissingTelegramUser
from app.api.schemas import (
    Cart,
    CartItem,
    CheckoutOrder,
    OrderDetail,
    OrderSummary,
    Payment,
)

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

    async def get_cart(self, telegram_user: Any) -> Cart:
        return await self._protected(telegram_user, self._client.get_cart)

    async def add_cart_item(
        self, telegram_user: Any, product_id: int, quantity: int = 1
    ) -> CartItem:
        return await self._protected(
            telegram_user, self._client.add_cart_item, product_id, quantity
        )

    async def update_cart_item(
        self, telegram_user: Any, item_id: int, quantity: int
    ) -> CartItem:
        return await self._protected(
            telegram_user, self._client.update_cart_item, item_id, quantity
        )

    async def remove_cart_item(self, telegram_user: Any, item_id: int) -> None:
        await self._protected(telegram_user, self._client.remove_cart_item, item_id)

    async def clear_cart(self, telegram_user: Any) -> None:
        await self._protected(telegram_user, self._client.clear_cart)

    async def checkout_cart(self, telegram_user: Any) -> CheckoutOrder:
        return await self._protected(telegram_user, self._client.checkout_cart)

    async def create_payment(self, telegram_user: Any, order_id: int) -> Payment:
        return await self._protected(
            telegram_user, self._client.create_payment, order_id
        )

    async def get_my_orders(self, telegram_user: Any) -> tuple[OrderSummary, ...]:
        return await self._protected(telegram_user, self._client.get_my_orders)

    async def get_my_order(self, telegram_user: Any, order_id: int) -> OrderDetail:
        return await self._protected(
            telegram_user, self._client.get_my_order, order_id
        )

    async def _protected(self, telegram_user: Any, operation, *args):
        identity = await self.ensure_authenticated(telegram_user)
        try:
            return await operation(identity.telegram_id, *args)
        except AuthenticationRequired:
            await self.synchronize(telegram_user)
            return await operation(identity.telegram_id, *args)

    @staticmethod
    def _identity(telegram_user: Any) -> TelegramIdentity:
        try:
            return TelegramIdentity.from_user(telegram_user)
        except ValueError as exc:
            raise MissingTelegramUser from exc
