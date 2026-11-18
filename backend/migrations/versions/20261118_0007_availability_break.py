"""Add an optional break between sessions to availability rules.

Revision ID: 20261118_0007
Revises: 20261118_0006
Create Date: 2026-11-18
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261118_0007"
down_revision: Union[str, None] = "20261118_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "availability_rules",
        sa.Column("break_minutes", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_availability_rules_break",
        "availability_rules",
        "break_minutes BETWEEN 0 AND 240",
    )


def downgrade() -> None:
    op.drop_constraint("ck_availability_rules_break", "availability_rules", type_="check")
    op.drop_column("availability_rules", "break_minutes")
