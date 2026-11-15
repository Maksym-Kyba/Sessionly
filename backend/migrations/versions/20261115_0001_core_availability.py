"""Create psychologist, weekly availability rules and materialized slots.

Revision ID: 20261115_0001
Revises:
Create Date: 2026-11-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261115_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "psychologists",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("public_id", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("time_zone", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_table(
        "availability_rules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("psychologist_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("local_start", sa.Time(timezone=False), nullable=False),
        sa.Column("local_end", sa.Time(timezone=False), nullable=False),
        sa.Column("session_duration_minutes", sa.Integer(), nullable=False),
        sa.Column("price_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="UAH", nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_availability_rules_weekday"),
        sa.CheckConstraint("session_duration_minutes > 0", name="ck_availability_rules_duration"),
        sa.CheckConstraint("price_minor >= 0", name="ck_availability_rules_price"),
        sa.CheckConstraint("valid_until IS NULL OR valid_until >= valid_from", name="ck_availability_rules_date_range"),
        sa.CheckConstraint("local_end > local_start", name="ck_availability_rules_time_range"),
        sa.ForeignKeyConstraint(["psychologist_id"], ["psychologists.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_availability_rules_psychologist_active",
        "availability_rules",
        ["psychologist_id", "is_active"],
    )
    op.create_table(
        "availability_slots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("psychologist_id", sa.Uuid(), nullable=False),
        sa.Column("availability_rule_id", sa.Uuid(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=3), server_default="UAH", nullable=False),
        sa.Column("state", sa.String(length=16), server_default="published", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("ends_at > starts_at", name="ck_availability_slots_time_range"),
        sa.CheckConstraint("price_minor >= 0", name="ck_availability_slots_price"),
        sa.CheckConstraint("state IN ('published', 'withdrawn')", name="ck_availability_slots_state"),
        sa.ForeignKeyConstraint(["availability_rule_id"], ["availability_rules.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["psychologist_id"], ["psychologists.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "psychologist_id", "starts_at", "ends_at", name="uq_availability_slots_identity"
        ),
    )
    op.create_index(
        "ix_availability_slots_psychologist_starts",
        "availability_slots",
        ["psychologist_id", "starts_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_availability_slots_psychologist_starts", table_name="availability_slots")
    op.drop_table("availability_slots")
    op.drop_index("ix_availability_rules_psychologist_active", table_name="availability_rules")
    op.drop_table("availability_rules")
    op.drop_table("psychologists")
