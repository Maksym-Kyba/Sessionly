from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.core.database import Base


class Psychologist(Base):
    __tablename__ = "psychologists"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    public_id: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, default=lambda: uuid4().hex
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    time_zone: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class GoogleIdentity(Base):
    __tablename__ = "google_identities"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    psychologist_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("psychologists.id", ondelete="RESTRICT"),
        nullable=False,
    )
    google_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email_at_link_time: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("google_subject", name="uq_google_identities_subject"),
        UniqueConstraint("psychologist_id", name="uq_google_identities_psychologist"),
    )


class OAuthTransaction(Base):
    __tablename__ = "oauth_transactions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    browser_binding_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    nonce_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    pkce_verifier_encrypted: Mapped[str] = mapped_column(String(1024), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("state_hash", name="uq_oauth_transactions_state_hash"),
        Index("ix_oauth_transactions_expires_at", "expires_at"),
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    psychologist_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("psychologists.id", ondelete="RESTRICT"), nullable=False
    )
    session_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("session_token_hash", name="uq_auth_sessions_token_hash"),
        Index("ix_auth_sessions_psychologist_expires", "psychologist_id", "expires_at"),
    )
