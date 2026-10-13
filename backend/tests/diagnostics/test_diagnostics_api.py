# ruff: noqa: RUF001

import asyncio
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.diagnostic_probes import (
    build_auto_probe_questions,
    build_competitive_insights,
    current_platform_results,
)
from app.jobs import process_one_job
from app.strategy import calculate_platform_visibility, calculate_readiness_scores
from tests.auth.test_auth_api import build_client
from tests.clients.test_clients_api import client_payload, login


def create_customer(
    client: TestClient,
    csrf: str,
    *,
    industry_code: str = "art_education",
) -> str:
    payload = deepcopy(client_payload())
    payload.update(
        {
            "standard_name": "莱恩美术",
            "short_name": "莱恩美术",
            "industry_code": industry_code,
            "industry_name": "本地生活服务",
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


def confirm_fact(
    client: TestClient,
    csrf: str,
    client_id: str,
    *,
    category: str,
    key: str,
    label: str,
    value: str,
) -> dict[str, object]:
    headers = {"X-CSRF-Token": csrf}
    created = client.post(
        f"/api/v1/clients/{client_id}/facts",
        headers=headers,
        json={
            "category": category,
            "key": key,
            "label": label,
            "value": value,
            "status": "client_provided",
            "valid_from": None,
            "valid_until": None,
            "evidence_ids": [],
        },
    )
    assert created.status_code == 201
    fact = created.json()["data"]
    with_evidence = client.post(
        f"/api/v1/facts/{fact['id']}/evidence",
        headers=headers,
        json={
            "source_type": "manual",
            "material_id": None,
            "source_label": "客户资料与负责人核验",
            "source_url": None,
            "quote": value,
            "observed_at": "2026-07-27",
            "authorization_status": "authorized",
        },
    )
    assert with_evidence.status_code == 201
    fact_with_evidence = with_evidence.json()["data"]
    confirmed = client.post(
        f"/api/v1/facts/{fact['id']}/confirm",
        headers=headers,
        json={
            "version": fact_with_evidence["version"],
            "evidence_ids": [fact_with_evidence["evidence"][0]["id"]],
            "confirmation_note": "已核验并允许公开",
        },
    )
    assert confirmed.status_code == 200
    return confirmed.json()["data"]


def seed_required_facts(
    client: TestClient,
    csrf: str,
    client_id: str,
    *,
    service: str = "少儿美术培训",
    audience: str = "即墨区 4—12 岁儿童及家长",
) -> list[dict[str, object]]:
    return [
        confirm_fact(
            client,
            csrf,
            client_id,
            category="service",
            key="service.primary",
            label="核心服务",
            value=service,
        ),
        confirm_fact(
            client,
            csrf,
            client_id,
            category="audience",
            key="audience.primary",
            label="适用客群",
            value=audience,
        ),
        confirm_fact(
            client,
            csrf,
            client_id,
            category="location",
            key="location.service_area",
            label="服务范围",
            value="即墨区",
        ),
    ]


def run_worker_once(client: TestClient, tmp_path: Path) -> None:
    settings = Settings(
        app_env="test",
        db_password=SecretStr("unused"),
        storage_root=tmp_path,
        model_execution_mode="fixed_mock",
    )
    processed = asyncio.run(process_one_job(client.app.state.session_factory, settings))
    assert processed is True


@pytest.mark.unit
def test_readiness_score_boundaries_are_explicit_and_bounded() -> None:
    empty = calculate_readiness_scores(
        entity_present_count=0,
        entity_total_count=10,
        fact_count=0,
        evidenced_fact_count=0,
        question_family_count=0,
        content_type_count=0,
        public_presence_count=None,
        ai_visibility_score=None,
    )
    assert empty == {
        "entity_completeness": 0,
        "evidence_coverage": 0,
        "content_coverage": 0,
        "source_coverage": None,
        "ai_visibility": None,
    }
    saturated = calculate_readiness_scores(
        entity_present_count=99,
        entity_total_count=10,
        fact_count=10,
        evidenced_fact_count=99,
        question_family_count=99,
        content_type_count=99,
        public_presence_count=99,
        ai_visibility_score=100,
    )
    assert all(0 <= score <= 100 for score in saturated.values() if score is not None)
    assert saturated["content_coverage"] == 100
    assert saturated["source_coverage"] == 100


@pytest.mark.unit
def test_auto_probe_questions_compact_detailed_facts_into_real_search_queries() -> None:
    questions = build_auto_probe_questions(
        brand="莱恩美术",
        district="即墨区",
        service=(
            "美术：素描、动漫、国画、创意思维绘画、水粉、水彩、线描、彩铅、"
            "美术中高考、艺术志愿填报；书法：硬笔书法、软笔书法"
        ),
        audience="4-18岁少儿美术书法培训",
    )

    assert [question["text"] for question in questions] == [
        "即墨少儿美术",
        "即墨少儿美术哪家好",
        "莱恩美术怎么样",
    ]
    assert all(len(question["text"]) <= 12 for question in questions)


@pytest.mark.unit
def test_platform_visibility_score_uses_only_real_evaluated_samples() -> None:
    result = calculate_platform_visibility(
        platform_id="deepseek",
        platform_name="DeepSeek",
        collection_mode="api",
        evaluations=[
            {
                "question_id": "recommend-1",
                "question_family": "recommendation",
                "priority": 1,
                "brand_found": True,
                "correctly_associated": True,
                "recommended": True,
                "matched_fact_count": 1,
                "source_visible": True,
            },
            {
                "question_id": "recommend-1",
                "question_family": "recommendation",
                "priority": 1,
                "brand_found": True,
                "correctly_associated": True,
                "recommended": True,
                "matched_fact_count": 1,
                "source_visible": True,
            },
        ],
        measured_at="2026-07-28T10:00:00+00:00",
    )
    assert result["score"] == 100
    assert result["grade"] == "excellent"
    assert result["status"] == "recommended"
    assert result["valid_sample_count"] == 2

    no_source_api = calculate_platform_visibility(
        platform_id="deepseek",
        platform_name="DeepSeek",
        collection_mode="api",
        evaluations=[
            {
                "question_id": "recommend-1",
                "question_family": "recommendation",
                "brand_found": True,
                "correctly_associated": True,
                "recommended": True,
                "matched_fact_count": 1,
                "source_visible": False,
                "source_evaluable": False,
            },
        ],
        measured_at="2026-07-28T10:00:00+00:00",
    )
    assert no_source_api["score"] == 100
    assert no_source_api["metrics"]["source_rate"] is None

    brand_only = calculate_platform_visibility(
        platform_id="deepseek",
        platform_name="DeepSeek",
        collection_mode="api",
        evaluations=[
            {
                "question_id": "discover-1",
                "question_family": "discovery",
                "brand_found": False,
                "correctly_associated": False,
                "recommended": False,
                "matched_fact_count": 0,
                "source_visible": False,
                "source_evaluable": False,
            },
            {
                "question_id": "brand-1",
                "question_family": "brand_verification",
                "brand_found": True,
                "correctly_associated": True,
                "recommended": False,
                "matched_fact_count": 1,
                "source_visible": False,
                "source_evaluable": False,
            },
        ],
        measured_at="2026-07-28T10:00:00+00:00",
    )
    assert brand_only["score"] == 0
    assert brand_only["status"] == "brand_only"
    assert "直接询问品牌" in str(brand_only["comment"])

    untested = calculate_platform_visibility(
        platform_id="doubao",
        platform_name="豆包",
        collection_mode="manual_consumer",
        evaluations=[],
        measured_at=None,
    )
    assert untested["score"] is None
    assert untested["grade"] is None
    assert untested["status"] == "untested"


@pytest.mark.unit
def test_historical_diagnostic_gets_wenxin_placeholder() -> None:
    results = current_platform_results(
        [
            {
                "platform_id": "deepseek",
                "platform_name": "DeepSeek",
                "status": "not_found",
                "score": 0,
                "questions": [{"id": "discovery", "text": "即墨少儿美术"}],
            },
        ],
    )
    assert [result["platform_id"] for result in results] == [
        "deepseek",
        "qwen",
        "doubao",
        "wenxin",
    ]
    assert results[-1]["status"] == "unconfigured"
    assert results[-1]["questions"] == [{"id": "discovery", "text": "即墨少儿美术"}]


@pytest.mark.unit
def test_competitive_insights_are_derived_from_observed_sources() -> None:
    insights = build_competitive_insights(
        [
            {
                "platform_id": "qwen",
                "platform_name": "通义千问",
                "status": "recommended",
                "source_capability": "available",
                "competitors": [
                    {
                        "name": "星河美术",
                        "mention_count": 1,
                        "recommendation_count": 1,
                        "appeared_before_client_count": 1,
                        "source_urls": ["https://baijiahao.baidu.com/s?id=1"],
                        "reasons": ["进入了推荐决策回答"],
                        "answer_excerpts": [
                            "星河美术提供试听、适龄课程和清晰的师资介绍，可作为备选。",
                        ],
                        "source_evidence": [
                            {
                                "title": "星河美术课程介绍",
                                "url": "https://baijiahao.baidu.com/s?id=1",
                                "site_name": "百家号",
                                "snippet": "包含课程、师资、试听和适合年龄说明。",
                            },
                        ],
                    },
                ],
                "sources": [
                    {
                        "title": "星河美术课程介绍",
                        "url": "https://baijiahao.baidu.com/s?id=1",
                        "channel_id": "baijia",
                        "channel_name": "百家号",
                        "question_ids": ["recommendation"],
                        "snippet": "包含课程、师资、试听和适合年龄说明。",
                    },
                ],
            },
            {
                "platform_id": "wenxin",
                "platform_name": "文心一言",
                "status": "mentioned",
                "source_capability": "available",
                "competitors": [],
                "sources": [
                    {
                        "title": "即墨少儿美术怎么选",
                        "url": "https://baijiahao.baidu.com/s?id=2",
                        "channel_id": "baijia",
                        "channel_name": "百家号",
                        "question_ids": ["category-discovery"],
                    },
                ],
            },
            {
                "platform_id": "deepseek",
                "platform_name": "DeepSeek",
                "status": "mentioned",
                "source_capability": "not_supported",
                "competitors": [],
                "sources": [],
            },
        ],
    )
    assert insights["evidence_platform_count"] == 2
    assert insights["source_count"] == 2
    assert insights["competitors"][0]["name"] == "星河美术"
    assert insights["competitors"][0]["answer_excerpts"]
    assert {signal["code"] for signal in insights["competitors"][0]["strength_signals"]} >= {
        "recommendation_match",
        "position_lead",
        "service_detail",
        "trust_evidence",
    }
    assert any("选择标准" in action for action in insights["competitors"][0]["recommended_actions"])
    assert insights["channel_signals"][0]["channel_name"] == "百家号"
    assert insights["channel_signals"][0]["platform_count"] == 2
    assert "不是平台公开或内部排序权重" in insights["methodology_note"]


@pytest.mark.integration
def test_diagnostic_blocks_until_public_core_facts_are_ready(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        blocked = client.post(
            f"/api/v1/clients/{client_id}/diagnostics",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "scope": ["entity", "evidence", "content", "source", "visibility"],
                "monitoring_window_days": 30,
            },
        )
        assert blocked.status_code == 422
        assert blocked.json()["message"] == "企业名称、地区或服务事实不足，无法诊断"
        assert (
            client.get(
                f"/api/v1/clients/{client_id}/diagnostics/latest",
            ).json()["data"]
            is None
        )

        facts = seed_required_facts(client, csrf, client_id)
        accepted = client.post(
            f"/api/v1/clients/{client_id}/diagnostics",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "scope": ["entity", "evidence", "content", "source", "visibility"],
                "monitoring_window_days": 30,
            },
        )
        assert accepted.status_code == 202
        assert accepted.json()["data"]["status"] == "queued"

        run_worker_once(client, tmp_path)
        result = client.get(f"/api/v1/clients/{client_id}/diagnostics/latest")
        assert result.status_code == 200
        diagnostic = result.json()["data"]
        assert diagnostic["status"] == "succeeded"
        assert diagnostic["current_level"] == "L0"
        assert diagnostic["scores"]["entity_completeness"] == 50
        assert diagnostic["scores"]["evidence_coverage"] == 100
        assert diagnostic["scores"]["ai_visibility"] is None
        assert diagnostic["overall_score"] is None
        assert diagnostic["overall_grade"] is None
        assert diagnostic["evaluated_platform_count"] == 0
        assert diagnostic["total_platform_count"] >= 2
        assert diagnostic["effective_sample_count"] == 0
        assert any(
            platform["platform_id"] == "deepseek"
            and platform["status"] == "unconfigured"
            and platform["score"] is None
            for platform in diagnostic["platform_results"]
        )
        assert diagnostic["is_stale"] is False
        assert diagnostic["changed_fact_count"] == 0
        assert diagnostic["scope"] == [
            "entity",
            "evidence",
            "content",
            "source",
            "visibility",
        ]
        assert diagnostic["monitoring_window_days"] == 30
        assert diagnostic["fact_snapshot_id"]
        assert any(
            issue["category"] == "visibility" and "没有取得有效回答" in issue["explanation"]
            for issue in diagnostic["issues"]
        )
        assert all("搜索量" not in issue["explanation"] for issue in diagnostic["issues"])

        changed = client.patch(
            f"/api/v1/facts/{facts[0]['id']}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": facts[0]["version"],
                "value": "少儿美术培训与书法课程",
            },
        )
        assert changed.status_code == 200
        historical = client.get(
            f"/api/v1/clients/{client_id}/diagnostics/latest",
        ).json()["data"]
        assert historical["is_stale"] is True
        assert historical["changed_fact_count"] == 1


