# Proposed API Contract

## Status

All routes, payloads, status codes and examples in this document are **PROPOSED**. They are
concrete review material for implementation planning, not approved API requirements. Product
rules in `PRODUCT_SPEC.md` remain authoritative.

Base path proposal: `/api/v1`. JSON is used unless a route redirects to an OAuth provider. Times
are RFC 3339 timestamps in UTC. IDs are opaque strings in examples.

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

## Availability

- `GET /api/v1/psychologists/{psychologist_id}/availability?from=...&to=...` — public list of
  bookable slots and display information.
- `PUT /api/v1/accounts/me/availability-rules/{rule_id}` — psychologist manages an availability
  rule (authenticated).
- `POST /api/v1/accounts/me/availability-rules` — psychologist creates an availability rule.

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

- `POST /api/v1/bookings` — atomically claim an available slot and create a 15-minute hold.
- `GET /api/v1/bookings/{booking_id}` — retrieve booking/payment progress using an unguessable
  client access token or authenticated psychologist session.
- `GET /api/v1/accounts/me/bookings` — list bookings for the authenticated psychologist.

Create request:

```json
{
  "slot_id": "slot_456",
  "booking_verification_token": "short-lived-booking-token",
  "idempotency_key": "client-generated-unique-value"
}
```

Success response:

```json
{
  "id": "book_789",
  "status": "held",
  "slot_id": "slot_456",
  "held_until": "2026-11-15T12:15:00Z",
  "payment": {
    "status": "pending",
    "mode": "mock",
    "action_url": "/api/v1/bookings/book_789/payments/mock"
  }
}
```

A competing claim should receive `409 slot_unavailable`. A successful response must not promise
that a later payment will confirm after `held_until`.

## Payments

- `POST /api/v1/bookings/{booking_id}/payments/mock` — **development only**, simulate a payment
  result without banking credentials. Proposed production behavior returns `404` or is absent.
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

Late payment response example:

```json
{
  "booking_id": "book_789",
  "payment_status": "manual_review",
  "booking_status": "manual_review",
  "message": "Payment received after the booking hold expired. The booking is not confirmed."
}
```

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

## Open contract decisions

- OAuth session mechanism, cookie policy, callback and account-linking behavior.
- Email-link token lifetime, scanner-safe consumption, delivery and rate limiting.
- Client access to booking status without creating a client account.
- Currency/amount representation and availability-rule payloads.
- Production payment provider, webhook authentication and payment/refund lifecycle.
- Whether late-payment review is exposed to clients, psychologists, or both.
