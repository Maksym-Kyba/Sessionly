"""Payment coordination between the payment gateway and booking confirmation.

The service collects a payment through a gateway and, for a successful payment, asks the booking
side whether it accepts the payment. It never changes booking state and never checks hold expiry:
booking lifecycle transitions and the 15-minute hold validation belong to the booking module.

`process_booking_payment` settles one gateway call against an injected booking confirmation
function and persists nothing. `pay_booking` is the persisted flow used by the mock payment
endpoint; it reaches the booking module only through `booking_adapter`.

The four booking confirmation decisions match the booking module's agreed confirmation outcomes.
Mapping both EXPIRED and NOT_CONFIRMABLE to manual review after a successful payment has been
agreed with the booking module owner. PROPOSED: payment status names are review material, not
final requirements.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.payments import booking_adapter, repository
from app.payments.gateway import (
    SUPPORTED_CURRENCY,
    InvalidPaymentRequest,
    PaymentGateway,
    PaymentIdempotencyConflict,
    PaymentOutcome,
    PaymentRequest,
)
from app.payments.models import Payment


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


class BookingConfirmationDecision(StrEnum):
    """The booking module's answer to a successful payment.

    Values match the booking module's confirmation outcomes so that the adapter can map them
    directly.
    """

    CONFIRMED = "CONFIRMED"
    ALREADY_CONFIRMED = "ALREADY_CONFIRMED"
    EXPIRED = "EXPIRED"
    NOT_CONFIRMABLE = "NOT_CONFIRMABLE"


class PaymentSettlementError(Exception):
    """A gateway outcome or booking decision is not one this service knows how to settle."""


class BookingNotPayable(Exception):
    """Booking reports that the booking is missing, no longer held, or past its hold deadline."""


class PaymentInProgress(Exception):
    """Another payment attempt for the same booking is still pending."""


class PaymentRequiresManualReview(Exception):
    """A previous payment for the booking awaits manual review, so no new attempt may charge.

    A successful charge that booking did not confirm is recorded as `manual_review`. Until that
    payment is resolved manually, accepting another attempt could charge the client twice.
    """


class BookingAccessDenied(Exception):
    """The client access token does not grant access to the booking, or the booking is unknown."""


class ConfirmBooking(Protocol):
    def __call__(self, booking_id: UUID, payment_reference: str) -> BookingConfirmationDecision:
        """Ask the booking side to accept a successful payment for a booking.

        The implementation, owned by the booking module, checks whether the hold is still active
        and whether a confirmed booking was confirmed by this same payment reference. Repeating
        the call with the same payment reference must be safe.
        """
        ...


@dataclass(frozen=True)
class PaymentSettlement:
    status: PaymentStatus
    provider: str
    provider_reference: str


@dataclass(frozen=True)
class RecordedPayment:
    """A persisted payment attempt as returned by `pay_booking`."""

    payment_id: UUID
    booking_id: UUID
    status: PaymentStatus
    booking_decision: BookingConfirmationDecision | None
    amount_minor: int
    currency: str
    provider: str
    provider_reference: str | None
    created_at: datetime
    updated_at: datetime
    idempotent_replay: bool


_STATUS_BY_DECISION = {
    BookingConfirmationDecision.CONFIRMED: PaymentStatus.SUCCEEDED,
    BookingConfirmationDecision.ALREADY_CONFIRMED: PaymentStatus.SUCCEEDED,
    BookingConfirmationDecision.EXPIRED: PaymentStatus.MANUAL_REVIEW,
    # Agreed with the booking module owner: the money was collected but the booking will not be
    # confirmed, so the payment is kept for manual review rather than treated as succeeded or
    # discarded.
    BookingConfirmationDecision.NOT_CONFIRMABLE: PaymentStatus.MANUAL_REVIEW,
}


def to_booking_decision(value: object) -> BookingConfirmationDecision:
    try:
        return BookingConfirmationDecision(value)
    except ValueError as exc:
        raise PaymentSettlementError("Unknown booking confirmation decision") from exc


def status_for_decision(decision: object) -> PaymentStatus:
    """Map booking's answer to a successful payment onto a payment status."""
    return _STATUS_BY_DECISION[to_booking_decision(decision)]


