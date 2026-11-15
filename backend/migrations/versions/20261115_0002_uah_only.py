"""Limit initial availability prices to UAH.

Revision ID: 20261115_0002
Revises: 20261115_0001
Create Date: 2026-11-15
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20261115_0002"
down_revision: Union[str, None] = "20261115_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_availability_rules_currency", "availability_rules", "currency = 'UAH'"
    )
    op.create_check_constraint(
        "ck_availability_slots_currency", "availability_slots", "currency = 'UAH'"
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_availability_slots_currency", "availability_slots", type_="check"
    )
    op.drop_constraint(
        "ck_availability_rules_currency", "availability_rules", type_="check"
    )
