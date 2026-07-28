# ADR-001 Implementation Roadmap

## Goal

Implement the order-owned, all-or-nothing license reservation lifecycle defined
by ADR-001. The work should preserve the existing order, payment, and
fulfilment boundaries while ensuring that a chargeable checkout is never
exposed before the complete order inventory is durably reserved.

The phases below are ordered so that each commit establishes the behavior
required by the next one. Each phase should be reviewed and verified before
work proceeds.

---

## Phase 1 — Reservation Domain

### Purpose

Establish the provider-neutral reservation and release behavior at the order
aggregate boundary. This comes first because checkout, finalization, and
webhook handling must all operate on one consistent reservation lifecycle.

The phase should reserve the complete quantity for every order item, create the
corresponding temporary assignments, reuse an already complete reservation,
and fail without leaving partial state when any item cannot be satisfied.
Release behavior should be available to later phases, but it should not yet be
wired into checkout or provider events.

### Entry criteria

- ADR-001 is accepted as the architectural basis for the work.
- Existing order, assignment, and license lifecycle tests pass.

### Files expected to change

- `backend/apps/orders/services.py`
- `backend/apps/orders/tests/test_order_service.py`

### Acceptance criteria

- A complete multi-item, multi-quantity order reservation is created atomically.
- Every reserved key matches the product of its assigned order item.
- An insufficient item leaves all keys available and creates no assignments.
- Repeating reservation for the same order reuses the complete existing
  reservation without allocating more keys.
- A reservation that is missing, partial, or inconsistent is rejected instead
  of silently repaired into an ambiguous state.
- Release returns only that unpaid order's reserved keys to availability and
  removes only its temporary assignments.
- Sold keys and paid orders cannot be released.

### Exit criteria

- The acceptance criteria are covered by provider-neutral domain tests.
- Reservation and release behavior is independently reviewable without
  checkout or provider-event changes.
- Rollback and idempotency behavior has been verified.

### Reviewer Notes

Pay particular attention to transaction boundaries, concurrent allocation,
all-or-nothing rollback, and reservation and release idempotency.

### Expected commit title

`Add atomic order license reservation`

### Estimated complexity

High

---

## Phase 2 — Checkout Integration

### Purpose

Make a complete durable reservation a prerequisite for creating or returning a
checkout. This follows Phase 1 because provider integration must invoke an
already-defined domain transition rather than own inventory behavior.

Reservation and establishment or reuse of the single active payment must remain
serialized for the order. Provider calls should retain their existing
transaction boundary, and a provider-creation failure must leave neither a
usable checkout nor a stranded reservation.

### Entry criteria

- Phase 1 reservation and release behavior is complete and verified.
- Existing checkout behavior and active-payment reuse are covered by passing
  tests.

### Files expected to change

- `backend/apps/orders/payment_services.py`
- `backend/apps/orders/services.py`
- `backend/apps/orders/tests/test_payment_service.py`
- `backend/apps/orders/tests/test_order_payment_api.py`

### Acceptance criteria

- The full reservation is durable before a checkout can be returned to a
  customer.
- Checkout is not created when any order item lacks sufficient inventory.
- Repeated or concurrent checkout requests reuse the order's reservation and
  do not establish duplicate active payment attempts.
- A pending payment retains the complete reservation.
- Failure to create a provider checkout makes the attempt inactive or removes
  the incomplete attempt, releases the reservation, and exposes no checkout.
- Existing provider calls remain outside database transactions.
- Direct and cart orders follow the same reservation rule.

### Exit criteria

- Both local immediate-payment and asynchronous checkout paths enter
  finalization with a complete reservation.
- Checkout-establishment failures leave no usable checkout or stranded
  reservation.
- The acceptance criteria pass without provider calls being moved inside
  database transactions.

### Reviewer Notes

Pay particular attention to order-level serialization, provider-call
transaction boundaries, active-payment reuse, and cleanup when checkout
establishment fails.

### Expected commit title

