from dataclasses import dataclass
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
