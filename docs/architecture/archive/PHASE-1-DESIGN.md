# Phase 1 — Reservation Domain Design

## Goal

Phase 1 establishes provider-neutral reservation and release behavior at the
`Order` aggregate boundary.

For an unpaid order, the complete quantity required by every `OrderItem` is
reserved atomically. Each reserved `LicenseKey` is connected to its item by a
temporary `LicenseAssignment`. A repeated request reuses an existing complete
and consistent reservation. If the order cannot be satisfied in full, or if
existing reservation state is incomplete or inconsistent, the operation fails
without changing inventory or assignments.

Phase 1 also establishes the inverse domain operation: a complete reservation
for an unpaid order can be released atomically. Release returns its reserved
keys to availability and removes its temporary assignments, but can never undo
a paid order or a sold key.

This phase does not connect either operation to checkout creation, payment
outcomes, payment finalization, or provider events.

## Out of Scope

Phase 1 intentionally excludes:

- checkout creation, checkout reuse, or changes to checkout behavior;
- payment creation, payment completion, or payment finalization;
- payment failure and expiration handling;
- Stripe or any other payment-provider integration;
- webhook handling or changes to webhook behavior;
- email sending or other customer notifications;
- API changes;
- wiring reservation release to external outcomes;
- inventory expiration policy or reservation-duration policy;
- operational reconciliation, monitoring, and support tooling;
- reporting and audit-retention policy; and
- database schema improvements unrelated to reservation.

## Non-goals

Phase 1 does not attempt to improve payment architecture, optimize checkout,
redesign webhooks, introduce reporting or operational tooling, define
reservation expiration policy, provide reconciliation or support capabilities,
or introduce additional database constraints.

## Design Decisions

- Reservation belongs to the order aggregate.
- Payment attempts and provider checkouts never own inventory.
- Reservation is provider-neutral.
- Release is provider-neutral.
- License assignment represents the order item's ownership of a reserved key.
- Reservation and release apply to the complete order and are atomic.
- Existing complete reservations and completed releases are handled
  idempotently.
- Inconsistent reservation state is rejected rather than repaired.

## Assumptions

- `OrderItem` remains the source of truth for the inventory required by an
  order.
- `LicenseAssignment` continues to represent ownership of a specific key by a
  specific order item.
- The `LicenseKey` lifecycle remains `AVAILABLE` to `RESERVED` to `SOLD`, with
  release permitting `RESERVED` to return to `AVAILABLE`.
- Existing order-level transaction isolation and serialization guarantees
  remain unchanged.
- Existing order, item, assignment, and license-key invariants remain
  authoritative.
- Phase 1 introduces no external communication or externally visible behavior
  changes.

## Existing implementation

### Participating models

- `Order` is the aggregate root. Its status distinguishes an unpaid order from
  a paid order, and its items define the complete inventory requirement.
- `OrderItem` defines a product, positive quantity, and price snapshot. The
  existing uniqueness constraint permits a product at most once per order.
- `LicenseKey` belongs to one product and already has the lifecycle states
  `AVAILABLE`, `RESERVED`, and `SOLD`. Its `sold_at` field records sale, not
  reservation.
- `LicenseAssignment` links one exact key to one exact order item. Its one-to-one
  relationship with `LicenseKey` enforces that a key can be assigned at most
  once. The owning order is reached through the order item.
- `Payment` participates only indirectly. It remains a payment-attempt record
  and does not own reservation state. Phase 1 does not create, update, or
  otherwise integrate payment attempts.

The legacy direct-order `Order.product` and `Order.license_key` fields still
exist. Existing fulfilment normalizes a pre-`OrderItem` direct order lazily and
populates the legacy key field after sale. Reservation ownership and the
temporary reservation record nevertheless remain the item collection and its
assignments; the legacy `Order.license_key` field is not reservation state.

### Participating services

The order domain service currently contains:

- direct-order creation, which creates the order and its single normalized
  order item;
- authoritative-total validation;
- normalization of legacy direct orders into order items for fulfilment;
- provider-neutral payment completion, which serializes on the order and
  payment, selects available keys under row locks, creates assignments, marks
  keys sold, and marks the order and payment paid in one transaction; and
- payment orchestration, which serializes payment activity for an order and
  reuses an active payment attempt.

