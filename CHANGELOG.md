# Changelog

All notable changes to this project will be documented in this file.

The format is inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The project is currently under active development.
Semantic versioning will be adopted once public releases begin. Until
then, `[Unreleased]` describes the current development state and the milestones
below summarize how the portfolio project evolved.

## [Unreleased]

### Added

- A Django REST API backed by PostgreSQL for the catalogue, accounts, carts,
  orders, and payments.
- A catalogue of games, DLC, subscriptions, gift cards, and software, organized
  by platform and category and backed by license-key inventory.
- Public product listing and detail endpoints with pagination, filtering,
  search, and ordering. Inactive products are hidden from catalogue and
  purchasing flows.
- Staff-only product creation, editing, and
  deactivation.
- Email-based registration, JWT authentication and refresh, user profiles, and
  protected Telegram identity synchronization.
- Direct and cart-based orders with generated `LUD-...` order numbers,
  authoritative totals, and item snapshots that preserve title, quantity, and
  unit price at purchase time.
- A private “My Orders” view showing the current user's orders newest first,
  with historical product titles preserved.
- Payment records and a local simulated payment flow for direct orders,
  including license-key assignment. No external payment provider is connected.
- A persistent authenticated cart with product addition, quantity updates,
  removal, clearing, and checkout.
- Atomic multi-item checkout that preserves product and price details before
  clearing the cart. Payment and license assignment remain separate.
- An English- and Russian-language Telegram bot for browsing the catalogue,
  viewing products, managing the authenticated cart, and confirming checkout.
- Resilient bot-to-API authentication with token refresh and user-friendly API
  and timeout errors.
- OpenAPI documentation and interactive Swagger UI for the
  REST API.
- Docker Compose services for PostgreSQL, the backend, and the Telegram
  bot.
- A Redis broker, separate Celery worker, Django Celery application, and
  diagnostic task with broker-free eager tests.
- Automated backend and bot test suites covering APIs, permissions, migrations,
  schemas, transactions, concurrency, authentication, localization, and UI
  presentation.
- Ruff linting for both Python applications and automated backend checks in
  GitHub Actions.

### Changed

- Orders now support both direct purchases and multi-product cart checkout
  through immutable item snapshots. The legacy `product` field remains on
  compatible direct-order responses.
- Order responses now include `source`, `total_price`, and normalized `items`.
  “My Orders” uses preserved item titles rather than current catalogue data.
- Direct order creation and its initial item snapshot now complete
  atomically.
- Payments use the order's authoritative total, so later catalogue price
  changes cannot affect the amount charged or recorded.
- Historical direct orders are backfilled from the best available stored
  financial evidence, with the current catalogue price used only for unpaid
  legacy records when necessary.
- Cart totals continue to reflect current prices while shopping; checkout
  freezes titles and prices for order history.
- Cart mutation and checkout synchronization was strengthened to prevent
  conflicting operations.
- Removed a redundant cart-item index already covered by the unique
  `(cart, product)` constraint.

### Fixed

- Prevented payment creation and simulated payment from using a changed
  catalogue price after an order has been placed.
- Made payment and license-key fulfillment atomic, so failures do not leave
  partial payment or inventory changes.
- Rejected legacy orders without an authoritative total or product reference
  with an explicit manual-review error instead of inventing financial data.
- Prevented duplicate active payment requests while keeping failed
  payments retryable.
- Prevented repeat or competing checkout requests from producing duplicate
  orders, and protected concurrent add/update/checkout combinations from lost
  cart quantities.
- Aligned payment and order schemas, including documented errors, with actual
  API responses.

### Security

- Restricted order creation, order history, payment creation, payment
  execution, and all cart operations to authenticated users.
- Enforced order and cart ownership in API queries so users cannot access or
  mutate another user's records; Telegram cart callbacks also validate their
  intended owner.
- Protected product write operations with staff permissions and the Telegram
  identity synchronization endpoint with a shared internal secret.
- Enforced database-level financial, quantity, uniqueness, cart ownership, and
  cart-order integrity rules.
- Added migration-time validation that stops financial constraints from being
  applied when incompatible negative values or malformed legacy cart orders
  already exist.
- Hardened payment, license allocation, cart mutation, and checkout against
  concurrent requests.

## Development milestones

1. Established the Docker-based Django and PostgreSQL foundation and core
   catalogue.
2. Added the public REST catalogue, product management, and API
   documentation.
3. Introduced direct orders and simulated payment with license-key
   fulfillment.
4. Added email accounts, JWT authentication, ownership controls, and order
   history.
5. Connected the localized Telegram catalogue and account
   experience.
6. Added persistent carts and confirmed checkout across the API and
   bot.
7. Introduced immutable order items, authoritative totals, and atomic order
   creation.
8. Hardened payments and carts against duplicate and concurrent
   operations.
9. Migrated legacy order data and enforced financial and quantity
   integrity.
