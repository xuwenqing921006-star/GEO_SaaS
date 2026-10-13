from datetime import date
from urllib.parse import urlparse
from uuid import uuid4

import pytest

import app.channels as channel_module
from app.channels import (
    CATALOG_VERIFIED_ON,
    CATALOG_VERSION,
    CHANNEL_CATALOG,
    NO_GUARANTEE,
    _score_channel,
)
from app.database import Client, ContentBrief
from tests.auth.test_auth_api import build_client
from tests.clients.test_clients_api import login
from tests.diagnostics.test_diagnostics_api import (
    create_customer,
    run_worker_once,
    seed_required_facts,
)
from tests.strategy.test_strategy_api import create_diagnostic, generate_strategy


def test_catalog_is_versioned_unique_and_uses_official_https_entries() -> None:
    ids = [item["id"] for item in CHANNEL_CATALOG]
    assert len(ids) == len(set(ids))
    assert CATALOG_VERSION.startswith("2026.")
    assert all(urlparse(str(item["official_url"])).scheme == "https" for item in CHANNEL_CATALOG)
    assert {item["ownership"] for item in CHANNEL_CATALOG} == {
        "operator_publishable",
        "client_required",
        "partner_cooperation",
    }
    assert sum(item["ownership"] == "operator_publishable" for item in CHANNEL_CATALOG) >= 5
    assert all("保证" not in " ".join(item["risks"]) for item in CHANNEL_CATALOG)


def test_local_service_industries_receive_distinct_content_aware_matrices() -> None:
    inputs = {
        "art_education": ("少儿美术培训", "selection_guide"),
        "housekeeping": ("家庭保洁", "local_scenario"),
        "repair": ("家电维修", "faq"),
    }
    matrices: dict[str, tuple[str, ...]] = {}
    for industry_code, (industry_name, content_type) in inputs.items():
        client = Client(
            standard_name=f"{industry_name}测试客户",
            normalized_name=f"{industry_code}-channel-test",
            short_name=industry_name,
            industry_code=industry_code,
            industry_name=industry_name,
            province="山东省",
            city="青岛市",
            district="即墨区",
            address="即墨区测试地址",
            cooperation_started_on=date(2026, 7, 27),
        )
        brief = ContentBrief(
            bundle_id=uuid4(),
            client_id=client.id,
            title=f"即墨{industry_name}怎么选",
            content_type=content_type,
            target_question_ids=[str(uuid4())],
            target_keywords=[f"即墨{industry_name}"],
            target_level="L2",
            audience=f"即墨区需要{industry_name}服务的用户",
            angle="从公开事实和核验动作说明选择标准",
            required_fact_ids=[str(uuid4())],
            required_evidence_ids=[str(uuid4())],
            expected_recommendation_reason="提供有依据的候选信息",
            prohibited_claims=[],
            retest_questions=[],
            suggested_channel_ids=[],
            priority=1,
        )
        scored = sorted(
            (
                (_score_channel(channel, brief, client, {"source"})[0], channel["id"])
                for channel in CHANNEL_CATALOG
                if channel["ownership"] == "operator_publishable"
            ),
            reverse=True,
        )
        matrices[industry_code] = tuple(channel_id for _, channel_id in scored[:4])
    assert len(set(matrices.values())) == 3
    assert "xiaohongshu" in matrices["art_education"]
    assert {"xiaohongshu", "douyin", "toutiao"}.issubset(
        matrices["housekeeping"],
    )
    assert {"baijia", "zhihu", "toutiao"}.issubset(matrices["repair"])


