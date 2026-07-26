# Ludora

Ludora is a backend-focused digital marketplace built around a Django REST API and
an aiogram Telegram client. It demonstrates catalogue management, two JWT
authentication paths, Telegram account synchronization, persistent carts, and
tested commerce domain logic in a Docker-based development environment.

The current release is **v0.2.0**. Stage 2 completed Telegram authentication,
including user synchronization, profiles, token refresh, and a one-time retry of
protected requests. Stage 3 adds authenticated cart management and order creation
from a cart; the published release marker remains v0.2.0.

## Architecture

Ludora contains two independently packaged Python applications:

- **Backend:** Django and Django REST Framework expose the marketplace API.
- **Database:** PostgreSQL stores users, catalogue data, carts, normalized order
  items, payments, and license keys.
- **Telegram bot:** aiogram communicates with the backend through an asynchronous
  HTTPX client.
- **Authentication:** Simple JWT supports email/password login. A separate
  internal endpoint authenticates Telegram identities using a shared secret and
  returns JWTs.
- **Infrastructure:** Docker Compose runs the backend, PostgreSQL, and bot
  services.

The Django backend is split into domain apps. Order and payment rules are kept in
service modules, while API views handle HTTP concerns. The bot separates API,
authentication, handlers, localization, keyboards, and presentation code.

The `payments` Django app is currently a placeholder; the implemented `Payment`
model and payment-related service logic live in the `orders` app.

## Implemented Functionality

### Catalogue and product management

- Public product catalogue with page-based pagination (10 products per page).
- Filtering by platform, product type, and category.
- Search across product title and description.
- Ordering by price, title, or creation date.
- Public product details.
- Staff-only product creation, update, and soft deletion.
- Platforms, categories, product types, and license-key inventory.

### Users and authentication

- Custom email-based Django user model.
- Registration and email/password JWT login.
- Authenticated current-user profile.
- JWT access-token refresh.
- Internal-secret-protected Telegram authentication endpoint.
- Atomic Telegram user creation/synchronization with a unique Telegram ID.
- Bot-side in-memory token storage.
- Automatic access-token refresh and one retry after a protected request returns
  `401 Unauthorized`.

### Carts, orders, and license keys

Backend models, APIs, and service logic already support:

- Creating an authenticated user's order for one product.
- One persistent cart per authenticated user.
- Adding, changing, removing, and clearing cart items.
- Server-calculated Decimal cart totals with a maximum quantity of 99 per
  product.
- Atomic multi-product order creation from the current cart.
- Immutable order-item title, quantity, and unit-price snapshots.
- Listing the authenticated user's orders.
- Creating payment records for owned orders.
- A simulated payment operation that assigns an available license key and marks
  the order as paid.

Cart checkout creates an order but intentionally creates no payment and assigns
no license key. The legacy simulated payment flow remains available only for
direct single-product orders. External payments, payment of cart orders, and
license-key delivery through the bot are not implemented.

## API

The backend returns JSON. Once it is running:

- Swagger UI: `http://localhost:8000/api/docs/`
- OpenAPI schema: `http://localhost:8000/api/schema/`
- Django admin: `http://localhost:8000/admin/`

### Products

| Method | Endpoint | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/products/` | Public | List active products |
| `GET` | `/api/products/<id>/` | Public | Retrieve an active product |
| `POST` | `/api/products/create/` | Staff | Create a product |
| `PUT`, `PATCH` | `/api/products/<id>/update/` | Staff | Update a product |
| `DELETE` | `/api/products/<id>/delete/` | Staff | Soft-delete a product |

Product-list query parameters include `platform`, `product_type`, `categories`,
`search`, `ordering`, and `page`.

### Authentication

| Method | Endpoint | Access | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/auth/register/` | Public | Register with email and password |
| `POST` | `/api/auth/login/` | Public | Obtain an access/refresh token pair |
| `POST` | `/api/auth/refresh/` | Refresh token | Obtain a new access token |
| `GET` | `/api/auth/me/` | JWT | Return the current user |
| `POST` | `/api/auth/telegram/` | Internal secret | Synchronize a Telegram user and issue JWTs |

The Telegram endpoint expects the shared secret in the
`X-Bot-Internal-Secret` header. It is intended for the bot, not as a public
client login endpoint.

### Orders

| Method | Endpoint | Access | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/orders/` | JWT | Create an order |
| `GET` | `/api/orders/my/` | JWT | List the current user's orders |
| `POST` | `/api/orders/<id>/pay/` | JWT | Run the simulated payment flow |
| `POST` | `/api/orders/payments/` | JWT | Create a payment for an owned order |

### Cart

| Method | Endpoint | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/cart/` | JWT | Get or automatically create the current user's cart |
| `POST` | `/api/cart/items/` | JWT | Add a product or increase its quantity |
| `PATCH` | `/api/cart/items/<id>/` | JWT | Set an owned cart item's quantity |
| `DELETE` | `/api/cart/items/<id>/` | JWT | Remove an owned cart item |
| `DELETE` | `/api/cart/clear/` | JWT | Clear the current user's cart |
| `POST` | `/api/cart/checkout/` | JWT | Atomically create an order and clear the cart |