`Reserve order licenses before checkout`

### Estimated complexity

High

---

## Phase 3 — Successful Payment Finalization

### Purpose

Convert an existing reservation into permanent fulfilment after verified
payment success. This phase depends on checkout integration guaranteeing that
the assignments and reserved keys already exist; finalization must never search
for replacement inventory.

The order, payment, assignments, and keys should cross their successful
boundary as one serialized and atomic transition. Existing post-commit customer
notification behavior should remain intact.

### Entry criteria

- Phase 2 guarantees a complete reservation before checkout is exposed.
- Success finalization tests can begin from a durable reserved order.

### Files expected to change

- `backend/apps/orders/services.py`
- `backend/apps/orders/tests/test_order_service.py`
- `backend/apps/orders/tests/test_order_payment_api.py`

### Acceptance criteria

- Successful finalization changes every assigned reserved key to sold.
- Existing assignments are retained as the permanent fulfilment record.
- Finalization allocates no new key and creates no replacement assignment.
- The order and successful payment become paid in the same atomic transition.
- The paid amount continues to match the authoritative order total.
- Repeating successful finalization is a no-op and does not send duplicate
  confirmation work.
- Missing, incomplete, or inconsistent reservations fail atomically and remain
  available for reconciliation.

### Exit criteria

- Success cannot produce partial fulfilment for any supported order shape.
- Retry and rollback tests verify atomic, idempotent finalization.
- Existing customer-visible outcomes and post-commit notification behavior are
  preserved.

### Reviewer Notes

Pay particular attention to atomic state transitions, idempotency, rollback
guarantees, and post-commit side effects.

### Expected commit title

`Finalize reserved licenses on payment success`

### Estimated complexity

Medium

---

## Phase 4 — Reservation Release

### Purpose

Connect conclusive unsuccessful payment outcomes to the domain release behavior
from Phase 1. This follows successful finalization so release can be guarded
against undoing a completed sale and can share the same order-level
serialization boundary.

This phase covers conclusive unsuccessful outcomes from synchronous payment
processing. Checkout-establishment cleanup is already owned by Phase 2, and
provider webhook outcomes are intentionally deferred to Phase 5.

### Entry criteria

- Phase 1 provides verified release behavior.
- Phase 3 prevents release from undoing successful finalization.
- Synchronous payment outcomes can be classified as pending or conclusively
  unsuccessful.

### Files expected to change

- `backend/apps/orders/payment_services.py`
- `backend/apps/orders/services.py`
- `backend/apps/orders/tests/test_payment_service.py`
- `backend/apps/orders/tests/test_order_service.py`

### Acceptance criteria

- A conclusively failed synchronous payment releases the entire reservation.
- A pending outcome does not release inventory.
- Release is atomic and idempotent.
- Release never changes sold keys or removes permanent fulfilment assignments.
- After conclusive release, the unpaid order can begin a later attempt with a
  new complete reservation.

### Exit criteria

- Tests distinguish pending outcomes from conclusive synchronous failure.
- Retries cannot observe a mixture of old and new assignments.
- Release behavior is independently reviewable without webhook changes.

### Reviewer Notes

Pay particular attention to terminal-state classification, serialization with
successful finalization, release idempotency, and retry safety.

### Expected commit title

`Release reservations after failed payments`

### Estimated complexity

Medium

---

## Phase 5 — Webhooks

### Purpose

Apply the reservation lifecycle to asynchronous provider outcomes. This phase
comes after both success and release transitions exist, allowing webhook code
to coordinate provider events without duplicating domain behavior.

Supported success, failure, and expiration events should be interpreted against
durable local state. Duplicate delivery and conflicting event order must retain
the ADR's rule that verified success takes precedence over release.

### Entry criteria

- Phases 3 and 4 provide verified success and release transitions.
- Supported provider events and their terminal or non-terminal meaning are
  documented by existing integration behavior.

### Files expected to change

- `backend/apps/payments/webhooks.py`
- `backend/apps/payments/tests/test_webhooks.py`