@pytest.mark.integration
def test_diagnostic_is_idempotent_and_issue_patch_uses_optimistic_lock(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf, industry_code="repair")
        seed_required_facts(
            client,
            csrf,
            client_id,
            service="家电维修",
            audience="即墨区需要家电检修的家庭",
        )
        job_key = str(uuid4())
        request = {
            "scope": ["entity", "evidence", "content", "source", "visibility"],
            "monitoring_window_days": 30,
        }
        first = client.post(
            f"/api/v1/clients/{client_id}/diagnostics",
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": job_key},
            json=request,
        )
        second = client.post(
            f"/api/v1/clients/{client_id}/diagnostics",
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": job_key},
            json=request,
        )
        assert first.json()["data"]["job_id"] == second.json()["data"]["job_id"]
        conflicting = client.post(
            f"/api/v1/clients/{client_id}/diagnostics",
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": job_key},
            json={**request, "monitoring_window_days": 60},
        )
        assert conflicting.status_code == 409
        assert conflicting.json()["code"] == 40903
        run_worker_once(client, tmp_path)

        diagnostic = client.get(
            f"/api/v1/clients/{client_id}/diagnostics/latest",
        ).json()["data"]
        issue = diagnostic["issues"][0]
        updated = client.patch(
            f"/api/v1/diagnostic-issues/{issue['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"version": issue["version"], "status": "ignored", "note": "当前阶段暂缓"},
        )
        assert updated.status_code == 200
        stale = client.patch(
            f"/api/v1/diagnostic-issues/{issue['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"version": issue["version"], "status": "resolved", "note": "旧页面提交"},
        )
        assert stale.status_code == 409
        assert stale.json()["message"] == "诊断问题已被更新，请刷新后重试"


