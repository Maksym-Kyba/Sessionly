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

- **P0 (required):** psychologist Google OAuth sign-in; available hours with session length and
  price; client email verification by one-time link; slot selection with a 15-minute hold; mock
  payments for development and payment confirmation only when validly received before hold
  expiry; psychologist dashboard; deployment to AWS over HTTPS.
- **P1 (desired):** Google Calendar synchronisation and AI scheduling assistant.
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

1. **Atomic slot hold.** Claiming a slot must be atomic; never check availability in Python and
   then write separately. A proposed implementation is a conditional database update or insert
   with a unique slot constraint and a returned claim result.
2. **Hold expiry.** A hold lasts 15 minutes. An expired hold cannot be used to confirm a later
   payment automatically.
3. **Booking statuses.** Booking status transitions happen only through the `booking` module.
   Candidate statuses are documented as proposals in `docs/DATABASE_DESIGN.md`.
4. **Payments.**
   - Payment events may be delivered more than once; handling must be idempotent.
   - A payment confirmed after hold expiry enters manual review and must never automatically
     confirm the booking, even if the slot is currently free. A refund may be required and is
     handled manually.
   - The production provider is undecided. Development must support a mock flow without personal
     banking API tokens.
5. **Cancellation and refunds.** Cancellation and rescheduling are arranged by direct contact
   with the psychologist. A client requesting cancellation at least 24 hours before the session
   is eligible for a manually handled refund. Exceptions and operational details remain open.
6. **Time.** All timestamps are stored as `timestamptz` in UTC. Each psychologist has a time zone
   in their profile. The frontend displays times in the user's local time zone.
7. **Sensitive data.** Client data is sensitive. Never log names or email addresses, never commit
   real data, and never commit `.env` files.

## Testing

Booking and payment logic must be covered by automated tests when implemented.

## Open Questions

- Production payment provider and required production payment flow.
- Email delivery provider, token lifetime, and behavior for link scanners or repeated clicks.
- OAuth client configuration, callback URLs, account-linking policy, and session mechanism.
- Cancellation-policy exceptions and manual refund operations.
- Google Calendar synchronisation frequency.
- Confirm that AWS EC2, Terraform, and Caddy remain the team's deployment target for this MVP.
