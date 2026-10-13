# ruff: noqa: RUF001

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.content import _parse_model_json
from app.database import Job, StrategyItem
from app.diagnostic_probes import compact_search_service
from app.jobs import claim_next_job, process_one_job
from app.responses import ApiFailure
from app.strategy import (
    KeywordSuggestion,
    KeywordSuggestionOutput,
    _service_topics,
    _strategy_templates,
    complete_keyword_categories,
    keyword_suggestion_is_natural,
    keyword_suggestion_is_supported,
    normalize_keyword_suggestions,
    process_strategy_job,
    stored_keyword_is_natural,
)
from tests.auth.test_auth_api import build_client
from tests.clients.test_clients_api import login
from tests.diagnostics.test_diagnostics_api import (
    create_customer,
    run_worker_once,
    seed_required_facts,
)


@pytest.mark.unit
def test_service_topics_reduce_a_course_catalog_to_searchable_services() -> None:
    topics = _service_topics(
        "素描, 动漫, 国画, 创意思维绘画, 水粉, 水彩, 线描, 彩铅, 美术中高考; "
        "书法: 硬笔书法, 软笔书法",
        brand="莱恩美术",
        audience="4—16岁少儿",
    )

    assert topics == ["少儿美术培训", "硬笔书法"]
    assert all(len(topic) <= 8 for topic in topics)


@pytest.mark.unit
def test_strategy_templates_turn_full_knowledge_into_natural_short_queries() -> None:
    items = _strategy_templates(
        brand="莱恩美术",
        district="即墨区",
        service=(
            "素描、动漫、国画、创意思维绘画、水粉、水彩、线描、彩铅、"
            "美术中高考、艺术志愿填报；书法：硬笔书法、软笔书法"
        ),
        audience="适合：4-18岁少儿美术书法培训，中高考美术培训",
    )
    texts = [str(item["text"]) for item in items]

    assert "即墨少儿美术机构" in texts
    assert "即墨少儿美术哪家好" in texts
    assert "请推荐一家即墨的少儿美术机构" in texts
    assert "莱恩美术怎么样" in texts
    assert all("素描、动漫" not in text for text in texts)
    assert all("4-18岁少儿美术书法培训" not in text for text in texts)


@pytest.mark.unit
def test_keyword_naturalness_rejects_a_knowledge_base_dump() -> None:
    suggestion = KeywordSuggestion(
        main_keyword="即墨少儿美术",
        long_tail_keyword=("即墨区美术：素描、动漫、国画、创意思维绘画、水粉、水彩有哪些机构"),
        keyword_type="local_service",
        user_intent="寻找机构",
        priority=1,
    )

    assert not keyword_suggestion_is_natural(
        suggestion,
        audience="适合：4-18岁少儿美术书法培训",
    )


@pytest.mark.unit
def test_keyword_naturalness_rejects_multiple_symptoms_in_one_query() -> None:
    suggestion = KeywordSuggestion(
        main_keyword="即墨硬笔书法",
        long_tail_keyword="孩子写字勾腕、翻腕、力气重，在即墨哪里可以纠正硬笔书法姿势？",
        keyword_type="scenario",
        user_intent="纠正书写姿势",
        priority=2,
    )

    assert not keyword_suggestion_is_natural(
        suggestion,
        audience="4-16岁少儿",
    )


@pytest.mark.unit
def test_old_ai_keyword_uses_current_naturalness_rules() -> None:
    item = StrategyItem(
        kind="keyword",
        text="孩子写字勾腕、翻腕、力气重，在即墨哪里可以纠正硬笔书法姿势？",
        keyword_type="scenario",
        provenance="ai_generated",
        target_level="L1",
        priority=2,
        rationale="旧模型生成",
        main_keyword="即墨硬笔书法",
        user_intent="纠正书写姿势",
        recommended_content_type="scenario_solution",
    )

    assert not stored_keyword_is_natural(item, audience="4-16岁少儿")


@pytest.mark.unit
def test_keyword_model_output_accepts_fences_aliases_and_extra_fields() -> None:
    parsed = _parse_model_json(
        """
        ```json
        {
          "keywords": [
            {
              "primary_keyword": "即墨少儿美术",
              "question": "即墨少儿美术哪家好",
              "category": "推荐决策",
              "intent": "寻找值得进一步咨询的机构",
              "priority": "high",
              "explanation": "额外说明不应让整批结果失败"
            }
          ]
        }
        ```
        """,
        KeywordSuggestionOutput,
    )
    suggestions = normalize_keyword_suggestions(parsed)

    assert len(suggestions) == 1
    assert suggestions[0].main_keyword == "即墨少儿美术"
    assert suggestions[0].long_tail_keyword == "即墨少儿美术哪家好"
    assert suggestions[0].keyword_type == "recommendation"
    assert suggestions[0].priority == 1


