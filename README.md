# Ludora

Backend for a Telegram-based digital marketplace built with Django REST Framework.

Ludora provides a REST API for managing digital products, orders, license keys, and authentication. The project is designed around a Django backend with an Aiogram client and Docker-based development workflow.

> Portfolio project focused on backend architecture, REST APIs, authentication, testing, and Docker.

---

## Badges

![Python](https://img.shields.io/badge/Python-3.13-blue)
![Django](https://img.shields.io/badge/Django-5.2-green)
![DRF](https://img.shields.io/badge/DRF-REST_Framework-red)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED)
![Pytest]
![Ruff]
![GitHub Actions](https://img.shields.io/badge/CI-GitHub_Actions-2088FF)


---

## Features

### Implemented

- **Product catalog API** — list, retrieve, create, update, and (soft) delete products. Products belong to a `Platform` and one or more `Category` entries, and have a `product_type` (game, DLC, subscription, gift card, or software).
- **Filtering, search, and ordering** on the product list endpoint (by platform, product type, category; text search on title/description; ordering by price, title, or creation date).
- **Pagination** on list endpoints (page-based, 10 items per page).
- **Soft delete for products** — deleting a product deactivates it (`is_active=False`) instead of removing the row; deactivated products no longer appear in the catalog.
- **Write access control** — product create/update/delete endpoints require an admin (staff) user.
- **License key storage** — license keys are stored per product with a status (`AVAILABLE`, `RESERVED`, `SOLD`) and assigned to an order at payment time.
- **JWT authentication** — registration, login (access/refresh token pair via Simple JWT), and an authenticated `me` endpoint.
- **Custom user model** — a project-owned, email-based `User` model with an optional unique Telegram identity.
- **Telegram bot authentication and profile** — Telegram accounts are synchronized through an internal-secret-protected endpoint, receive JWTs, and can view a localized `/profile`.
- **Order creation and history** — authenticated users can create orders and list their own order history.
- **Simulated payment flow** — a service-layer function marks an order as paid, atomically reserves an available license key for the product, and creates a `Payment` record. No external payment provider is called.
- **OpenAPI schema and Swagger UI** via drf-spectacular.
- **Django admin** for products, platforms, categories, license keys, and orders.
- **Dockerized environment** — `backend`, `postgres`, and `bot` services via Docker Compose. The backend waits for PostgreSQL to become ready (via `pg_isready` in `entrypoint.sh`) before starting Django.
- **CI pipeline** — GitHub Actions runs Ruff lint checks and the pytest suite against the Docker Compose stack on every push/PR to `master`.
- **Test suite** — pytest/DRF tests covering authentication, the products API, order creation and history, the payment service, and order/payment models. All tests currently pass.

### Not Yet Implemented

- Checkout, order creation, payments, and license-key delivery from the Telegram bot.
- Real payment gateway integration (e.g. Stripe, Telegram Stars) — the `payments` app currently only defines its Django app config, with no models or logic.
- Reverse proxy / production deployment setup — `docker/nginx` is a placeholder; no `nginx` service exists in `docker-compose.yml` yet.

> This README describes the project's current, verifiable state rather than its intended end state. See [Roadmap](#roadmap) for planned work.

---

## Tech Stack

**Backend**
- Python 3.13
- Django 5.2
- Django REST Framework
- Simple JWT (authentication)
- django-filter (filtering)
- drf-spectacular (OpenAPI schema & Swagger UI)
- PostgreSQL 16

**Bot**
- Aiogram 3
- HTTPX

**Tooling & Infrastructure**
- Docker / Docker Compose
- uv (package management)
- Ruff (linting & formatting)
- pre-commit
- pytest / pytest-django
- GitHub Actions (CI)

---

## Architecture Overview

Ludora is split into two independently packaged Python projects that share infrastructure via Docker Compose:

- **`backend/`** — a modular Django project exposing a REST API. The bot (and any future client) is intended to communicate with the backend exclusively through this API.
- **`bot/`** — an Aiogram 3 client with catalogue, authentication, profile,
  localization, and presentation layers.

The backend follows a modular Django app structure, where each business domain is isolated into its own app. Business logic for orders and payments lives in dedicated service modules (`apps/orders/services.py`, `apps/orders/payment_services.py`) rather than in the views, keeping the views thin and the logic testable in isolation.

The `payments` app is currently a placeholder for a future payment provider integration. `Order` and `Payment` models, and all payment logic that exists today, live inside the `orders` app.

```
┌─────────────┐        REST API        ┌──────────────┐
│  Telegram    │  <------------------>  │   Backend     │
│  Bot (Aiogram)│                        │ (Django + DRF)│
└─────────────┘                        └──────┬───────┘
                                                │
                                                ▼
                                        ┌───────────────┐
                                        │  PostgreSQL 16 │
                                        └───────────────┘
```

---

## Project Structure

```
ludora/
├── backend/
│   ├── apps/
│   │   ├── games/            # Product catalog: platforms, categories, products, license keys
│   │   ├── authentication/   # JWT auth, Telegram sync, registration, "me"
│   │   ├── users/            # Custom user model
│   │   ├── orders/           # Orders, payments, license assignment
│   │   └── payments/         # Placeholder — app config only, no logic yet
│   ├── config/                # Django project settings & configuration
│   ├── manage.py
│   ├── entrypoint.sh           # Waits for PostgreSQL before starting Django
│   ├── Dockerfile
│   └── pyproject.toml
│
├── bot/
│   ├── app/
│   │   ├── api/                 # Typed backend API client
│   │   ├── auth/                # Token models, storage, and auth service
│   │   ├── handlers/            # /start, /catalogue, /profile
│   │   ├── localization/        # English and Russian messages/preferences
│   │   ├── presentation/        # Escaped Telegram HTML
│   │   └── main.py              # Application construction and polling
│   ├── Dockerfile
│   └── pyproject.toml
│
├── docker/
│   ├── nginx/                   # Placeholder for a future reverse proxy (not in use)
│   └── postgres/                 # Placeholder for future PostgreSQL customization (not in use)
│
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## API Overview

The API follows REST principles and returns JSON. Interactive documentation (Swagger UI, powered by drf-spectacular) is available once the backend is running, at `/api/docs/`.

### Products (`apps/games`)

| Method | Endpoint                     | Auth        | Description                        |
|--------|-------------------------------|-------------|--------------------------------------|
| GET    | `/api/products/`              | Public      | List active products (filter, search, order, paginate) |
| GET    | `/api/products/<id>/`         | Public      | Retrieve a single active product     |
| POST   | `/api/products/create/`       | Admin       | Create a new product                 |
| PATCH  | `/api/products/<id>/update/`  | Admin       | Update an existing product           |
| DELETE | `/api/products/<id>/delete/`  | Admin       | Deactivate a product (soft delete)   |

Filtering is available on `platform`, `product_type`, and `categories`; search covers `title` and `description`; ordering supports `price`, `title`, and `created_at`.

### Authentication (`apps/authentication`)

| Method | Endpoint            | Auth          | Description                     |
|--------|-----------------------|---------------|-----------------------------------|
| POST   | `/api/auth/register/` | Public        | Register a new user               |
| POST   | `/api/auth/login/`    | Public        | Obtain a JWT access/refresh pair  |
| POST   | `/api/auth/telegram/` | Internal secret | Synchronize a Telegram user and obtain JWTs |
| POST   | `/api/auth/refresh/`  | Refresh token | Refresh a JWT access token         |
| GET    | `/api/auth/me/`       | Authenticated | Retrieve the current user profile |

### Orders (`apps/orders`)

| Method | Endpoint                    | Auth          | Description                                     |
|--------|-------------------------------|---------------|--------------------------------------------------|
| POST   | `/api/orders/`                | Authenticated | Create an order for a product                    |
| GET    | `/api/orders/my/`             | Authenticated | List the current user's order history            |
| POST   | `/api/orders/<id>/pay/`       | Authenticated | Simulate payment; assigns a license key on success |
| POST   | `/api/orders/payments/`       | Public        | Create a `Payment` record for an order            |

Exact request/response schemas are best explored through the generated OpenAPI schema (`/api/schema/`) rather than duplicated here, to avoid documentation drift.

---

## Core Domains

**Catalog domain**

- `Platform` — a storefront/service a product is sold on (e.g. Steam, Epic, GOG).
- `Category` — a classification tag for products (e.g. RPG, Action, Indie), independent of `product_type`.
- `Product` — a sellable item with a `product_type` (`GAME`, `DLC`, `SUBSCRIPTION`, `GIFT_CARD`, `SOFTWARE`), linked to one `Platform` and any number of `Category` entries.
- `LicenseKey` — a redeemable key tied to a `Product`, with a status (`AVAILABLE`, `RESERVED`, `SOLD`) that changes when it's assigned to a paid order.

**Identity domain**

- A project-owned email-based `User` model is the ownership anchor for orders.
  `telegram_id` is nullable for ordinary users and unique for linked accounts;
  bot-managed users use deterministic `telegram-<id>@bot.ludora.invalid`
  addresses and unusable passwords.

**Commerce domain**

- `Order` — a purchase of a single product, with a generated order number, status (`CREATED`, `PAID`, `CANCELLED`), and, once paid, the assigned `LicenseKey`.
- `Payment` — a payment attempt associated with an order, with its own status (`CREATED`, `PENDING`, `PAID`, `FAILED`). Both `Order` and `Payment` are implemented inside the `orders` app.

---

## Authentication Overview

Ludora uses **JWT-based authentication** via Simple JWT:

1. A user registers via `POST /api/auth/register/`.
2. The user logs in via `POST /api/auth/login/` and receives an access/refresh token pair.
3. Authenticated requests (profile retrieval, order creation, order history, payment) send the JWT access token.
4. The identity layer is backed by a custom `User` model, so it can be extended independently of Django's default user model.

For Telegram, `/start` sends the stable numeric Telegram user ID and optional
profile metadata to `POST /api/auth/telegram/` using
`X-Bot-Internal-Secret`. The backend atomically creates or retrieves the
unique mapping and returns access/refresh JWTs plus safe profile data. The bot
stores tokens by Telegram ID behind a replaceable storage interface. Protected
requests retry once after refreshing a rejected access token. `/profile`
performs synchronization itself when needed, so `/start` is not a prerequisite.

The current token and language-preference stores are process-local memory:
tokens are lost on restart and are not shared across bot replicas. Redis or a
database-backed implementation is the intended production replacement.

---

## Order / Payment Flow Overview

1. An authenticated user creates an **order** for a product (`POST /api/orders/`).
2. The user pays the order (`POST /api/orders/<id>/pay/`). This call is a **simulation** — no external payment gateway is contacted.
3. On payment, the service layer atomically: reserves an `AVAILABLE` license key for the product, marks it `SOLD`, assigns it to the order, sets the order status to `PAID`, and creates a `Payment` record.
4. If no license key is available for the product, the payment fails with an error and the order is left unpaid.
5. The user's order history, including assigned license keys, is available via `GET /api/orders/my/`.

---

## Docker Setup

The project ships with a Docker Compose configuration that runs three services:

- `backend` — the Django/DRF application
- `postgres` — PostgreSQL 16
- `bot` — the Aiogram bot service (starts and polls Telegram; exits cleanly if `BOT_TOKEN` is not set)

The backend container waits for PostgreSQL to accept connections (via `pg_isready` in `entrypoint.sh`) before starting Django, avoiding startup race conditions.

Set the same non-empty `BOT_INTERNAL_SECRET` for the backend and bot. It is
loaded from `.env`, is never part of Telegram messages, and must not be
committed. Other bot variables are `BOT_TOKEN`, `BOT_BACKEND_BASE_URL`,
`BOT_API_TIMEOUT`, and `BOT_DEFAULT_LANGUAGE`.

### Running with Docker

```bash
# 1. Copy environment variables
cp .env.example .env

# 2. Build and start all services
docker compose up --build

# 3. Apply migrations (in a separate terminal)
docker compose exec backend uv run python manage.py migrate

# 4. Create a superuser (optional, for Django admin / product management)
docker compose exec backend uv run python manage.py createsuperuser
```

The API is available at `http://localhost:8000/api/`, with Swagger UI at `http://localhost:8000/api/docs/`.

---

## Local Development Instructions

The backend and bot are separate Python projects, each managed with **uv**.

### Backend

```bash
cd backend
uv sync
uv run python manage.py migrate
uv run python manage.py runserver
```

### Bot

```bash
cd bot
uv sync
uv run python app/main.py
```

The available commands are `/start`, `/catalogue`, and `/profile`.

### Code Quality

The project uses **Ruff** for linting and formatting, enforced locally via **pre-commit**:

```bash
uv tool install pre-commit
pre-commit install
pre-commit run --all-files
```

---

## Testing

```bash
cd backend
uv run pytest
```

Tests are written with pytest/pytest-django and cover:

- authentication (registration, login, profile)
- the products API (list, detail, create, update, delete)
- order creation and order history
- the payment service and payment API
- order and payment model behavior

All tests currently pass and run automatically in CI on every push/PR to `master`.

---

## CI/CD

The GitHub Actions workflow, on every push/PR to `master`:

- builds and starts the full Docker Compose stack
- runs Ruff lint checks against the backend
- runs the full pytest suite inside the `backend` container

This keeps the codebase lint-clean and functionally verified before merging changes.

---

## Roadmap

The following items are planned but **not yet implemented**:

- [ ] Telegram bot checkout, order placement, payment flow, and license-key delivery
- [ ] Integration with a real payment provider (e.g. Stripe, Telegram Stars)
- [ ] Admin-side reporting/analytics
- [ ] Reverse proxy and production deployment setup (nginx, TLS, environment hardening, CD pipeline)
- [ ] Rate limiting / throttling on public API endpoints

---

## Author / Portfolio Note

## About

Ludora is a personal backend portfolio project built to practice backend architecture with Django, Django REST Framework, PostgreSQL, Docker, and automated testing.

The project is developed incrementally, and this README reflects only features that are currently implemented.
