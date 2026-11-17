from email.message import EmailMessage
import smtplib
import ssl

import pytest
from pydantic import SecretStr

from app.core.config import settings
from app.main import build_email_sender
from app.notifications.email_sender import (
    DevelopmentEmailSender,
    EmailDeliveryUnavailable,
    GmailSMTPEmailSender,
    UnconfiguredEmailSender,
)


class FakeSMTP:
    def __init__(self, *, failure: str | None = None, ambiguous_timeout: bool = False) -> None:
        self.failure = failure
        self.ambiguous_timeout = ambiguous_timeout
        self.message: EmailMessage | None = None
        self.starttls_context: ssl.SSLContext | None = None
        self.login_arguments: tuple[str, str] | None = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def ehlo(self):
        if self.failure == "ehlo":
            raise smtplib.SMTPServerDisconnected("smtp response body")

    def starttls(self, *, context: ssl.SSLContext):
        self.starttls_context = context
        if self.failure == "starttls":
            raise ssl.SSLError("tls response body")

    def login(self, username: str, password: str):
        self.login_arguments = (username, password)
        if self.failure == "login":
            raise smtplib.SMTPAuthenticationError(535, b"sensitive smtp response")

    def send_message(self, message: EmailMessage):
        self.message = message
        if self.failure == "send":
            raise smtplib.SMTPDataError(554, b"sensitive smtp response")
        if self.ambiguous_timeout:
            raise TimeoutError("smtp may have accepted the message")
        return {}


def test_gmail_sender_uses_starttls_and_sends_verification_message(monkeypatch):
    smtp = FakeSMTP()
    captured = {}

    def make_smtp(host: str, port: int, *, timeout: float):
        captured.update(host=host, port=port, timeout=timeout)
        return smtp

    monkeypatch.setattr("app.notifications.email_sender.smtplib.SMTP", make_smtp)
    sender = GmailSMTPEmailSender(
        "sessionly.demo@gmail.com", "abcd efgh ijkl mnop", timeout_seconds=6
    )
    sender.send_verification("client@example.test", "https://sessionly.test/verify#token=raw-token")

    assert captured == {"host": "smtp.gmail.com", "port": 587, "timeout": 6}
    assert smtp.starttls_context is not None
    assert smtp.starttls_context.check_hostname is True
    assert smtp.starttls_context.verify_mode == ssl.CERT_REQUIRED
    assert smtp.login_arguments == ("sessionly.demo@gmail.com", "abcdefghijklmnop")
    assert smtp.message is not None
    assert smtp.message["To"] == "client@example.test"
    assert smtp.message["From"] == "Sessionly <sessionly.demo@gmail.com>"
    assert "https://sessionly.test/verify#token=raw-token" in smtp.message.get_content()


@pytest.mark.parametrize("failure", ["ehlo", "starttls", "login", "send"])
def test_gmail_sender_sanitizes_smtp_failures(monkeypatch, failure):
    smtp = FakeSMTP(failure=failure)
    monkeypatch.setattr("app.notifications.email_sender.smtplib.SMTP", lambda *args, **kwargs: smtp)
    sender = GmailSMTPEmailSender("private@example.test", "secret-app-password")

    with pytest.raises(EmailDeliveryUnavailable) as raised:
        sender.send_verification(
            "private-recipient@example.test", "https://private.test/#token=secret"
        )

    assert str(raised.value) == "Gmail SMTP delivery failed"
    assert "secret-app-password" not in str(raised.value)
    assert "private-recipient@example.test" not in str(raised.value)
    assert "secret" not in str(raised.value)


def test_gmail_sender_treats_ambiguous_timeout_as_delivery_failure(monkeypatch):
    smtp = FakeSMTP(ambiguous_timeout=True)
    monkeypatch.setattr("app.notifications.email_sender.smtplib.SMTP", lambda *args, **kwargs: smtp)
    sender = GmailSMTPEmailSender("sessionly.demo@gmail.com", "app-password")

    with pytest.raises(EmailDeliveryUnavailable, match="Gmail SMTP delivery failed"):
        sender.send_verification("client@example.test", "https://sessionly.test/#token=token-value")

    assert smtp.message is not None
    assert "token-value" in smtp.message.get_content()


def test_email_sender_factory_fails_closed_in_production_without_gmail_credentials(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "email_provider", "gmail_smtp")
    monkeypatch.setattr(settings, "gmail_smtp_username", "sessionly.demo@gmail.com")
    monkeypatch.setattr(settings, "gmail_app_password", None)

    assert isinstance(build_email_sender(), UnconfiguredEmailSender)


def test_email_sender_factory_keeps_development_capture_as_default(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "email_provider", "development")
    monkeypatch.setattr(settings, "gmail_app_password", SecretStr("unused"))

    assert isinstance(build_email_sender(), DevelopmentEmailSender)