The current internal fulfilment behavior is the closest existing operation to
Phase 1 reservation: it handles multiple items and quantities atomically, but
it allocates keys only at payment completion and moves them directly from
`AVAILABLE` to `SOLD`. Phase 1 separates provider-neutral reservation and
release from that later successful-payment transition. Existing checkout,
payment-provider, and webhook services are outside the Phase 1 change scope.

### Existing test coverage

`backend/apps/orders/tests/test_order_service.py` already covers:

- assignment of the correct product's key during fulfilment;
- fulfilment of a multi-item, multi-quantity order;
- rollback of all fulfilment when one item has insufficient inventory;
- preservation of order and payment state when no key is available;
- idempotent payment completion without duplicate assignments;
- transaction rollback behavior;
- serialization of concurrent payment activity for the same order; and
- successful and unsuccessful provider outcomes leaving inventory in the
  expected current state.

Related existing coverage includes:

- `backend/apps/orders/tests/test_migrations.py`, which verifies that a key can
  be assigned only once;
- `backend/apps/games/tests/test_license_key_model.py`, which verifies license
  key model constraints;
- `backend/apps/orders/tests/test_order_model.py`, which covers order and item
  model invariants;
- `backend/apps/orders/tests/test_payment_service.py` and
  `test_order_payment_api.py`, which cover active-payment reuse and the current
  checkout/payment boundary; and
- `backend/apps/payments/tests/test_webhooks.py`, which covers current
  fulfilment idempotency and failure-event behavior.

Those tests provide regression context. Phase 1 requires new focused,
provider-neutral domain tests for reservation and release; payment and webhook
tests must not be changed in this phase.

## Domain invariants

After Phase 1, all of the following must hold:

1. Reservation is owned by the order, not by a payment attempt or provider
   checkout.
2. Reservation is all-or-nothing across every item and every unit in the order.
   Partial reservation is not a valid committed state.
3. A complete reservation has exactly as many assignments for each order item
   as that item's quantity.
4. Every assigned key belongs to the product of its assigned order item.
5. Every key in a temporary assignment is `RESERVED`.
6. Every `RESERVED` key held for an order is represented by exactly one
   assignment to exactly one of that order's items.
7. A license key can be assigned at most once and cannot be promised to more
   than one order.
8. Only `AVAILABLE` keys may enter a new reservation.
9. Repeating reservation for an order with a complete, consistent reservation
   reuses that reservation and allocates no additional keys.
10. A missing, partial, over-complete, wrong-product, wrong-state, or otherwise
    inconsistent existing reservation is rejected; it is not silently repaired
    or replaced.
11. An insufficient-inventory failure leaves every involved key and assignment
    unchanged.
12. Release is all-or-nothing for the order's complete temporary reservation.
13. Release affects only the unpaid owning order's `RESERVED` keys and temporary
    assignments.
14. Repeating a completed release is a no-op.
15. A paid order cannot be released.
16. A `SOLD` key cannot become `AVAILABLE` again, and its permanent assignment
    cannot be removed by release.
17. Order reservation and release do not create or transfer inventory
    ownership to a `Payment`.
18. Existing order invariants remain authoritative, including positive item
    quantities, one product occurrence per order, exclusive key assignment,
    and fulfilment only when every required quantity is satisfied.

## Invariants Checklist

- [ ] Every `RESERVED` key belongs to exactly one order.
- [ ] Every `RESERVED` key has exactly one assignment.
- [ ] Every assignment references the correct product.
- [ ] Every order item has exactly its required assignment quantity.
- [ ] Partial reservation cannot exist as committed state.
- [ ] Reservation and release affect the complete order.
- [ ] Payment and provider state never own reserved inventory.
- [ ] `SOLD` inventory never becomes `AVAILABLE`.

## Public operations

### Reserve the complete order inventory

**Purpose**

Establish or reuse the exact set of keys held for all items in one unpaid order,
independently of any payment provider.

**Preconditions**

- The order exists and is not paid.
- The order has a valid, non-empty item collection defining its full inventory
  requirement.
- Each item has a product and positive quantity, as enforced by the existing
  domain model.
- The order is processed under the shared order-level serialization boundary.
- Existing assignments for the order are either absent or form one complete,
  consistent reservation.

**Postconditions**

- If no reservation existed, every item has exactly its required number of
  assignments, every assigned key matches the item's product, and every such
  key is `RESERVED`.
- No selected key remains available to another order.
- If a complete reservation already existed, the same assignments and keys are
  retained with no new allocation.
- No payment or provider state is changed.

**Failure conditions**

