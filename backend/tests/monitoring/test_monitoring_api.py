import asyncio
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.database import (
    Client,
    DiagnosticRun,
    MonitoringQuestionSet,
    StrategyBundle,
    StrategyItem,
)
from app.jobs import process_one_job
from app.monitoring import calculate_monitoring_metrics
from tests.auth.test_auth_api import build_client
from tests.clients.test_clients_api import client_payload, login


def create_customer(client: TestClient, csrf: str, *, name: str = "莱恩美术") -> str:
    payload = deepcopy(client_payload())
    payload.update(
        {
            "standard_name": name,
            "short_name": name,
            "industry_code": "art_education",
            "industry_name": "少儿美术培训",
            "district": "即墨区",
            "service_radius": "即墨区",
        },
    )
    response = client.post(
        "/api/v1/clients",
        headers={"X-CSRF-Token": csrf},
        json=payload,
    )
    assert response.status_code == 201
    return str(response.json()["data"]["id"])


async def _seed_confirmed_strategy(
    session_factory: object,
    client_id: str,
) -> list[dict[str, object]]:
    questions = [
        ("即墨少儿美术培训怎么选?", "discovery", "L2", 1),
        ("即墨少儿美术培训推荐哪家?", "recommendation", "L3", 1),
        ("孩子刚开始接触美术，咨询前应确认哪些信息?", "scenario", "L2", 2),
        ("即墨少儿美术培训机构比较时要看什么?", "comparison", "L2", 2),
        ("莱恩美术在即墨提供什么少儿美术服务?", "brand_verification", "L1", 1),
    ]
    client_uuid = UUID(client_id)
    async with session_factory() as database:  # type: ignore[operator]
        diagnostic = DiagnosticRun(
            client_id=client_uuid,
            status="succeeded",
            current_level="L1",
            scores={},
            scope=["visibility"],
            monitoring_window_days=30,
            fact_snapshot=[],
            completed_at=datetime.now(UTC),
        )
        database.add(diagnostic)
        await database.flush()
        bundle = StrategyBundle(
            client_id=client_uuid,
            diagnostic_run_id=diagnostic.id,
        )
        database.add(bundle)
        await database.flush()
        result: list[dict[str, object]] = []
        for text, family, target_level, priority in questions:
            item = StrategyItem(
                bundle_id=bundle.id,
                client_id=client_uuid,
                kind="question",
                text=text,
                family=family,
                keyword_type=None,
                provenance="system_inference",
                target_level=target_level,
                priority=priority,
                rationale="监测金标问题",
                locked=True,
                active=True,
            )
            database.add(item)
            await database.flush()
            result.append(
                {
                    "id": str(item.id),
                    "text": text,
                    "family": ("category_discovery" if family == "discovery" else family),
                    "is_brand_query": family == "brand_verification",
                    "target_level": target_level,
                    "priority": priority,
                }
            )
        await database.commit()
        return result


async def _seed_selected_keyword_strategy(
    session_factory: object,
    client_id: str,
) -> tuple[str, list[dict[str, object]]]:
    client_uuid = UUID(client_id)
    async with session_factory() as database:  # type: ignore[operator]
        diagnostic = DiagnosticRun(
            client_id=client_uuid,
            status="succeeded",
            current_level="L0",
            scores={},
            scope=["visibility"],
            monitoring_window_days=30,
            fact_snapshot=[],
            completed_at=datetime.now(UTC),
        )
        database.add(diagnostic)
        await database.flush()
        bundle = StrategyBundle(
            client_id=client_uuid,
            diagnostic_run_id=diagnostic.id,
        )
        database.add(bundle)
        await database.flush()
        item = StrategyItem(
            bundle_id=bundle.id,
            client_id=client_uuid,
            kind="keyword",
            text="即墨少儿美术培训哪家好",
            family=None,
            keyword_type="recommendation",
            provenance="ai_generated",
            target_level="L3",
            priority=1,
            rationale="用户正在寻找推荐候选",
            selected=True,
            locked=False,
            active=True,
        )
        database.add(item)
        await database.flush()
        await database.commit()
        return str(item.id), [
            {
                "id": str(item.id),
                "text": item.text,
                "family": "recommendation",
                "is_brand_query": False,
                "target_level": "L3",
                "priority": 1,
            },
        ]


