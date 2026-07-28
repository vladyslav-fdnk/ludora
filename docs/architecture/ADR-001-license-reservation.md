# ADR-001 — License Reservation Architecture

- Status: Proposed
- Date: 2026-07-28
- Scope: Ludora backend order payment and digital-license fulfilment

## 1. Context

Ludora sells digital products fulfilled with license keys. An `Order` is the
commercial unit presented to the customer and may contain multiple
`OrderItems`. Each item records a product, quantity, and price snapshot.
Customers pay the total for the entire order through one checkout rather than
paying for individual items.

Inventory is finite. Every unit in an order requires a distinct license key for
the corresponding product. Payment confirmation and license fulfilment must
therefore behave as one coherent business process even though the payment
provider is external to Ludora.

The current domain already contains the concepts required for fulfilment:
orders and order items, payment attempts, license keys with lifecycle states,
and license assignments connecting keys to order items. This ADR establishes
how those concepts cooperate during reservation and payment.

## 2. Problem Statement

License availability must be established before the customer can successfully
pay. Allocating keys only after payment confirmation creates an unacceptable
failure mode: the provider may successfully charge the customer while Ludora
can no longer fulfil one or more order items.

The architecture must:

- reserve every required key before an external checkout can accept payment;
- treat the order, not an individual payment attempt or order item, as the
  reservation boundary;
- support multiple products and quantities in one order;
- prevent the same key from being promised to more than one order;
- complete or release the reservation consistently for all order items;
- preserve safe retry and duplicate-event behavior; and
- preserve the existing rule that an order has at most one active payment
  attempt.

## 3. Existing Architecture

The current backend uses the following domain model:

- `Order` is the aggregate purchased by the customer. It owns the order total,
  customer identity, payment outcome, and collection of order items.
- `OrderItem` is a product-and-quantity line within an order. An order may
  contain multiple items, while a product appears at most once in that order.
- `Payment` belongs to an order and records one attempt to pay the full
  authoritative order total. An order can retain historical failed or completed
  attempts.
- `LicenseKey` belongs to a product and owns its inventory lifecycle:
  `AVAILABLE`, `RESERVED`, or `SOLD`.
- `LicenseAssignment` connects one specific `LicenseKey` to one `OrderItem`.
  Multiple assignments satisfy an item whose quantity is greater than one.

The current payment flow serializes payment activity for an order, reuses an
existing active attempt where appropriate, and handles provider callbacks
idempotently. Fulfilment validates availability for every item as a single
transaction and creates assignments for the selected keys.

At present, keys are selected and marked `SOLD` when payment is completed.
That establishes transactional fulfilment inside Ludora, but it does not hold
inventory during the external checkout interval. This ADR adds that missing
reservation phase while retaining the existing aggregate and relationship
boundaries.

## 4. Existing Invariants

The following existing invariants remain authoritative:

1. An order may contain multiple order items.
2. Each order item has a positive quantity and a non-negative unit price.
3. The order total is authoritative for payment; a payment attempt must match
   that total.
4. The customer pays for the whole order in one checkout.
5. One order may have at most one active payment, where active means
   `CREATED` or `PENDING`.
6. A payment represents a payment attempt only. It does not own inventory or
   fulfilment.
7. A license key can be assigned at most once.
8. A license assignment always associates one order item with one specific
   license key.
9. Paid orders and paid payment attempts are completed idempotently.
10. An order is fulfilled only when all required quantities can be satisfied.

Reservation does not weaken or replace any of these invariants.

## 5. Decision

License reservation belongs to the `Order` aggregate.

Before Ludora exposes a checkout that can successfully charge the customer, it
must reserve the complete set of license keys required by every order item.
Reservation is all-or-nothing across the order. Partial reservation is not a
valid externally visible state.

The reservation is expressed through `LicenseAssignment` records. Each
assignment identifies the order item being fulfilled and the exact key held for
it. The owning order is reached through the order item. Assignments created
while keys are `RESERVED` are temporary; the same assignments become the
durable fulfilment record when those keys become `SOLD`.

`LicenseKey` owns only its lifecycle:

```text
AVAILABLE  ---- reserve for order ---->  RESERVED
RESERVED   ---- payment succeeds ---->  SOLD
RESERVED   ---- payment fails/expires -> AVAILABLE
```

