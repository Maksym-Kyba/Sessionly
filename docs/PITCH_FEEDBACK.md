# Pitch Feedback and Follow-up

The instructor reviewed the one-page pitch and stated that the final presentation must answer the
questions raised in the team's own feedback. This document summarises that feedback and the
general feedback given to all teams, and lists the work planned in response. The slides are due on
18 November 2026 at 23:59, and the demo takes place on 19 November 2026.

## Instructor Feedback on Sessionly

1. **Existing alternatives.** Which solutions are already on the market? The instructor noted that
   Sessionly could also work as a CRM, and that this could be a paid feature: seeing your clients
   and bringing them back for further sessions.
2. **Competition and uniqueness.** Are general booking services, for example for barbershops,
   competitors? What makes Sessionly unique for the psychologist market?
3. **Monetisation.** What exactly will a psychologist be willing to pay for?
4. **Data privacy.** Privacy is critical. How does Sessionly guarantee it, for example that a
   psychologist can never see another psychologist's clients?

## Relevant General Feedback

The following points from the feedback given to all teams apply to Sessionly:

- **Validation with numbers.** Interviews and surveys show interest, not readiness to use the
  product. Set concrete targets (sign-ups, repeat use, agreement to accept real bookings) and,
  when reporting survey results, state who was asked, how many people and which questions.
- **Who pays and for what.** Identify the paying customer and what they pay for. Referral and
  partner programmes are also possible models.
- **Alternatives.** Name concrete competitors and the feature that distinguishes Sessionly.
- **Unit economics.** Estimate the running costs (hosting, payment provider fees, AI) and the number
  of paying psychologists at which the product breaks even.
- **Product form.** Consider whether part of the product would be more convenient in another form,
  for example reminders through a Telegram bot.
- **Retention.** Explain why psychologists and clients return, for example through reminders,
  without creating a sense of obligation or guilt.
- **Scaling.** Show how the product can grow beyond the first users.

## Action Items

Each item answers one or more of the questions above. Owners are proposed and may be changed by
the team.

| Item | Answers | Owner |
|---|---|---|
| Interview at least 5 practising psychologists and let at least 3 try the prototype; record the results without personal data | Validation, monetisation, alternatives, feedback report | Yuliia |
| Write the user feedback report: who tried the prototype, how many people, what they said and what changed | Course requirement, validation | Yuliia |
| Estimate unit economics: the EC2 server costs about USD 21 per month, plus payment provider fees and AI costs | Unit economics | Yuliia |
| Add an automated test showing that a psychologist cannot read another psychologist's bookings or clients | Data privacy | Maxym |
| Propose the pricing model (subscription or commission per paid session) and the payment provider, including its fees | Monetisation, unit economics | Melaniia |
| Research concrete alternatives: general booking services, calendar booking pages and services for psychologists in Ukraine and abroad | Alternatives, uniqueness | Whole team |
| Prepare slides that answer each of the four instructor questions | All | Whole team |

## Current Answers

These are working answers for the presentation. They will be updated with interview results.

- **Uniqueness:** clients book without creating an account and only verify their email; payment in
  advance with a 15-minute hold confirms the appointment automatically; overlapping appointments
  are prevented by the database; the interface is in Ukrainian and prices are in hryvnias.
- **Possible paid features:** a client list with session history (CRM), the AI scheduling
  assistant, Google Calendar synchronisation and reminders.
- **Privacy:** psychologists sign in only through Google; the session is stored in an HttpOnly
  cookie with CSRF protection and served only over HTTPS; the backend scopes psychologist data by
  the psychologist identified by the session; one-time client links are stored only as hashes; and
  client email addresses are never logged.
