# CLAUDE.md

Guidance for AI coding assistants working in this repository.

## Working Agreement

- **Ask before any file change.** Before creating, modifying or deleting a file, describe the
  proposed change and its rationale, then wait for explicit approval. Approval applies only to
  the changes explicitly approved for the current task.
- **Repository language.** Everything committed to the repository (code, comments,
  documentation, commit messages) must be in formal, well-structured English.
- **Keep it simple.** Do not introduce new services, libraries, message queues, cloud
  infrastructure or microservices unless explicitly requested. Deployment uses a single EC2
  instance; do not add other AWS services without asking.
- **Do not invent requirements.** Distinguish approved product requirements from proposed
  technical decisions and unresolved questions. Do not turn a proposal into an implementation
  requirement without approval.

## Project Overview

Sessionly is a web platform where psychologists publish available time slots and clients book
sessions online. It is a team project for the Object-Oriented Analysis and Design course at the
Ukrainian Catholic University.

- **Psychologist:** signs in exclusively through Google OAuth, sets up a profile, publishes
  availability, and views appointments in a dashboard.
- **Client:** has no account. The client verifies their email using a one-time verification link,
  selects a slot held for 15 minutes, and pays. Successful payment received within the hold may
  confirm the booking automatically after server-side verification.
- **Late payment:** a payment confirmed after the 15-minute hold expires must never automatically
  confirm the booking. It requires manual review and may require a manual refund.
- **Cancellation and rescheduling:** clients contact the psychologist directly. A client who
  requests cancellation at least 24 hours before the scheduled session is eligible for a refund;
  the psychologist handles refunds manually.

## Course Requirements

The prototype is demonstrated on 19 November 2026. Graded criteria:

- The repository has the top-level parts `backend/`, `frontend/`, `infra/` and a `README.md`
  that tells a stranger what the product is and how to run and deploy it.
- The prototype is deployed, reachable over HTTPS, and psychologists can sign in with Google
  OAuth.
- A report with user feedback: who tried it, how many people, what they said, and what was
  changed as a result.

### First Version Scope

- **P0 (first MVP milestone):** psychologist Google OAuth sign-in; available hours with session
  length and price; client email verification by one-time link; 15-minute slot hold with atomic
  expiry/replacement and no overlapping active holds or confirmed appointments; development mock
  payments and safe handling of payments confirmed after hold expiry; psychologist dashboard;
  deployment to AWS over HTTPS.
- **P1 (later MVP milestone):** Google Calendar synchronisation and AI scheduling assistant.
  Both remain within the approved MVP scope and are not post-MVP features.
- **P2 (if time permits):** statistics and design improvements.
- **Out of scope for automated application flows:** cancellation and rescheduling (handled by
  direct contact), automatic refunds, client accounts. Manual refunds follow the approved
  24-hour cancellation eligibility rule.

## Technology Stack

- **Frontend:** Next.js, React
- **Backend:** Python, FastAPI
- **Database:** PostgreSQL, SQLAlchemy (ORM), Alembic (migrations)
- **Local environment:** Docker Compose
- **Development payments:** mock payment flow; no personal banking API tokens required
- **Production payment provider:** not finalized
- **Calendar and AI integrations:** Google Calendar API; OpenAI API (P1)
- **Hosting:** a single AWS EC2 instance running Docker Compose, with Caddy for HTTPS;
  infrastructure is defined with Terraform in `infra/`. Do not silently change these requirements.

## Architecture

The backend is a **modular monolith**: one application, one database.

Top-level layout: `backend/`, `frontend/`, `infra/`.

Modules: `accounts`, `availability`, `booking`, `payments`, `calendar`, `notifications`,
`assistant`.

- One module = one folder = one responsibility.
- A module may use another module only through that module's `api.py`.
- Each module owns its tables. A module never reads or writes another module's tables.
- Layering inside a module: `router` → `service` → `repository`. Routers contain no SQL;
  repositories contain no business decisions.
- Modules communicate through plain function calls. No queues or events at this stage.
- Every database schema change is a new Alembic migration. Existing migrations are never edited.
- Keep booking lifecycle transitions in `booking`; use module public interfaces for cross-module
  operations. Any proposed ownership of availability-slot claims must preserve these boundaries.

## Business Rules

1. **Hold deadline.** A hold expires exactly 15 minutes after its creation time.
2. **Atomic expiry and replacement.** Expired holds must not block new reservations indefinitely.
   Expiring stale holds and creating a replacement hold must be one concurrency-safe transaction;
   never check availability in Python and then write separately.
3. **No overlapping appointments.** A psychologist cannot have overlapping active holds or
   confirmed appointments, including bookings created from distinct slot records. The PostgreSQL
   range-exclusion mechanism in `docs/DATABASE_DESIGN.md` is **PROPOSED**, not an approved schema.
4. **Booking statuses.** Booking status transitions happen only through the `booking` module.
   Proposed transitions and names are documented in `docs/DATABASE_DESIGN.md`.
5. **Payments.**
   - Payment events may be delivered more than once; handling must be idempotent.
   - A payment confirmed after hold expiry enters manual review and must never automatically
     confirm the expired booking, even if the interval is currently free. A refund may be required
     and is handled manually.
   - The authoritative payment timestamp is unresolved until the team explicitly approves a policy.
   - The production provider is undecided. Development must support a mock flow without personal
     banking API tokens.
6. **Cancellation and refunds.** Cancellation and rescheduling are arranged by direct contact
   with the psychologist. A client requesting cancellation at least 24 hours before the session
   is eligible for a manually handled refund. Exceptions and operational details remain open.
7. **Time.** All timestamps are stored as `timestamptz` in UTC. Each psychologist has a time zone
   in their profile. The frontend displays times in the user's local time zone.
8. **Sensitive data.** Client data is sensitive. Never log names or email addresses, never commit
   real data, and never commit `.env` files.

## Testing

Booking and payment logic must be covered by automated tests when implemented. Include concurrent
scenarios for simultaneous identical holds, partially overlapping appointments, valid adjacent
appointments, expiry/replacement races, payment-versus-expiry races, and duplicate payment events.
These are test expectations only; do not add tests unless implementation work is approved.

## Open Questions

- Production payment provider and required production payment flow.
- Email delivery provider, token lifetime, and behavior for link scanners or repeated clicks.
- OAuth client configuration, callback URLs, account-linking policy, and session mechanism.
- Cancellation-policy exceptions and manual refund operations.
- Google Calendar synchronisation frequency.
- Which payment timestamp is authoritative at the 15-minute expiry boundary. This remains
  unresolved until the team explicitly approves the policy.
- Confirm that AWS EC2, Terraform, and Caddy remain the team's deployment target for this MVP.
