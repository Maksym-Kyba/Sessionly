# Proposed API Contract

## Status

All routes, payloads, status codes and examples in this document are **PROPOSED**. They are
concrete review material for implementation planning, not approved API requirements. Product
rules in `PRODUCT_SPEC.md` remain authoritative.

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

**PROPOSED callback outcome:** set a secure, HTTP-only, same-site session cookie and redirect to the
frontend. Token storage/session details and account-linking rules require approval. No password or
alternate psychologist login endpoint is proposed.

### Client email verification

- `POST /api/v1/email-verifications` — request a one-time link. Return the same generic response
  whether or not delivery is possible to avoid disclosing email registration state.
- `POST /api/v1/email-verifications/consume` — consume the token extracted by the frontend from
  the emailed link and return a short-lived booking verification token.

Request example:

```json
{
  "email": "client@example.test",
  "psychologist_id": "psy_123"
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

The verification-token lifetime, email provider, resend limits and scanner-safe link flow are
unresolved. Clients do not receive accounts or persistent sessions.

## Public psychologist profile

- `GET /api/v1/psychologists/{public_id}` — return the public booking-page profile.

Response example (**PROPOSED**):

```json
{
  "public_id": "psych_123",
  "display_name": "Dr. Example",
  "session_duration_minutes": 50,
  "price_minor": 120000,
  "currency": "UAH"
}
```

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

- `POST /api/v1/bookings` — atomically expire applicable stale holds, claim a non-overlapping
  interval, and create a hold that expires exactly 15 minutes after database creation time.
- `GET /api/v1/bookings/{booking_id}` — retrieve booking/payment progress using the client bearer
  token returned by booking creation or an authenticated psychologist session.
- `GET /api/v1/accounts/me/bookings` — list bookings for the authenticated psychologist.

Create request:

```json
{
  "slot_id": "slot_456",
  "booking_verification_token": "short-lived-booking-token",
  "idempotency_key": "client-generated-unique-value"
}
```

Success response (assuming database creation time `2026-11-15T12:00:00Z`):

```json
{
  "id": "book_789",
  "status": "held",
  "slot_id": "slot_456",
  "created_at": "2026-11-15T12:00:00Z",
  "hold_expires_at": "2026-11-15T12:15:00Z",
  "client_access_token": "opaque-high-entropy-token-returned-once",
  "payment": {
    "status": "pending",
    "mode": "mock",
    "action_url": "/api/v1/bookings/book_789/payments/mock"
  }
}
```

The `client_access_token` is a **PROPOSED** opaque, cryptographically random bearer token returned
once over HTTPS. Store only a hash server-side and never log the token. The expiry and renewal policy
for this token remain unresolved. The client sends it as
`Authorization: Bearer <client_access_token>` when retrieving booking status. No client account is
created.

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

- OAuth session mechanism, cookie policy, callback and account-linking behavior.
- Email-link token lifetime, scanner-safe consumption, delivery and rate limiting.
- Client access to booking status without creating a client account.
- Currency/amount representation and availability-rule payloads.
- Production payment provider, webhook authentication and payment/refund lifecycle.
- Whether late-payment review is exposed to clients, psychologists, or both.
- Booking access-token expiry, renewal and revocation policy.
- Which payment timestamp is authoritative at hold expiry; this is explicitly unresolved pending
  team approval.