@pytest.mark.integration
def test_diagnostic_scope_controls_scores_and_issues(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        seed_required_facts(client, csrf, client_id)
        accepted = client.post(
            f"/api/v1/clients/{client_id}/diagnostics",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={"scope": ["entity"], "monitoring_window_days": 14},
        )
        assert accepted.status_code == 202
        run_worker_once(client, tmp_path)

        diagnostic = client.get(
            f"/api/v1/clients/{client_id}/diagnostics/latest",
        ).json()["data"]
        assert diagnostic["scope"] == ["entity"]
        assert diagnostic["monitoring_window_days"] == 14
        assert diagnostic["scores"]["entity_completeness"] == 50
        assert all(
            diagnostic["scores"][key] is None
            for key in (
                "evidence_coverage",
                "content_coverage",
                "source_coverage",
                "ai_visibility",
            )
        )
        assert [issue["category"] for issue in diagnostic["issues"]] == ["entity"]


@pytest.mark.integration
def test_paused_client_cannot_start_a_diagnostic(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        seed_required_facts(client, csrf, client_id)
        version = client.get(f"/api/v1/clients/{client_id}").json()["data"]["version"]
        paused = client.patch(
            f"/api/v1/clients/{client_id}",
            headers={"X-CSRF-Token": csrf},
            json={"version": version, "status": "paused"},
        )
        assert paused.status_code == 200

        response = client.post(
            f"/api/v1/clients/{client_id}/diagnostics",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "scope": ["entity", "evidence", "content", "source", "visibility"],
                "monitoring_window_days": 30,
            },
        )
        assert response.status_code == 409
        assert response.json()["message"] == "客户已暂停或归档，不能创建诊断任务"
