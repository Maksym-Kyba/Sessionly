"""Add payment attempts with idempotency and settlement constraints.

Revision ID: 20261118_0006
Revises: 20261117_0005
Create Date: 2026-11-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261118_0006"
down_revision: Union[str, None] = "20261117_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("booking_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_reference", sa.String(length=255), nullable=True),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("booking_decision", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.clock_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.clock_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint("amount_minor > 0", name="ck_payments_amount"),
        sa.CheckConstraint("currency = 'UAH'", name="ck_payments_currency"),
        sa.CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'manual_review')",
            name="ck_payments_status",
        ),
        sa.CheckConstraint(
            "booking_decision IS NULL OR booking_decision IN "
            "('CONFIRMED', 'ALREADY_CONFIRMED', 'EXPIRED', 'NOT_CONFIRMABLE')",
            name="ck_payments_booking_decision",
        ),
        sa.CheckConstraint(
            "status <> 'succeeded' OR (provider_reference IS NOT NULL "
            "AND booking_decision IS NOT NULL "
            "AND booking_decision IN ('CONFIRMED', 'ALREADY_CONFIRMED'))",
            name="ck_payments_succeeded_requires_confirmation",
        ),
        sa.CheckConstraint(
            "status <> 'manual_review' OR provider_reference IS NOT NULL",
            name="ck_payments_manual_review_requires_reference",
        ),
        sa.CheckConstraint(
            "status NOT IN ('pending', 'failed') OR booking_decision IS NULL",
            name="ck_payments_undecided_without_booking_decision",
        ),
        sa.ForeignKeyConstraint(["booking_id"], ["bookings.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_payments_idempotency_key_hash", "payments", ["idempotency_key_hash"], unique=True
    )
    op.create_index(
        "uq_payments_provider_reference", "payments", ["provider_reference"], unique=True
    )
    op.create_index(
        "uq_payments_one_pending_per_booking",
        "payments",
        ["booking_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "uq_payments_one_succeeded_per_booking",
        "payments",
        ["booking_id"],
        unique=True,
        postgresql_where=sa.text("status = 'succeeded'"),
    )
    op.create_index("ix_payments_booking_created", "payments", ["booking_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_payments_booking_created", table_name="payments")
    op.drop_index("uq_payments_one_succeeded_per_booking", table_name="payments")
    op.drop_index("uq_payments_one_pending_per_booking", table_name="payments")
    op.drop_index("uq_payments_provider_reference", table_name="payments")
    op.drop_index("uq_payments_idempotency_key_hash", table_name="payments")
    op.drop_table("payments")