Neither the active `Payment` nor a provider checkout owns the reservation.
Replacing a failed attempt for the same payable order does not redefine which
inventory the order requires. This separation keeps payment history independent
from inventory ownership.

The active-payment invariant must continue to hold throughout reservation and
checkout creation:

```text
Order
+-- zero or one active Payment (CREATED or PENDING)
`-- OrderItem(s)
    `-- LicenseAssignment(s)
        `-- RESERVED LicenseKey(s)
```

Reservation, assignment creation, and active-payment establishment form one
serialized order-level operation. A competing request can neither create a
second active payment nor reserve a second set of keys for the same order.
Selection of keys must also exclude keys concurrently reserved or sold by
another order.

## 6. Reservation Lifecycle

The normal lifecycle is:

```text
Customer requests checkout
           |
           v
Serialize activity for the Order
           |
           v
Validate order and full payable total
           |
           v
Reserve every required key atomically:
  AVAILABLE -> RESERVED
  Create temporary LicenseAssignments
           |
           v
Establish/reuse the Order's single active Payment
           |
           v
Create or return external checkout
           |
      +----+----------------+
      |                     |
      v                     v
Payment succeeds       Payment fails/expires
      |                     |
      v                     v
RESERVED -> SOLD       RESERVED -> AVAILABLE
Assignments retained   Temporary assignments
as fulfilment record   removed
      |                     |
      v                     v
Order becomes PAID     Order remains unpaid
```

The checkout must not become chargeable until the full reservation is durable.
If reservation cannot satisfy every order item, no active checkout is created
and no charge can succeed.

Successful payment finalization changes all assigned keys from `RESERVED` to
`SOLD`, records the paid outcome for the payment attempt and order, and retains
the assignments as the fulfilment record. These changes are one atomic
order-level transition.

Failed or expired payment finalization changes all keys reserved for the order
from `RESERVED` to `AVAILABLE`, removes the temporary assignments, and records
the attempt as no longer active. Release is also an all-or-nothing order-level
transition.

Duplicate requests and provider events must be idempotent. Reprocessing success
must not sell additional keys; reprocessing failure or expiration must not
release keys that have already been sold.

A reservation may be released only after the associated checkout is
conclusively unable to succeed. Success and failure/expiration processing are
serialized for the order. This prevents a late success from observing released
inventory and preserves the rule that Ludora must never successfully charge a
customer and then fail because keys are unavailable.

## 7. Multi-item Orders

All order items participate in one reservation decision. For each item, the
number of assignments must equal its quantity, and every assigned key must
belong to that item's product.

For example:

```text
Order LUD-...
+-- Item A: Product A x 2
|   +-- Assignment -> Product A / Key 101
|   `-- Assignment -> Product A / Key 102
`-- Item B: Product B x 1
    `-- Assignment -> Product B / Key 205
```

The reservation succeeds only if all three keys can be reserved together. If
Product B has no available key, the two Product A keys must remain
`AVAILABLE`; Ludora must not retain a partial reservation.

The customer sees one checkout for the complete order total. There is no
per-item payment state and no independently successful subset of an order.
Likewise, successful payment sells every assigned key as one fulfilment
operation.

## 8. Failure Scenarios

### Insufficient inventory before checkout

If any item cannot be satisfied in full, the reservation fails atomically. No
keys remain reserved, no temporary assignments remain, and no chargeable
checkout is made available.

### Concurrent checkout requests for the same order

Order-level serialization ensures that requests observe or reuse the same
active payment and reservation. They cannot create multiple active attempts or
duplicate reservations.

### Concurrent demand for the same key

Key allocation is exclusive. Only one order may move a particular key from
`AVAILABLE` to `RESERVED`; other orders must select different available keys or
fail reservation.

### Payment-provider checkout creation fails

Because the customer cannot complete the checkout, the payment attempt ceases
to be active and the order reservation is released. Reserved keys return to
`AVAILABLE`, and temporary assignments are removed.

### Payment is pending

The active payment and full order reservation remain in place. No other payment
attempt may become active for the order, and no assigned key may be allocated
elsewhere.

### Payment fails or checkout expires

The attempt becomes inactive. All keys reserved for the order return to
`AVAILABLE`, and all temporary assignments for that reservation are removed.
The order remains eligible for a later payment attempt, subject to a new
complete reservation.

### Payment succeeds

All reserved keys become `SOLD`, the temporary assignments become permanent
fulfilment records, and the order and payment become paid. The operation is
atomic and idempotent.

