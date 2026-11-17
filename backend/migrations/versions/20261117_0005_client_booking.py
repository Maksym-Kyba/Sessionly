"""Add verified client booking credentials and durable idempotency.

Revision ID: 20261117_0005
Revises: 20261117_0004
Create Date: 2026-11-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261117_0005"
down_revision: Union[str, None] = "20261117_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("client_email", sa.String(length=320), nullable=True))
    op.add_column(
        "bookings", sa.Column("client_access_token_hash", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "bookings",
        sa.Column("client_access_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_bookings_client_access_token_hash", "bookings", ["client_access_token_hash"]
    )
    op.create_check_constraint(
        "ck_bookings_access_token_fields",
        "bookings",
        "(client_access_token_hash IS NULL) = (client_access_token_expires_at IS NULL)",
    )

    op.create_table(
        "email_verification_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("psychologist_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.statement_timestamp(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["psychologist_id"], ["psychologists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_email_verification_tokens_hash"),
    )
    op.create_index(
        "ix_email_verification_tokens_expiry", "email_verification_tokens", ["expires_at"]
    )
    op.create_index(
        "ix_email_verification_tokens_scope",
        "email_verification_tokens",
        ["psychologist_id", "email"],
    )

    op.create_table(
        "booking_verification_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("psychologist_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.statement_timestamp(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["psychologist_id"], ["psychologists.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_booking_verification_grants_hash"),
    )
    op.create_index(
        "ix_booking_verification_grants_expiry", "booking_verification_grants", ["expires_at"]
    )

    op.create_table(
        "public_rate_limit_buckets",
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.CheckConstraint("request_count > 0", name="ck_public_rate_limit_count"),
        sa.PrimaryKeyConstraint("key_hash"),
    )
    op.create_index(
        "ix_public_rate_limits_window", "public_rate_limit_buckets", ["window_started_at"]
    )

    op.create_table(
        "booking_idempotency_keys",
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("verification_grant_hash", sa.String(length=64), nullable=True),
        sa.Column("booking_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.statement_timestamp(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "(booking_id IS NULL) = (verification_grant_hash IS NULL)",
            name="ck_booking_idempotency_completion_fields",
        ),
        sa.PrimaryKeyConstraint("key_hash"),
        sa.UniqueConstraint("booking_id", name="uq_booking_idempotency_booking"),
    )
    op.create_index("ix_booking_idempotency_created_at", "booking_idempotency_keys", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_booking_idempotency_created_at", table_name="booking_idempotency_keys")
    op.drop_table("booking_idempotency_keys")
    op.drop_index("ix_public_rate_limits_window", table_name="public_rate_limit_buckets")
    op.drop_table("public_rate_limit_buckets")
    op.drop_index("ix_booking_verification_grants_expiry", table_name="booking_verification_grants")
    op.drop_table("booking_verification_grants")
    op.drop_index("ix_email_verification_tokens_scope", table_name="email_verification_tokens")
    op.drop_index("ix_email_verification_tokens_expiry", table_name="email_verification_tokens")
    op.drop_table("email_verification_tokens")
    op.drop_constraint("ck_bookings_access_token_fields", "bookings", type_="check")
    op.drop_constraint("uq_bookings_client_access_token_hash", "bookings", type_="unique")
    op.drop_column("bookings", "client_access_token_expires_at")
    op.drop_column("bookings", "client_access_token_hash")
    op.drop_column("bookings", "client_email")