def process_booking_payment(
    gateway: PaymentGateway,
    request: PaymentRequest,
    confirm_booking: ConfirmBooking,
) -> PaymentSettlement:
    """Collect a payment and settle it against booking confirmation.

    Only a successful payment reaches booking confirmation; a failed payment never does, and an
    unknown outcome raises `PaymentSettlementError` without contacting booking. A successful
    payment that booking does not confirm requires manual review and is never treated as a
    confirmed booking.
    """
    result = gateway.process_payment(request)
    if result.outcome is PaymentOutcome.SUCCEEDED:
        status = status_for_decision(confirm_booking(request.booking_id, result.provider_reference))
    elif result.outcome is PaymentOutcome.FAILED:
        status = PaymentStatus.FAILED
    else:
        raise PaymentSettlementError("Unknown payment outcome")
    return PaymentSettlement(
        status=status,
        provider=result.provider,
        provider_reference=result.provider_reference,
    )


_ONE_PENDING_PER_BOOKING = "uq_payments_one_pending_per_booking"


def _violated_constraint(exc: IntegrityError) -> str | None:
    diagnostics = getattr(exc.orig, "diag", None)
    return getattr(diagnostics, "constraint_name", None)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _request_hash(booking_id: UUID, provider: str, request_details: str) -> str:
    return _sha256(f"{booking_id}\n{provider}\n{request_details}")


def _recorded(payment: Payment, *, idempotent_replay: bool) -> RecordedPayment:
    return RecordedPayment(
        payment_id=payment.id,
        booking_id=payment.booking_id,
        status=PaymentStatus(payment.status),
        booking_decision=(
            None
            if payment.booking_decision is None
            else BookingConfirmationDecision(payment.booking_decision)
        ),
        amount_minor=payment.amount_minor,
        currency=payment.currency,
        provider=payment.provider,
        provider_reference=payment.provider_reference,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
        idempotent_replay=idempotent_replay,
    )


def _claim(
    session: Session,
    booking_id: UUID,
    key_hash: str,
    request_hash: str,
    provider: str,
    client_access_token: str | None,
) -> tuple[UUID, bool]:
    """Record a pending payment, or find the attempt already recorded for this key.

    Returns the payment ID and whether the key had already been used. The pending row is committed
    before any charge, so an interrupted attempt always leaves a record behind. When a client
    access token is given, booking verifies it first, before any replay or new attempt.

    A new attempt is refused while any payment for the booking awaits manual review. The check
    runs under the booking's payment lock, which `_process` also holds when it records
    `manual_review`, so a concurrent attempt either sees the committed review state or is
    already blocked as in progress by the pending row. Replays of a known key are unaffected.
    """
    with session.begin():
        repository.lock_booking_payments(session, booking_id)
        if client_access_token is not None and not booking_adapter.client_can_access_booking(
            session, booking_id, client_access_token
        ):
            raise BookingAccessDenied("Booking not found")
        existing = repository.get_by_idempotency_key_hash(session, key_hash)
        if existing is None:
            if repository.has_manual_review_payment(session, booking_id):
                raise PaymentRequiresManualReview(
                    "A previous payment for this booking awaits manual review"
                )
            payable = booking_adapter.payable_booking(session, booking_id)
            if payable is None:
                raise BookingNotPayable("Booking is not payable")
            if payable.amount_minor <= 0 or payable.currency != SUPPORTED_CURRENCY:
                raise InvalidPaymentRequest("Booking amount cannot be paid through the gateway")
            try:
                with session.begin_nested():
                    payment_id = repository.insert_pending(
                        session,
                        booking_id=booking_id,
                        key_hash=key_hash,
                        request_hash=request_hash,
                        provider=provider,
                        amount_minor=payable.amount_minor,
                        currency=payable.currency,
                    )
            except IntegrityError as exc:
                if _violated_constraint(exc) == _ONE_PENDING_PER_BOOKING:
                    raise PaymentInProgress(
                        "Another payment for this booking is still pending"
                    ) from exc
                raise
            if payment_id is not None:
                return payment_id, False
            # A concurrent request recorded the same key first.
            existing = repository.get_by_idempotency_key_hash(session, key_hash)
        if existing is None or existing.request_hash != request_hash:
            raise PaymentIdempotencyConflict(
                "Idempotency key was already used for a different payment request"
            )
        return existing.id, True


