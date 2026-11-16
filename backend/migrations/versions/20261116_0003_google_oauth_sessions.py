"""Add psychologist Google identities, OAuth transactions, and sessions.

Revision ID: 20261116_0003
Revises: 20261115_0002
Create Date: 2026-11-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261116_0003"
down_revision: Union[str, None] = "20261115_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "google_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("psychologist_id", sa.Uuid(), nullable=False),
        sa.Column("google_subject", sa.String(length=255), nullable=False),
        sa.Column("email_at_link_time", sa.String(length=320), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["psychologist_id"], ["psychologists.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("google_subject", name="uq_google_identities_subject"),
        sa.UniqueConstraint("psychologist_id", name="uq_google_identities_psychologist"),
    )
    op.create_table(
        "oauth_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("browser_binding_hash", sa.String(length=64), nullable=False),
        sa.Column("nonce_hash", sa.String(length=64), nullable=False),
        sa.Column("pkce_verifier_encrypted", sa.String(length=1024), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash", name="uq_oauth_transactions_state_hash"),
    )
    op.create_index("ix_oauth_transactions_expires_at", "oauth_transactions", ["expires_at"])
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("psychologist_id", sa.Uuid(), nullable=False),
        sa.Column("session_token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["psychologist_id"], ["psychologists.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_token_hash", name="uq_auth_sessions_token_hash"),
    )
    op.create_index(
        "ix_auth_sessions_psychologist_expires", "auth_sessions", ["psychologist_id", "expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_auth_sessions_psychologist_expires", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_oauth_transactions_expires_at", table_name="oauth_transactions")
    op.drop_table("oauth_transactions")
    op.drop_table("google_identities")
