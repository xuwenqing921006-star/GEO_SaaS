import asyncio
from datetime import date
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import Evidence, Fact, FactConflict, FactEvidence
from app.knowledge_context import list_content_eligible_facts
from tests.auth.test_auth_api import build_client
from tests.clients.test_clients_api import client_payload, login


@pytest.mark.integration
def test_selecting_conflict_candidate_reopens_fact_and_links_evidence(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        created = client.post(
            "/api/v1/clients",
            headers={"X-CSRF-Token": csrf},
            json=client_payload(),
        ).json()["data"]
        client_id = UUID(created["id"])
        factory = cast(
            async_sessionmaker[AsyncSession],
            cast(FastAPI, client.app).state.session_factory,
        )

        async def seed() -> tuple[str, str]:
            async with factory() as database:
                fact = Fact(
                    client_id=client_id,
                    category="location",
                    key="location.service_area",
                    label="服务范围",
                    value="青岛市",
                    status="confirmed",
                    confidence=100,
                )
                evidence = Evidence(
                    client_id=client_id,
                    source_type="manual",
                    source_label="负责人核验",
                    quote="服务范围为即墨区",
                    observed_at=date(2026, 7, 27),
                    authorization_status="authorized",
                )
                database.add_all([fact, evidence])
                await database.flush()
                conflict = FactConflict(
                    client_id=client_id,
                    fact_key=fact.key,
                    label=fact.label,
                    candidates=[
                        {
                            "value": "即墨区",
                            "source_label": evidence.source_label,
                            "evidence_id": str(evidence.id),
                        },
                    ],
                    status="open",
                )
                database.add(conflict)
                await database.commit()
                return str(conflict.id), str(evidence.id)

        conflict_id, evidence_id = asyncio.run(seed())
        resolved = client.post(
            f"/api/v1/conflicts/{conflict_id}/resolve",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": 1,
                "action": "select",
                "selected_evidence_id": evidence_id,
                "manual_value": None,
                "resolution_note": "负责人选择可公开来源",
            },
        )
        assert resolved.status_code == 200
        assert resolved.json()["data"]["status"] == "resolved"
        facts = client.get(f"/api/v1/clients/{client_id}/facts").json()["data"]["items"]
        assert facts[0]["value"] == "即墨区"
        assert facts[0]["status"] == "client_provided"
        assert facts[0]["confidence"] == 80
        assert facts[0]["evidence"][0]["id"] == evidence_id


@pytest.mark.integration
def test_ignoring_conflict_makes_related_fact_private(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        created = client.post(
            "/api/v1/clients",
            headers={"X-CSRF-Token": csrf},
            json=client_payload(),
        ).json()["data"]
        client_id = UUID(created["id"])
        factory = cast(
            async_sessionmaker[AsyncSession],
            cast(FastAPI, client.app).state.session_factory,
        )

        async def seed() -> str:
            async with factory() as database:
                fact = Fact(
                    client_id=client_id,
                    category="service",
                    key="service.primary",
                    label="核心服务",
                    value="家电维修",
                    status="confirmed",
                    confidence=100,
                )
                evidence = Evidence(
                    client_id=client_id,
                    source_type="manual",
                    source_label="旧资料",
                    quote="提供家电维修",
                    observed_at=date(2026, 7, 27),
                    authorization_status="authorized",
                )
                database.add_all([fact, evidence])
                await database.flush()
                database.add(FactEvidence(fact_id=fact.id, evidence_id=evidence.id))
                conflict = FactConflict(
                    client_id=client_id,
                    fact_key=fact.key,
                    label=fact.label,
                    candidates=[],
                    status="open",
                )
                database.add(conflict)
                await database.commit()
                assert await list_content_eligible_facts(database, client_id) == []
                return str(conflict.id)

        conflict_id = asyncio.run(seed())
        ignored = client.post(
            f"/api/v1/conflicts/{conflict_id}/resolve",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": 1,
                "action": "ignore",
                "selected_evidence_id": None,
                "manual_value": None,
                "resolution_note": "不采用该冲突事实",
            },
        )
        assert ignored.status_code == 200
        facts = client.get(f"/api/v1/clients/{client_id}/facts").json()["data"]["items"]
        assert facts[0]["status"] == "private"

        async def read_context() -> list[Fact]:
            async with factory() as database:
                return await list_content_eligible_facts(database, client_id)

        assert asyncio.run(read_context()) == []
