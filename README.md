# Sessionly

Booking, payments and scheduling for independent psychologists.

**Live demo:** _URL will be added after deployment._

Sessionly is developed as a team project for the Object-Oriented Analysis and Design course
at the Ukrainian Catholic University.

## Overview

Sessionly is a web application that helps independent psychologists manage their appointments
in one place. Psychologists publish their available hours; clients choose a time, pay online,
and receive an automatically confirmed appointment. This removes the back-and-forth messaging
about booking, payments and calendar updates.

## Problem

Psychologists often manage appointments manually through messaging apps, phone calls,
spreadsheets or separate calendar applications. This leads to:

- time spent coordinating suitable dates and times;
- double bookings and scheduling conflicts;
- missed or unpaid appointments;
- repetitive communication with clients.

## Target Users

- **Psychologists:** independent psychologists in Ukraine who manage their own appointments
  without an administrator.
- **Clients:** people who book a session through a psychologist's personal booking link.

## Features

- **Accounts:** psychologists sign up, sign in and set up a profile.
- **Availability:** psychologists set available hours for the next month, session length and price.
- **Booking:** clients verify their email address and choose a free slot. The slot is reserved
  for 15 minutes to complete payment; otherwise it becomes available again.
- **Payment and confirmation:** clients pay in a sandbox payment environment. A successful
  payment confirms the appointment automatically, without manual approval.
- **Dashboard:** psychologists see upcoming appointments and their statuses
  (scheduled, completed, cancelled).
- **Google Calendar integration:** times marked as busy in the psychologist's Google Calendar
  are hidden from clients; confirmed appointments are added to the calendar.
- **AI scheduling assistant:** suggests a time for the next appointment based on booking history
  and available slots, and drafts an invitation message. The psychologist decides whether to
  send it.

## Technology Stack

| Technology | Purpose |
|---|---|
| Next.js, React | Frontend |
| Python, FastAPI | Backend and business logic |
| PostgreSQL | Database |
| SQLAlchemy, Alembic | Data access and schema migrations |
| Docker Compose | Local development environment |
| Google Calendar API | Calendar synchronisation |
| WayForPay (sandbox) | Test payments |
| OpenAI API | AI scheduling suggestions and message drafts |

## Repository Structure

```
Sessionly/
├── backend/             # FastAPI application, database models, migrations, tests
├── frontend/            # Next.js application
├── infra/               # Deployment configuration
├── docker-compose.yml   # Local development environment
├── .env.example         # Template for environment variables
└── README.md
```

## Architecture

The backend is a **modular monolith**: a single FastAPI application with a single PostgreSQL
database, divided into modules with clear boundaries.

| Module | Responsibility |
|---|---|
| `accounts` | Psychologist registration, authentication and profile |
| `availability` | Available hours, session length and price |
| `booking` | Slot reservation, booking statuses, cancellation |
| `payments` | Payment creation and provider webhook handling |
| `calendar` | Google Calendar synchronisation |
| `notifications` | Email verification codes and booking confirmations |
| `assistant` | AI scheduling suggestions |

Modules communicate only through each module's public interface (`api.py`) and never access
another module's tables. Within a module, code is layered as router → service → repository.

### Key Design Decisions

- **No double booking.** A slot is reserved with a single atomic SQL statement that succeeds
  only if the slot is free or its previous reservation has expired.
- **Reservation expiry without timers.** A reservation whose `held_until` time has passed is
  treated as free, so correctness does not depend on a background job.
- **Payment confirmation by the server only.** A booking is confirmed only after the payment
  provider's webhook is verified, never on the basis of a browser redirect. Webhooks are
  processed idempotently, since providers may deliver them more than once.
- **Replaceable payment provider.** The provider is accessed through a `PaymentGateway`
  interface.
- **Time zones.** All timestamps are stored in UTC; each psychologist has a time zone in their
  profile, and the frontend displays times in the user's local time zone.
- **Privacy.** Client data is treated as sensitive: personal data is not logged, and secrets
  are never committed.

## Getting Started

### Prerequisites

- Git
- Docker and Docker Compose

### Run Locally

```bash
git clone <repository-url>
cd Sessionly
cp .env.example .env    # fill in the required values
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API documentation: http://localhost:8000/docs

## Deployment

_To be completed once the deployment target is finalised._

## Team

| Member | Responsibilities |
|---|---|
| Yuliia Oliinyk | Frontend (psychologist dashboard, calendar, client booking flow), AI scheduling assistant, AWS deployment, user feedback report |
| Maxym Kyba | Backend, database, booking and reservation logic, authentication, payment processing |
| Melaniia Poliuha | Google Calendar integration, payment provider integration, user validation |

## Roadmap

Planned after the first version:

- appointment rescheduling;
- reminders for clients;
- automatic refunds;
- appointment statistics.
