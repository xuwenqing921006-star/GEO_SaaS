# ruff: noqa: RUF001

from pathlib import Path
from uuid import uuid4

import pytest

from app.keyword_workspace import _normalize_keyword_priority
from tests.auth.test_auth_api import build_client
from tests.clients.test_clients_api import login
from tests.diagnostics.test_diagnostics_api import (
    create_customer,
    run_worker_once,
    seed_required_facts,
)


@pytest.mark.unit
def test_keyword_workspace_accepts_common_model_priority_labels() -> None:
    assert _normalize_keyword_priority("high") == 1
    assert _normalize_keyword_priority("HIGH") == 1
    assert _normalize_keyword_priority("高") == 1
    assert _normalize_keyword_priority("medium") == 2
    assert _normalize_keyword_priority("low") == 3
    assert _normalize_keyword_priority(3) == 3
    assert _normalize_keyword_priority([]) == 2


@pytest.mark.integration
def test_keyword_workspace_creates_tasks_and_confirms_only_selected_candidates(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf, industry_code="art_education")
        seed_required_facts(
            client,
            csrf,
            client_id,
            service="少儿美术培训；硬笔书法；美术中高考",
            audience="4—18岁少儿及家长",
        )

        initial = client.get(f"/api/v1/clients/{client_id}/keyword-workspace")
        assert initial.status_code == 200
        workspace = initial.json()["data"]
        assert workspace["profile"]["primary_keyword"] == "少儿美术培训"
        assert {"即墨区", "即墨", "青岛即墨", "青岛市即墨区"}.issubset(
            set(workspace["profile"]["regions"]),
        )
        assert "硬笔书法" in workspace["profile"]["secondary_keywords"]
        assert 5 <= workspace["profile"]["recommended_count"] <= 40
        assert workspace["generations"] == []

        profile = client.put(
            f"/api/v1/clients/{client_id}/keyword-profile",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": workspace["profile"]["version"],
                "primary_keyword": "少儿美术培训",
                "regions": ["即墨区", "即墨", "青岛即墨"],
                "secondary_keywords": ["硬笔书法", "美术中高考"],
                "keyword_types": ["recommendation", "brand", "scenario"],
            },
        )
        assert profile.status_code == 200
        saved_profile = profile.json()["data"]
        assert saved_profile["regions"] == ["即墨区", "即墨", "青岛即墨"]
        assert saved_profile["recommended_count"] == 16

        queued = client.post(
            f"/api/v1/clients/{client_id}/keyword-generations",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "profile_version": saved_profile["version"],
                "target_count": 8,
            },
        )
        assert queued.status_code == 202
        accepted = queued.json()["data"]
        assert accepted["status"] in {"queued", "running"}
        run_worker_once(client, tmp_path)

        detail = client.get(
            f"/api/v1/keyword-generations/{accepted['generation_id']}",
        )
        assert detail.status_code == 200
        generation = detail.json()["data"]
        assert generation["status"] == "awaiting_confirmation"
        assert generation["target_count"] == 8
        assert generation["generated_count"] == 8
        assert len(generation["candidates"]) == 8
        normalized = [candidate["normalized_text"] for candidate in generation["candidates"]]
        assert len(normalized) == len(set(normalized))
        assert {candidate["keyword_type"] for candidate in generation["candidates"]} <= {
            "recommendation",
            "brand",
            "scenario",
        }

        removed_candidate = generation["candidates"][0]
        removed = client.patch(
            f"/api/v1/keyword-candidates/{removed_candidate['id']}",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": removed_candidate["version"],
                "selected": False,
                "active": False,
            },
        )
        assert removed.status_code == 200
        selected_ids = [
            candidate["id"]
            for candidate in generation["candidates"]
            if candidate["id"] != removed_candidate["id"]
        ]
        confirmed = client.post(
            f"/api/v1/keyword-generations/{generation['id']}/confirm",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": generation["version"],
                "candidate_ids": selected_ids,
            },
        )
        assert confirmed.status_code == 200
        confirmed_generation = confirmed.json()["data"]
        assert confirmed_generation["status"] == "confirmed"
        assert confirmed_generation["confirmed_count"] == 7

        strategy = client.get(f"/api/v1/clients/{client_id}/strategy").json()["data"]
        confirmed_keywords = [
            item
            for item in strategy["items"]
            if item["kind"] == "keyword" and item["active"] and item["selected"]
        ]
        assert {item["text"] for item in confirmed_keywords} == {
            candidate["text"]
            for candidate in generation["candidates"]
            if candidate["id"] in selected_ids
        }


@pytest.mark.integration
def test_keyword_generations_exclude_exact_history_and_archive_without_forgetting(
    tmp_path: Path,
) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf, industry_code="art_education")
        seed_required_facts(client, csrf, client_id, service="少儿美术培训；硬笔书法")
        profile = client.get(
            f"/api/v1/clients/{client_id}/keyword-workspace",
        ).json()["data"]["profile"]

        def create_generation() -> dict[str, object]:
            response = client.post(
                f"/api/v1/clients/{client_id}/keyword-generations",
                headers={
                    "X-CSRF-Token": csrf,
                    "Idempotency-Key": str(uuid4()),
                },
                json={"profile_version": profile["version"], "target_count": 6},
            )
            assert response.status_code == 202
            run_worker_once(client, tmp_path)
            return client.get(
                f"/api/v1/keyword-generations/{response.json()['data']['generation_id']}",
            ).json()["data"]

        first = create_generation()
        second = create_generation()
        first_texts = {item["normalized_text"] for item in first["candidates"]}
        second_texts = {item["normalized_text"] for item in second["candidates"]}
        assert first_texts
        assert second_texts
        assert first_texts.isdisjoint(second_texts)

        archived = client.delete(
            f"/api/v1/keyword-generations/{second['id']}",
            headers={"X-CSRF-Token": csrf},
            params={"version": second["version"]},
        )
        assert archived.status_code == 200
        assert archived.json()["data"]["archived"] is True
        workspace = client.get(
            f"/api/v1/clients/{client_id}/keyword-workspace",
        ).json()["data"]
        assert second["id"] not in {item["id"] for item in workspace["generations"]}

        third = create_generation()
        third_texts = {item["normalized_text"] for item in third["candidates"]}
        assert third_texts.isdisjoint(first_texts | second_texts)


@pytest.mark.integration
def test_keyword_profile_rejects_limits_before_generation(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        seed_required_facts(client, csrf, client_id)
        profile = client.get(
            f"/api/v1/clients/{client_id}/keyword-workspace",
        ).json()["data"]["profile"]

        too_many_regions = client.put(
            f"/api/v1/clients/{client_id}/keyword-profile",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": profile["version"],
                "primary_keyword": "少儿美术培训",
                "regions": ["地区1", "地区2", "地区3", "地区4", "地区5", "地区6"],
                "secondary_keywords": [],
                "keyword_types": ["recommendation"],
            },
        )
        assert too_many_regions.status_code == 422

        invalid_count = client.post(
            f"/api/v1/clients/{client_id}/keyword-generations",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={"profile_version": profile["version"], "target_count": 51},
        )
        assert invalid_count.status_code == 422
