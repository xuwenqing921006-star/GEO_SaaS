from datetime import date
from uuid import UUID

from sqlalchemy import exists, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import DatabaseSession, Evidence, Fact, FactConflict, FactEvidence

PUBLIC_AUTHORIZATIONS = ("authorized", "not_required")


async def lock_content_fact_set(database: AsyncSession, client_id: UUID) -> None:
    """Serialize changes to one client's content-eligible fact set on PostgreSQL."""

    if database.get_bind().dialect.name != "postgresql":
        return
    advisory_key = client_id.int & 0x7FFF_FFFF_FFFF_FFFF
    await database.execute(
        text("SELECT pg_advisory_xact_lock(:advisory_key)"),
        {"advisory_key": advisory_key},
    )


async def list_content_eligible_facts(
    database: DatabaseSession,
    client_id: UUID,
    *,
    as_of: date | None = None,
) -> list[Fact]:
    """Return active knowledge entries without requiring a separate review step."""
    current_date = as_of or date.today()
    has_open_conflict = exists(
        select(FactConflict.id).where(
            FactConflict.client_id == client_id,
            FactConflict.fact_key == Fact.key,
            FactConflict.status == "open",
        ),
    )
    has_non_public_evidence = exists(
        select(FactEvidence.fact_id)
        .join(Evidence, Evidence.id == FactEvidence.evidence_id)
        .where(
            FactEvidence.fact_id == Fact.id,
            Evidence.authorization_status.not_in(PUBLIC_AUTHORIZATIONS),
        ),
    )
    rows = await database.scalars(
        select(Fact)
        .where(
            Fact.client_id == client_id,
            Fact.status.in_(
                ("confirmed", "client_provided", "external_source", "inferred"),
            ),
            (Fact.valid_from.is_(None) | (Fact.valid_from <= current_date)),
            (Fact.valid_until.is_(None) | (Fact.valid_until >= current_date)),
            ~has_open_conflict,
            ~has_non_public_evidence,
        )
        .order_by(Fact.category, Fact.key),
    )
    return list(rows.all())
