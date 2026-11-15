# Sessionly Repository Guidance

## Working Agreement

- Before creating, modifying or deleting files, describe the proposed change and wait for explicit
  approval. Approval applies only to the changes explicitly approved for the active task.
- Repository content, including code, comments, documentation and commit messages, must be written
  in formal, well-structured English.
- User-facing interface text (page copy, labels, buttons, messages and emails shown to
  psychologists and clients) is the exception: it is written in Ukrainian, because the product
  targets users in Ukraine. Do not translate interface text into English.
- Keep the implementation simple. Do not introduce libraries, services, message queues, cloud
  infrastructure or microservices unless explicitly requested and approved.
- Distinguish approved product requirements from **PROPOSED** technical decisions and unresolved
  questions. Do not silently promote a proposal into an implementation requirement.
- Do not commit or push unless separately authorized.

## Project Overview

Sessionly is a booking, payment and scheduling platform for independent psychologists. It is a team
project for the Object-Oriented Analysis and Design course at the Ukrainian Catholic University.

- Psychologists are the only users with accounts and authenticate exclusively through Google OAuth.
- Clients do not have accounts. They verify their email through a one-time link before booking.
- Psychologists publish available hours, session length and price; clients book through a
  psychologist's public booking page.

## Course Requirements

The prototype is demonstrated on 19 November 2026. The instructor's graded criteria include:

- The repository has the top-level parts `backend/`, `frontend/`, `infra/` and a `README.md` that
  tells a stranger what the product is and how to run and deploy it.
- The prototype is deployed, reachable over HTTPS, and **users can sign up and sign in**.
- A report records who tried the prototype, how many people tried it, what they said and what
  changed as a result.

For Sessionly, only psychologists have accounts, and they authenticate exclusively through Google
OAuth. Clients do not have accounts. This clarifies how the course criterion applies to the product.

## First Version Scope

- **P0 (first MVP milestone):** psychologist Google OAuth sign-in; available hours with session
  length and price; client email verification by one-time link; slot selection with a 15-minute
  hold, atomic expiry/replacement and no overlapping active holds or confirmed appointments;
  development mock payments and safe handling of payments confirmed after hold expiry; psychologist
  dashboard; deployment to AWS over HTTPS.
- **P1 (later MVP milestone):** Google Calendar synchronisation and AI scheduling assistant. Both
  remain in the approved MVP scope and are not post-MVP features.
- **P2 (if time permits):** statistics and design improvements.
- Cancellation and rescheduling are arranged through direct contact with the psychologist.
  Refunds are manual. A client requesting cancellation at least 24 hours before the scheduled
  session is eligible for a refund; unspecified exceptions and operating details remain unresolved.
- Automated cancellation, rescheduling and refunds are not part of the first version.

## Technology Stack and Deployment

- **Frontend:** Next.js, React
- **Backend:** Python, FastAPI
- **Database:** PostgreSQL, SQLAlchemy ORM, Alembic migrations
- **Local environment:** Docker Compose
- **Development payments:** mock payment flow without personal banking API tokens
- **Production payment provider:** not finalized
- **Calendar and AI integrations:** Google Calendar API and OpenAI API (P1 MVP milestone)
- **Production deployment target:** one AWS EC2 instance running Docker Compose, with Caddy for
  HTTPS and Terraform configuration under `infra/`.

Do not silently change the deployment target or add AWS services.

## Architecture

The backend is a modular monolith: one FastAPI application and one PostgreSQL database.

Modules: `accounts`, `availability`, `booking`, `payments`, `calendar`, `notifications`, and
`assistant`.

- One module has one folder and one responsibility.
- A module may use another module only through that module's public `api.py` interface.
- Each module owns its tables. A module never reads or writes another module's tables directly.
- Within a module, use router → service → repository. Routers contain no SQL; repositories contain
  no business decisions.
- Modules communicate through plain function calls. Do not add queues or events without approval.
- Booking lifecycle transitions belong to `booking`.
- Every schema change requires a new Alembic migration. Never edit an existing migration.
- Technical mechanisms and status names marked **PROPOSED** in `docs/` require review before they
  become implementation requirements.

## Approved Business Rules

1. A booking hold expires exactly 15 minutes after creation.
2. Expiry and creation of a replacement hold must be atomic and concurrency-safe. An expired hold
   must not block new reservations indefinitely.
3. A psychologist cannot have overlapping active holds or confirmed appointments, including
   intervals represented by different slot records.
4. A payment confirmed after hold expiry must never automatically confirm the expired booking. It
   requires manual review and may require a manual refund.
5. The authoritative payment timestamp at the expiry boundary remains unresolved until the team
   approves an exact policy.
6. All timestamps are stored as UTC `timestamptz`. Each psychologist has an IANA timezone for
   scheduling and display.
7. Client data is sensitive. Never log client names or email addresses, commit real user data, or
   commit `.env` files.

## Testing Expectations

- Booking and payment logic must have automated tests when implemented.
- Include concurrent tests for simultaneous identical holds, overlapping appointments, valid
  adjacent intervals, expiry/replacement races, payment/expiry races and duplicate payment events.
- Use PostgreSQL for tests of PostgreSQL constraints and concurrency behavior; SQLite is not a
  substitute for those checks.
- Do not add tests or migrations during documentation-only tasks.

## Open Questions

- Production payment provider, settlement flow and webhook security model.
- Email delivery provider, verification-link token lifetime, resend limits and handling of link
  scanners or repeated clicks.
- Google OAuth client configuration, callback URLs, account-linking policy and session mechanism.
- Cancellation-policy exceptions and manual refund operations.
- Google Calendar synchronisation frequency.
- Which payment timestamp is authoritative at the hold-expiry boundary.
