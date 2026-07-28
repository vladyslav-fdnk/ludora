# Ludora

Ludora is a digital-product marketplace built as a Django modular monolith with
an aiogram Telegram client. It provides a public catalogue, JWT authentication,
persistent carts, immutable order snapshots, license-key fulfilment, local
payment simulation, Stripe Checkout, and signed Stripe webhooks.

## Stack

- Python 3.13, Django 5.x, Django REST Framework
- PostgreSQL 16
- Celery with Redis 8
- aiogram and HTTPX
- Stripe Checkout
- Docker Compose, uv, pytest, and Ruff

## Architecture

The Django backend is the system of record. PostgreSQL stores identities,
catalogue data, carts, order snapshots, payment attempts, and license
assignments. The Telegram bot is an API client and does not access the database.
Celery handles post-commit order-confirmation email through Redis.

```text
API clients ─┐
             ├─> Django REST API ─> PostgreSQL
Telegram ─> bot ┘          │
                           └─> Redis ─> Celery worker ─> email backend

Stripe Checkout ─> POST /api/payments/stripe/webhook/ ─> payment fulfilment
```

The backend is divided by domain:

```text
backend/apps/
├── authentication/   # registration, JWT, Telegram authentication
├── users/            # custom email-based user
├── games/            # catalogue and license inventory
├── carts/            # mutable carts and atomic checkout
├── orders/           # order snapshots, payments, fulfilment, email
├── payments/         # local/Stripe providers and Stripe webhooks
└── core/             # shared infrastructure and diagnostic tasks
```

See [Architecture](docs/ARCHITECTURE.md) for transaction boundaries, the domain
model, and the payment and webhook state transitions.

## Docker quick start

Requirements: Docker with the Compose plugin.

1. Create the environment file and replace the placeholder secrets:

   ```bash
   cp .env.example .env
   ```

   Set at least `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`,
   `BOT_INTERNAL_SECRET`, and `BOT_TOKEN` if the bot will run.

2. Build and start the infrastructure:

   ```bash
   docker compose build
   docker compose up -d postgres redis
   ```

3. Apply migrations:

   ```bash
   docker compose run --rm backend uv run python manage.py migrate
   ```

4. Start the backend and worker:

   ```bash
   docker compose up backend celery_worker
   ```

   If `BOT_TOKEN` and `BOT_INTERNAL_SECRET` are configured, include the bot with
   `docker compose up backend celery_worker bot` (or run `docker compose up`).

5. Optionally create an administrator:

   ```bash
   docker compose exec backend uv run python manage.py createsuperuser
   ```

Services:

| Service | Address or role |
| --- | --- |
| Backend | `http://localhost:8000/` |
| Swagger UI | `http://localhost:8000/api/docs/` |
| OpenAPI schema | `http://localhost:8000/api/schema/` |
| Django Admin | `http://localhost:8000/admin/` |
| PostgreSQL | host port `5433` (container port `5432`) |
| Redis | internal broker; no host port is published |
| Celery worker | consumes Redis tasks |
| Telegram bot | long polling; no HTTP port |

The backend and worker entrypoint wait for PostgreSQL. Compose is a development
topology, not a production deployment: it uses Django's development server,
bind-mounts source, and does not include TLS or a reverse proxy.

To stop containers, run `docker compose down`. Add `--volumes` only when you
intentionally want to delete the local PostgreSQL data volume.

## Local development without Docker

PostgreSQL is required for the backend; SQLite is not a supported substitute
because the test suite and commerce services rely on PostgreSQL locking.
Redis is required only for a real Celery worker. Django and the bot read the
process environment directly; they do not load the repository `.env` file
outside Compose. Export the variables from `.env` in your shell before running
these commands.

```bash
cd backend
uv sync --frozen
uv run python manage.py migrate
uv run python manage.py runserver
```

Use host-reachable database settings, for example
`POSTGRES_HOST=localhost` and `POSTGRES_PORT=5433` when using the Compose
database. In another terminal:

```bash
cd bot
uv sync --frozen
uv run python -m app.main
```

For a locally running backend, set
`BOT_BACKEND_BASE_URL=http://localhost:8000`.

## Configuration

Copy `.env.example` to `.env`. Boolean values are case-sensitive and must be
`True` or `False`. Do not commit real credentials.

