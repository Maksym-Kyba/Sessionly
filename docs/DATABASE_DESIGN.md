# Proposed Database Design

## Status

The entities, columns, constraints and status names below are **PROPOSED** technical decisions for
review unless marked implemented. They guide implementation without constituting approved product
requirements. Product rules are in `PRODUCT_SPEC.md`. The accounts authentication tables described
below are implemented by the backend's new additive migration; other schemas remain proposals.

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

**Implemented `google_identities`**

- `id` primary key
- `psychologist_id` foreign key to `psychologists.id`
- `google_subject` unique, stable Google account subject
- `email_at_link_time`
- `created_at`, `updated_at`

No password credentials are stored. The backend implementation uses Google's stable `sub` as the
identity key and never links an existing psychologist by matching email. A matching email without
the same linked Google subject requires manual resolution.

**Implemented `auth_sessions`**

- `id`, `psychologist_id` foreign key, unique `session_token_hash`
- `created_at`, `expires_at`, nullable `revoked_at`

The browser receives an opaque random token once in an HttpOnly cookie. Only its SHA-256 hash is
stored. Sessions have a seven-day absolute expiry; concurrent sessions are allowed. Logout
revokes the current row. No Google access or refresh token is stored for sign-in.

**Implemented `oauth_transactions`**

- `id`, unique `state_hash`, `browser_binding_hash`, `nonce_hash`, encrypted `pkce_verifier_encrypted`
- `expires_at`, nullable `consumed_at`, `created_at`

State, nonce, and browser binding are random, short-lived, and one-use. The browser binding is
issued as a short-lived HttpOnly cookie so a valid callback must return in the browser that started
the flow. The PKCE verifier is encrypted at rest with
the configured OAuth state encryption key. Expired transaction rows are removed when a new login
starts. A consumed transaction becomes unusable immediately and is removed on a later cleanup once
expired. The implementation uses PKCE S256 and the `openid email profile` scopes only.

### `notifications` module

**Implemented Phase B `email_verification_tokens`**

- `id` primary key
- `email` (sensitive; redact from logs)
- `psychologist_id` scope for the requested psychologist
- `token_hash` unique; never persist the raw link token
- `expires_at` (30 minutes after issuance), `consumed_at`, `created_at`

A token can be consumed once. The module also owns `booking_verification_grants`, which contain a
verified email and psychologist scope, a unique token hash, 30-minute expiry, and one-use
`consumed_at`. `public_rate_limit_buckets` stores HMAC-derived rate-limit keys and fixed-window
counters without storing client IP addresses. Email requests are limited per email and psychologist;
token consumption also has a global short-window limit. Expired token/grant rows are pruned during
verification requests. No raw link or grant token is stored.

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
public availability read. Refreshes and rule changes lock the psychologist row so concurrent
refreshes reconcile a single desired slot set. Retired or superseded slots are marked
`withdrawn` and retained; slot rows are never deleted by availability operations.

### `booking` module

**Implemented Phase A `bookings`**

- `id`, `availability_slot_id`, `psychologist_id`
- `starts_at`, `ends_at` (`timestamptz`), `session_duration_minutes`, `price_minor`, and `currency`
  copied from the selected slot as booking-owned immutable snapshots
- `status`, `created_at`, `updated_at`, `hold_expires_at`, nullable `confirmed_at`, and nullable
  `payment_reference`
- nullable `client_email`, `client_access_token_hash`, and `client_access_token_expires_at`; Phase A
  internal holds may omit client credentials, while public Phase B bookings set the verified email
  and only the hash of a 90-day opaque client access token

`hold_expires_at` is set by a PostgreSQL default using the same `statement_timestamp()` as
`created_at`, plus exactly 15 minutes. The implemented Phase A statuses are uppercase `HELD`,
`CONFIRMED`, and `EXPIRED`. `HELD -> CONFIRMED` and `HELD -> EXPIRED` are the only transitions in
this phase. A successful confirmation records one unique payment reference. Cancellation and
completion states are deferred.