def create_question_set(client: TestClient, csrf: str, client_id: str) -> dict[str, object]:
    questions = asyncio.run(_seed_confirmed_strategy(client.app.state.session_factory, client_id))
    response = client.post(
        f"/api/v1/clients/{client_id}/question-sets",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "即墨少儿美术首轮监测",
            "frozen": True,
            "questions": questions,
        },
    )
    assert response.status_code == 201
    return dict(response.json()["data"])


@pytest.mark.unit
def test_metrics_gold_values_separate_modes_and_question_denominators() -> None:
    metrics = calculate_monitoring_metrics(
        [
            {
                "status": "succeeded",
                "collection_mode": "api",
                "question_id": "discovery-core",
                "question_family": "category_discovery",
                "is_brand_query": False,
                "priority": 1,
                "brand_found": True,
                "correctly_associated": True,
                "recommended": False,
                "recommendation_supported": None,
                "facts_accurate": True,
                "source_visible": True,
            },
            {
                "status": "succeeded",
                "collection_mode": "api",
                "question_id": "discovery-core",
                "question_family": "category_discovery",
                "is_brand_query": False,
                "priority": 1,
                "brand_found": True,
                "correctly_associated": True,
                "recommended": False,
                "recommendation_supported": None,
                "facts_accurate": None,
                "source_visible": False,
            },
            {
                "status": "succeeded",
                "collection_mode": "api",
                "question_id": "recommend",
                "question_family": "recommendation",
                "is_brand_query": False,
                "priority": 1,
                "brand_found": False,
                "correctly_associated": False,
                "recommended": False,
                "recommendation_supported": None,
                "facts_accurate": None,
                "source_visible": False,
            },
            {
                "status": "succeeded",
                "collection_mode": "api",
                "question_id": "brand-check",
                "question_family": "brand_verification",
                "is_brand_query": True,
                "priority": 1,
                "brand_found": True,
                "correctly_associated": True,
                "recommended": True,
                "recommendation_supported": False,
                "facts_accurate": False,
                "source_visible": False,
            },
            {
                "status": "succeeded",
                "collection_mode": "manual_consumer",
                "question_id": "manual-discovery",
                "question_family": "category_discovery",
                "is_brand_query": False,
                "priority": 1,
                "brand_found": False,
                "correctly_associated": False,
                "recommended": False,
                "recommendation_supported": None,
                "facts_accurate": None,
                "source_visible": False,
            },
            {
                "status": "failed",
                "collection_mode": "manual_consumer",
                "brand_found": False,
                "correctly_associated": False,
                "recommended": False,
                "facts_accurate": None,
            },
            {
                "status": "not_executed",
                "collection_mode": "manual_consumer",
                "brand_found": False,
                "correctly_associated": False,
                "recommended": False,
                "facts_accurate": None,
            },
        ],
    )

    assert metrics["sample_count"] == 7
    assert metrics["effective_sample_count"] == 5
    assert metrics["failed_count"] == 1
    assert metrics["not_executed_count"] == 1
    assert metrics["brand_found_rate"] is None
    assert metrics["mode_breakdown"]["api"]["brand_found_rate"] == 66.67
    assert metrics["mode_breakdown"]["manual_consumer"]["brand_found_rate"] == 0
    assert metrics["mode_breakdown"]["api"]["recommendation_rate"] == 0
    assert metrics["mode_breakdown"]["api"]["fact_accuracy_rate"] == 50
    assert metrics["mode_breakdown"]["api"]["repeat_appearance_rate"] == 100
    assert metrics["metric_details"]["discovery"]["denominator"] is None
    assert metrics["metric_details"]["discovery"]["numerator"] is None
    assert metrics["metric_details"]["discovery"]["rate"] is None


