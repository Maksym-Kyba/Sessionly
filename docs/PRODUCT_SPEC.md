# Sessionly Product Specification

## Status and terminology

This document separates approved product requirements from technical proposals and unresolved
questions. **PROPOSED** means a technical detail intended to guide review and implementation; it is
not an approved product requirement.

## Product

Sessionly helps independent psychologists publish availability and manage paid appointments.
Clients book through a psychologist's booking page without creating Sessionly accounts.

## Approved product requirements

### Users and identity

- Psychologists authenticate exclusively through Google OAuth.
- Clients do not have accounts.
- Before booking, a client verifies their email through a one-time verification link.

### Availability and booking

- Psychologists publish available hours, session length and price.
- A booking hold expires exactly 15 minutes after it is created.
- Expired holds must not block a new reservation indefinitely.
- Hold expiration and creation of a replacement hold must be concurrency-safe and atomic.
- The same psychologist must not have overlapping active holds or confirmed appointments.

### Payments

- Mock payments are supported for development and do not require personal banking API tokens.
- The production payment provider is not finalized.
- A payment confirmed after the 15-minute hold expires must never automatically confirm the
  booking.
- A late payment requires manual review and may require a refund.

### Cancellation and rescheduling

- Clients arrange cancellation and rescheduling by contacting the psychologist directly.
- A client who requests cancellation at least 24 hours before the scheduled session is eligible
  for a refund.
- The psychologist handles eligible refunds manually.
- Exceptions and operational details are unresolved and must not be inferred.

### Privacy and time

- Client personal data is sensitive and must not appear in logs.
- Timestamps are stored in UTC; each psychologist has a time zone for display and scheduling.

### Deployment constraint already present in project instructions

- The production target is one AWS EC2 instance running Docker Compose, Caddy for HTTPS and
  Terraform configuration under `infra/`.
- This review preserves that target and does not propose replacement infrastructure.

## Scope

### MVP scope: first milestone

- Psychologist Google OAuth sign-in and profile.
- Availability, session duration and price.
- One-time client email verification link.
- Fifteen-minute booking hold, atomic expiry/replacement, and protection against overlapping
  active holds or confirmed appointments.
- Development mock payment flow and safe handling of payments confirmed after hold expiry.
- Psychologist appointment dashboard.
- HTTPS deployment to the documented AWS target: one EC2 instance, Docker Compose, Caddy and
  Terraform under `infra/`.

### MVP scope: later development milestones

These are approved MVP features even if implemented after the first milestone:

- Google Calendar synchronisation.
- AI scheduling assistant.

Statistics and design improvements remain lower priority as recorded in the existing project
instructions.

### Not automated in the first version

- Client accounts.
- Cancellation or rescheduling workflows inside Sessionly; clients contact the psychologist.
- Automatic refunds.

## Technical proposals

These proposals are not product requirements and need technical review:

- **PROPOSED:** model Google OAuth identity separately from psychologist profile data.
- **PROPOSED:** deliver verification links with random, single-use, expiring tokens; store only a
  token hash and consume it once. Delivery provider and token lifetime remain undecided.
- **Implemented in Booking Phase B:** client email links and booking-verification grants are
  single-use, hash-only credentials with a 30-minute lifetime. Email verification requests are
  rate-limited; booking holds begin only after verification and are not extended by it.
- **Implemented in Booking Phase B:** client booking access uses an opaque token stored as a hash,
  with a 90-day expiry and email re-verification for recovery. Reissuing a token invalidates the
  previous token.
- **Implemented in Booking Phase A:** store `hold_expires_at` as the PostgreSQL statement creation
  time plus 15 minutes; atomically expire stale holds and create a replacement in one transaction.
- **Implemented in Booking Phase A:** use a PostgreSQL GiST exclusion constraint over psychologist
  ID and a half-open appointment time range for `HELD` and `CONFIRMED` bookings. `btree_gist`
  combines psychologist equality with range overlap; details are in `DATABASE_DESIGN.md`.
- **PROPOSED:** treat a late successful payment as a payment review case; leave the booking expired
  and unconfirmed, prevent automatic reassignment of that payment, and record any manual outcome
  for auditability.
- **PROPOSED:** isolate payment-provider-specific behavior behind a payment gateway interface;
  use a local mock implementation during development.
- **PROPOSED:** keep table ownership within the existing modular-monolith boundaries and expose
  cross-module operations only through each module's `api.py`.

See `API_CONTRACT.md` and `DATABASE_DESIGN.md` for more concrete proposals.

## Unresolved questions

- Which production payment provider, settlement flow and webhook security model will be used?
- What happens operationally when a late payment is under review, including response time and
  client communication?
- Which production email delivery provider will send verification links? The local development
  sender captures links in process memory; production delivery requires a configured provider
  adapter. The implemented link/grant lifetime, resend limits and fragment-based scanner-safe flow
  are technical choices and can be revised after team review.
- What Google OAuth client and registered callback URLs will be used in each environment? Existing
  legacy psychologist rows without a linked Google subject require explicit manual resolution;
  they are never linked automatically by email.
- Are there exceptions to refund eligibility, and how will psychologists record and execute manual
  refunds?
- What direct-contact information will be shown to clients?
- How often should Google Calendar synchronisation run?
- Which payment timestamp is authoritative at the hold-expiration boundary (for example, provider
  confirmation time or the time Sessionly receives and verifies the event)? This remains unresolved
  until the team approves an exact policy.