**Implemented Phase B `booking_idempotency_keys`** stores a SHA-256 hash of the client idempotency
key, a slot request fingerprint, a hash of the one-time verification grant, a nullable booking
foreign key populated in the same transaction, and the creation timestamp. Raw idempotency, grant,
and client access tokens are never stored. A replay with the same unexpired grant returns the
booking/deadline without an access token. A replay with a fresh grant must match the booking email
and psychologist, then rotates and returns a new access token.

### `payments` module

**Implemented `payments`** (migration `20261118_0006`, Payments Phase 2). One row is one payment
attempt for a booking.

- `id` (UUID primary key), `booking_id` (foreign key to `bookings.id`, `ON DELETE RESTRICT`)
- `idempotency_key_hash` — SHA-256 of the client's `Idempotency-Key`; the raw key is not stored
- `request_hash` — SHA-256 of the booking, provider and simulated result; a reused key with a
  different request is a conflict
- `provider` (`mock`), nullable `provider_reference` (set once the gateway answers)
- `amount_minor`, `currency` — copied from the booking snapshot, never from the client
- `status` — `pending`, `succeeded`, `failed` or `manual_review`
- `booking_decision` — nullable booking confirmation outcome (`CONFIRMED`, `ALREADY_CONFIRMED`,
  `EXPIRED`, `NOT_CONFIRMABLE`), kept so that manual review can see why a payment was not accepted
- `created_at`, `updated_at` (`timestamptz`, database clock)

Constraints:

- Unique `idempotency_key_hash` and unique `provider_reference`.
- Partial unique indexes: at most one `pending` and at most one `succeeded` payment per booking.
- `amount_minor > 0` and `currency = 'UAH'` (temporary MVP assumptions, matching the gateway).
- `succeeded` requires a provider reference and a `CONFIRMED` or `ALREADY_CONFIRMED` decision, so a
  successful charge alone can never be recorded as an accepted booking payment.
- `manual_review` requires a provider reference; `pending` and `failed` rows carry no decision.

No client email, credentials, card data or provider payloads are stored.

**Downgrade warning.** Downgrading below migration `20261118_0006` drops the `payments` table and
permanently deletes payment history, including `manual_review` records that may be needed to
decide manual refunds. Do not run `alembic downgrade` past this revision in production except as
a deliberate, approved operation after a database backup.

**PROPOSED `payment_events`** (not implemented): `id`, `payment_id`, `provider`, nullable
`provider_event_id`, `event_type`, a received timestamp and minimal redacted metadata, with unique
`(provider, provider_event_id)` for webhook idempotency once an external provider exists.

Do not store banking credentials or full sensitive provider payloads without an approved need.

## Candidate statuses

### Booking

Implemented Phase A states are uppercase `HELD`, `CONFIRMED`, and `EXPIRED`. The implemented
transitions are `HELD -> CONFIRMED` and `HELD -> EXPIRED`. A late payment cannot move an expired
booking to confirmed. Future `COMPLETED` and cancellation states are deferred.

### Availability slot publication

- `published` — available-rule output eligible for public listing, subject to filtering through
  `booking.api` for active holds and confirmed appointments.
- `withdrawn` — no longer offered for new bookings after a rule is retired or changed.

Availability publication state is distinct from reservation and booking lifecycle state. Rule
retirement may withdraw unbooked future slots, but must preserve slot records associated with active
holds or confirmed bookings. It never deletes or changes a confirmed booking.

### Payment

Implemented statuses:

- `pending` — recorded and committed before the gateway is called; awaiting the gateway result.
- `succeeded` — successful charge accepted by booking (`CONFIRMED`, or `ALREADY_CONFIRMED` for the
  same payment reference).