def _settle_success(session: Session, payment: Payment) -> None:
    """Ask booking to confirm a successful charge; never leave the charge unrecorded."""
    try:
        with session.begin_nested():
            decision = to_booking_decision(
                booking_adapter.confirm_booking(
                    session, payment.booking_id, payment.provider_reference
                )
            )
    except Exception:
        # Deliberately broad: whatever went wrong in booking confirmation, the successful charge
        # must be persisted for manual review instead of being rolled back with the error.
        payment.status = PaymentStatus.MANUAL_REVIEW
        payment.booking_decision = None
        return
    payment.booking_decision = decision
    payment.status = status_for_decision(decision)


def _process(
    session: Session,
    booking_id: UUID,
    payment_id: UUID,
    gateway: PaymentGateway,
    *,
    idempotent_replay: bool,
) -> RecordedPayment:
    """Charge a pending payment and settle it in one transaction.

    The booking's payment lock and the payment row lock are taken first, so concurrent requests
    are serialized: a request for the same attempt finds the final status instead of charging
    again, and an attempt with another key cannot pass its payability check while this charge is
    being settled. Booking's confirmation joins this transaction, so the payment status and the
    booking transition commit together.
    """
    with session.begin():
        repository.lock_booking_payments(session, booking_id)
        payment = repository.get_for_update(session, payment_id)
        if payment is None:
            raise LookupError("Payment attempt disappeared")
        if payment.status != PaymentStatus.PENDING:
            return _recorded(payment, idempotent_replay=idempotent_replay)
        result = gateway.process_payment(
            PaymentRequest(
                booking_id=payment.booking_id,
                amount_minor=payment.amount_minor,
                currency=payment.currency,
                idempotency_key=str(payment.id),
            )
        )
        if result.outcome is PaymentOutcome.SUCCEEDED:
            payment.provider_reference = result.provider_reference
            session.flush()
            _settle_success(session, payment)
        elif result.outcome is PaymentOutcome.FAILED:
            payment.provider_reference = result.provider_reference
            payment.status = PaymentStatus.FAILED
        else:
            raise PaymentSettlementError("Unknown payment outcome")
        session.flush()
        session.refresh(payment)
        return _recorded(payment, idempotent_replay=idempotent_replay)


def _pay(
    session: Session,
    booking_id: UUID,
    idempotency_key: str,
    gateway: PaymentGateway,
    *,
    request_details: str,
    client_access_token: str | None,
) -> RecordedPayment:
    if session.in_transaction():
        raise RuntimeError("Payments must manage their own transactions")
    if not isinstance(idempotency_key, str) or not idempotency_key.strip():
        raise InvalidPaymentRequest("idempotency_key must be a non-empty string")
    key_hash = _sha256(idempotency_key)
    request_hash = _request_hash(booking_id, gateway.provider_name, request_details)
    payment_id, key_seen_before = _claim(
        session,
        booking_id,
        key_hash,
        request_hash,
        gateway.provider_name,
        client_access_token,
    )
    return _process(session, booking_id, payment_id, gateway, idempotent_replay=key_seen_before)


def pay_booking_for_client(
    session: Session,
    booking_id: UUID,
    client_access_token: str,
    idempotency_key: str,
    gateway: PaymentGateway,
    *,
    request_details: str = "",
) -> RecordedPayment:
    """Collect a payment on behalf of a client holding the booking's access token.

    Booking verifies the token before any replay or new attempt; an invalid token, an expired
    token or an unknown booking raises `BookingAccessDenied`. See `pay_booking` for the rest of
    the flow.
    """
    if not isinstance(client_access_token, str) or not client_access_token:
        raise BookingAccessDenied("Booking not found")
    return _pay(
        session,
        booking_id,
        idempotency_key,
        gateway,
        request_details=request_details,
        client_access_token=client_access_token,
    )


def pay_booking(
    session: Session,
    booking_id: UUID,
    idempotency_key: str,
    gateway: PaymentGateway,
    *,
    request_details: str = "",
) -> RecordedPayment:
    """Collect a persisted payment for a booking and settle it against booking confirmation.

    Internal callers only: this function does not check client access, in the same way that
    booking's internal `create_hold` does not verify client email. Public routes must use
    `pay_booking_for_client`.

    The amount and currency always come from booking's snapshot. The session must not have an
    active transaction: the pending record is committed before the gateway is called.

    `request_details` identifies the client's request beyond the booking (for the mock, the
    simulated outcome); reusing an idempotency key with different details is a conflict.
    """
    return _pay(
        session,
        booking_id,
        idempotency_key,
        gateway,
        request_details=request_details,
        client_access_token=None,
    )