@pytest.mark.unit
def test_keyword_support_checks_saved_text_and_completes_all_six_categories() -> None:
    unsupported = KeywordSuggestion(
        main_keyword="即墨少儿美术",
        long_tail_keyword="青岛宠物医院哪家好",
        keyword_type="recommendation",
        user_intent="寻找机构",
        priority=1,
    )
    assert not keyword_suggestion_is_supported(
        unsupported,
        brand="莱恩美术",
        district="即墨",
        service_topics=["少儿美术"],
    )

    generated = [
        {
            "kind": "keyword",
            "text": f"即墨少儿美术问题{index}",
            "keyword_type": "local_service",
        }
        for index in range(12)
    ]
    fallback = [
        {
            "kind": "keyword",
            "text": f"{keyword_type}备选",
            "keyword_type": keyword_type,
        }
        for keyword_type in (
            "local_service",
            "brand",
            "recommendation",
            "scenario",
            "service_detail",
            "comparison",
        )
    ]
    seen = {str(item["text"]) for item in generated}
    complete_keyword_categories(generated, fallback, seen)

    assert {str(item["keyword_type"]) for item in generated} == {
        "local_service",
        "brand",
        "recommendation",
        "scenario",
        "service_detail",
        "comparison",
    }


@pytest.mark.unit
def test_keyword_normalization_skips_a_malformed_item_without_stopping_the_batch() -> None:
    output = KeywordSuggestionOutput(
        items=[
            {
                "main_keyword": "即墨少儿美术",
                "long_tail_keyword": "即墨少儿美术推荐",
                "keyword_type": "recommendation",
                "user_intent": "寻找机构",
                "priority": [],
            },
            {
                "main_keyword": "莱恩美术",
                "long_tail_keyword": "莱恩美术怎么样",
                "keyword_type": "brand",
                "user_intent": "了解品牌",
                "priority": 1,
            },
        ],
    )

    normalized = normalize_keyword_suggestions(output)

    assert [item.long_tail_keyword for item in normalized] == ["莱恩美术怎么样"]


def create_diagnostic(client, csrf: str, client_id: str, tmp_path: Path) -> str:
    response = client.post(
        f"/api/v1/clients/{client_id}/diagnostics",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid4())},
        json={
            "scope": ["entity", "evidence", "content", "source", "visibility"],
            "monitoring_window_days": 30,
        },
    )
    assert response.status_code == 202
    run_worker_once(client, tmp_path)
    diagnostic = client.get(
        f"/api/v1/clients/{client_id}/diagnostics/latest",
    ).json()["data"]
    return str(diagnostic["id"])


def generate_strategy(
    client,
    csrf: str,
    client_id: str,
    diagnostic_id: str,
    tmp_path: Path,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/clients/{client_id}/strategy/generate",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid4())},
        json={
            "diagnostic_run_id": diagnostic_id,
            "include_families": [
                "discovery",
                "recommendation",
                "scenario",
                "comparison",
                "brand_verification",
            ],
            "brief_count": 3,
        },
    )
    assert response.status_code == 202
    run_worker_once(client, tmp_path)
    strategy = client.get(f"/api/v1/clients/{client_id}/strategy")
    assert strategy.status_code == 200
    return strategy.json()["data"]


