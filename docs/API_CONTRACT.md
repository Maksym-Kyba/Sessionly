# Proposed API Contract

## Status

Routes and payloads in this document are **PROPOSED** unless a section says they are implemented.
The psychologist OAuth/session endpoints, public profile, availability, and Booking Phase A and B
flows are implemented on the backend branch. Payment routes in this document remain proposals and
are not implemented. Product rules in `PRODUCT_SPEC.md` remain authoritative.

Base path proposal: `/api/v1`. JSON is used unless a route redirects to an OAuth provider. Times
are RFC 3339 timestamps in UTC. IDs are opaque strings in examples.

The approved MVP scope includes Google Calendar synchronisation and the AI scheduling assistant;
they may be implemented in later MVP milestones. This contract currently focuses on identity,
booking and payment endpoints. Their detailed endpoints remain **PROPOSED** and are not specified
here.

## Identity and verification

### Psychologist Google OAuth

- `GET /api/v1/auth/google/start` — redirect to Google consent with a CSRF-protected `state`.
- `GET /api/v1/auth/google/callback?code=...&state=...` — exchange the authorization result,
  create or locate the psychologist identity, then establish an application session.
- `POST /api/v1/auth/logout` — invalidate the current psychologist session.
- `GET /api/v1/accounts/me` — return the authenticated psychologist profile.

**Implemented callback/session behavior:** set a secure, HttpOnly session cookie and redirect to
the configured, allowlisted frontend URL. The implementation uses an opaque server-side session token
whose SHA-256 hash is stored in the database, with a seven-day absolute expiry. Multiple sessions
are allowed. OAuth state and nonce are one-use, PKCE uses S256, and the Google ID token is verified
server-side. OAuth state is also bound to a short-lived HttpOnly browser cookie; callbacks that
arrive from a different browser are rejected. Existing accounts are never linked by email; a
matching email without a linked Google subject returns a generic `account_unavailable` callback
result. No password or alternate psychologist login endpoint is proposed.

`GET /api/v1/accounts/me` returns the psychologist profile and a session-bound `csrf_token`. Cookie
authenticated POST/PUT/DELETE requests, including logout and availability changes, must send that
value in `X-CSRF-Token` and an allowed `Origin`. The session cookie is HttpOnly; local HTTP uses
`SameSite=Lax` with `Secure=false`, while HTTPS deployments use `Secure=true`. The default
production cookie name uses the `__Host-` prefix, `Path=/`, and no `Domain` attribute. If frontend
and backend are cross-site in production, the deployment must explicitly use `SameSite=None` and
HTTPS; this requires frontend confirmation.

### Client email verification

- `POST /api/v1/email-verifications` — request a one-time link. Return the same generic `202`
  response for a known or unknown psychologist and for rate-limited requests.
- `POST /api/v1/email-verifications/consume` — consume the token extracted by the frontend from
  the emailed link and return a one-time, 30-minute booking verification grant.

Request example:

```json
{
  "email": "client@example.test",
  "psychologist_public_id": "psych_123"
}
```

Generic response example:

```json
{
  "status": "accepted"
}
```

Consume request and response examples:

```json
{
  "token": "one-time-link-token"
}
```

```json
{
  "status": "verified",
  "booking_verification_token": "short-lived-booking-token",
  "expires_at": "2026-11-15T12:30:00Z"
}
```

Implemented behavior: verification links and booking verification grants expire after 30 minutes.
Tokens are generated with 256 bits of randomness, only SHA-256 hashes are stored, and each link and
grant can be consumed once. The link token is placed in the URL fragment (`#token=...`) so browsers
do not send it to frontend servers or include it in HTTP request logs. The frontend extracts the
fragment and submits it in the POST body; GET requests never consume tokens. Email requests are
limited to three per email per hour and one hundred per psychologist per hour; link consumption is
limited to 300 requests per minute application-wide. The local development
sender captures links in process memory for tests and does not expose them through an API route.
If delivery is not configured or the sender reports an operational error, the endpoint returns a
generic `503` without persisting the new token. Clients do not receive accounts or persistent
sessions.

## Public psychologist profile

- `GET /api/v1/psychologists/{public_id}` — return the public booking-page profile.

Current response example (values shown as null because profile terms vary or no future slots exist):

```json
{
  "public_id": "psych_123",
  "display_name": "Dr. Example",
  "time_zone": "Europe/Kyiv",
  "session_duration_minutes": null,
  "price_minor": null,
  "currency": null
}
```

`session_duration_minutes`, `price_minor`, and `currency` are returned only when all future
published availability slots share the same values; otherwise all three fields are `null`. This
uses availability data without inventing a profile-wide rate. The frontend should display each
slot's own values when the profile fields are null. Whether the profile response should use this
nullable shape or omit profile-level terms entirely remains a frontend/API contract question.