- The order is paid.
- The order has no usable item collection.
- Any item lacks enough exclusively available keys.
- Existing reservation state is partial, over-complete, wrong-product,
  duplicated, contains a non-reserved key, or is otherwise inconsistent.
- A concurrent allocation prevents the full order requirement from being
  satisfied.
- Any persistence failure occurs while changing keys or assignments.

Every failure leaves the pre-operation inventory and assignments unchanged.

**Idempotency requirements**

Repeating the operation for a complete, consistent reservation returns or
recognizes that same reservation. It must not select more keys, create more
assignments, or change key state. A malformed existing reservation is a
business failure, not an idempotency case.

### Release the order reservation

**Purpose**

Remove an unpaid order's temporary inventory hold so its keys can be allocated
again.

**Preconditions**

- The order exists and is unpaid.
- Processing uses the same order-level serialization boundary as reservation
  and later payment finalization.
- If a reservation is present, it is complete and consistent: all relevant
  assignments belong to the order's items, match item products and quantities,
  and point to `RESERVED` keys.

Phase 1 exposes this capability for later callers; it does not decide that a
checkout or payment outcome is conclusive enough to invoke it.

**Postconditions**

- Every key in the order's temporary reservation is `AVAILABLE`.
- Only that order's temporary assignments are removed.
- No sold key, permanent assignment, other order, or payment record is changed.
- A later reservation request may select a new complete set of keys.

**Failure conditions**

- The order is paid.
- Any assignment to the order points to a `SOLD` key.
- Present reservation state is partial, over-complete, wrong-product,
  wrong-state, or otherwise inconsistent.
- Any persistence failure occurs during release.

Every failure leaves the complete pre-operation state unchanged.

**Idempotency requirements**

Repeating release after a successful release is a no-op: there are no temporary
assignments to remove and no keys to change. This no-reservation state is valid
for release of an unpaid order, while reservation itself treats a missing
reservation as the normal starting state from which it creates one. Release
must never interpret sold inventory as an already-released reservation.

## State transitions

```text
AVAILABLE
    |
    | complete order reservation commits
    v
RESERVED
    |
    | verified payment success commits (later phase)
    v
SOLD
```

`AVAILABLE` to `RESERVED` is valid only as part of a complete, atomic
order-level reservation. The key must match the assigned item's product and
must be exclusively available when selected. The transition and creation of
its assignment commit together. If any order item cannot be satisfied, none of
the order's keys transition.

`RESERVED` to `SOLD` is valid only for the keys already assigned to the order
when verified payment succeeds. The assignments are retained as permanent
fulfilment records. Defining or changing that successful finalization behavior
belongs to Phase 3, not Phase 1.

```text
RESERVED
    |
    | complete unpaid-order reservation is released
    v
AVAILABLE
```

`RESERVED` to `AVAILABLE` is valid only for a complete temporary reservation
owned by an unpaid order and only when release is invoked after an external
caller has determined that payment can no longer succeed. All of the order's
temporary assignments are removed in the same atomic transition. Phase 1
provides the guarded domain transition but does not wire or classify external
payment outcomes.

There is no valid transition from `SOLD` to `RESERVED` or `AVAILABLE`.

## Concurrency assumptions

- Reservation, release, active-payment establishment in later phases, and
  successful or unsuccessful finalization in later phases must share one
  serialization boundary per order. Competing operations for the same order
  must not observe or commit intermediate aggregate state.
- Different orders may be processed concurrently when they do not contend for
  the same available inventory.
- Different orders competing for keys of the same product may execute
  concurrently, but allocation of each key must be exclusive. Contention may
  cause one order to use different keys or fail for insufficient inventory; it
  must never cause duplicate assignment or a partial reservation.
- Row locking is expected on the order being changed and on candidate or
  already-assigned license-key rows whose lifecycle state will be validated or
  changed. Existing assignments must be read consistently with those locked
  aggregate and key states.
- Database uniqueness of `LicenseAssignment.license_key` remains the final
  structural guard against one key being assigned twice, but concurrency
  correctness must not depend on handling a committed partial result.
- Idempotency is required at both public domain boundaries. Concurrent or
  repeated reservation requests for the same order converge on one complete
  reservation. Concurrent or repeated release requests cannot free other
  inventory, delete permanent assignments, or turn sold keys available.
- Reservation and release each have a single transaction boundary. No caller
  may observe committed key-state changes without their corresponding complete
  assignment changes, or vice versa.