@pytest.mark.integration
@pytest.mark.parametrize(
    ("industry_code", "service", "audience", "forbidden_term"),
    [
        ("art_education", "少儿美术培训", "即墨区 4—12 岁儿童及家长", "家电"),
        ("housekeeping", "家庭保洁", "即墨区有日常保洁需求的家庭", "师资"),
        ("repair", "家电维修", "即墨区需要家电检修的家庭", "课程"),
    ],
)
def test_strategy_generates_five_explainable_families_for_local_service_industries(
    tmp_path: Path,
    industry_code: str,
    service: str,
    audience: str,
    forbidden_term: str,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf, industry_code=industry_code)
        seed_required_facts(
            client,
            csrf,
            client_id,
            service=service,
            audience=audience,
        )
        diagnostic_id = create_diagnostic(client, csrf, client_id, tmp_path)
        strategy = generate_strategy(client, csrf, client_id, diagnostic_id, tmp_path)

        questions = [item for item in strategy["items"] if item["kind"] == "question"]
        assert {item["family"] for item in questions} == {
            "discovery",
            "recommendation",
            "scenario",
            "comparison",
            "brand_verification",
        }
        assert all(item["provenance"] == "system_inference" for item in questions)
        assert all("依据已确认事实" in item["rationale"] for item in questions)
        assert all("搜索量" not in item["rationale"] for item in strategy["items"])
        assert all("竞争度" not in item["rationale"] for item in strategy["items"])
        assert all(forbidden_term not in item["text"] for item in strategy["items"])
        assert compact_search_service(service, audience) in " ".join(
            item["text"] for item in strategy["items"]
        )
        keywords = [item for item in strategy["items"] if item["kind"] == "keyword"]
        assert len(keywords) >= 12
        assert {
            "local_service",
            "brand",
            "recommendation",
            "scenario",
            "service_detail",
            "comparison",
        }.issubset({item["keyword_type"] for item in keywords})
        assert all(item["main_keyword"] for item in keywords)
        assert all(item["user_intent"] for item in keywords)
        assert all(item["selected"] is False for item in keywords)
        assert all(item["generated_count"] == 0 for item in keywords)
        assert len(strategy["briefs"]) == 3
        assert all(brief["required_fact_ids"] for brief in strategy["briefs"])

        first_keyword = keywords[0]
        selected = client.patch(
            f"/api/v1/strategy-items/{first_keyword['id']}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": first_keyword["version"],
                "selected": True,
            },
        )
        assert selected.status_code == 200
        assert selected.json()["data"]["selected"] is True


@pytest.mark.integration
def test_locked_manual_strategy_item_survives_regeneration_and_stale_patch_fails(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        seed_required_facts(client, csrf, client_id)
        diagnostic_id = create_diagnostic(client, csrf, client_id, tmp_path)
        strategy = generate_strategy(client, csrf, client_id, diagnostic_id, tmp_path)
        item = next(value for value in strategy["items"] if value["kind"] == "question")
        custom_text = "即墨家长第一次了解少儿美术时，应该核实哪些公开信息?"
        updated = client.patch(
            f"/api/v1/strategy-items/{item['id']}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": item["version"],
                "text": custom_text,
                "priority": 1,
                "locked": True,
            },
        )
        assert updated.status_code == 200
        stale = client.patch(
            f"/api/v1/strategy-items/{item['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"version": item["version"], "priority": 3},
        )
        assert stale.status_code == 409

        regenerated = generate_strategy(client, csrf, client_id, diagnostic_id, tmp_path)
        preserved = next(value for value in regenerated["items"] if value["id"] == item["id"])
        assert preserved["text"] == custom_text
        assert preserved["locked"] is True
        assert preserved["priority"] == 1
        assert (
            len(
                [
                    value
                    for value in regenerated["items"]
                    if value["kind"] == "question"
                    and value["family"] == preserved["family"]
                    and value["active"]
                ],
            )
            == 1
        )


@pytest.mark.integration
def test_failed_regeneration_keeps_the_last_successful_strategy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        seed_required_facts(client, csrf, client_id)
        first_diagnostic_id = create_diagnostic(client, csrf, client_id, tmp_path)
        first_strategy = generate_strategy(
            client,
            csrf,
            client_id,
            first_diagnostic_id,
            tmp_path,
        )
        active_item_ids = {item["id"] for item in first_strategy["items"]}

        second_diagnostic_id = create_diagnostic(client, csrf, client_id, tmp_path)
        queued = client.post(
            f"/api/v1/clients/{client_id}/strategy/generate",
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid4())},
            json={
                "diagnostic_run_id": second_diagnostic_id,
                "include_families": [
                    "discovery",
                    "recommendation",
                    "scenario",
                    "comparison",
                    "brand_verification",
                ],
                "brief_count": 3,
            },
        )
        assert queued.status_code == 202

        async def fail_generation(*args: object, **kwargs: object) -> list[dict[str, object]]:
            raise ApiFailure(
                status_code=429,
                code=42902,
                message="模型服务暂时不可用",
                retryable=True,
            )

        monkeypatch.setattr(
            "app.strategy._strategy_templates_for_job",
            fail_generation,
        )
        claimed_job = asyncio.run(claim_next_job(client.app.state.session_factory))
        assert claimed_job is not None
        assert claimed_job.job_type == "strategy_generate"
        settings = Settings(
            app_env="test",
            db_password=SecretStr("unused"),
            storage_root=tmp_path,
            model_execution_mode="fixed_mock",
        )
        assert (
            asyncio.run(
                process_strategy_job(
                    client.app.state.session_factory,
                    claimed_job,
                    settings,
                ),
            )
            is True
        )

        after_failure = client.get(
            f"/api/v1/clients/{client_id}/strategy",
        ).json()["data"]
        assert after_failure["diagnostic_run_id"] == first_diagnostic_id
        assert {item["id"] for item in after_failure["items"]} == active_item_ids
        job = client.get(f"/api/v1/jobs/{queued.json()['data']['job_id']}")
        assert job.status_code == 200
        assert job.json()["data"]["status"] == "failed"
        assert job.json()["data"]["error_message"] == "模型服务暂时不可用"