@pytest.mark.integration
def test_monitoring_catalog_is_reduced_to_three_automatic_platforms(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        headers = {"X-CSRF-Token": csrf}
        client_id = create_customer(client, csrf)

        catalog_response = client.get("/api/v1/monitoring/platforms")
        assert catalog_response.status_code == 200
        catalog = catalog_response.json()["data"]["items"]
        by_id = {item["id"]: item for item in catalog}
        assert set(by_id) == {
            "deepseek",
            "qwen",
            "doubao",
        }
        assert all(item["mode"] == "api" for item in catalog)
        assert all(item["provider"] == item["id"] for item in catalog)
        assert all(item["priority"] in {"P0", "P1"} for item in catalog)
        assert all(item["consumer_entry_url"].startswith("https://") for item in catalog)

        question_set = create_question_set(client, csrf, client_id)
        assert question_set["frozen"] is True
        assert len(question_set["questions"]) == 5

        frozen_update = client.patch(
            f"/api/v1/question-sets/{question_set['id']}",
            headers=headers,
            json={
                "version": question_set["version"],
                "name": "不应覆盖冻结问题",
                "questions": question_set["questions"][:1],
            },
        )
        assert frozen_update.status_code == 409

        idempotency_key = str(uuid4())
        batch_payload = {
            "question_set_id": question_set["id"],
            "platform_ids": ["deepseek", "qwen", "doubao"],
            "api_sample_count": 1,
            "manual_placeholders": False,
        }
        created = client.post(
            f"/api/v1/clients/{client_id}/monitoring-batches",
            headers={**headers, "Idempotency-Key": idempotency_key},
            json=batch_payload,
        )
        assert created.status_code == 202
        batch_id = created.json()["data"]["batch"]["id"]
        assert created.json()["data"]["job"]["job_type"] == "monitoring_batch"

        replayed = client.post(
            f"/api/v1/clients/{client_id}/monitoring-batches",
            headers={**headers, "Idempotency-Key": idempotency_key},
            json=batch_payload,
        )
        assert replayed.status_code == 202
        assert replayed.json()["data"]["batch"]["id"] == batch_id

        settings = Settings(
            app_env="test",
            db_password=SecretStr("unused"),
            storage_root=tmp_path,
            model_execution_mode="fixed_mock",
        )
        assert asyncio.run(process_one_job(client.app.state.session_factory, settings)) is True

        batch_response = client.get(f"/api/v1/monitoring-batches/{batch_id}")
        assert batch_response.status_code == 200
        batch = batch_response.json()["data"]
        statuses = {(sample["platform_id"], sample["status"]) for sample in batch["samples"]}
        assert ("deepseek", "succeeded") in statuses
        assert ("qwen", "succeeded") in statuses
        assert ("doubao", "succeeded") in statuses
        assert batch["status"] == "succeeded"
        assert batch["summary"]["effective_sample_count"] == 15
        assert batch["summary"]["not_executed_count"] == 0
        automatic = next(
            sample for sample in batch["samples"] if sample["platform_id"] == "deepseek"
        )["evaluation"]
        assert automatic["facts_accurate"] is None
        assert automatic["recommendation_supported"] is None
        return

        doubao_samples = [
            sample for sample in batch["samples"] if sample["platform_id"] == "doubao"
        ]
        manual = client.post(
            f"/api/v1/monitoring-batches/{batch_id}/manual-samples",
            headers=headers,
            json={
                "items": [
                    {
                        "sample_id": doubao_samples[0]["id"],
                        "status": "succeeded",
                        "raw_answer": (
                            "选择即墨少儿美术机构时可以核对服务范围和课程信息。"
                            "莱恩美术位于即墨，建议向机构确认当前课程安排。"
                        ),
                        "asked_at": "2026-07-28T10:00:00Z",
                    },
                    {
                        "sample_id": doubao_samples[1]["id"],
                        "status": "failed",
                        "failure_reason": "消费者端暂时无法加载回答",
                        "asked_at": "2026-07-28T10:05:00Z",
                    },
                ],
            },
        )
        assert manual.status_code == 200
        changed = manual.json()["data"]["items"]
        succeeded_sample = next(item for item in changed if item["status"] == "succeeded")
        assert succeeded_sample["evaluation"]["brand_found"] is True
        assert succeeded_sample["evaluation"]["facts_accurate"] is None
        assert next(item for item in changed if item["status"] == "failed")["evaluation"] is None

        evaluation = succeeded_sample["evaluation"]
        corrected = client.put(
            f"/api/v1/monitoring-samples/{succeeded_sample['id']}/evaluation",
            headers=headers,
            json={
                "version": evaluation["version"],
                "brand_found": True,
                "correctly_associated": True,
                "recommended": False,
                "recommendation_supported": None,
                "facts_accurate": True,
                "source_visible": False,
                "mentioned_name": "莱恩美术",
                "reasons": ["提及企业，但没有形成明确推荐"],
                "incorrect_facts": [],
                "visible_sources": [],
                "note": "人工复核",
            },
        )
        assert corrected.status_code == 200
        assert corrected.json()["data"]["evaluator"] == "user"
        assert corrected.json()["data"]["suggested_actions"][0]["action_type"] == (
            "add_content_brief"
        )
        assert corrected.json()["data"]["suggested_actions"][0]["target_page"] == "P04"

        metrics_response = client.get(
            f"/api/v1/clients/{client_id}/monitoring-metrics",
            params={"from": "2026-07-01", "to": "2026-07-31"},
        )
        assert metrics_response.status_code == 200
        metrics = metrics_response.json()["data"]
        assert metrics["sample_count"] == 15
        assert metrics["effective_sample_count"] == 11
        assert metrics["failed_count"] == 1
        assert metrics["not_executed_count"] == 3
        assert metrics["time_range"] == {"from": "2026-07-01", "to": "2026-07-31"}

        feedback = client.post(
            f"/api/v1/monitoring-evaluations/{evaluation['id']}/feedback",
            headers=headers,
            json={
                "action_type": "add_content_brief",
                "reason": "已经提及品牌但未形成推荐，需要补充选择理由型内容。",
                "target_page": "P04",
            },
        )
        assert feedback.status_code == 201
        assert feedback.json()["data"]["target_level"] == "L3"
        assert feedback.json()["data"]["converted_record_type"] == "optimization_action"
        assert feedback.json()["data"]["converted_record_id"]
        replayed_feedback = client.post(
            f"/api/v1/monitoring-evaluations/{evaluation['id']}/feedback",
            headers=headers,
            json={
                "action_type": "add_content_brief",
                "reason": "已经提及品牌但未形成推荐，需要补充选择理由型内容。",
                "target_page": "P04",
            },
        )
        assert replayed_feedback.status_code == 200
        assert replayed_feedback.json()["data"]["id"] == feedback.json()["data"]["id"]

        actions = client.get(
            f"/api/v1/clients/{client_id}/optimization-actions",
            params={"target_page": "P04"},
        )
        assert actions.status_code == 200
        assert actions.json()["data"]["items"][0]["source"] == "monitoring_feedback"


@pytest.mark.integration
def test_selected_keyword_can_create_and_reuse_frozen_monitoring_baseline(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        headers = {"X-CSRF-Token": csrf}
        client_id = create_customer(client, csrf)
        keyword_id, selected_questions = asyncio.run(
            _seed_selected_keyword_strategy(client.app.state.session_factory, client_id)
        )

        frozen = client.post(
            f"/api/v1/clients/{client_id}/question-sets",
            headers=headers,
            json={
                "name": "已选关键词首轮监测",
                "frozen": True,
                "questions": selected_questions,
            },
        )
        assert frozen.status_code == 201

        async def deselect_keyword_after_freeze() -> bool:
            async with client.app.state.session_factory() as database:
                item = await database.get(StrategyItem, UUID(keyword_id))
                assert item is not None
                assert item.locked is True
                item.selected = False
                await database.commit()
                return item.locked

        assert asyncio.run(deselect_keyword_after_freeze()) is True
        created = client.post(
            f"/api/v1/clients/{client_id}/monitoring-batches",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={
                "question_set_id": frozen.json()["data"]["id"],
                "platform_ids": ["deepseek"],
                "api_sample_count": 1,
                "manual_placeholders": True,
            },
        )
        assert created.status_code == 202


@pytest.mark.integration
def test_batch_requires_frozen_confirmed_strategy_and_active_client(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        headers = {"X-CSRF-Token": csrf}
        client_id = create_customer(client, csrf)
        confirmed_questions = asyncio.run(
            _seed_confirmed_strategy(client.app.state.session_factory, client_id)
        )
        draft = client.post(
            f"/api/v1/clients/{client_id}/question-sets",
            headers=headers,
            json={
                "name": "草稿问题集",
                "frozen": False,
                "questions": confirmed_questions,
            },
        )
        assert draft.status_code == 201
        rejected = client.post(
            f"/api/v1/clients/{client_id}/monitoring-batches",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={
                "question_set_id": draft.json()["data"]["id"],
                "platform_ids": ["deepseek"],
                "api_sample_count": 1,
                "manual_placeholders": True,
            },
        )
        assert rejected.status_code == 422
        assert rejected.json()["message"] == "问题集未冻结或未选择监测平台"

        async def simulate_legacy_frozen_question_set() -> None:
            async with client.app.state.session_factory() as database:
                question_set = await database.get(
                    MonitoringQuestionSet,
                    UUID(draft.json()["data"]["id"]),
                )
                assert question_set is not None
                question_set.frozen = True
                question_set.questions = [
                    {
                        "id": str(uuid4()),
                        "text": "升级前任意冻结的问题",
                        "family": "category_discovery",
                        "is_brand_query": False,
                        "target_level": "L2",
                        "priority": 1,
                    },
                ]
                await database.commit()

        asyncio.run(simulate_legacy_frozen_question_set())
        legacy_rejected = client.post(
            f"/api/v1/clients/{client_id}/monitoring-batches",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={
                "question_set_id": draft.json()["data"]["id"],
                "platform_ids": ["deepseek"],
                "api_sample_count": 1,
                "manual_placeholders": True,
            },
        )
        assert legacy_rejected.status_code == 422
        assert legacy_rejected.json()["message"] == (
            "监测问题必须来自关键词页面已选择的关键词或已锁定的问题"
        )

        async def pause_customer() -> None:
            async with client.app.state.session_factory() as database:
                customer = await database.get(Client, UUID(client_id))
                assert customer is not None
                customer.status = "paused"
                await database.commit()

        asyncio.run(pause_customer())
        frozen = client.post(
            f"/api/v1/clients/{client_id}/question-sets",
            headers=headers,
            json={
                "name": "冻结问题集",
                "frozen": True,
                "questions": confirmed_questions,
            },
        )
        assert frozen.status_code == 201
        inactive_client = client.post(
            f"/api/v1/clients/{client_id}/monitoring-batches",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={
                "question_set_id": frozen.json()["data"]["id"],
                "platform_ids": ["deepseek"],
                "api_sample_count": 1,
                "manual_placeholders": True,
            },
        )
        assert inactive_client.status_code == 409


@pytest.mark.integration
def test_manual_mode_and_cross_client_boundaries_are_enforced(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        headers = {"X-CSRF-Token": csrf}
        first_id = create_customer(client, csrf, name="莱恩美术")
        second_id = create_customer(client, csrf, name="海岸美术")
        question_set = create_question_set(client, csrf, first_id)
        created = client.post(
            f"/api/v1/clients/{first_id}/monitoring-batches",
            headers={**headers, "Idempotency-Key": str(uuid4())},
            json={
                "question_set_id": question_set["id"],
                "platform_ids": ["deepseek", "doubao"],
                "api_sample_count": 1,
                "manual_placeholders": True,
            },
        )
        assert created.status_code == 202
        batch_id = created.json()["data"]["batch"]["id"]

        assert (
            client.get(
                f"/api/v1/clients/{second_id}/monitoring-batches/latest",
            ).status_code
            == 404
        )

        batch = client.get(f"/api/v1/monitoring-batches/{batch_id}").json()["data"]
        api_sample = next(
            sample for sample in batch["samples"] if sample["platform_id"] == "deepseek"
        )
        rejected = client.post(
            f"/api/v1/monitoring-batches/{batch_id}/manual-samples",
            headers=headers,
            json={
                "items": [
                    {
                        "sample_id": api_sample["id"],
                        "status": "failed",
                        "failure_reason": "不允许人工覆盖 API 样本",
                        "asked_at": "2026-07-28T10:00:00Z",
                    },
                ],
            },
        )
        assert rejected.status_code == 422
