"""Add booking holds and active appointment overlap protection.

Revision ID: 20261117_0004
Revises: 20261116_0003
Create Date: 2026-11-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ExcludeConstraint

revision: str = "20261117_0004"
down_revision: Union[str, None] = "20261116_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table(
        "bookings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("availability_slot_id", sa.Uuid(), nullable=False),
        sa.Column("psychologist_id", sa.Uuid(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("session_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("price_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.statement_timestamp(),
            nullable=False,
        ),
        sa.Column(
            "hold_expires_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(statement_timestamp() + INTERVAL '15 minutes')"),
            nullable=False,
        ),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_reference", sa.String(length=255), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.clock_timestamp(),
            nullable=False,
        ),
        sa.CheckConstraint("ends_at > starts_at", name="ck_bookings_time_range"),
        sa.CheckConstraint("session_duration_minutes > 0", name="ck_bookings_duration"),
        sa.CheckConstraint("price_minor >= 0", name="ck_bookings_price"),
        sa.CheckConstraint("currency = 'UAH'", name="ck_bookings_currency"),
        sa.CheckConstraint("status IN ('HELD', 'CONFIRMED', 'EXPIRED')", name="ck_bookings_status"),
        sa.ForeignKeyConstraint(
            ["availability_slot_id"], ["availability_slots.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["psychologist_id"], ["psychologists.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_reference", name="uq_bookings_payment_reference"),
        ExcludeConstraint(
            ("psychologist_id", "="),
            (sa.text("tstzrange(starts_at, ends_at, '[)')"), "&&"),
            where=sa.text("status IN ('HELD', 'CONFIRMED')"),
            using="gist",
            name="ex_bookings_no_overlapping_active_appointments",
        ),
    )
    op.create_index(
        "ix_bookings_expiration_candidates",
        "bookings",
        ["psychologist_id", "hold_expires_at"],
        postgresql_where=sa.text("status = 'HELD'"),
    )
    op.create_index(
        "ix_bookings_psychologist_status_starts",
        "bookings",
        ["psychologist_id", "status", "starts_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_bookings_psychologist_status_starts", table_name="bookings")
    op.drop_index("ix_bookings_expiration_candidates", table_name="bookings")
    op.drop_table("bookings")
    # Keep btree_gist installed; it may predate this revision or be used by another table.
