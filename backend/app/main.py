from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.availability.router import router as availability_router
from app.accounts.router import router as accounts_router
from app.booking.router import router as booking_router
from app.core.config import settings
from app.core.database import engine
from app.notifications.email_sender import (
    DevelopmentEmailSender,
    GmailSMTPEmailSender,
    UnconfiguredEmailSender,
)
from app.notifications.router import router as notifications_router

app = FastAPI(title="Sessionly API")
app.include_router(accounts_router)
app.include_router(availability_router)
app.include_router(notifications_router)
app.include_router(booking_router)


def build_email_sender():
    if settings.app_env == "development" and settings.email_provider == "development":
        return DevelopmentEmailSender()

    username = (settings.gmail_smtp_username or "").strip()
    app_password = (
        settings.gmail_app_password.get_secret_value()
        if settings.gmail_app_password is not None
        else ""
    )
    if settings.email_provider == "gmail_smtp" and username and app_password.strip():
        return GmailSMTPEmailSender(
            username,
            app_password,
            timeout_seconds=settings.gmail_smtp_timeout_seconds,
        )
    return UnconfiguredEmailSender()


app.state.email_sender = build_email_sender()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "Idempotency-Key"],
)


@app.get("/health")
def health() -> dict[str, str]:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc

    return {"status": "ok", "database": "ok"}