@pytest.mark.integration
def test_regeneration_archives_briefs_that_already_have_fact_snapshots(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        seed_required_facts(client, csrf, client_id)
        diagnostic_id = create_diagnostic(client, csrf, client_id, tmp_path)
        first_strategy = generate_strategy(
            client,
            csrf,
            client_id,
            diagnostic_id,
            tmp_path,
        )
        first_brief = first_strategy["briefs"][0]
        created_document = client.post(
            f"/api/v1/clients/{client_id}/documents",
            headers={"X-CSRF-Token": csrf},
            json={
                "brief_id": first_brief["id"],
                "title": first_brief["title"],
            },
        )
        assert created_document.status_code == 201
        run_worker_once(client, tmp_path)

        regenerated = generate_strategy(
            client,
            csrf,
            client_id,
            diagnostic_id,
            tmp_path,
        )

        assert regenerated["version"] == first_strategy["version"] + 1
        assert all(brief["id"] != first_brief["id"] for brief in regenerated["briefs"])
        archived = client.get(f"/api/v1/briefs/{first_brief['id']}")
        assert archived.status_code == 200
        assert archived.json()["data"]["status"] == "archived"


@pytest.mark.integration
def test_duplicate_active_generation_returns_the_existing_job(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        seed_required_facts(client, csrf, client_id)
        diagnostic_id = create_diagnostic(client, csrf, client_id, tmp_path)
        payload = {
            "diagnostic_run_id": diagnostic_id,
            "include_families": [
                "discovery",
                "recommendation",
                "scenario",
                "comparison",
                "brand_verification",
            ],
            "brief_count": 30,
        }

        first = client.post(
            f"/api/v1/clients/{client_id}/strategy/generate",
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid4())},
            json=payload,
        )
        assert first.status_code == 202

        for brief_count in range(1, 21):
            unrelated = client.post(
                f"/api/v1/clients/{client_id}/strategy/generate",
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid4())},
                json={**payload, "brief_count": brief_count},
            )
            assert unrelated.status_code == 202

        second = client.post(
            f"/api/v1/clients/{client_id}/strategy/generate",
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid4())},
            json=payload,
        )

        assert second.status_code == 202
        assert second.json()["data"]["job_id"] == first.json()["data"]["job_id"]


@pytest.mark.integration
def test_unexpected_strategy_exception_marks_the_job_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        seed_required_facts(client, csrf, client_id)
        diagnostic_id = create_diagnostic(client, csrf, client_id, tmp_path)
        queued = client.post(
            f"/api/v1/clients/{client_id}/strategy/generate",
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid4())},
            json={
                "diagnostic_run_id": diagnostic_id,
                "include_families": ["discovery"],
                "brief_count": 1,
            },
        )
        assert queued.status_code == 202

        async def crash_strategy_job(*args: object, **kwargs: object) -> bool:
            session_factory = args[0]
            claimed_job = args[1]
            async with session_factory() as database:  # type: ignore[operator]
                stored_job = await database.get(Job, claimed_job.id)  # type: ignore[union-attr]
                assert stored_job is not None
                stored_job.lease_until = datetime.now(UTC) - timedelta(seconds=1)
                await database.commit()
            raise RuntimeError("unexpected strategy failure")

        monkeypatch.setattr(
            "app.strategy.process_strategy_job",
            crash_strategy_job,
        )
        settings = Settings(
            app_env="test",
            db_password=SecretStr("unused"),
            storage_root=tmp_path,
            model_execution_mode="fixed_mock",
        )

        assert (
            asyncio.run(
                process_one_job(
                    client.app.state.session_factory,
                    settings,
                ),
            )
            is True
        )
        job = client.get(f"/api/v1/jobs/{queued.json()['data']['job_id']}")
        assert job.status_code == 200
        assert job.json()["data"]["status"] == "failed"
        assert job.json()["data"]["error_message"] == "任务处理异常，请稍后重试"


