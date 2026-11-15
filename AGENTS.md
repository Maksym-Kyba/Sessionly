# Repository Guidance for AI Agents

## Working agreement

- Before creating, modifying or deleting files, describe the proposed changes and wait for explicit
  approval. Approval applies only to the work explicitly approved for the active task.
- Write committed repository content in formal, well-structured English.
- Keep the implementation simple. Do not add libraries, services, queues, cloud infrastructure or
  microservices unless the team explicitly approves them.
- Separate approved product requirements, **PROPOSED** technical decisions and unresolved
  questions. Never silently promote a proposal into a requirement.
- Do not commit or push unless separately authorized.

## Approved product requirements

- Psychologists authenticate exclusively through Google OAuth.
- Clients have no accounts and verify email through a one-time link.
- A hold expires exactly 15 minutes after creation. Expiry and replacement must be atomic and
  concurrency-safe; expired holds must not block new reservations indefinitely.
- Overlapping active holds and confirmed appointments for the same psychologist are prohibited.
- Google Calendar integration and the AI scheduling assistant are both within the approved MVP
  scope; they may be implemented in later MVP milestones.
- Mock payments are available for development without personal banking API tokens. The production
  payment provider is not finalized.
- A payment confirmed after hold expiry must never automatically confirm the expired booking. It
  requires manual review and may require a refund.
- The authoritative payment timestamp at the expiry boundary is unresolved until the team approves
  an exact policy.
- Cancellation and rescheduling are arranged through direct contact with the psychologist.
- A cancellation request made at least 24 hours before the session is eligible for a refund,
  handled manually by the psychologist. Unspecified exceptions and operating details remain open.

## Architecture boundaries

- Preserve the modular monolith: one FastAPI application and one PostgreSQL database.
- Modules: `accounts`, `availability`, `booking`, `payments`, `calendar`, `notifications`,
  `assistant`.
- Each module owns its tables. Cross-module operations use only the owning module's `api.py`.
- Within a module, use router → service → repository; routers contain no SQL and repositories contain
  no business decisions.
- Modules communicate with plain function calls; do not add queues or events without approval.
- Booking lifecycle transitions belong to `booking`.
- PostgreSQL overlap-prevention mechanisms and status transitions documented with **PROPOSED** are
  technical proposals, not approved schema requirements.
- Every schema change requires a new Alembic migration; never edit an existing migration.
- When booking logic is implemented, test concurrent same-slot and overlapping-slot attempts,
  adjacent intervals, expiry/replacement races, payment/expiry races, and duplicate payment events.
  Do not add tests or migrations as part of documentation-only work.
- Do not implement business logic, authentication, integrations or migrations until specifically
  requested and approved.

## Deployment and privacy

- Preserve the existing target: one AWS EC2 instance, Docker Compose, Caddy for HTTPS and Terraform
  in `infra/`. Ask the team before changing it or adding AWS services.
- Store timestamps as UTC `timestamptz`; psychologist profiles carry a display time zone.
- Never log client names or email addresses, commit real user data, or commit `.env` files.

See `CLAUDE.md` and `docs/` for the detailed requirements, proposed API/database designs and open
questions.
