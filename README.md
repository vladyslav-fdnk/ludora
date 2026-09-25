# Ludora

[![CI](https://github.com/vladyslav-fdnk/ludora/actions/workflows/tests.yml/badge.svg?branch=master)](https://github.com/vladyslav-fdnk/ludora/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.13-blue)
![Django](https://img.shields.io/badge/django-5.x-green)
[![License: MIT](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

Ludora is a digital-product marketplace built as a Django modular monolith with
an aiogram Telegram client. It provides a public catalogue, JWT authentication,
persistent carts, immutable order snapshots, license-key fulfilment, local
payment simulation, Stripe Checkout, and signed Stripe webhooks.

## Engineering highlights

The focus of the project is correctness of the purchase flow under concurrency
and unreliable external systems, not CRUD volume.

- **No overselling.** Checkout reserves license keys for the whole order under
  PostgreSQL row locks (`select_for_update`) before a payment is exposed to the
  customer. Database constraints back the invariants in the service layer.
- **Idempotent, order-tolerant webhooks.** Stripe events are signature-verified,
  deduplicated by event ID, and safe to receive twice or out of order.
- **Payment attempt ownership.** An order names the single payment attempt
  allowed to finalize or release its reservation, so a stale or superseded
  payment can never fulfil or cancel a newer one
  ([ADR-001](docs/architecture/ADR-001-license-reservation.md)).
- **Clean transaction boundaries.** External provider calls run outside
  database transactions; confirmation email is queued to Celery only after
  commit.
- **Immutable order snapshots.** Prices and items are copied at checkout, so
  catalogue changes never rewrite purchase history.
- **Thin Telegram client.** The bot talks only to the public API, with no
  database access, and supports English and Russian.
- **Tested against real PostgreSQL.** About 400 backend and bot tests, plus
  Ruff, Django system checks, and migration-drift checks, run in GitHub Actions
  on every push and pull request.

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

6. Optionally load the demo catalogue: 10 products across 5 platforms, each with
   10 clearly fake `DEMO-...` license keys. The command is idempotent and tops
   stock back up on every run:

   ```bash
   docker compose exec backend uv run python manage.py seed_demo
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

## Production deployment

`docker-compose.prod.yml` is a production-like topology: gunicorn behind nginx,
images built without test tooling, no source bind mounts, and no published
database port. A one-shot `migrate` service applies migrations and collects
static files before the backend, worker, and bot start.

```bash
cp .env.example .env   # set real secrets and the variables below
docker compose -f docker-compose.prod.yml up -d --build
# include the Telegram bot:
docker compose -f docker-compose.prod.yml --profile bot up -d --build
```

Set at least:

- `DJANGO_ALLOWED_HOSTS` — your domain plus `backend` and `localhost`, which the
  bot and the container health check use internally.
- `DJANGO_CSRF_TRUSTED_ORIGINS` — for example `https://shop.example.com`, so
  Django Admin works over HTTPS.
- `DJANGO_BEHIND_HTTPS_PROXY=True` when TLS is terminated in front of nginx.
- `HTTP_PORT` (default `80`) and `GUNICORN_WORKERS` (default `3`) if needed.

For a demo deployment, load the sample catalogue with
`docker compose -f docker-compose.prod.yml exec backend uv run python manage.py seed_demo`.

nginx serves `/static/` and `/media/` from volumes and proxies everything else
to gunicorn. TLS is expected in front of nginx: a cloud load balancer, Caddy, or
certbot on the host. See [docker/nginx](docker/nginx/README.md).

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
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | Comma-separated origins, e.g. `https://shop.example.com` |
| `DJANGO_BEHIND_HTTPS_PROXY` | `False` | Trust `X-Forwarded-Proto` and use secure cookies |
| `DJANGO_STATIC_ROOT`, `DJANGO_MEDIA_ROOT` | `backend/staticfiles`, `backend/media` | Collected static and uploaded media paths |
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

### License reservation

Checkout reserves the complete order inventory before a payment is exposed to
the customer, and `Order.reservation_payment_attempt` names the single
payment authorized to finalize or release that reservation. A superseded or
historical payment outcome can never finalize or release a newer attempt's
reservation. See [ADR-001](docs/architecture/ADR-001-license-reservation.md)
and its [implementation roadmap](docs/architecture/IMPLEMENTATION_ROADMAP.md)
for the full design and phase-by-phase status.

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
├── docker/nginx/               # reverse proxy configuration
├── docker-compose.yml          # local development topology
├── docker-compose.prod.yml     # gunicorn + nginx production topology
├── .env.example               # configuration template
└── .github/workflows/tests.yml # CI checks
```

## Status and limitations

The core purchase flow is complete and covered by tests. Known limitations:

- The production Compose file does not manage TLS certificates, secrets, or
  database backups; these belong to the hosting environment.
- Stripe completion is webhook-driven only. The synchronous `/pay/` command is
  supported for the local provider.

See [Repository hygiene](docs/REPOSITORY_HYGIENE.md) for deliberate
compatibility fields and planned cleanup.

---

_README written with the assistance of Claude (Anthropic)._
