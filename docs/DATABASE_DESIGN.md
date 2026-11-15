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
- Currency is restricted to ISO code `UAH` for the initial implementation; enabling other
  currencies requires a reviewed schema/API change.
- `valid_from`, `valid_until`, `created_at`, `updated_at`

**PROPOSED `availability_slots`**

- `id`, `psychologist_id`, optional `availability_rule_id`
- `starts_at`, `ends_at` (`timestamptz`, stored in UTC)
- `price_minor`, `currency`
- proposed publication state (`published`, `withdrawn`); reservation/hold state is owned by the
  `booking` module and is not stored here
- `created_at`, `updated_at`

Candidate uniqueness: `(psychologist_id, starts_at, ends_at)` to avoid duplicate generated slots.
Slots are materialized for the next 30 days under the current preferred technical direction.
Weekly rules use each psychologist's IANA timezone. DST gap and ambiguity policies must be explicit
before implementation; the exact policy remains unresolved.

**PROPOSED implementation behavior for this milestone, pending team approval:** a local occurrence
that falls in a DST gap is skipped; an ambiguous local time uses `fold=0` (the earlier UTC
occurrence). Slot duration is elapsed minutes in UTC. These rules are covered by tests, but remain
technical proposals until the team confirms the desired product behavior.
If a rule's start or end boundary is nonexistent on a DST transition date, the implementation skips
that entire rule occurrence for that date.

The implementation refreshes the rolling horizon on rule create/update/retirement and before a
public availability read. **PROPOSED:** refresh and rule changes lock the psychologist row so
concurrent refreshes reconcile a single desired slot set. Retired or superseded slots are marked
`withdrawn` and retained; slot rows are never deleted by availability operations.

### `booking` module

**PROPOSED `bookings`**

- `id`, `slot_id`, `psychologist_id`
- `starts_at`, `ends_at` (`timestamptz`, copied from the selected slot for the appointment claim)
- `client_email` (sensitive; redact from logs)
- `access_token_hash` and nullable `access_token_expires_at` (**PROPOSED**; expiry policy
  unresolved)
- `status`
- `created_at`, `updated_at`, `hold_expires_at`, `confirmed_at`, `completed_at`,
  `cancel_requested_at`

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

- `held` — created with `hold_expires_at = created_at + 15 minutes`; the appointment interval is
  reserved until payment succeeds in time or the hold expires.
- `confirmed` — payment confirmation was accepted before `hold_expires_at`.
- `expired` — the deadline passed without timely accepted payment. This state releases the interval
  for a new reservation.
- `completed` — the session took place.
- `cancelled` — a psychologist handled cancellation out of band and recorded the result, if the team
  chooses to persist that status.

**PROPOSED transitions:** `held -> confirmed` only for a timely payment; `held -> expired` at the
15-minute deadline; `confirmed -> completed`; and optionally `confirmed -> cancelled` after an
out-of-band cancellation. An expired booking remains `expired` after a late payment event; that event
sets the payment to `manual_review` and can never confirm the booking. The exact authoritative
payment timestamp is an unresolved policy question, not decided by this proposal.

### Availability slot publication

- `published` — available-rule output eligible for public listing, subject to filtering through
  `booking.api` for active holds and confirmed appointments.
- `withdrawn` — no longer offered for new bookings after a rule is retired or changed.

Availability publication state is distinct from reservation and booking lifecycle state. Rule
retirement may withdraw unbooked future slots, but must preserve slot records associated with active
holds or confirmed bookings. It never deletes or changes a confirmed booking.

### Payment

- `pending` — created, awaiting result.
- `succeeded` — timely success recorded and accepted by the booking module.
- `failed` — provider/mock reports failure.
- `manual_review` — payment confirmation is late or its timing requires review; booking remains
  unconfirmed and, if expired, stays `expired`.
- `refund_pending` — a manual refund has been decided and is being processed out of band.
- `refunded` — manual refund completion recorded.

Only the booking module may transition `held` to `confirmed`, and only after its atomic deadline
check accepts the payment as timely. The authority and precedence of provider timestamps versus
Sessionly's verified receipt time are unresolved and require team approval.

## Double-booking and expiry safeguards

The 15-minute expiry, atomic replacement requirement, no-overlap rule and prohibition on automatic
confirmation after expiry are approved business requirements. The PostgreSQL mechanisms below are
**PROPOSED** technical decisions.

1. Never read availability in Python and then create a hold in a separate operation.
2. **PROPOSED:** set `hold_expires_at` from the database creation timestamp plus exactly 15 minutes.
   Use a database timestamp, not an application host clock.
3. **PROPOSED atomic replacement transaction:** resolve the requested published slot through
   `availability.api`, transition relevant stale `held` bookings with
   `hold_expires_at <= clock_timestamp()` to `expired`, then insert the new `held` booking in one
   transaction. Booking owns all reservation state; changing a booking to `expired` removes its
   interval from the active exclusion constraint. If slot validation, expiration or insertion fails,
   roll back the transaction. This lazy expiry means no background timer is required to make an
   expired hold reclaimable.
