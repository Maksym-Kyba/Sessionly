# Sessionly

Booking, payments and scheduling for independent psychologists.

**Live demo:** _URL will be added after deployment._

Sessionly is developed as a team project for the Object-Oriented Analysis and Design course
at the Ukrainian Catholic University.

## Overview

Sessionly helps independent psychologists publish available hours and lets clients book and pay
for sessions without creating client accounts. Psychologists sign in exclusively with Google
OAuth. Clients verify their email through a one-time link before booking.

## Problem

Psychologists often manage appointments manually through messaging apps, phone calls,
spreadsheets or separate calendar applications. This leads to:

- time spent coordinating suitable dates and times;
- double bookings and scheduling conflicts;
- missed or unpaid appointments;
- repetitive communication with clients.

## Target Users

- **Psychologists:** independent psychologists in Ukraine who manage their own appointments
  without an administrator and authenticate through Google OAuth.
- **Clients:** people who book through a psychologist's personal booking link; clients do not
  have Sessionly accounts.

## Features

- **Psychologist access:** Google OAuth sign-in and profile setup.
- **Availability:** psychologists set available hours, session length and price.
- **Email verification and booking:** clients verify their email with a one-time link, choose a
  free slot, and receive a 15-minute hold while completing payment.
- **Payment and confirmation:** development supports mock payments without personal banking API
  tokens. A valid payment confirmed before the hold expires can confirm the appointment.
  A payment confirmed after hold expiry never automatically confirms the booking; it requires
  manual review and may require a manual refund. The production payment provider is not finalized.
- **Cancellation and rescheduling:** clients contact the psychologist directly. A client who
  requests cancellation at least 24 hours before the scheduled session is eligible for a refund,
  handled manually by the psychologist.
- **Dashboard:** psychologists see upcoming appointments and their statuses.
- **Google Calendar integration (planned):** busy times can be hidden from clients and confirmed
  appointments can be added to the calendar.
- **AI scheduling assistant (planned):** suggests a time based on booking history and availability,
  and drafts an invitation message for the psychologist to review.

## Technology Stack

| Technology | Purpose |
|---|---|
| Next.js, React | Frontend |
| Python, FastAPI | Backend and business logic |
| PostgreSQL | Database |
| SQLAlchemy, Alembic | Data access and schema migrations |
| Docker Compose | Local development environment |
| Google OAuth | Psychologist sign-in |
| Mock payments | Development payment flow; production provider TBD |
| Google Calendar API | Planned calendar synchronisation |
| OpenAI API | Planned AI scheduling suggestions and message drafts |

## Repository Structure

```
Sessionly/
├── backend/             # FastAPI application, database models, migrations, tests
├── frontend/            # Next.js application
├── infra/               # Terraform deployment configuration
├── docs/                # Product, API and database design documents
├── docker-compose.yml   # Local development environment
├── .env.example         # Template for environment variables
├── AGENTS.md            # Repository-wide agent guidance
└── README.md
```

## Architecture

The backend is a **modular monolith**: a single FastAPI application with a single PostgreSQL
database, divided into modules with clear boundaries.

| Module | Responsibility |
|---|---|
| `accounts` | Psychologist Google OAuth identity and profile |
| `availability` | Available hours, session length, price and published slots |
| `booking` | Holds, booking statuses and appointment lifecycle |
| `payments` | Payment attempts, mock development flow and future provider boundary |
| `calendar` | Google Calendar synchronisation (planned) |
| `notifications` | One-time email verification links and booking notifications |
| `assistant` | AI scheduling suggestions (planned) |

Modules communicate only through each module's public interface (`api.py`) and never access
another module's tables. Within a module, code is layered as router → service → repository.
Proposed endpoints and data structures are documented in `docs/API_CONTRACT.md` and
`docs/DATABASE_DESIGN.md`; unapproved technical details are labeled **PROPOSED**.

### Key Product Rules

- A booking hold lasts 15 minutes and slot claims must prevent double booking atomically.
- Payment confirmation after hold expiry must never automatically confirm the booking. It goes to
  manual review and may require a manual refund.
- A client requesting cancellation at least 24 hours before the session is eligible for a
  psychologist-handled manual refund. Cancellation and rescheduling are arranged directly with the
  psychologist; exceptions and operating details are still open questions.
- All timestamps are stored in UTC; each psychologist has a time zone in their profile.
- Client data is sensitive: personal data is not logged and secrets are never committed.

## Getting Started

### Prerequisites

- Git
- Python 3.12 or newer
- uv
- Docker and Docker Compose

### Run Locally

From the repository root:

```bash
cp .env.example .env
# Keep the sample values for local development, or update the database credentials and URL together.
docker compose up -d db
```

In a second terminal, start the backend:

```bash
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

The local PostgreSQL service is available at `127.0.0.1:15432` and maps to port `5432` inside
the container. There are no application tables or migration revisions yet.

- Backend health: http://localhost:8000/health
- Backend API documentation: http://localhost:8000/docs
- PostgreSQL: `localhost:15432`

Stop PostgreSQL with `docker compose down`. To remove its persistent local data as well, run
`docker compose down -v`.

## Deployment

The current project deployment requirement is a single AWS EC2 instance running Docker Compose,
with Caddy for HTTPS and Terraform configuration in `infra/`. The team should confirm that this
remains the MVP target; this documentation update does not change it.

## Documentation Status

`docs/PRODUCT_SPEC.md` separates approved product requirements from proposed technical decisions
and unresolved questions. `docs/API_CONTRACT.md` and `docs/DATABASE_DESIGN.md` contain concrete
implementation proposals; details marked **PROPOSED** are not approved requirements.

## Team

| Member | Responsibilities |
|---|---|
| Yuliia Oliinyk | Frontend (psychologist dashboard, calendar, client booking flow), AI scheduling assistant, AWS deployment, user feedback report |
| Maxym Kyba | Backend, database, booking and reservation logic, authentication, payment processing |
| Melaniia Poliuha | Google Calendar integration, payment provider integration, user validation |

## Roadmap

Planned after the first version:

- Google Calendar synchronisation;
- AI scheduling assistant;
- appointment statistics and design improvements.