@pytest.mark.integration
def test_catalog_filters_and_rejects_invalid_filter(tmp_path) -> None:
    with build_client(tmp_path) as client:
        login(client)
        response = client.get(
            "/api/v1/channels?ownership=operator_publishable&cost=free",
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["catalog_version"] == CATALOG_VERSION
        assert len(data["items"]) >= 5
        assert all(item["ownership"] == "operator_publishable" for item in data["items"])
        assert all(item["cost"] == "free" for item in data["items"])
        assert all(item["verified_on"] == CATALOG_VERIFIED_ON.isoformat() for item in data["items"])

        invalid = client.get("/api/v1/channels?ownership=unknown")
        assert invalid.status_code == 400
        assert invalid.json()["message"] == "渠道筛选参数无效"


@pytest.mark.integration
def test_inactive_link_state_is_hidden_by_default_but_available_for_maintenance(
    tmp_path,
    monkeypatch,
) -> None:
    retired = {
        **CHANNEL_CATALOG[0],
        "id": "retired-entry",
        "name": "已停用渠道",
        "active": False,
    }
    monkeypatch.setattr(
        channel_module,
        "CHANNEL_CATALOG",
        (*CHANNEL_CATALOG, retired),
    )
    with build_client(tmp_path) as client:
        login(client)
        active = client.get("/api/v1/channels").json()["data"]["items"]
        maintenance = client.get("/api/v1/channels?active=false").json()["data"]["items"]
        assert all(item["id"] != "retired-entry" for item in active)
        assert any(
            item["id"] == "retired-entry" and item["active"] is False for item in maintenance
        )


@pytest.mark.integration
def test_recommendations_require_briefs_and_prioritize_operator_public_web(tmp_path) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf, industry_code="housekeeping")
        without_briefs = client.post(
            f"/api/v1/clients/{client_id}/channel-recommendations/generate",
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid4())},
            json={"brief_ids": [], "include_ownership": ["operator_publishable"]},
        )
        assert without_briefs.status_code == 422

        facts = seed_required_facts(
            client,
            csrf,
            client_id,
            service="家庭保洁",
            audience="即墨区有日常保洁需求的家庭",
        )
        diagnostic_id = create_diagnostic(client, csrf, client_id, tmp_path)
        strategy = generate_strategy(client, csrf, client_id, diagnostic_id, tmp_path)
        assert strategy["briefs"]

        key = str(uuid4())
        queued = client.post(
            f"/api/v1/clients/{client_id}/channel-recommendations/generate",
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": key},
            json={
                "brief_ids": [],
                "include_ownership": [
                    "operator_publishable",
                    "client_required",
                    "partner_cooperation",
                ],
            },
        )
        assert queued.status_code == 202
        replay = client.post(
            f"/api/v1/clients/{client_id}/channel-recommendations/generate",
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": key},
            json={
                "brief_ids": [],
                "include_ownership": [
                    "operator_publishable",
                    "client_required",
                    "partner_cooperation",
                ],
            },
        )
        assert replay.status_code == 202
        assert replay.json()["data"]["job_id"] == queued.json()["data"]["job_id"]
        conflict = client.post(
            f"/api/v1/clients/{client_id}/channel-recommendations/generate",
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": key},
            json={
                "brief_ids": [],
                "include_ownership": ["operator_publishable"],
            },
        )
        assert conflict.status_code == 409

        run_worker_once(client, tmp_path)
        recommendations = client.get(
            f"/api/v1/clients/{client_id}/channel-recommendations",
        )
        assert recommendations.status_code == 200
        items = recommendations.json()["data"]["items"]
        assert len(items) == len(strategy["briefs"]) * 7
        assert items[0]["channel"]["ownership"] == "operator_publishable"
        assert items[0]["priority"] == 1
        assert items[0]["fit_score"] >= 90
        assert all(item["caveat"] == NO_GUARANTEE for item in items)
        assert all(item["generation_id"] for item in items)
        assert all(item["brief_id"] and item["brief_title"] for item in items)
        assert all(item["brief_content_type"] for item in items)
        assert all(item["required_adaptation"] for item in items)
        assert all(item["account_positioning"] for item in items)
        assert all(item["authorization_note"] for item in items)
        assert all(item["cost_note"] and item["risk_note"] for item in items)
        assert all(item["target_ecosystems"] for item in items)
        assert all(item["catalog_version"] == CATALOG_VERSION for item in items)
        assert any(item["channel"]["ownership"] == "client_required" for item in items)
        assert any(item["channel"]["ownership"] == "partner_cooperation" for item in items)
        assert all("自动发布" not in " ".join(item["required_actions"]) for item in items)
        refreshed_strategy = client.get(
            f"/api/v1/clients/{client_id}/strategy",
        ).json()["data"]
        recommended_by_brief = {
            brief["id"]: [
                item["channel"]["id"]
                for item in items
                if item["brief_id"] == brief["id"]
                and item["channel"]["ownership"] == "operator_publishable"
            ][:4]
            for brief in refreshed_strategy["briefs"]
        }
        assert all(
            brief["suggested_channel_ids"] == recommended_by_brief[brief["id"]]
            for brief in refreshed_strategy["briefs"]
        )

        original_name = items[0]["channel"]["name"]
        channel_id = items[0]["channel"]["id"]
        with pytest.MonkeyPatch.context() as catalog_patch:
            catalog_patch.setitem(
                channel_module.CATALOG_BY_ID[channel_id],
                "name",
                "目录中的新名称",
            )
            unchanged = client.get(
                f"/api/v1/clients/{client_id}/channel-recommendations",
            ).json()["data"]["items"]
            assert unchanged[0]["channel"]["name"] == original_name

        regenerated = client.post(
            f"/api/v1/clients/{client_id}/channel-recommendations/generate",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "brief_ids": [],
                "include_ownership": [
                    "operator_publishable",
                    "client_required",
                    "partner_cooperation",
                ],
            },
        )
        assert regenerated.status_code == 202
        run_worker_once(client, tmp_path)
        active = client.get(
            f"/api/v1/clients/{client_id}/channel-recommendations",
        ).json()["data"]["items"]
        history = client.get(
            f"/api/v1/clients/{client_id}/channel-recommendations?active_only=false",
        ).json()["data"]["items"]
        assert len(history) == len(active) * 2
        assert len({item["generation_id"] for item in history}) == 2

        changed = client.patch(
            f"/api/v1/facts/{facts[0]['id']}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": facts[0]["version"],
                "value": "家庭保洁与深度清洁",
            },
        )
        assert changed.status_code == 200
        stale_request = client.post(
            f"/api/v1/clients/{client_id}/channel-recommendations/generate",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "brief_ids": [],
                "include_ownership": ["operator_publishable"],
            },
        )
        assert stale_request.status_code == 202
        run_worker_once(client, tmp_path)
        stale_job = client.get(
            f"/api/v1/jobs/{stale_request.json()['data']['job_id']}",
        ).json()["data"]
        assert stale_job["status"] == "failed"
        assert stale_job["error_message"] == "知识库已更新，请先重新运行 GEO 诊断"