## Availability

- `GET /api/v1/psychologists/{public_id}/availability?from=...&to=...` — public list of
  bookable slots and display information.
- `GET /api/v1/accounts/me/availability-rules` — list the authenticated psychologist's rules.
- `POST /api/v1/accounts/me/availability-rules` — psychologist creates an availability rule.
- `PUT /api/v1/accounts/me/availability-rules/{rule_id}` — psychologist updates an availability
  rule.
- `DELETE /api/v1/accounts/me/availability-rules/{rule_id}` — retire a rule.

All availability-rule routes require the authenticated psychologist. The delete operation is
**PROPOSED** as a soft retirement: stop generating future slots and withdraw unbooked future slots,
while preserving slot records associated with active holds or confirmed appointments. It must not
cancel, delete or otherwise change confirmed bookings. The behavior for active holds is to preserve
their slot records and let the booking module manage their lifecycle.

**PROPOSED rule request body** (used by both `POST` and full-replacement `PUT`):

```json
{
  "weekday": 0,
  "local_start": "09:00:00",
  "local_end": "12:00:00",
  "session_duration_minutes": 50,
  "price_minor": 120000,
  "currency": "UAH",
  "valid_from": "2026-11-16",
  "valid_until": null
}
```

`weekday` is **PROPOSED** as Monday `0` through Sunday `6`; rule times are local wall-clock times
in the psychologist profile's IANA time zone. Rules generate materialized slots for the next 30
local calendar days. Price is represented in integer minor units with an ISO 4217 currency code.
**UAH is the only supported currency in this milestone.**
Rule deletion retires the rule and withdraws its future unbooked slots; slot records remain in the
database so later booking records are not removed or changed.

**PROPOSED validation:** a session must fit entirely within its same-day rule interval. Active
rules for the same weekday and intersecting date ranges cannot overlap in local time unless their
weekly schedule, duration and price are identical. Identical rules are deduplicated during slot
materialization; different overlapping rules or slots are rejected with `409`. Overnight rules are
not supported by this proposal because their recurrence weekday/date semantics are unspecified.

**PROPOSED operational detail:** the public availability `GET` refreshes the psychologist's
materialized 30-day slot horizon before returning currently published slots. The refresh is
idempotent and serialized with rule changes.

Response example:

```json
{
  "psychologist_id": "psy_123",
  "time_zone": "Europe/Kyiv",
  "slots": [
    {
      "id": "slot_456",
      "starts_at": "2026-11-20T09:00:00Z",
      "ends_at": "2026-11-20T10:00:00Z",
      "price_minor": 150000,
      "currency": "UAH",
      "state": "available"
    }
  ]
}
```

Whether slot duration, currency and price are represented this way is **PROPOSED**.

## Booking

**Phase A status:** the database model, internal Booking Module API, 15-minute hold and exclusion
constraint are implemented. **Phase B status:** client email verification, public hold creation,
access-token retrieval and booking reads are implemented as described below. Payment processing
remains outside this phase.

The internal `booking.api.create_hold(session, slot_id)` creates a `HELD` reservation with the
selected slot's appointment interval, duration, price, and currency copied as immutable booking
snapshots. It uses the PostgreSQL clock for `created_at` and sets `hold_expires_at` exactly 15
minutes later. A database exclusion constraint prevents overlapping `HELD` or `CONFIRMED` bookings
for the same psychologist; intervals are half-open `[start, end)`, so adjacent appointments are
allowed. Creation first transitions that psychologist's expired holds to `EXPIRED` in the same
transaction.

Public hold creation consumes a valid booking verification grant before calling the internal
`create_hold` operation. The grant is scoped to the psychologist and verified email. Email
verification occurs before hold creation; it never extends or resets a hold. Every hold therefore
gets the full 15 minutes from its own database creation timestamp.

### Public client booking endpoints

`POST /api/v1/bookings` requires `Idempotency-Key` (16–128 characters) and the following body:

```json
{
  "slot_id": "b9e421ae-5b3a-43fc-84ec-c871e63318af",
  "booking_verification_token": "one-time-verified-grant"
}
```

The first successful response is `201 Created` and includes the immutable appointment snapshot,
`HELD` status, `hold_expires_at`, and an opaque `client_access_token`. The access token is returned
only in this response; only its hash is stored. The response uses `Cache-Control: no-store` and
contains no client email. Payment is not implemented in Phase B; the response's
`payment_stage: "awaiting_payment_integration"` indicates that a verified client can proceed to the
payment stage once the Payments Module is integrated. No public payment or confirmation route is
provided here.

