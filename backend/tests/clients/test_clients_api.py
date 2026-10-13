from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from tests.auth.test_auth_api import build_client


def login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "CorrectPassword2026!"},
    )
    return str(response.json()["data"]["csrf_token"])


def client_payload() -> dict[str, object]:
    return {
        "standard_name": "莱恩美术",
        "short_name": "莱恩",
        "industry_code": "art_education",
        "province": "山东省",
        "city": "青岛市",
        "district": "即墨区",
        "address": "示例地址",
        "contact_phone": None,
        "contact_wechat": None,
        "business_hours": None,
        "service_radius": None,
        "cooperation_started_on": date(2026, 1, 1).isoformat(),
        "notes": None,
    }


@pytest.mark.integration
def test_client_lifecycle_and_dashboard_follow_the_contract(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        headers = {"X-CSRF-Token": csrf}

        created = client.post(
            "/api/v1/clients",
            headers=headers,
            json=client_payload(),
        )
        assert created.status_code == 201
        client_data = created.json()["data"]
        client_id = client_data["id"]
        assert client_data["version"] == 1
        assert client_data["fact_completeness"] == 35

        listing = client.get("/api/v1/clients", params={"q": "莱恩"})
        assert listing.status_code == 200
        assert listing.json()["data"]["total"] == 1
        assert listing.json()["data"]["items"][0]["fact_completeness"] == 35

        for category, key, label, value in (
            ("service", "service.primary", "核心服务", "少儿美术培训"),
            ("identity", "identity.introduction", "企业介绍", "本地少儿美术培训机构"),
            ("audience", "audience.primary", "主要服务对象", "4—16 岁儿童"),
            ("capability", "capability.primary", "企业优势", "五家直营校区"),
            ("contact", "contact.public", "联系电话", "12345678901"),
        ):
            fact = client.post(
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
            assert fact.status_code == 201
        completed_profile = client.get(f"/api/v1/clients/{client_id}")
        assert completed_profile.json()["data"]["fact_completeness"] == 100

        updated = client.patch(
            f"/api/v1/clients/{client_id}",
            headers=headers,
            json={"version": 1, "standard_name": "莱恩少儿美术"},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["version"] == 2

        conflict = client.patch(
            f"/api/v1/clients/{client_id}",
            headers=headers,
            json={"version": 1, "standard_name": "旧版本覆盖"},
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == 40901

        paused = client.patch(
            f"/api/v1/clients/{client_id}",
            headers=headers,
            json={"version": 2, "status": "paused"},
        )
        assert paused.json()["data"]["status"] == "paused"

        archived = client.post(
            f"/api/v1/clients/{client_id}/archive",
            headers=headers,
            json={"version": 3, "reason": "暂停合作"},
        )
        assert archived.json()["data"]["status"] == "archived"
        assert client.get("/api/v1/clients", params={"q": "莱恩"}).json()["data"]["total"] == 0
        archived_listing = client.get(
            "/api/v1/clients",
            params={"q": "莱恩", "status": "archived"},
        )
        assert archived_listing.json()["data"]["total"] == 1

        restored = client.post(
            f"/api/v1/clients/{client_id}/restore",
            headers=headers,
            json={"version": 4},
        )
        assert restored.json()["data"]["status"] == "active"

        dashboard = client.get(f"/api/v1/clients/{client_id}/dashboard")
        assert dashboard.status_code == 200
        assert dashboard.json()["data"]["client"]["standard_name"] == "莱恩少儿美术"
        assert dashboard.json()["data"]["next_actions"][0]["target_page"] == "P02"
        assert dashboard.json()["data"]["next_actions"][0]["target_level"] == "L1"

        missing = client.get("/api/v1/clients/00000000-0000-4000-8000-000000000999")
        assert missing.status_code == 404
        assert missing.json()["message"] == "客户不存在"


@pytest.mark.integration
def test_clients_require_session_and_csrf(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        assert client.get("/api/v1/clients").status_code == 401
        csrf = login(client)
        invalid_page = client.get("/api/v1/clients", params={"page": 0})
        assert invalid_page.status_code == 400
        assert invalid_page.json()["message"] == "分页或筛选参数无效"
        invalid_client = client.post(
            "/api/v1/clients",
            headers={"X-CSRF-Token": csrf},
            json={"standard_name": ""},
        )
        assert invalid_client.status_code == 400
        assert invalid_client.json()["message"] == "客户资料校验失败"
        rejected = client.post("/api/v1/clients", json=client_payload())
        assert rejected.status_code == 403


@pytest.mark.integration
def test_client_updates_are_atomic_and_duplicate_names_are_rejected(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        headers = {"X-CSRF-Token": csrf}
        created = client.post("/api/v1/clients", headers=headers, json=client_payload())
        client_id = created.json()["data"]["id"]
        barrier = Barrier(2)

        def update_name(name: str) -> int:
            barrier.wait()
            return int(
                client.patch(
                    f"/api/v1/clients/{client_id}",
                    headers=headers,
                    json={"version": 1, "standard_name": name},
                ).status_code,
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(update_name, ["第一次更新", "第二次更新"]))
        assert sorted(statuses) == [200, 409]

        duplicate_payload = client_payload()
        duplicate_payload["standard_name"] = "  莱恩美术  "
        duplicate = client.post(
            "/api/v1/clients",
            headers=headers,
            json=duplicate_payload,
        )
        assert duplicate.status_code == 201

        equivalent_payload = client_payload()
        equivalent_payload["standard_name"] = "莱恩美术"
        equivalent = client.post(
            "/api/v1/clients",
            headers=headers,
            json=equivalent_payload,
        )
        assert equivalent.status_code == 409
        assert equivalent.json()["message"] == "客户标准名称已存在"

        null_required = client.patch(
            f"/api/v1/clients/{client_id}",
            headers=headers,
            json={"version": 2, "province": None},
        )
        assert null_required.status_code == 400
        assert null_required.json()["message"] == "客户资料校验失败"

        null_status = client.patch(
            f"/api/v1/clients/{client_id}",
            headers=headers,
            json={"version": 2, "status": None},
        )
        assert null_status.status_code == 400
        assert null_status.json()["message"] == "客户资料校验失败"

        expanded_payload = client_payload()
        expanded_payload["standard_name"] = "ﬃ" * 200
        expanded = client.post(
            "/api/v1/clients",
            headers=headers,
            json=expanded_payload,
        )
        assert expanded.status_code == 201


@pytest.mark.integration
def test_archived_client_can_only_return_through_restore(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        headers = {"X-CSRF-Token": csrf}
        created = client.post("/api/v1/clients", headers=headers, json=client_payload())
        client_id = created.json()["data"]["id"]
        archived = client.post(
            f"/api/v1/clients/{client_id}/archive",
            headers=headers,
            json={"version": 1, "reason": "暂停合作"},
        )
        assert archived.status_code == 200

        bypass = client.patch(
            f"/api/v1/clients/{client_id}",
            headers=headers,
            json={"version": 2, "status": "active"},
        )
        assert bypass.status_code == 409
        assert bypass.json()["code"] == 40902

        restored = client.post(
            f"/api/v1/clients/{client_id}/restore",
            headers=headers,
            json={"version": 2},
        )
        assert restored.status_code == 200
