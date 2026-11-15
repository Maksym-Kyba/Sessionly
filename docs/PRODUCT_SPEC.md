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
- A selected slot is held for 15 minutes while payment is completed.
- Slot claiming must prevent double booking.

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

- The documented target is one AWS EC2 instance running Docker Compose, Caddy for HTTPS and
  Terraform configuration in `infra/`.
- This work preserves that target. The team should confirm that it remains the MVP deployment
  target; no replacement architecture is proposed here.

## Scope

### Required for the first version

- Psychologist Google OAuth sign-in and profile.
- Availability, session duration and price.
- One-time client email verification link.
- Fifteen-minute booking hold and double-booking protection.
- Development mock payment flow and safe handling of payments confirmed after hold expiry.
- Psychologist appointment dashboard.
- HTTPS deployment, subject to confirmation of the existing AWS deployment target.

### Planned or conditional

- Google Calendar synchronisation and AI scheduling assistant are listed as desired follow-up
  features in the current project instructions.
- Statistics and design improvements are lower priority.

### Not automated in the first version

- Client accounts.
- Cancellation or rescheduling workflows inside Sessionly; clients contact the psychologist.
- Automatic refunds.

## Technical proposals

These proposals are not product requirements and need technical review:

- **PROPOSED:** model Google OAuth identity separately from psychologist profile data.
- **PROPOSED:** deliver verification links with random, single-use, expiring tokens; store only a
  token hash and consume it once. Delivery provider and token lifetime remain undecided.
- **PROPOSED:** treat a late successful payment as a review case; leave the booking unconfirmed,
  prevent automatic reassignment of that payment, and record any manual outcome for auditability.
- **PROPOSED:** isolate payment-provider-specific behavior behind a payment gateway interface;
  use a local mock implementation during development.
- **PROPOSED:** keep table ownership within the existing modular-monolith boundaries and expose
  cross-module operations only through each module's `api.py`.

See `API_CONTRACT.md` and `DATABASE_DESIGN.md` for more concrete proposals.

## Unresolved questions

- Which production payment provider, settlement flow and webhook security model will be used?
- What happens operationally when a late payment is under review, including response time and
  client communication?
- Which email delivery provider will send verification links? What token lifetime and resend
  limits are appropriate? How should email link scanners be handled?
- What are the Google OAuth callback URLs, account-linking rules and application session mechanism?
- Are there exceptions to refund eligibility, and how will psychologists record and execute manual
  refunds?
- What direct-contact information will be shown to clients?
- How often should Google Calendar synchronisation run?
- Does the team confirm AWS EC2, Docker Compose, Caddy and Terraform as the MVP deployment target?
