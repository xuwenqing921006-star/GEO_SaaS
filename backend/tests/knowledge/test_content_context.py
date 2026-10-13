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
def test_content_context_uses_managed_facts_without_a_review_step(
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

        async def seed_and_read() -> list[str]:
            async with factory() as database:
                evidence = Evidence(
                    client_id=client_id,
                    source_type="manual",
                    source_label="负责人核验",
                    quote="可公开核验资料",
                    observed_at=date(2026, 7, 27),
                    authorization_status="authorized",
                )
                eligible = Fact(
                    client_id=client_id,
                    category="service",
                    key="service.primary",
                    label="核心服务",
                    value="家电维修",
                    status="confirmed",
                )
                conflicted = Fact(
                    client_id=client_id,
                    category="location",
                    key="location.service_area",
                    label="服务范围",
                    value="即墨区",
                    status="confirmed",
                )
                private = Fact(
                    client_id=client_id,
                    category="contact",
                    key="contact.private",
                    label="私人电话",
                    value="13000000000",
                    status="private",
                )
                candidate = Fact(
                    client_id=client_id,
                    category="audience",
                    key="audience.primary",
                    label="服务客户",
                    value="家庭用户",
                    status="client_provided",
                )
                restricted_candidate = Fact(
                    client_id=client_id,
                    category="capability",
                    key="capability.restricted",
                    label="非公开能力",
                    value="内部资料",
                    status="client_provided",
                )
                restricted_evidence = Evidence(
                    client_id=client_id,
                    source_type="manual",
                    source_label="历史非公开资料",
                    quote="仅限内部使用",
                    observed_at=date(2026, 7, 27),
                    authorization_status="restricted",
                )
                expired = Fact(
                    client_id=client_id,
                    category="price",
                    key="price.expired",
                    label="过期价格",
                    value="旧价格",
                    status="confirmed",
                    valid_until=date(2025, 12, 31),
                )
                future = Fact(
                    client_id=client_id,
                    category="price",
                    key="price.future",
                    label="未来价格",
                    value="未来价格",
                    status="confirmed",
                    valid_from=date(2027, 1, 1),
                )
                database.add_all(
                    [
                        evidence,
                        restricted_evidence,
                        eligible,
                        conflicted,
                        private,
                        candidate,
                        restricted_candidate,
                        expired,
                        future,
                    ],
                )
                await database.flush()
                database.add_all(
                    [
                        FactEvidence(fact_id=eligible.id, evidence_id=evidence.id),
                        FactEvidence(fact_id=conflicted.id, evidence_id=evidence.id),
                        FactEvidence(fact_id=expired.id, evidence_id=evidence.id),
                        FactEvidence(fact_id=future.id, evidence_id=evidence.id),
                        FactEvidence(
                            fact_id=restricted_candidate.id,
                            evidence_id=restricted_evidence.id,
                        ),
                        FactConflict(
                            client_id=client_id,
                            fact_key=conflicted.key,
                            label=conflicted.label,
                            candidates=[],
                            status="open",
                        ),
                    ],
                )
                await database.commit()
                return [
                    fact.key
                    for fact in await list_content_eligible_facts(
                        database,
                        client_id,
                        as_of=date(2026, 7, 27),
                    )
                ]

        assert asyncio.run(seed_and_read()) == [
            "audience.primary",
            "service.primary",
        ]