Replaying the same idempotency key and slot returns `200 OK` with the same booking and original
deadline and `idempotent_replay: true`. If the replay uses the same still-valid consumed grant, the
response has `client_access_token: null`. If the client supplies a fresh grant, the server verifies
that it belongs to the booking's email and psychologist, then rotates the access token and returns
the new token. A different slot with the same key returns `409`; a grant for another email is
rejected. Raw idempotency keys are not stored. A client that lost the original response can
re-verify the email and replay the same key and slot to recover the booking ID and a new access
token. The server never stores a plaintext token to reconstruct it.

`GET /api/v1/bookings/{booking_id}` returns appointment status and snapshot values to either a
client presenting `Authorization: Bearer <client_access_token>` or the psychologist who owns the
booking and has a valid OAuth session. It never returns the client email or access token. Client
access tokens expire 90 days after issue, can be recovered by re-verifying the email, and only the
latest issued token remains valid. Responses use `Cache-Control: no-store`. A missing, invalid, or
expired client token receives the same `404` booking response.

`POST /api/v1/bookings/{booking_id}/access-token` recovers a lost credential. Its body contains a
fresh one-time `booking_verification_token`; its email and psychologist scope must match the booking.
The endpoint consumes the grant, replaces the stored token hash and returns a new token and expiry.
The previous client access token is immediately invalidated.

`POST /api/v1/bookings` returns `409 slot_unavailable` for an unavailable/withdrawn slot or an
overlap, `409` for an idempotency-key mismatch, and `400` for an invalid or expired verification
grant. Verification-link consumption and recovery reject invalid, expired, consumed, or
out-of-scope tokens with a generic `400`. Public booking and credential responses are not cached.

The internal payment integration API is also defined without implementing payments:

- `booking.api.get_payable_booking(session, booking_id)` returns the amount, currency, and deadline
  only while the booking is still payable; values come from the booking snapshot.
- `booking.api.confirm_held_booking(session, booking_id, payment_result)` returns
  `CONFIRMED`, `ALREADY_CONFIRMED`, `EXPIRED`, or `NOT_CONFIRMABLE`. The same payment reference is
  required for `ALREADY_CONFIRMED`. Confirmation checks the hold against the database clock while
  holding the psychologist and booking locks. It does not accept an amount or currency from the
  caller. Late results leave the booking expired and unconfirmed.

`get_payable_booking` returns a `PayableBooking` value with `booking_id`, `amount_minor`, `currency`,
and `hold_expires_at`. The payment module supplies a `PaymentResult` value containing
`payment_reference` (a stable provider/mock reference, at most 255 characters; nullable for failed
results; surrounding whitespace is trimmed) and `succeeded` (boolean). It must not supply an amount
or currency. Only a verified provider event or trusted development mock may be passed to the internal
confirmation API; an untrusted client request is not evidence of payment. The payable response is a
snapshot, not a promise that the hold will remain active while
the external payment is underway; confirmation always rechecks the deadline. A failed result returns
`NOT_CONFIRMABLE` and leaves a still-live hold unchanged. A late result returns `EXPIRED`; the
Payments Module records that payment for manual review. Reusing a reference already assigned to a
different booking returns `NOT_CONFIRMABLE`. The reference is globally unique in Booking storage.

The payment timestamp authority remains unresolved. For this phase, confirmation is accepted only
if the hold is still active when the booking confirmation transaction performs its database-time
check.

These functions accept the shared SQLAlchemy `Session`. They start and commit a transaction when
called with no active transaction; otherwise they join the caller's transaction. A caller that
passes an active transaction owns its commit or rollback. The lock order is psychologist, then
availability slot, then booking rows for hold creation; confirmation locks psychologist, then the
booking row.

- `POST /api/v1/bookings` — atomically expire applicable stale holds, claim a non-overlapping
  interval, and create a hold that expires exactly 15 minutes after database creation time.
- `GET /api/v1/bookings/{booking_id}` — retrieve booking/payment progress using the client bearer
  token returned by booking creation or an authenticated psychologist session.
- `GET /api/v1/accounts/me/bookings` — list bookings for the authenticated psychologist.

Create request (the `idempotency_key` is sent in the `Idempotency-Key` header):

```json
{
  "slot_id": "b9e421ae-5b3a-43fc-84ec-c871e63318af",
  "booking_verification_token": "one-time-verified-grant"
}
```

Success response (assuming database creation time `2026-11-15T12:00:00Z`):

