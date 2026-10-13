"""Enforce authentication and client invariants.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-27
"""

from collections.abc import Sequence
from unicodedata import normalize

import sqlalchemy as sa
from alembic import context, op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _normalize_client_name(value: str) -> str:
    return " ".join(normalize("NFKC", value).casefold().split())


def upgrade() -> None:
    op.add_column("owners", sa.Column("singleton_key", sa.Integer(), nullable=True))
    op.add_column("owners", sa.Column("session_version", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF (SELECT count(*) FROM owners) > 1 THEN
                    RAISE EXCEPTION
                        '0003 requires at most one owner; remove unintended owners first';
                END IF;
            END
            $$;
            """,
        ),
    )
    op.execute(sa.text("UPDATE owners SET singleton_key = 1, session_version = 1"))
    op.alter_column("owners", "singleton_key", existing_type=sa.Integer(), nullable=False)
    op.alter_column("owners", "session_version", existing_type=sa.Integer(), nullable=False)
    op.create_check_constraint(
        "ck_owners_singleton_key",
        "owners",
        "singleton_key = 1",
    )
    op.create_unique_constraint(
        "uq_owners_singleton_key",
        "owners",
        ["singleton_key"],
    )

    op.add_column(
        "owner_sessions",
        sa.Column("session_version", sa.Integer(), nullable=True),
    )
    op.execute(
        sa.text(
            """
            UPDATE owner_sessions
            SET session_version = owners.session_version
            FROM owners
            WHERE owners.id = owner_sessions.owner_id
            """,
        ),
    )
    op.alter_column(
        "owner_sessions",
        "session_version",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.add_column("clients", sa.Column("normalized_name", sa.Text(), nullable=True))
    if context.is_offline_mode():
        op.execute(
            sa.text(
                """
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM clients) THEN
                        RAISE EXCEPTION
                            '0003 with existing clients must run through online Alembic';
                    END IF;
                END
                $$;
                """,
            ),
        )
    else:
        clients = sa.table(
            "clients",
            sa.column("id", sa.Uuid()),
            sa.column("standard_name", sa.String(200)),
            sa.column("normalized_name", sa.Text()),
        )
        connection = op.get_bind()
        rows = connection.execute(
            sa.select(clients.c.id, clients.c.standard_name),
        ).mappings()
        seen: dict[str, object] = {}
        for row in rows:
            normalized_name = _normalize_client_name(row["standard_name"])
            if normalized_name in seen:
                raise RuntimeError(
                    "0003 found duplicate normalized client names; resolve them first",
                )
            seen[normalized_name] = row["id"]
            connection.execute(
                sa.update(clients)
                .where(clients.c.id == row["id"])
                .values(normalized_name=normalized_name),
            )
    op.alter_column(
        "clients",
        "normalized_name",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.create_unique_constraint(
        "uq_clients_normalized_name",
        "clients",
        ["normalized_name"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_clients_normalized_name", "clients", type_="unique")
    op.drop_column("clients", "normalized_name")
    op.drop_column("owner_sessions", "session_version")
    op.drop_constraint("uq_owners_singleton_key", "owners", type_="unique")
    op.drop_constraint("ck_owners_singleton_key", "owners", type_="check")
    op.drop_column("owners", "session_version")
    op.drop_column("owners", "singleton_key")
