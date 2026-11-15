# Proposed Database Design

## Status

The entities, columns, constraints and status names below are **PROPOSED** technical decisions for
review. They guide implementation without constituting approved product requirements. Product
rules are in `PRODUCT_SPEC.md`. No schema or Alembic migration is created by this document.

## Existing architecture constraints

- One PostgreSQL database and one modular-monolith application.
- Each module owns its tables. Other modules interact only through the owner's `api.py`.
- Module layering is router → service → repository.
- Booking lifecycle transitions belong to `booking`; no module may directly write another
  module's tables.
- Schema changes require new Alembic revisions; existing revisions are never edited.

## Candidate entities and ownership

### `accounts` module

**PROPOSED `psychologists`**

- `id` primary key
- `public_id` unique identifier used in public booking URLs
- `display_name`
- `email` (unique where present; do not log)
- `time_zone`
- `created_at`, `updated_at`

**PROPOSED `google_identities`**

- `id` primary key
- `psychologist_id` foreign key to `psychologists.id`
- `google_subject` unique, stable Google account subject
- `email_at_link_time`
- `created_at`

No password credentials are proposed. OAuth tokens/session data are intentionally not specified
until session and refresh-token requirements are decided.

### `notifications` module

**PROPOSED `email_verification_tokens`**

- `id` primary key
- `email` (sensitive; redact from logs)
- `psychologist_id` or booking context, depending on final flow
- `token_hash` unique; never persist the raw link token
- `expires_at`, `consumed_at`, `created_at`

A token can be consumed once. Token lifetime, resend policy, storage retention and email provider
are open questions.

### `availability` module

**PROPOSED `availability_rules`**

- `id`, `psychologist_id`
- weekday/recurrence fields and local start/end times
- `session_duration_minutes`, `price_minor`, `currency`
- `valid_from`, `valid_until`, `created_at`, `updated_at`

**PROPOSED `availability_slots`**

- `id`, `psychologist_id`, optional `availability_rule_id`
- `starts_at`, `ends_at` (`timestamptz`, stored in UTC)
- `price_minor`, `currency`
- `claim_state` (`available`, `held`, `booked`), nullable `held_until`, nullable
  `claimed_by_booking_id`
- `created_at`, `updated_at`

Candidate uniqueness: `(psychologist_id, starts_at, ends_at)` to avoid duplicate generated slots.
Exact recurrence representation and whether slots are materialized are unresolved technical choices.

### `booking` module

**PROPOSED `bookings`**

- `id`, `slot_id`
- `client_email` (sensitive; redact from logs)
- `status`
- `held_until`, `confirmed_at`, `completed_at`, `cancel_requested_at`
- `created_at`, `updated_at`

The booking stores a price/currency snapshot or references an immutable slot price; this choice
needs review. Cancellation/rescheduling is handled out of band, so `cancel_requested_at` is only a
possible manual record, not a required product workflow.

### `payments` module

**PROPOSED `payments`**

- `id`, `booking_id`, `amount_minor`, `currency`
- `mode` (`mock` or future provider), nullable `provider_reference`
- `status`, `received_at`, `reviewed_at`, `created_at`, `updated_at`

**PROPOSED `payment_events`**

- `id`, `payment_id`, `provider`, nullable `provider_event_id`
- `event_type`, received timestamp and minimal redacted/auditable metadata
- Unique `(provider, provider_event_id)` for idempotency where an external provider exists.

Do not store banking credentials or full sensitive provider payloads without an approved need.

## Candidate statuses

All names and exact transitions in this section are **PROPOSED**.

### Booking

- `held` — slot claimed, payment window active.
- `confirmed` — payment was validly confirmed before hold expiry.
- `completed` — session took place.
- `expired` — hold elapsed without a timely successful payment.
- `cancelled` — a psychologist handled cancellation out of band and recorded the result, if the team
  chooses to persist that status.
- `manual_review` — payment arrived after expiry; booking is not confirmed pending human review.

### Availability slot claim

- `available` — no active hold or confirmed booking.
- `held` — tied to one booking until `held_until`.
- `booked` — reserved by a confirmed booking.

Slot-claim state is distinct from the booking lifecycle state. The API/ownership arrangement for
changing it must respect the module boundary and be approved before implementation.

### Payment

- `pending` — created, awaiting result.
- `succeeded` — timely success recorded.
- `failed` — provider/mock reports failure.
- `manual_review` — success arrived after the hold expired; never confirms the booking.
- `refund_pending` — a manual refund has been decided and is being processed out of band.
- `refunded` — manual refund completion recorded.

A direct `succeeded` → `confirmed` action is allowed only for a timely payment through the booking
module. A late event may be financially successful while payment outcome is `manual_review`.

## Double-booking and expiry safeguards

These safeguards are **PROPOSED** implementation constraints to satisfy the approved no-double-booking
and 15-minute-hold requirements:

1. Never read a slot as free in Python and then write a hold in a separate operation.
2. Make the claim atomic in PostgreSQL. **PROPOSED transaction:** create a held booking, then call
   `availability.api.claim_slot(...)`, which performs a conditional `UPDATE` of its slot row where
   `claim_state = 'available'` or `claim_state = 'held' AND held_until <= now()`. Set the new
   `claim_state`, `held_until` and booking reference and return the claimed ID. Roll back the
   booking insert if the update returns no row. A database unique constraint on the slot's active
   booking reference is a second guard.
3. Add the partial unique booking index for active claims described above. Return conflict if the
   atomic slot update affects no row. Expired and cancelled history must not permanently block
   another booking attempt for the same published slot.
4. Use database time for hold expiry and store all instants as `timestamptz` UTC.
5. Make retries idempotent with a client idempotency key or equivalent unique operation identity.
6. Record provider events with a unique event identity to prevent duplicate webhook processing.
7. Process a payment event against the hold expiry and booking state in a transaction. If payment
   confirmation is after expiry, persist `manual_review`; do not run the normal confirmation path,
   even if the slot is currently available. Manual review may result in a refund.
8. Slot-claim updates must go through `availability.api`; no direct cross-module table access.
   The booking service owns booking lifecycle transitions. Sharing the transaction/session across
   these module APIs is a **PROPOSED** implementation detail that must be reviewed before coding.

## Index and integrity proposals

- Unique `google_subject`.
- Unique slot identity per psychologist and start/end interval.
- **PROPOSED:** partial unique index on `bookings.slot_id` for statuses that actively own a
  slot (`held` and `confirmed`). This permits a new booking attempt after expiry/cancellation while
  preventing two active bookings from owning the same slot. `manual_review` does not acquire the
  slot automatically; a late payment must not displace a newer valid hold or booking.
- Unique verification-token hash.
- Unique provider event identity where supplied.
- Index availability by `(psychologist_id, starts_at)` and bookings by `(psychologist_id, status,
  held_until)` through a deliberate ownership/reference design.
- Foreign keys should use explicit delete behavior; cascade policy is not yet decided.

## Open database decisions

- Whether availability slots are materialized and which module owns the atomic claim record.
- How to keep one atomic transaction while respecting module-owned tables and public APIs.
- Whether expired bookings are persisted or derived from `held_until`.
- Whether manual cancellation/refund outcomes are recorded in the application and who can write them.
- Currency scale/allowed currencies, price snapshot policy and session duration constraints.
- OAuth session/refresh-token storage and client verification retention.
- Exact PostgreSQL constraints/indexes after API and workflow review.
