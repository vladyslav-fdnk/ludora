# API and payment guide

Swagger UI at `/api/docs/` and the generated schema at `/api/schema/` are the
canonical request and response reference. This guide summarizes the public
contract and integration flow.

## Authentication

| Method | Endpoint | Access | Purpose |
| --- | --- | --- | --- |
| `POST` | `/api/auth/register/` | Public | Register by email and password |
| `POST` | `/api/auth/token/` | Public | Obtain JWT access and refresh tokens |
| `POST` | `/api/auth/token/refresh/` | Refresh token | Refresh access |
| `GET` | `/api/auth/me/` | JWT | Current user |
| `POST` | `/api/auth/telegram/` | Internal secret | Synchronize Telegram identity and issue JWTs |

Legacy `/api/auth/login/` and `/api/auth/refresh/` aliases remain for the bot.
Use `Authorization: Bearer <token>` on protected routes. Telegram
authentication uses `X-Bot-Internal-Secret`.

## Catalogue and cart

| Method | Endpoint | Access | Purpose |
| --- | --- | --- | --- |
| `GET` | `/api/products/` | Public | Active product list |
| `GET` | `/api/products/<id>/` | Public | Active product detail |
| `POST` | `/api/products/create/` | Staff | Create product |
| `PUT`, `PATCH` | `/api/products/<id>/update/` | Staff | Update product |
| `DELETE` | `/api/products/<id>/delete/` | Staff | Soft-deactivate product |
| `GET` | `/api/cart/` | JWT | Current cart |
| `POST` | `/api/cart/items/` | JWT | Add/increase an item |
| `PATCH`, `DELETE` | `/api/cart/items/<id>/` | JWT | Set quantity/remove item |
| `DELETE` | `/api/cart/clear/` | JWT | Clear cart |
| `POST` | `/api/cart/checkout/` | JWT | Create order snapshots and clear cart |

Product listing supports `platform`, `product_type`, and `categories` filters;
`search` across title/description; `ordering` by `price`, `title`, or
`created_at`; and page-number pagination.

## Orders and payments

| Method | Endpoint | Access | Purpose |
| --- | --- | --- | --- |
| `GET`, `POST` | `/api/orders/` | JWT | List visible orders/create direct order |
| `GET` | `/api/orders/<id>/` | JWT | Visible order detail |
| `GET` | `/api/orders/my/` | JWT | Owner summary list |
| `GET` | `/api/orders/my/<id>/` | JWT | Owner detail, payments, and paid keys |
| `POST` | `/api/orders/payments/` | JWT | Create provider payment |
| `POST` | `/api/orders/<id>/pay/` | JWT | Synchronously confirm local payment |
| `POST` | `/api/payments/stripe/webhook/` | Signed public webhook | Apply Stripe Checkout event |

Create a provider payment:

```http
POST /api/orders/payments/
Authorization: Bearer <access-token>
Content-Type: application/json

{"order": 42}
```

A successful Stripe response includes `checkout_url`; redirect the customer to
that URL. A local-provider response has `checkout_url: null`, after which the
development-only `/api/orders/<id>/pay/` command completes the simulation.

Only one `CREATED` or `PENDING` payment may exist per order. A failed attempt
does not cancel the order, so a later request can create a new attempt.

Expected domain failures use `{"error": "..."}` with `400`, while an order
outside the authenticated user's ownership scope is returned as `404`.
Serializer validation errors use standard DRF field-error responses.

## Stripe Checkout and webhooks

Set:

```dotenv
PAYMENT_PROVIDER=stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_CURRENCY=usd
STRIPE_SUCCESS_URL=http://localhost:3000/payment/success
STRIPE_CANCEL_URL=http://localhost:3000/payment/cancel
```

Configure the Stripe endpoint as:

```text
https://<public-backend>/api/payments/stripe/webhook/
```

Subscribe to:

```text
checkout.session.completed
checkout.session.async_payment_succeeded
checkout.session.async_payment_failed
checkout.session.expired
```

For local forwarding with the Stripe CLI:

```bash
stripe listen --forward-to localhost:8000/api/payments/stripe/webhook/
```

Copy the CLI's `whsec_...` value into `STRIPE_WEBHOOK_SECRET`, restart the
backend, create an order and payment through the API, then open the returned
Checkout URL. The backend reads the raw request body and `Stripe-Signature`;
do not put the webhook behind middleware or a proxy that rewrites the body.

The webhook returns:

- `200 {"received": true}` for a valid supported event and for a valid
  unsupported event that is intentionally ignored;
- `400 {"error": "Invalid Stripe webhook"}` for signature, payload, payment
  reference, provider, or Checkout Session mismatches;
- a server configuration error if `STRIPE_WEBHOOK_SECRET` is empty.

The success redirect is not proof of payment. Clients should read the private
order endpoint until the webhook has advanced the order to `PAID`; license keys
are exposed there only after that transition.

## OpenAPI maintenance

Generate and validate the schema from `backend/`:

```bash
uv run python manage.py spectacular --file schema.yml --validate
```

When an endpoint, serializer, permission, or error response changes, update its
drf-spectacular annotation and this summary in the same change.