- `failed` — the gateway reports failure; booking is not contacted and a held booking stays held.
- `manual_review` — the charge succeeded but booking returned `EXPIRED` or `NOT_CONFIRMABLE`, or
  booking confirmation raised an error. The booking is never confirmed automatically; an expired
  booking stays `expired`. Mapping both `EXPIRED` and `NOT_CONFIRMABLE` to manual review has been
  agreed with the booking module owner. While a booking has a `manual_review` payment, no new
  payment attempt with another idempotency key is accepted for it. The status is never cleared
  automatically; a resolution workflow is not implemented.

**PROPOSED** statuses (not implemented): `refund_pending` (a manual refund has been decided and is
processed out of band) and `refunded` (manual refund completion recorded).

Only the booking module may transition `HELD` to `CONFIRMED`, and only after its atomic deadline
check accepts the payment as timely. The authority and precedence of provider timestamps versus
Sessionly's verified receipt time are unresolved and require team approval.

**Payment transaction flow (implemented).** A payment attempt uses two transactions:

1. *Claim:* take a payments-owned PostgreSQL advisory lock for the booking, verify the client
   access token through `booking.api.get_client_booking`, then either find the attempt recorded
   for the idempotency key or, for a new key, refuse the attempt if the booking has a
   `manual_review` payment, read the payable snapshot through `booking.api.get_payable_booking`
   and insert a `pending` row. This transaction commits before any charge.
2. *Process:* take the same advisory lock and lock the payment row, call the gateway with the
   payment ID as the gateway idempotency key, store the provider reference, and call
   `booking.api.confirm_held_booking`, which joins the transaction. The payment status and the
   booking transition commit together. A confirmation error inside its savepoint leaves the charge
   recorded as `manual_review`.

The lock order is the payments advisory lock, then the payment row, then booking's own locks
(psychologist, then booking). The foreign key from `payments.booking_id` to `bookings.id` with
`ON DELETE RESTRICT` was approved in the PR #21 review. The advisory-lock approach was approved
for the mock gateway only; a real payment provider requires reviewing this transaction model,
because the charge currently runs while the lock is held.

The `manual_review` check in the claim step is race-safe because `manual_review` is written only
by the process step while it holds the same advisory lock. A concurrent attempt therefore either
waits for that lock and then sees the committed `manual_review` row, or reaches the claim while
the attempt is still `pending` and is rejected by the one-pending-per-booking index.

**Recovery limitation.** If the process stops after the claim commits, the attempt remains
`pending` and blocks other attempts for that booking. A retry with the same idempotency key resumes
it. There is no background reconciliation process yet; a stuck `pending` attempt requires manual
resolution.

## Double-booking and expiry safeguards

The 15-minute expiry, atomic replacement requirement, no-overlap rule and prohibition on automatic
confirmation after expiry are approved business requirements. Mechanisms marked implemented below
are the Phase A technical implementation.

1. Never read availability in Python and then create a hold in a separate operation. Phase A's
   internal service uses `availability.api` to read and lock the selected slot in the same SQLAlchemy
   transaction as the booking insert.
2. `created_at` and `hold_expires_at` use the PostgreSQL statement timestamp. The latter is exactly
   15 minutes after the former, without relying on the application host clock.
3. Hold creation locks rows in the order **psychologist → availability slot → booking rows**. The
   availability module already locks the psychologist before changing rules and reconciling slots;
   payment confirmation must follow psychologist → booking row. This shared psychologist lock
   serializes availability changes, hold creation, expiry, and confirmation for one psychologist
   without introducing a reverse lock order.
4. In one transaction, hold creation transitions stale `HELD` rows for that psychologist where
   `hold_expires_at <= clock_timestamp()` to `EXPIRED`, then inserts the new `HELD` booking. Failure
   rolls the transaction back. Public availability filters active intervals against booking-owned
   data; the database remains authoritative when a hold request is made.