- Phase 1 performs no provider calls, so no external I/O participates in these
  transaction or locking boundaries.

## Risks

- Partial commits could separate key lifecycle state from assignment ownership.
- Provider concerns could become coupled to the reservation domain.
- Reservation ownership could be duplicated across order and payment concepts.
- Existing assignments could be accepted despite inconsistent quantity,
  product, or lifecycle state.
- Transaction boundaries could leak intermediate aggregate state.
- Incorrect serialization or inventory exclusivity could allow competing
  reservations to claim the same key.
- Idempotent retries could be mistaken for permission to repair inconsistent
  state.

## Failure scenarios

### Insufficient inventory

If even one item lacks its full quantity of exclusively available matching
keys, reservation fails. No new assignments remain and no key from any other
item remains reserved.

### Partial existing reservation

If assignment count is below an item's quantity, or some but not all items are
reserved, the state is rejected without repair. Existing state is left intact
for reconciliation.

### Over-complete existing reservation

If an item has more assignments than its quantity, the state is inconsistent
and is rejected without deleting or reallocating anything.

### Product mismatch

If an assigned key belongs to a product other than its order item's product,
reservation and release reject the inconsistent state without mutation.

### Assignment and key-state mismatch

If a temporary assignment points to an `AVAILABLE` or `SOLD` key, or an
existing reservation otherwise mixes lifecycle states, it is rejected.
Release specifically must not treat a sold assignment as temporary.

### Duplicate reservation request

If the existing reservation is complete and consistent, the request succeeds
idempotently by reusing it. No additional keys or assignments are created.

### Concurrent reservation request for the same order

Requests are serialized. The later request observes and reuses the committed
complete reservation, rather than allocating a second set.

### Concurrent demand for the same key

Only one order can reserve a key. The other order must obtain a different
matching available key or fail its whole reservation.

### Missing reservation

For reservation, no existing assignments is the normal initial state and a
complete reservation may be created. For release of an unpaid order, no
temporary assignments is the idempotent already-released state and no mutation
occurs. A mixture of missing and present assignments is a partial reservation
and is rejected.

### Release of a paid order

Release fails without changing keys or assignments, even if the stored
fulfilment state is inconsistent.

### Release containing sold inventory

Release fails atomically. No sold key becomes available and no permanent
assignment is removed.

### Release containing another order's inventory

Release is scoped through the target order's items. It cannot update keys or
remove assignments owned by another order.

### Persistence failure

Any internal failure while reserving or releasing rolls back the entire local
transition. No partial key-state or assignment change is committed, and the
operation can be retried against the unchanged durable state.

### Payment and provider failures

Phase 1 does not interpret payment state or provider outcomes. Later phases
decide when to invoke release. The Phase 1 release operation only enforces the
domain safety rules once invoked.

## Testing strategy

### Unit tests

Provider-neutral service tests should verify the observable business decisions:

- a complete single-item reservation;
- a complete multi-item, multi-quantity reservation;
- exact per-item assignment counts and product matching;
- reuse of a complete reservation without allocating additional keys;
- rejection of paid orders and unusable item collections;
- rejection of partial, over-complete, wrong-product, and mixed-state existing
  reservations;
- complete release of an unpaid reservation;
- repeated release as a no-op; and
- rejection of release for paid orders or sold keys.

Assertions should cover both the returned/raised domain outcome and all
persisted key and assignment state. Provider clients must not participate.

### Integration tests

Database-backed tests should verify the cooperation of the existing constraints,
relationships, transactions, and lifecycle values:

- exact assignment-to-item-to-order ownership;
- one assignment per key;
- selection only from matching `AVAILABLE` inventory;
- isolation between orders during release;
- unchanged `sold_at` semantics during reservation and release;
- no `Payment` creation or mutation; and
- compatibility with both normalized direct orders and cart orders.

Existing payment completion, API, provider, and webhook suites remain regression
coverage but are not redesigned or modified in Phase 1.

### Concurrency tests

Transaction-level tests using independent database connections should cover:

- two simultaneous reservations for the same order converging on one complete
  reservation;
- two different orders competing for exactly the same limited inventory, with
  at most one complete success and no duplicate key assignment;
- two different orders with sufficient separate inventory both succeeding;
- simultaneous reservation and release for the same order producing one valid
  serialized outcome, never a partial state; and
- repeated simultaneous releases remaining scoped and idempotent.