@pytest.mark.integration
def test_multi_account_publishing_routes_are_exposed_without_credentials(
    tmp_path,
) -> None:
    with build_client(tmp_path, publishing_execution_mode="fixed_mock") as client:
        csrf = login(client)
        paths = set(client.app.openapi()["paths"])
        assert "/api/v1/documents/{document_id}/publish" in paths
        assert "/api/v1/publishing/channels" in paths
        assert "/api/v1/publishing/channels/{channel_id}/accounts" in paths
        assert "/api/v1/publishing/accounts/{account_id}/login-window" in paths
        assert "/api/v1/publishing/accounts/{account_id}/test" in paths
        assert not [
            path
            for path in paths
            if any(fragment in path for fragment in ("/credentials", "/passwords"))
        ]

        catalog = client.get("/api/v1/publishing/channels")
        assert catalog.status_code == 200
        channels = catalog.json()["data"]["items"]
        assert {item["id"] for item in channels} == {
            "toutiao",
            "baijia",
            "netease",
            "sohu",
            "penguin",
        }
        toutiao = next(item for item in channels if item["id"] == "toutiao")
        assert toutiao["implementation_status"] == "available"
        netease = next(item for item in channels if item["id"] == "netease")
        assert netease["login_url"] == "https://mp.163.com/"
        assert netease["manage_url"] == "https://mp.163.com/#/content-manage"
        assert netease["generation_spec"]["title_max_characters"] == 64
        assert netease["generation_spec"]["image_requirements"]["minimum_body_images"] == 3
        assert netease["generation_spec"]["image_requirements"]["target_body_images"] == 3
        assert netease["generation_spec"]["image_requirements"]["maximum_body_images"] == 3
        assert netease["generation_spec"]["image_requirements"]["cover_width"] == 1200
        assert netease["generation_spec"]["image_requirements"]["cover_height"] == 900
        penguin = next(item for item in channels if item["id"] == "penguin")
        assert penguin["login_url"] == "https://om.qq.com/"
        assert penguin["generation_spec"]["daily_publication_limit"] == 5
        assert penguin["generation_spec"]["image_requirements"]["cover_source"] == "body"
        assert all(item["can_configure"] is True for item in channels)
        assert all(item["max_accounts"] == 5 for item in channels)
        created_account = client.post(
            "/api/v1/publishing/channels/toutiao/accounts",
            headers={"X-CSRF-Token": csrf},
            json={"display_name": "头条默认账号"},
        )
        assert created_account.status_code == 201
        account = created_account.json()["data"]
        assert account["session_health"] == "not_checked"
        assert account["automatic_check_interval_hours"] == 24
        assert account["next_automatic_check_at"] is None

        tested = client.post(
            f"/api/v1/publishing/accounts/{account['id']}/test",
            headers={"X-CSRF-Token": csrf},
        )
        assert tested.status_code == 200
        connected = tested.json()["data"]
        assert connected["connection_status"] == "connected"
        assert connected["session_health"] == "healthy"
        assert connected["next_automatic_check_at"]
        enabled = client.patch(
            f"/api/v1/publishing/accounts/{account['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"enabled": True, "version": connected["version"]},
        )
        assert enabled.status_code == 200
        assert enabled.json()["data"]["enabled"] is True

        for index in range(1, 5):
            created = client.post(
                "/api/v1/publishing/channels/toutiao/accounts",
                headers={"X-CSRF-Token": csrf},
                json={"display_name": f"头条账号 {index}"},
            )
            assert created.status_code == 201
        overflow = client.post(
            "/api/v1/publishing/channels/toutiao/accounts",
            headers={"X-CSRF-Token": csrf},
            json={"display_name": "第六个账号"},
        )
        assert overflow.status_code == 409