| Variable | Default in code/example | Purpose |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | insecure code fallback | Django signing and JWT key; set a strong value |
| `DJANGO_DEBUG` | `False` | Enable Django debug mode |
| `DJANGO_ALLOWED_HOSTS` | empty / local hosts in example | Comma-separated hosts |
| `POSTGRES_DB` | `ludora_store` / `game_key_store` | Database name |
| `POSTGRES_USER` | `ludora_store` / `game_key_store` | Database user |
| `POSTGRES_PASSWORD` | empty / placeholder | Database password |
| `POSTGRES_HOST` | `localhost` / `postgres` | Database host |
| `POSTGRES_PORT` | `5432` | Database port inside the selected network |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Redis broker URL; Compose overrides the host to `redis` |
| `EMAIL_BACKEND` | console backend | Django email backend |
| `EMAIL_HOST`, `EMAIL_PORT` | `localhost`, `25` | SMTP endpoint |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | empty | Optional SMTP credentials |
| `EMAIL_USE_TLS` | `False` | Enable SMTP TLS |
| `EMAIL_TIMEOUT` | `10` | SMTP timeout in seconds |
| `DEFAULT_FROM_EMAIL` | `Ludora <noreply@localhost>` | Sender address |
| `PAYMENT_PROVIDER` | `local` | Provider for new payments: `local` or `stripe` |
| `STRIPE_SECRET_KEY` | empty | Stripe API secret key |
| `STRIPE_WEBHOOK_SECRET` | empty | Endpoint signing secret (`whsec_...`) |
| `STRIPE_CURRENCY` | `usd` | Three-letter Stripe currency code |
| `STRIPE_SUCCESS_URL` | empty | Checkout success redirect URL |
| `STRIPE_CANCEL_URL` | empty | Checkout cancellation redirect URL |
| `BOT_TOKEN` | empty | Telegram Bot API token |
| `BOT_INTERNAL_SECRET` | empty | Shared secret for Telegram authentication |
| `BOT_BACKEND_BASE_URL` | required / `http://backend:8000` in example | Backend base URL |
| `BOT_API_TIMEOUT` | `5` | Backend request timeout in seconds |
| `BOT_DEFAULT_LANGUAGE` | `en` | Default language: `en` or `ru` |

All five Stripe variables are required when `PAYMENT_PROVIDER=stripe`.

## Payments

Orders begin in `CREATED`. Cart checkout or direct-order creation stores
server-calculated item and total snapshots before payment.

- `POST /api/orders/payments/` creates one active payment attempt for an owned
  order. The local provider returns no checkout URL; Stripe returns a hosted
  Checkout URL.
- `POST /api/orders/<id>/pay/` is the synchronous confirmation command used by
  the Telegram flow. It works with the local provider. Stripe intentionally has
  no synchronous confirmation implementation; Stripe completion is webhook
  driven.
- On confirmed success, the service locks the order, payment, and available
  keys; assigns one key per purchased unit; marks the payment and order paid;
  and queues confirmation email after the database commit.

For Stripe setup and local webhook forwarding, see
[API and payment guide](docs/API.md#stripe-checkout-and-webhooks).

## API

The generated OpenAPI schema is the canonical request/response reference.
[API documentation](docs/API.md) summarizes routes, authorization, errors,
payment behavior, and example Stripe usage.

Protected endpoints use:

```text
Authorization: Bearer <access-token>
```

The Telegram authentication endpoint additionally requires
`X-Bot-Internal-Secret`.

## Development workflow

Keep the two uv lockfiles in sync with their respective `pyproject.toml`.
Typical checks mirror CI:

```bash
cd backend
uv sync --frozen
uv run ruff check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest

cd ../bot
uv sync --frozen
uv run ruff check .
uv run pytest
```

With running containers:

```bash
docker compose exec backend uv run ruff check .
docker compose exec backend uv run python manage.py check
docker compose exec backend uv run python manage.py makemigrations --check --dry-run
docker compose exec backend uv run pytest
docker compose exec bot uv run ruff check .
docker compose exec bot uv run pytest
```

Use `docker compose run --rm <service> ...` instead when the service is not
already running. Backend tests use eager Celery execution and mock Stripe's
network transport, so Redis and real Stripe credentials are not required.

## Repository layout

```text
ludora/
├── backend/                    # Django API and Celery application
├── bot/                        # aiogram client
├── docs/
│   ├── API.md                  # endpoint and payment integration guide
│   ├── ARCHITECTURE.md         # architecture and lifecycle guarantees
│   └── REPOSITORY_HYGIENE.md   # review findings and follow-up work
├── docker/                     # reserved service-specific configuration
├── docker-compose.yml          # local development topology
├── .env.example               # configuration template
└── .github/workflows/tests.yml # CI checks
```

See [Repository hygiene](docs/REPOSITORY_HYGIENE.md) for the current static
review, deliberate compatibility fields, and non-production limitations.
