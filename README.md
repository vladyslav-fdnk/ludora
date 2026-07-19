# Telegram Game Key Store

A store for digital game keys, sold through a Telegram bot, built on a
Django backend. This repository currently contains the **initial project
scaffolding only** — architecture and tooling, no business logic yet.

## Stack

| Concern            | Choice                          |
|---------------------|----------------------------------|
| Language            | Python 3.13                     |
| Web framework        | Django (DRF to be added later)  |
| Bot framework        | Aiogram 3                       |
| Database             | PostgreSQL                      |
| Package management   | uv                               |
| Linting/formatting   | Ruff                             |
| Git hooks            | pre-commit                      |
| Containerization      | Docker / Docker Compose         |

## Project structure

```
game_key_store/
│
├── backend/                 # Django project (monolith for now)
│   ├── config/               # Settings, root URLs, WSGI/ASGI entry points
│   ├── apps/                 # Django apps, one per bounded context
│   │   ├── games/             # TODO: catalog of games and keys
│   │   ├── users/              # TODO: users linked to Telegram accounts
│   │   ├── orders/             # TODO: orders and order items
│   │   └── payments/            # TODO: Telegram Stars / Stripe payments
│   ├── manage.py
│   ├── Dockerfile
│   └── pyproject.toml
│
├── bot/                     # Aiogram 3 Telegram bot
│   ├── app/
│   │   ├── handlers/          # TODO: aiogram routers
│   │   ├── keyboards/          # TODO: keyboard builders
│   │   ├── services/            # TODO: business logic / backend client
│   │   └── main.py              # Bot/Dispatcher bootstrap, no handlers yet
│   ├── Dockerfile
│   └── pyproject.toml
│
├── docker/
│   ├── postgres/             # Reserved for future DB init scripts
│   └── nginx/                # Reserved for future reverse proxy config
│
├── .env.example
├── .gitignore
├── .pre-commit-config.yaml
├── docker-compose.yml
└── README.md
```

`backend/` and `bot/` are two independent Python projects (each with its
own `pyproject.toml`, dependencies, and Dockerfile), coordinated together
only through `docker-compose.yml` and shared environment variables. This
keeps the web backend and the bot deployable and scalable independently.

## Why this structure

- **`config/` vs `apps/`** — Django project-level configuration (settings,
  URLs, WSGI/ASGI) is kept separate from domain apps, matching common
  large-Django-project layout instead of the default flat `manage.py`
  layout.
- **One app per bounded context** (`games`, `users`, `orders`, `payments`)
  — each will own its own models/logic later, keeping domains isolated
  instead of one large app.
- **`apps/payments`** exists now, empty, specifically so Telegram Stars and
  Stripe integrations have an obvious, isolated home later instead of being
  bolted onto `orders`.
- **`bot/app/handlers|keyboards|services`** — separates *what the bot
  receives* (handlers), *what it shows* (keyboards), and *what it does*
  (services/business logic), so handlers stay thin.
- **Two `pyproject.toml` files** — backend and bot have different, mostly
  non-overlapping dependencies (Django vs Aiogram) and different deployment
  lifecycles; separate environments avoid dependency bloat/conflicts.
- **`docker/postgres`, `docker/nginx`** — created empty on purpose, so the
  places for future infrastructure config are obvious without adding
  unused config now.

## Startup behavior

- **backend** waits for PostgreSQL before starting. `backend/entrypoint.sh`
  polls `pg_isready` (installed via the `postgresql-client` package) and
  only then execs the container's command — no fixed `sleep`.
- **bot** does not start if `BOT_TOKEN` is not set. `bot/app/main.py` logs
  `BOT_TOKEN is not configured, skipping bot startup.` and exits with code
  `0`, so the container doesn't crash-loop when the token is intentionally
  left empty (e.g. in an environment that only runs the backend).

## Environment variables

All configuration is environment-driven (see `.env.example`). Copy it to
get started:

```bash
cp .env.example .env
```

## Running with Docker Compose

```bash
docker compose up --build
```

This starts three services: `postgres`, `backend` (Django dev server on
`:8000`), and `bot` (long-polling Aiogram bot).

## Local development without Docker

Each project manages its own environment with `uv`:

```bash
# Backend
cd backend
uv sync
uv run python manage.py runserver

# Bot
cd bot
uv sync
uv run python app/main.py
```

## Linting

```bash
uv run ruff check .
uv run ruff format .
```

## Pre-commit

```bash
uv tool install pre-commit   # or: pip install pre-commit
pre-commit install
```

## Roadmap (not implemented yet)

- Models for games, keys, users, orders, payments
- Django REST Framework API
- Telegram Stars payments
- Stripe payments
- Web interface
- Celery + Redis for background tasks (key delivery, payment webhooks)
- Nginx reverse proxy for deployment
