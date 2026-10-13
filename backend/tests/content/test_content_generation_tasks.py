import asyncio
from collections import Counter
from io import BytesIO
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from fastapi import FastAPI
from PIL import Image
from sqlalchemy import select, update

from app.database import ContentBrief, ContentDocument
from tests.auth.test_auth_api import build_client
from tests.clients.test_clients_api import login
from tests.content.test_content_api import prepare_keyword_strategy, run_content_worker
from tests.diagnostics.test_diagnostics_api import create_customer


def connect_channel(client, csrf: str, channel_id: str) -> str:
    created = client.post(
        f"/api/v1/publishing/channels/{channel_id}/accounts",
        headers={"X-CSRF-Token": csrf},
        json={"display_name": f"{channel_id}-内容任务账号"},
    )
    assert created.status_code == 201
    account = created.json()["data"]
    tested = client.post(
        f"/api/v1/publishing/accounts/{account['id']}/test",
        headers={"X-CSRF-Token": csrf},
    )
    assert tested.status_code == 200
    connected = tested.json()["data"]
    enabled = client.patch(
        f"/api/v1/publishing/accounts/{account['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"version": connected["version"], "enabled": True},
    )
    assert enabled.status_code == 200
    return str(account["id"])


@pytest.mark.integration
def test_content_task_uses_active_keywords_connected_channels_and_balanced_forms(
    tmp_path: Path,
) -> None:
    with build_client(
        tmp_path,
        model_execution_mode="fixed_mock",
        publishing_execution_mode="fixed_mock",
    ) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        keyword = prepare_keyword_strategy(client, csrf, client_id, tmp_path)
        assert keyword["selected"] is False
        toutiao_account_id = connect_channel(client, csrf, "toutiao")
        connect_channel(client, csrf, "sohu")

        unconfigured = client.post(
            f"/api/v1/clients/{client_id}/documents/batch",
            headers={"X-CSRF-Token": csrf},
            json={
                "keyword_ids": [keyword["id"]],
                "platform_type": "self_media",
                "article_count": 1,
                "length": "medium",
                "content_form_codes": ["selection_guide"],
                "target_channel_ids": ["netease"],
            },
        )
        assert unconfigured.status_code == 422
        assert "配置" in unconfigured.json()["message"]

        missing_assets = client.post(
            f"/api/v1/clients/{client_id}/documents/batch",
            headers={"X-CSRF-Token": csrf},
            json={
                "keyword_ids": [keyword["id"]],
                "platform_type": "self_media",
                "article_count": 1,
                "length": "medium",
                "content_form_codes": ["selection_guide"],
                "target_channel_ids": ["sohu"],
            },
        )
        assert missing_assets.status_code == 422
        assert "开始生成前缺少发布素材" in missing_assets.json()["message"]

        image = BytesIO()
        Image.new("RGB", (1200, 800), "#3977e8").save(image, format="PNG")
        uploaded = client.post(
            f"/api/v1/clients/{client_id}/materials",
            headers={"X-CSRF-Token": csrf},
            data={"category": "image", "authorization_status": "authorized"},
            files=[("files", ("企业环境.png", image.getvalue(), "image/png"))],
        )
        assert uploaded.status_code == 201

        created = client.post(
            f"/api/v1/clients/{client_id}/documents/batch",
            headers={"X-CSRF-Token": csrf},
            json={
                "keyword_ids": [keyword["id"]],
                "platform_type": "self_media",
                "article_count": 3,
                "length": "medium",
                "content_form_codes": ["selection_guide", "practical_guide"],
                "target_channel_ids": ["toutiao", "sohu"],
            },
        )

        assert created.status_code == 201, created.text
        payload = created.json()["data"]
        assert payload["total"] == 6
        assert payload["task"]["article_count_per_channel"] == 3
        assert payload["task"]["total_count"] == 6
        assert payload["task"]["platform_type"] == "self_media"
        assert payload["task"]["content_form_codes"] == [
            "selection_guide",
            "practical_guide",
        ]
        assert payload["task"]["channel_ids"] == ["toutiao", "sohu"]
        assert payload["task"]["keyword_snapshots"][0]["text"] == keyword["text"]

        application = cast(FastAPI, client.app)

        async def task_briefs() -> list[tuple[str, str]]:
            async with application.state.session_factory() as database:
                rows = await database.execute(
                    select(ContentBrief.target_channel_id, ContentBrief.content_type)
                    .join(ContentDocument, ContentDocument.brief_id == ContentBrief.id)
                    .where(
                        ContentDocument.generation_task_id == UUID(payload["task"]["id"]),
                    ),
                )
                return [(str(channel), str(form)) for channel, form in rows.all()]

        distributions: dict[str, Counter[str]] = {}
        for channel, form in asyncio.run(task_briefs()):
            distributions.setdefault(channel, Counter())[form] += 1
        assert set(distributions) == {"toutiao", "sohu"}
        assert all(sum(counts.values()) == 3 for counts in distributions.values())
        assert all(sorted(counts.values()) == [1, 2] for counts in distributions.values())

        listing = client.get(
            f"/api/v1/clients/{client_id}/content-generation-tasks",
        )
        assert listing.status_code == 200
        assert listing.json()["data"]["items"][0]["id"] == payload["task"]["id"]

        detail = client.get(
            f"/api/v1/content-generation-tasks/{payload['task']['id']}",
        )
        assert detail.status_code == 200
        assert len(detail.json()["data"]["documents"]) == 6
        assert detail.json()["data"]["confirmed_at"] is None

        premature_confirmation = client.post(
            f"/api/v1/content-generation-tasks/{payload['task']['id']}/confirm",
            headers={"X-CSRF-Token": csrf},
            json={"version": detail.json()["data"]["version"]},
        )
        assert premature_confirmation.status_code == 422

        for _ in range(6):
            run_content_worker(client, tmp_path)

        completed = client.get(
            f"/api/v1/content-generation-tasks/{payload['task']['id']}",
        )
        assert completed.status_code == 200
        assert completed.json()["data"]["status"] == "completed"

        toutiao_document = next(
            item
            for item in completed.json()["data"]["documents"]
            if item["current_version"]["target_channel_id"] == "toutiao"
        )
        publish_before_confirmation = client.post(
            f"/api/v1/documents/{toutiao_document['id']}/publish",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": "unconfirmed-task-publication",
            },
            json={
                "version": toutiao_document["version"],
                "account_ids": [toutiao_account_id],
            },
        )
        assert publish_before_confirmation.status_code == 422
        assert "确认" in publish_before_confirmation.json()["message"]

        removable_document = next(
            item
            for item in completed.json()["data"]["documents"]
            if item["id"] != toutiao_document["id"]
        )
        deleted = client.delete(
            f"/api/v1/documents/{removable_document['id']}",
            headers={"X-CSRF-Token": csrf},
            params={"version": removable_document["version"]},
        )
        assert deleted.status_code == 200, deleted.text

        after_delete = client.get(
            f"/api/v1/content-generation-tasks/{payload['task']['id']}",
        )
        assert after_delete.status_code == 200
        assert after_delete.json()["data"]["total_count"] == 5
        assert after_delete.json()["data"]["completed_count"] == 5
        assert after_delete.json()["data"]["status"] == "completed"
        assert len(after_delete.json()["data"]["documents"]) == 5
        assert all(
            item["id"] != removable_document["id"]
            for item in after_delete.json()["data"]["documents"]
        )

        async def mark_task_articles_ready() -> None:
            async with application.state.session_factory() as database:
                await database.execute(
                    update(ContentDocument)
                    .where(
                        ContentDocument.generation_task_id == UUID(payload["task"]["id"]),
                        ContentDocument.current_version_id.is_not(None),
                    )
                    .values(status="checked"),
                )
                await database.commit()

        asyncio.run(mark_task_articles_ready())
        confirmed = client.post(
            f"/api/v1/content-generation-tasks/{payload['task']['id']}/confirm",
            headers={"X-CSRF-Token": csrf},
            json={"version": completed.json()["data"]["version"]},
        )
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()["data"]["confirmed_at"] is not None
        assert all(
            item["generation_task_confirmed_at"] is not None
            for item in confirmed.json()["data"]["documents"]
        )