After every race, each order must be either wholly unreserved or wholly and
consistently reserved, and each key must have at most one assignment.

### Rollback tests

Forced failures should be introduced after some in-transaction state changes
but before commit to verify:

- failure on a later item rolls back earlier item reservations;
- assignment creation failure rolls back all key transitions;
- key update failure leaves assignments unchanged;
- release failure after processing some keys restores the complete reservation;
  and
- rejected inconsistent state causes no attempted repair.

Each rollback test should re-read durable database state from a fresh query and
confirm that retry observes the original coherent state.

## Phase Dependencies

Phase 1 provides the provider-neutral reservation and release domain
capabilities used by later phases:

- Phase 2 depends on reservation before checkout integration.
- Phase 3 depends on an existing reservation for successful payment
  finalization.
- Phase 4 depends on release for conclusive unsuccessful payment outcomes.
- Phase 5 depends on both reservation finalization and release when coordinating
  provider events.

This order keeps later payment and provider behavior dependent on established
domain transitions rather than redefining inventory ownership.

## Future Extension Points

Later phases extend the reservation domain by invoking its existing boundaries:

- checkout creation requires a complete reservation;
- payment success finalizes a complete reservation;
- payment failure invokes release only after a conclusive outcome;
- reservation expiration may invoke release under a separately defined policy;
  and
- reconciliation and operational tooling may inspect inconsistent state
  without changing Phase 1 ownership or lifecycle rules.

These extensions add orchestration and policy around reservation and release;
they do not change the Phase 1 aggregate owner, assignment representation,
atomicity, or provider-neutral boundaries.

## Open Questions

No remaining architectural questions for Phase 1.

The reservation duration, provider-versus-local expiration authority,
operational review thresholds, audit retention for released temporary
assignments, and customer-support presentation remain the explicit future
questions in ADR-001. They do not affect the provider-neutral reservation and
guarded release operations delivered in Phase 1 and must not be decided here.

## Success Criteria

- A complete order reservation can exist and be reused idempotently.
- A complete unpaid-order reservation can be released idempotently.
- All reservation, release, ownership, and lifecycle invariants hold.
- Failures and rollbacks leave no partial or inconsistent committed state.
- Checkout, payment, provider, API, email, and webhook behavior remain
  unchanged.

## Glossary

**Reservation:** Temporary ownership by an order of the complete inventory
required before payment.

**Assignment:** The relationship between an order item and one specific license
key.

**Release:** Removal of an unpaid order's complete temporary inventory
ownership.

**Finalization:** Conversion of a complete reservation from `RESERVED`
inventory to `SOLD` inventory after verified payment success.

**Complete reservation:** The exact required quantity of correctly matched,
reserved, and assigned keys for every order item.

**Inconsistent reservation:** Assignment or key state that violates reservation
quantity, ownership, product, or lifecycle invariants.

## Definition of Done

- The implementation conforms to ADR-001 and this Phase 1 design.
- The Phase 1 roadmap acceptance and exit criteria are satisfied.
- Reservation and release invariants, atomicity, rollback, and idempotency are
  verified.
- All relevant tests pass without changes to checkout, payment, API, provider,
  notification, or webhook behavior.
- Architecture, roadmap, design, and implementation documentation remain
  consistent.
- Code review confirms the Phase 1 scope and reviewer checklist.

## Readiness

Phase 1 is ready for implementation.

ADR-001 fixes the aggregate owner, lifecycle states, assignment representation,
atomicity boundary, exclusivity rule, idempotency behavior, release guardrails,
and serialization requirements. The roadmap fixes the Phase 1 scope and
acceptance criteria. The existing models already represent all required
relationships and states, and the existing fulfilment tests provide a baseline
for multi-item atomicity and rollback. The public domain operations, their
valid inputs and outcomes, concurrency expectations, failure behavior, and
test obligations are therefore defined without requiring changes to the ADR or
decisions from later phases.

## Reviewer Checklist

- [ ] Reservation is atomic.
- [ ] Release is atomic.
- [ ] No partial reservation can be committed.
- [ ] Rollback leaves no inconsistent state.
- [ ] Reservation and release idempotency are preserved.
- [ ] Reservation remains owned by the order aggregate.
- [ ] No provider logic is introduced.
- [ ] No webhook logic is introduced.
- [ ] No payment ownership of inventory is introduced.
- [ ] No checkout, payment, API, or notification behavior is changed.
