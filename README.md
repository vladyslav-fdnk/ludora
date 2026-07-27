# Ludora

![Python](https://img.shields.io/badge/Python-3.13-3776AB?style=flat-square&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.2-092E20?style=flat-square&logo=django&logoColor=white)
![Django REST Framework](https://img.shields.io/badge/DRF-3.17-A30000?style=flat-square&logo=django&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Docker Compose](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-8-DC382D?style=flat-square&logo=redis&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.5-37814A?style=flat-square&logo=celery&logoColor=white)

Backend-first digital marketplace built with Django REST Framework and aiogram, featuring JWT authentication, persistent carts, payment simulation, license fulfillment, and Telegram integration.


Ludora is a backend-focused marketplace for digital products and license keys.
It combines a Django REST API, an aiogram Telegram bot, Django Admin, PostgreSQL,
Redis, and Celery in a Docker Compose development environment.

## Capabilities

- Searchable, filterable, and paginated product catalogue.
- Email/password and Telegram authentication with JWT access and refresh tokens.
- Persistent carts with server-calculated prices and atomic checkout.
- Direct and multi-item orders with immutable purchase snapshots.
- Owner-scoped order history and paid license-key access.
- Transaction-safe license fulfilment using a deterministic local payment
  simulation.
- Telegram browsing, profiles, cart management, checkout, and order history in
  English and Russian.
- Staff catalogue and inventory management through Django Admin, including
  atomic CSV license-key imports.
- Background tasks through Celery and Redis.

The local payment provider is for development only; no production payment
gateway is integrated. Telegram checkout can create a payment, but its payment
completion UI is not yet an end-to-end flow.

## Quick Start

### Requirements

- Docker
- Docker Compose plugin

### Run with Docker Compose

1. Create the local environment file:

   ```bash
   cp .env.example .env
   ```

2. Set non-empty values for `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`,
   `BOT_TOKEN`, and `BOT_INTERNAL_SECRET`.

3. Build the images and start PostgreSQL:

   ```bash
   docker compose build
   docker compose up -d postgres
   ```

4. Apply database migrations:

   ```bash
   docker compose run --rm backend uv run python manage.py migrate
   ```

5. Start the application:

   ```bash
   docker compose up
   ```

6. Optionally create a Django Admin user in another terminal:

   ```bash
   docker compose exec backend uv run python manage.py createsuperuser
   ```

The API is available at `http://localhost:8000/`. The Telegram bot starts long
polling when its required environment variables are configured.

## Explore the Project

- Swagger UI: `http://localhost:8000/api/docs/`
- OpenAPI schema: `http://localhost:8000/api/schema/`
- Django Admin: `http://localhost:8000/admin/`
- [Architecture](docs/ARCHITECTURE.md) — component boundaries, domain model,
  payment and fulfilment rules, and design decisions.
- [Changelog](CHANGELOG.md) — implemented changes and development milestones.

## API Overview

The OpenAPI schema is the complete request and response reference. The main
endpoint groups are summarized below.

### Authentication

| Method | Endpoint | Access | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/auth/register/` | Public | Register with email and password |
| `POST` | `/api/auth/token/` | Public | Obtain JWT access and refresh tokens |
| `POST` | `/api/auth/token/refresh/` | Refresh token | Obtain a new access token |
| `GET` | `/api/auth/me/` | JWT | Retrieve the current user |
| `POST` | `/api/auth/telegram/` | Internal secret | Synchronize a Telegram user and issue JWTs |

Send access tokens to protected endpoints as:

```text
Authorization: Bearer <access-token>
```

The Telegram endpoint uses `X-Bot-Internal-Secret` and is intended only for the
bot. Legacy `/api/auth/login/` and `/api/auth/refresh/` aliases remain available
for the Telegram client.

### Products

| Method | Endpoint | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/products/` | Public | List active products |
| `GET` | `/api/products/<id>/` | Public | Retrieve an active product |
| `POST` | `/api/products/create/` | Staff | Create a product |
| `PUT`, `PATCH` | `/api/products/<id>/update/` | Staff | Update a product |
| `DELETE` | `/api/products/<id>/delete/` | Staff | Soft-delete a product |

Product lists support platform, product type, and category filters; text search;
ordering; and pagination.

### Cart

| Method | Endpoint | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/cart/` | JWT | Retrieve or create the current user's cart |
| `POST` | `/api/cart/items/` | JWT | Add a product or increase its quantity |
| `PATCH` | `/api/cart/items/<id>/` | JWT | Change an item's quantity |
| `DELETE` | `/api/cart/items/<id>/` | JWT | Remove an item |
| `DELETE` | `/api/cart/clear/` | JWT | Clear the cart |
| `POST` | `/api/cart/checkout/` | JWT | Create an order and clear the cart |

### Orders and payments

| Method | Endpoint | Access | Purpose |
| --- | --- | --- | --- |
| `GET`, `POST` | `/api/orders/` | JWT | List visible orders or create a direct order |
| `GET` | `/api/orders/<id>/` | JWT | Retrieve a visible order |
| `GET` | `/api/orders/my/` | JWT | List the current user's order summaries |
| `GET` | `/api/orders/my/<id>/` | JWT | Retrieve an owned order and paid fulfilment details |
| `POST` | `/api/orders/payments/` | JWT | Create a payment for an owned order |
| `POST` | `/api/orders/<id>/pay/` | JWT | Run the local simulated payment flow |

Regular users can access only their own orders. Staff users can access all
orders. See the [architecture documentation](docs/ARCHITECTURE.md) for payment,
concurrency, fulfilment, and data-exposure guarantees.

## Telegram Bot

The bot supports:

- `/start` for Telegram authentication and synchronization.
- `/catalogue` for catalogue browsing and product details.
- `/profile` for the synchronized backend profile.
- `/cart` for cart management and checkout.
- `/orders` for personal order summaries and details.
- English and Russian interface text.
- Automatic access-token refresh with one retry.

Tokens and language preferences are currently process-local and are lost when
the bot restarts.

## Development

### Tests

```bash
docker compose exec backend uv run pytest
docker compose run --rm bot uv run pytest
```

To run tests without Docker, use `uv sync` followed by `uv run pytest` from each
package directory.

### Linting

```bash
docker compose exec backend uv run ruff check .
docker compose run --rm bot uv run ruff check .
```

For local environments, run `uv run ruff check .` from both `backend/` and
`bot/`.

### Celery

Follow worker output with:

```bash
docker compose logs -f celery_worker
```

Send the diagnostic task from the backend container with:

```bash
docker compose exec backend uv run python manage.py shell -c \
  "from apps.core.tasks import log_worker_probe; print(log_worker_probe.delay('manual-worker-probe').id)"
```

Redis is used as the Celery broker; task results are not stored. The local
console email backend also writes eligible order-confirmation emails to worker
output.

## Configuration

Copy `.env.example` to `.env`; never commit real secrets.

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Django cryptographic signing key |
| `DJANGO_DEBUG` | Django debug mode |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated allowed hosts |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | PostgreSQL credentials |
| `POSTGRES_HOST`, `POSTGRES_PORT` | PostgreSQL connection |
| `CELERY_BROKER_URL` | Celery broker URL |
| `EMAIL_BACKEND` | Django email backend |
| `EMAIL_HOST`, `EMAIL_PORT` | SMTP server |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Optional SMTP credentials |
| `EMAIL_USE_TLS`, `EMAIL_TIMEOUT` | SMTP transport settings |
| `DEFAULT_FROM_EMAIL` | Transactional email sender |
| `BOT_TOKEN` | Telegram Bot API token |
| `BOT_INTERNAL_SECRET` | Shared secret for Telegram authentication |
| `BOT_BACKEND_BASE_URL` | Backend URL used by the bot |
| `BOT_API_TIMEOUT` | Backend request timeout |
| `BOT_DEFAULT_LANGUAGE` | Default bot language (`en` or `ru`) |

## Repository Layout

```text
ludora/
├── backend/                 # Django API, domain apps, admin, and Celery worker
├── bot/                     # aiogram Telegram client
├── docs/ARCHITECTURE.md     # Architecture and implementation decisions
├── docker-compose.yml       # Local service topology
├── .env.example             # Configuration template
└── README.md
```

## Roadmap

- Complete the Telegram payment-status and fulfilment flow.
- Integrate a production payment provider.
- Extend confirmation email to multi-item cart orders.
- Move bot token and language storage to shared Redis-backed storage.

The repository contains subsequent
cart, fulfilment, admin, and order-history work.
