from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
import smtplib
import ssl
from typing import Protocol


class EmailSender(Protocol):
    def send_verification(self, recipient: str, verification_url: str) -> None: ...


class EmailDeliveryUnavailable(RuntimeError):
    """Raised when the configured email provider cannot accept a message."""


@dataclass(frozen=True)
class CapturedVerificationEmail:
    recipient: str
    verification_url: str


class DevelopmentEmailSender:
    """Capture messages in process for local development and tests only."""

    def __init__(self) -> None:
        self.messages: list[CapturedVerificationEmail] = []

    def send_verification(self, recipient: str, verification_url: str) -> None:
        self.messages.append(CapturedVerificationEmail(recipient, verification_url))


class UnconfiguredEmailSender:
    """Fail closed until a production provider adapter is configured."""

    def send_verification(self, recipient: str, verification_url: str) -> None:
        raise EmailDeliveryUnavailable("Production email delivery is not configured")


class GmailSMTPEmailSender:
    """Send verification messages through a dedicated Gmail account using STARTTLS."""

    host = "smtp.gmail.com"
    port = 587

    def __init__(self, username: str, app_password: str, timeout_seconds: float = 8.0) -> None:
        self.username = username.strip()
        self._app_password = "".join(app_password.split())
        self.timeout_seconds = timeout_seconds

    def send_verification(self, recipient: str, verification_url: str) -> None:
        message = EmailMessage()
        message["From"] = formataddr(("Sessionly", self.username))
        message["To"] = recipient
        message["Subject"] = "Підтвердіть адресу електронної пошти — Sessionly"
        message.set_content(
            "Вітаємо! Щоб підтвердити адресу електронної пошти, відкрийте посилання:\n\n"
            f"{verification_url}\n\n"
            "Посилання одноразове та діє 30 хвилин. Якщо ви не надсилали запит, "
            "проігноруйте цей лист."
        )

        try:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout_seconds) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
                smtp.login(self.username, self._app_password)
                refused_recipients = smtp.send_message(message)
                if refused_recipients:
                    raise smtplib.SMTPRecipientsRefused(refused_recipients)
        except (OSError, smtplib.SMTPException):
            # SMTP exceptions can contain recipient and server-response details.
            raise EmailDeliveryUnavailable("Gmail SMTP delivery failed") from None
