# CLAUDE.md

Guidance for AI coding assistants working in this repository.

## Working Agreement

- **Ask before any file change.** Before creating, modifying or deleting a file, describe the
  proposed change and its rationale, then wait for explicit approval.
- **Repository language.** Everything committed to the repository (code, comments,
  documentation, commit messages) must be in formal, well-structured English.
- **Keep it simple.** Do not introduce new services, libraries, message queues, cloud
  infrastructure or microservices unless explicitly requested. If something seems necessary,
  explain why and ask first. Deployment uses a single EC2 instance; do not add other AWS
  services without asking.
- **Do not invent requirements.** If something is not specified here or in the README, ask.

## Project Overview

Sessionly is a web platform where psychologists publish available time slots and clients book
and pay for sessions online. It is a team project for the Object-Oriented Analysis and Design
course at the Ukrainian Catholic University.

- **Psychologist:** signs up, sets up a profile, connects Google Calendar, adds slots, and views
  appointments in a dashboard.
- **Client:** opens a booking page, verifies their email with a one-time code, selects a slot
  (held for 15 minutes), pays (sandbox), and receives a confirmation. The booking is added to the
  psychologist's Google Calendar. No psychologist approval is required after payment.

## Course Requirements

The prototype is demonstrated on 19 November 2026. Graded criteria:

- The repository has the top-level parts `backend/`, `frontend/`, `infra/` and a `README.md`
  that tells a stranger what the product is and how to run and deploy it.
- The prototype is deployed, reachable over HTTPS, and users can sign up and sign in.
- A report with user feedback: who tried it, how many people, what they said, and what was
  changed as a result.

### First Version Scope

- **P0 (required):** psychologist sign-up and sign-in, available hours with session length and
  price, slot selection with a 15-minute hold, sandbox payment with automatic confirmation,
  psychologist dashboard, deployment to AWS over HTTPS.
- **P1 (desired):** Google Calendar synchronisation, AI scheduling assistant, client email
  verification.
- **P2 (if time permits):** statistics, design improvements.
- **Out of scope:** rescheduling, reminders, automatic refunds.

## Technology Stack

- **Frontend:** Next.js, React
- **Backend:** Python, FastAPI
- **Database:** PostgreSQL, SQLAlchemy (ORM), Alembic (migrations)
- **Local environment:** Docker Compose
- **Integrations:** Google Calendar API; WayForPay (sandbox)
- **AI:** OpenAI API
- **Hosting:** a single AWS EC2 instance running Docker Compose, with Caddy for HTTPS;
  infrastructure is defined with Terraform in `infra/`

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

## Business Rules

1. **Atomic slot hold.** Holding a slot is a single SQL statement:
   `UPDATE ... WHERE status = 'free' OR (status = 'held' AND held_until < now()) RETURNING id`.
   Never check availability in Python and then write separately.
2. **Hold expiry.** A hold whose `held_until` is in the past is treated as free. Correctness does
   not depend on a background timer.
3. **Booking statuses.** `held → confirmed → completed`, `held → expired`,
   `confirmed → cancelled`. Status transitions happen only through the `booking` module.
4. **Payments.**
   - Webhooks may be delivered more than once; handling must be idempotent (unique constraint on
     the provider event ID).
   - Payment received after hold expiry: confirm if the slot is still free; otherwise mark the
     payment for refund.
   - The provider is accessed only through a `PaymentGateway` interface.
5. **Time.** All timestamps are stored as `timestamptz` in UTC. Each psychologist has a time zone
   in their profile. The frontend displays times in the user's local time zone.
6. **Sensitive data.** Client data is sensitive. Never log names or email addresses, never commit
   real data, and never commit `.env` files.

## Testing

Booking and payment logic must be covered by automated tests.

## Open Questions

Do not assume answers to these; ask the team.

- Cancellation and refund policy.
- Google Calendar synchronisation frequency.