4. **PROPOSED no-overlap constraint:** install PostgreSQL's trusted `btree_gist` extension and add
   a partial exclusion constraint on the booking table:

   ```sql
   CREATE EXTENSION IF NOT EXISTS btree_gist;

   ALTER TABLE bookings
     ADD CONSTRAINT no_overlapping_active_appointments
     EXCLUDE USING gist (
       psychologist_id WITH =,
       tstzrange(starts_at, ends_at, '[)') WITH &&
     ) WHERE (status IN ('held', 'confirmed'));
   ```

   The half-open range allows back-to-back appointments. The exclusion constraint rejects overlaps
   across distinct slot rows as well as exact duplicates, including concurrent inserts. PostgreSQL
   range exclusion constraints support non-overlap, and `btree_gist` supplies GiST equality support
   for UUID psychologist IDs. The constraint creates its GiST index. The exact table owner and
   transaction/session arrangement must preserve module boundaries.
5. A separate unique slot identity constraint may prevent duplicate generated slots, but it is not
   a substitute for the range exclusion constraint. Add a B-tree index on `(hold_expires_at)` with
   predicate `status = 'held'` to find expiration candidates. Do not use `now()` or
   `clock_timestamp()` in a partial-index predicate: expired rows leave the active exclusion set
   through an explicit status transition.
6. On exclusion violation or an unavailable/withdrawn slot result, roll back and return a conflict
   response. Make client retries idempotent with a unique idempotency key or equivalent operation
   identity.
7. Serialize payment confirmation and expiry by updating/locking the booking row in a transaction.
   Confirm only when status is still `held` and the approved payment-time comparison is before
   `hold_expires_at`. Otherwise keep the booking `expired` and mark the payment `manual_review`;
   never auto-confirm it even if the interval is free. The timestamp used for that comparison is
   unresolved pending explicit team approval.
8. Slot-claim changes go through `availability.api`; booking lifecycle transitions go through
   `booking`. Any shared transaction/session mechanism across those APIs is **PROPOSED** and must
   preserve table ownership boundaries.

## Index and integrity proposals

- Unique `google_subject`.
- Unique slot identity per psychologist and start/end interval, to prevent duplicate generated
  slot records only.
- **PROPOSED:** partial GiST exclusion constraint for active (`held`, `confirmed`) appointment
  ranges, as shown above; it prevents overlapping intervals per psychologist, not just identical
  timestamps.
- **PROPOSED:** B-tree index on `hold_expires_at` with `WHERE status = 'held'` for expiry lookup.
  The status transition removes an expired hold from the exclusion constraint; time-dependent
  predicates are not used in indexes.
- A late-payment booking in `expired` does not reclaim or block the interval automatically.
- Unique verification-token hash.
- Unique provider event identity where supplied.
- Index availability by `(psychologist_id, starts_at)` and bookings by `(psychologist_id, status,
  hold_expires_at)` through a deliberate ownership/reference design.
- Foreign keys should use explicit delete behavior; cascade policy is not yet decided.

## Proposed concurrency test scenarios

These scenarios should be covered by automated tests when the booking implementation is approved;
this document adds no test code.

1. Two simultaneous holds for the same slot: exactly one succeeds; the other receives a conflict.
2. Two simultaneous holds for different partially overlapping slot intervals for one psychologist:
   at most one remains active, enforced by the exclusion constraint.
3. Two adjacent intervals where the first ends exactly when the second starts: both may be held or
   confirmed because the proposed range is `[start, end)`.
4. A new hold request at/after the 15-minute deadline while the old hold is still marked `held`
   and no other active appointment overlaps: one transaction expires/releases the old hold and
   creates the new one; no stale hold blocks it.
5. Two competing requests attempting to replace an expired hold: only one new active overlapping
   hold succeeds.
6. Payment confirmation racing with expiry and a new overlapping reservation: no two active
   appointments coexist; if the payment is late under the approved timestamp policy, the old booking
   remains expired and is never automatically confirmed.
7. Repeat a payment event: idempotency prevents duplicate state changes or a second confirmation.

## Open database decisions

- Booking-access-token expiry, renewal and revocation policy.
- Which payment timestamp is authoritative at the expiry boundary (provider confirmation time or
  Sessionly's verified receipt time)? This remains unresolved until the team approves the policy.
- How to keep one atomic transaction while respecting module-owned tables and public APIs.
- Whether expired bookings are persisted or derived from `hold_expires_at`.
- Whether manual cancellation/refund outcomes are recorded in the application and who can write them.
- Price snapshot policy and session duration limits beyond the current availability-window check.
- Whether currencies beyond the initial `UAH` support should be enabled.
- OAuth session/refresh-token storage and client verification retention.
- Exact PostgreSQL constraints/indexes after API and workflow review.