@pytest.mark.integration
def test_strategy_requires_matching_successful_diagnostic(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        seed_required_facts(client, csrf, client_id)
        response = client.post(
            f"/api/v1/clients/{client_id}/strategy/generate",
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid4())},
            json={
                "diagnostic_run_id": str(uuid4()),
                "include_families": ["discovery"],
                "brief_count": 1,
            },
        )
        assert response.status_code == 422
        assert response.json()["message"] == "诊断或事实不满足策略生成条件"


@pytest.mark.integration
def test_strategy_rejects_a_diagnostic_after_its_fact_snapshot_changes(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        facts = seed_required_facts(client, csrf, client_id)
        diagnostic_id = create_diagnostic(client, csrf, client_id, tmp_path)
        service_fact = facts[0]
        edited = client.patch(
            f"/api/v1/facts/{service_fact['id']}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": service_fact["version"],
                "value": "家电维修",
            },
        ).json()["data"]
        reconfirmed = client.post(
            f"/api/v1/facts/{service_fact['id']}/confirm",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": edited["version"],
                "evidence_ids": [evidence["id"] for evidence in edited["evidence"]],
                "confirmation_note": "重新核验并允许公开",
            },
        )
        assert reconfirmed.status_code == 200

        response = client.post(
            f"/api/v1/clients/{client_id}/strategy/generate",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "diagnostic_run_id": diagnostic_id,
                "include_families": ["discovery"],
                "brief_count": 1,
            },
        )
        assert response.status_code == 422
        assert response.json()["message"] == "诊断使用的事实已变化，请重新运行诊断"


@pytest.mark.integration
def test_strategy_idempotency_key_rejects_different_parameters(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        seed_required_facts(client, csrf, client_id)
        diagnostic_id = create_diagnostic(client, csrf, client_id, tmp_path)
        job_key = str(uuid4())
        request = {
            "diagnostic_run_id": diagnostic_id,
            "include_families": ["discovery"],
            "brief_count": 1,
        }
        first = client.post(
            f"/api/v1/clients/{client_id}/strategy/generate",
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": job_key},
            json=request,
        )
        assert first.status_code == 202
        conflict = client.post(
            f"/api/v1/clients/{client_id}/strategy/generate",
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": job_key},
            json={**request, "brief_count": 2},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == 40903


@pytest.mark.integration
def test_brief_cannot_drop_or_replace_its_public_fact_evidence_chain(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        seed_required_facts(client, csrf, client_id)
        diagnostic_id = create_diagnostic(client, csrf, client_id, tmp_path)
        strategy = generate_strategy(client, csrf, client_id, diagnostic_id, tmp_path)
        brief = strategy["briefs"][0]

        empty = client.patch(
            f"/api/v1/briefs/{brief['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"version": brief["version"], "required_fact_ids": []},
        )
        assert empty.status_code == 400

        unconfirmed = client.post(
            f"/api/v1/clients/{client_id}/facts",
            headers={"X-CSRF-Token": csrf},
            json={
                "category": "service",
                "key": "service.unverified",
                "label": "未核验服务",
                "value": "未核验增值服务",
                "status": "client_provided",
                "valid_from": None,
                "valid_until": None,
                "evidence_ids": [],
            },
        ).json()["data"]
        with_private_evidence = client.post(
            f"/api/v1/facts/{unconfirmed['id']}/evidence",
            headers={"X-CSRF-Token": csrf},
            json={
                "source_type": "manual",
                "material_id": None,
                "source_label": "内部记录",
                "source_url": None,
                "quote": "仅内部使用",
                "observed_at": "2026-07-27",
                "authorization_status": "restricted",
            },
        ).json()["data"]
        rejected = client.patch(
            f"/api/v1/briefs/{brief['id']}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": brief["version"],
                "required_fact_ids": [unconfirmed["id"]],
                "required_evidence_ids": [
                    with_private_evidence["evidence"][0]["id"],
                ],
            },
        )
        assert rejected.status_code == 422