Cart item requests accept product identifiers and positive quantities only.
Prices, line totals, and cart totals are always calculated by the backend.

## Telegram Bot

The bot currently provides:

- `/start` — synchronizes the Telegram identity with the backend and stores the
  returned JWTs.
- `/catalogue` — displays the paginated product catalogue.
- Product detail navigation through inline keyboards.
- `/profile` — synchronizes when necessary and displays the backend user profile.
- `/cart` and the main-menu Cart button — display the authenticated cart.
- Add-to-cart controls on product details.
- Quantity increase/decrease, removal, and confirmed cart clearing.
- Confirmed order creation with a localized order summary.
- English and Russian interface text and language selection.
- Friendly handling of backend, timeout, and malformed-response errors.
- Refresh-token handling with a single retry of a rejected protected request.

Tokens and language preferences are process-local and are lost when the bot
restarts. They are not shared between bot replicas.

## Local Setup

The recommended development workflow uses Docker Compose and requires Docker
with the Compose plugin.

1. Copy the environment template:

   ```bash
   cp .env.example .env
   ```

2. Set non-empty values for `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`,
   `BOT_TOKEN`, and `BOT_INTERNAL_SECRET`. The same `.env` file is loaded by the
   backend and bot, so the internal secret is shared automatically.

3. Build and start the services:

   ```bash
   docker compose up --build
   ```

4. In another terminal, apply migrations:

   ```bash
   docker compose exec backend uv run python manage.py migrate
   ```

5. Create a superuser for Django admin and protected product management:

   ```bash
   docker compose exec backend uv run python manage.py createsuperuser
   ```

The API is then available at `http://localhost:8000/`. The bot starts long
polling when its required environment variables are configured.

### Tests

The current suites contain **123 backend tests** and **82 bot tests**.

```bash
docker compose exec backend uv run pytest
docker compose run --rm bot uv run pytest
```

They can also be run from each package directory after `uv sync`:

```bash
cd backend
uv sync
uv run pytest

cd ../bot
uv sync
uv run pytest
```

### Ruff

Run Ruff separately for both Python packages:

```bash
docker compose exec backend uv run ruff check .
docker compose run --rm bot uv run ruff check .
```

For local `uv` environments, run `uv run ruff check .` from `backend/` and
`bot/`.

## Environment Variables

Copy `.env.example` and provide local values; do not commit `.env` or real
secrets.

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Django cryptographic signing key |
| `DJANGO_DEBUG` | Enables or disables Django debug mode |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed host names |
| `BOT_INTERNAL_SECRET` | Shared secret for the internal Telegram auth endpoint |
| `POSTGRES_DB` | PostgreSQL database name |
| `POSTGRES_USER` | PostgreSQL user |
| `POSTGRES_PASSWORD` | PostgreSQL password |
| `POSTGRES_HOST` | PostgreSQL host name |
| `POSTGRES_PORT` | PostgreSQL port |
| `BOT_TOKEN` | Telegram Bot API token |
| `BOT_BACKEND_BASE_URL` | Backend base URL used by the bot |
| `BOT_API_TIMEOUT` | Backend request timeout in seconds |
| `BOT_DEFAULT_LANGUAGE` | Default bot language (`en` or `ru`) |

## Project Structure

```text
ludora/
├── backend/
│   ├── apps/
│   │   ├── authentication/  # Email/JWT and internal Telegram authentication
│   │   ├── carts/           # Persistent carts, cart items, checkout API/services
│   │   ├── games/           # Products, platforms, categories, and license keys
│   │   ├── orders/          # Orders, order items, payments, APIs, and services
│   │   ├── payments/        # Placeholder for future provider integration
│   │   └── users/           # Custom email-based user model
│   ├── config/              # Django settings and root URL configuration
│   ├── manage.py
│   ├── entrypoint.sh
│   ├── Dockerfile
│   └── pyproject.toml
├── bot/
│   ├── app/
│   │   ├── api/             # Typed asynchronous backend client
│   │   ├── auth/            # Telegram auth service and token storage
│   │   ├── handlers/        # Start, catalogue, profile, and cart handlers
│   │   ├── keyboards/       # Inline and reply keyboards
│   │   ├── localization/    # English/Russian messages and preferences
│   │   └── presentation/    # Telegram-safe response formatting
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
├── docker-compose.yml
├── .env.example
└── README.md
```

## Roadmap

The next planned marketplace features are:

- [x] Cart
- [x] Cart items
- [x] Order creation from a cart
- [ ] External payment integration
- [ ] License-key delivery through the bot
- [ ] Redis-backed token storage
- [ ] Order history in the Telegram bot

## Release

**v0.2.0 — Telegram authentication completed**

This portfolio release includes internal Telegram authentication, Telegram user
synchronization, bot profiles, JWT refresh, and one-time retry behavior. The
backend commerce logic predates the planned end-to-end cart, checkout, payment
provider, and bot delivery experience.