### Acceptance criteria

- Verified successful events finalize the existing reservation.
- Failed and expired events release the reservation only when the checkout can
  no longer succeed.
- Pending or unpaid non-terminal events retain the reservation.
- Duplicate events are idempotent at both event and domain levels.
- A late failure or expiration cannot undo a completed sale.
- Conflicting terminal events are serialized for the order, with verified
  success taking precedence.
- Invalid or unrelated events cannot affect reservations.

### Exit criteria

- Every supported event type is covered by focused webhook tests.
- Duplicate delivery and both orders of conflicting terminal events are
  verified.
- Webhook coordination remains independently reviewable from the domain
  transitions introduced in earlier phases.

### Reviewer Notes

Pay particular attention to event verification, idempotency, event ordering,
locking behavior, and the precedence of verified success.

### Expected commit title

`Handle reservation outcomes from payment webhooks`

### Estimated complexity

High

---

## Phase 6 — Tests

### Purpose

Complete the cross-cutting regression and concurrency coverage after all
integration paths share the reservation lifecycle. Focused tests belong with
the earlier commits; this final phase adds scenarios that span multiple
boundaries or require the complete implementation.

This phase is last because meaningful end-to-end and race-condition assertions
depend on checkout, success, release, and webhook behavior all being present.

### Entry criteria

- Phases 1–5 are complete, independently tested, and reviewed.
- All integration paths use the shared reservation lifecycle.

### Files expected to change

- `backend/apps/orders/tests/test_order_service.py`
- `backend/apps/orders/tests/test_payment_service.py`
- `backend/apps/orders/tests/test_order_payment_api.py`
- `backend/apps/payments/tests/test_webhooks.py`

### Acceptance criteria

- End-to-end coverage includes direct and cart orders, multiple products, and
  quantities greater than one.
- Concurrency coverage proves that competing orders cannot reserve the same key.
- Concurrent requests for one order produce one reservation and at most one
  active payment attempt.
- Rollback coverage proves that no partial reservation, sale, or release is
  committed.
- Retry coverage proves reservation, success, and release idempotency.
- Out-of-order webhook coverage proves that successful payment cannot be undone.
- The complete existing test suite passes without changing unrelated behavior.

### Exit criteria

- The cross-cutting acceptance criteria are covered without duplicating focused
  tests from earlier phases.
- The full backend test suite passes using the same database engine used for
  transaction and locking behavior in production.
- The complete ADR-001 implementation is ready for final review.

### Reviewer Notes

Pay particular attention to race coverage, rollback assertions, realistic
database behavior, and whether failures would expose partial state.

### Expected commit title

`Add reservation lifecycle regression coverage`

### Estimated complexity

High

---

## Deferred Architectural Decisions

The following architectural safeguards are intentionally postponed because
they are not prerequisites for the first implementation of ADR-001:

- add a database partial unique constraint enforcing at most one active payment
  per order;
- add database constraints for further `LicenseKey` lifecycle consistency,
  including relationships between status and lifecycle timestamps;
- add database-level consistency protections where assignment state and key
  state can be expressed safely without coupling inventory ownership to a
  payment attempt.

Each deferred decision should be proposed and reviewed separately before
implementation.

## Future Improvements

The following operational and engineering improvements can follow the initial
ADR-001 implementation:

- add reconciliation tooling and reporting for reservations that remain
  pending beyond the expected checkout window;
- add operational dashboards for reservation age, inventory state, and payment
  outcomes; and
- add richer audit retention for released temporary assignments if business or
  compliance requirements call for it.

These improvements should be proposed, reviewed, and committed separately.
They must preserve the ownership and lifecycle decisions in ADR-001.

## Completion Checklist

- [ ] Phase 1 completed
- [ ] Phase 2 completed
- [ ] Phase 3 completed
- [ ] Phase 4 completed
- [ ] Phase 5 completed
- [ ] Phase 6 completed

- [ ] ADR-001 fully implemented