### Duplicate or out-of-order provider events

Events are interpreted against the durable order, payment, assignment, and key
states. A repeated success is a no-op after completion. A failure or expiration
cannot undo a completed sale. Conflicting terminal events are resolved under
serialized order processing, with a verified successful charge taking
precedence over release.

### Internal failure during finalization

The entire local transition rolls back. The order remains reserved rather than
partially sold or partially released, allowing safe retry and reconciliation
without allocating replacement inventory after a charge.

## 9. Rejected Alternatives

### Reservation owned by Payment

This alternative was rejected because the current architecture already
guarantees at most one active `Payment` per `Order`. A `Payment` represents only
a payment attempt; it does not own inventory or fulfilment.

Inventory ownership belongs to the `Order` aggregate. Coupling reservations to
`Payment` would duplicate that responsibility and unnecessarily increase model
complexity, particularly when one payment attempt is replaced by another for
the same order.

### Reserve inventory only after successful payment

This alternative was rejected because inventory could be gone by the time
Ludora receives payment confirmation. The customer could then be successfully
charged for an order that cannot be fulfilled.

The system must guarantee fulfilment before external payment succeeds.
Therefore, the complete inventory requirement must be reserved before checkout
can become chargeable.

## 10. Design Principles

- `Order` is the aggregate root and owns one complete purchase lifecycle.
- `Payment` represents only an attempt to pay for an order.
- Reservation is owned by the `Order` aggregate.
- `LicenseAssignment` binds specific inventory to an `OrderItem`.
- `LicenseKey` owns only its inventory lifecycle state.
- Required inventory must exist and be reserved before payment succeeds.
- Fulfilment must never depend on searching for inventory after payment.

## 11. Consequences

### Positive

- Inventory is guaranteed before the customer can be successfully charged.
- Multi-item and multi-quantity orders are reserved and fulfilled atomically.
- A specific key is traceable from inventory through its order item to the
  order.
- Payment attempts remain a clean history of provider interactions rather than
  becoming inventory owners.
- The same assignment represents both the temporary hold and the final
  fulfilment, avoiding a second mapping at payment success.
- Retries and duplicate provider events can be handled without allocating
  additional keys.

### Costs and trade-offs

- Reserved inventory is unavailable to other customers while checkout is
  pending.
- Reservation release depends on reliable terminal payment or expiration
  signals.
- Checkout, webhook, and expiration paths must coordinate around the same
  order-level state.
- Operational visibility is required to identify reservations that remain
  pending longer than intended.
- The order-level all-or-nothing rule may reject a checkout even when only one
  line lacks inventory; this is intentional because Ludora accepts one payment
  for the whole order.

## 12. Future Extensions

The architecture permits future capabilities without changing the ownership
decision:

- configurable reservation durations by provider or product class;
- explicit customer cancellation of an unpaid checkout;
- automated reconciliation of long-running pending payments;
- operational reporting for reserved inventory and reservation age;
- support for additional payment providers with equivalent terminal-state
  guarantees;
- controlled retry of an unpaid order after its former reservation is
  conclusively released; and
- richer audit history for reservation, release, and sale transitions.

Any extension must preserve full-order reservation, one active payment per
order, exclusive key assignment, and the guarantee that payment success never
depends on finding inventory afterward.

## 13. Architectural Considerations

### Architectural Note

The assignment lifecycle is intentional because it keeps reservation and
fulfilment simple:

```text
Reservation
    -> temporary LicenseAssignment
    -> payment success -> assignment becomes permanent
    -> payment failure -> assignment removed
```

The same assignment therefore records both the temporary inventory hold and,
after successful payment, permanent fulfilment. Releasing a reservation removes
the temporary assignment.

### Open Questions

- What reservation duration provides the right balance between customer
  checkout completion and inventory availability?
- Which provider state is authoritative when local timeout policy and provider
  expiration are observed at different times?
- What operational threshold should identify a pending reservation for manual
  review?
- What retention and audit requirements apply to the history of temporary
  assignments after release?
- How should customer support present an order whose checkout expired after a
  long-running pending payment?

## Revision History

| Date | Revision |
| --- | --- |
| 2026-07-28 | Initial decision recording the order-owned license reservation architecture. |

## Related ADRs

- None.

Future ADRs may describe:

- Order Aggregate
- Shopping Cart
- Inventory Management
- Payment Lifecycle