5. **Implemented no-overlap constraint:** the migration installs PostgreSQL's `btree_gist` extension
   and adds a partial GiST exclusion constraint on the booking table:

   ```sql
   CREATE EXTENSION IF NOT EXISTS btree_gist;

   ALTER TABLE bookings
     ADD CONSTRAINT ex_bookings_no_overlapping_active_appointments
     EXCLUDE USING gist (
       psychologist_id WITH =,
       tstzrange(starts_at, ends_at, '[)') WITH &&
     ) WHERE (status IN ('HELD', 'CONFIRMED'));
   ```

   The half-open range allows back-to-back appointments. The exclusion constraint rejects overlaps
   across distinct slot rows as well as exact duplicates, including concurrent inserts. PostgreSQL
   range exclusion constraints support non-overlap, and `btree_gist` supplies GiST equality support
   for UUID psychologist IDs. The constraint creates its GiST index. The exact table owner and
   transaction/session arrangement must preserve module boundaries.
6. A separate unique slot identity constraint prevents duplicate generated slots, but it is not
   a substitute for the range exclusion constraint. A B-tree index on
   `(psychologist_id, hold_expires_at)` with predicate `status = 'HELD'` finds expiration candidates.
   Do not use `now()` or
   `clock_timestamp()` in a partial-index predicate: expired rows leave the active exclusion set
   through an explicit status transition.
7. On exclusion violation or an unavailable/withdrawn slot result, roll back and return a conflict
   response. Make client retries idempotent with a unique idempotency key or equivalent operation
   identity.
8. Internal `booking.api.get_payable_booking` returns only a live hold and its snapshotted amount and
   currency. `booking.api.confirm_held_booking` locks the psychologist and booking row, then checks
   the hold against `clock_timestamp()` within the transaction. It returns `CONFIRMED` only for a
   successful result while the hold is active, `ALREADY_CONFIRMED` only for the same previously
   recorded payment reference, `EXPIRED` for an expired hold, and `NOT_CONFIRMABLE` otherwise. It
   never accepts caller-provided amount or currency. Payment recording and late-payment review remain
   the Payments Module's responsibility.
9. Availability owns and reconciles its slot rows without calling the Booking Module. A slot may be
   withdrawn or updated when its rule changes, but the foreign key prevents deletion while a
   booking references it. The booking's copied interval, duration, price and currency are unchanged.
   The public availability route composes `availability.service` with `booking.api` to filter active
   overlapping intervals; neither service imports the other module's implementation.

## Index and integrity proposals

- Unique `google_subject`.
- Unique slot identity per psychologist and start/end interval, to prevent duplicate generated
  slot records only.
- **Implemented:** partial GiST exclusion constraint for active (`HELD`, `CONFIRMED`) appointment
  ranges, as shown above; it prevents overlapping intervals per psychologist, not just identical
  timestamps.
- **Implemented:** B-tree index on `hold_expires_at` with `WHERE status = 'HELD'` for expiry lookup.
  The status transition removes an expired hold from the exclusion constraint; time-dependent
  predicates are not used in indexes.
- A late-payment booking in `EXPIRED` does not reclaim or block the interval automatically.
- Unique verification-token hash.
- Unique provider event identity where supplied.
- Availability slots are indexed by `(psychologist_id, starts_at)`; Booking uses the partial
  `(psychologist_id, hold_expires_at)` expiry index and `(psychologist_id, status, starts_at)` query
  index. These indexes support the current Phase A queries; add others only when measured access
  patterns require them.
- Foreign keys should use explicit delete behavior; cascade policy is not yet decided.

## Proposed concurrency test scenarios

These PostgreSQL scenarios are covered by the Booking Phase A test suite.

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

- Which payment timestamp is authoritative at the expiry boundary (provider confirmation time or
  Sessionly's verified receipt time)? This remains unresolved until the team approves the policy.
- Whether manual cancellation/refund outcomes are recorded in the application and who can write them.
- Whether the implemented 90-day client access-token lifetime should be changed after frontend
  review.
- Session duration limits beyond the current availability-window check.
- Whether currencies beyond the initial `UAH` support should be enabled.
- Client verification-token retention policy.