```json
{
  "id": "6e88d567-aeca-477d-a84b-243401925480",
  "status": "HELD",
  "slot_id": "b9e421ae-5b3a-43fc-84ec-c871e63318af",
  "starts_at": "2026-11-18T12:00:00Z",
  "ends_at": "2026-11-18T12:50:00Z",
  "session_duration_minutes": 50,
  "price_minor": 120000,
  "currency": "UAH",
  "created_at": "2026-11-15T12:00:00Z",
  "hold_expires_at": "2026-11-15T12:15:00Z",
  "client_access_token": "opaque-high-entropy-token-returned-once",
  "client_access_token_expires_at": "2027-02-13T12:00:00Z",
  "idempotent_replay": false,
  "payment_stage": "awaiting_payment_integration"
}
```

These endpoint and lifetime details are technical implementation choices for Phase B. No client
account is created.

A competing request for the same slot or any overlapping time for the same psychologist receives
`409 slot_unavailable`. Adjacent appointments where one ends exactly when the next starts are
allowed under the **PROPOSED** half-open interval convention `[start, end)`. A successful response
must not promise that a payment confirmed after `hold_expires_at` will confirm the booking.

**PROPOSED concurrency contract:** simultaneous requests that overlap cannot both return a held
booking. When a hold reaches its deadline, a new request must be able to expire it and create a
replacement without an intermediate race in which both holds are active or the expired hold blocks
reservations indefinitely.

## Payments

- `POST /api/v1/bookings/{booking_id}/payments/mock` — **development only**, simulate a payment
  result without banking credentials. Proposed production behavior returns `404` or is absent.

Request examples (**PROPOSED**):

```json
{"result": "success"}
```

```json
{"result": "failure"}
```

The `result` field accepts only `success` or `failure`; this endpoint does not accept provider
credentials or personal banking tokens.
- `POST /api/v1/payments/webhooks/{provider}` — future provider callback endpoint; provider name,
  signature scheme and exact payload are unresolved.
- `GET /api/v1/bookings/{booking_id}/payment-status` — return payment and review state.

Mock success example:

```json
{
  "booking_id": "book_789",
  "payment_status": "succeeded",
  "booking_status": "confirmed"
}
```

Late payment response example (**PROPOSED**):

```json
{
  "booking_id": "book_789",
  "payment_status": "manual_review",
  "booking_status": "expired",
  "message": "Payment received after the booking hold expired. The booking is not confirmed."
}
```

The late event does not transition the booking from `expired` to `confirmed`; its payment remains
subject to manual review and may require a refund. Which timestamp establishes that payment
confirmation was before or after expiry remains unresolved pending team approval. Until then, this
contract must not define a provider timestamp as authoritative.

The late-payment result must never automatically confirm a booking, even if the slot appears free
when the payment event is processed. Manual review may conclude that a refund is needed.

## Direct-contact cancellation and rescheduling

No cancellation or rescheduling mutation endpoint is proposed for the first version. Clients
contact the psychologist directly. A client requesting cancellation at least 24 hours before the
session is eligible for a manual refund handled by the psychologist. Exceptions and operational
recordkeeping are unresolved.

## Proposed error envelope

```json
{
  "error": {
    "code": "slot_unavailable",
    "message": "This time slot is no longer available."
  }
}
```

Candidate status codes: `400` invalid input, `401` missing/invalid psychologist session,
`403` forbidden, `404` missing resource, `409` slot conflict or idempotency conflict, `422` invalid
state transition, `429` rate limit, and `5xx` unexpected service failure. These mappings are
**PROPOSED**.

## Proposed concurrency test scenarios

These are test cases to implement later; this document adds no test code.

- Two simultaneous requests for the same slot: exactly one hold succeeds; the other receives
  `409 slot_unavailable`.
- Two simultaneous requests for different, partially overlapping intervals belonging to the same
  psychologist: at most one active hold succeeds.
- Two adjacent intervals for the same psychologist: both holds may succeed because `[start, end)`
  ranges that only touch at an endpoint do not overlap.
- A new request racing with an expired hold and no other overlapping active appointment: the
  expired hold is atomically transitioned out of the active state and one replacement hold succeeds;
  no stale active hold blocks it indefinitely.
- A payment confirmation racing with expiry and a replacement hold: either timely confirmation wins
  and the overlapping replacement conflicts, or expiry/replacement wins and a late payment remains
  under review. The old booking and replacement cannot both become active, and a late payment never
  confirms the expired booking.

## Open contract decisions

- Production email provider and its deployment configuration/credentials mechanism.
- Currency/amount representation beyond the implemented initial UAH availability values.
- Production payment provider, webhook authentication and payment/refund lifecycle.
- Whether late-payment review is exposed to clients, psychologists, or both.
- Whether the current 90-day client access-token lifetime should be changed after frontend review.
- Which payment timestamp is authoritative at hold expiry; this is explicitly unresolved pending
  team approval.
