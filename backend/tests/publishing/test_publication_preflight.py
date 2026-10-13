from uuid import uuid4

import pytest

import app.publishing as publishing_module
from app.publishing import ConnectionResult
from tests.auth.test_auth_api import build_client
from tests.clients.test_clients_api import login
from tests.content.test_content_api import prepare_keyword_strategy, run_content_worker
from tests.diagnostics.test_diagnostics_api import create_customer


@pytest.mark.integration
def test_publication_preflight_stops_and_disables_an_expired_account(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with build_client(
        tmp_path,
        model_execution_mode="fixed_mock",
        publishing_execution_mode="fixed_mock",
    ) as client:
        csrf = login(client)
        client_id = create_customer(client, csrf)
        keyword = prepare_keyword_strategy(client, csrf, client_id, tmp_path)
        selected = client.patch(
            f"/api/v1/strategy-items/{keyword['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"version": keyword["version"], "selected": True},
        ).json()["data"]

        account = client.post(
            "/api/v1/publishing/channels/toutiao/accounts",
            headers={"X-CSRF-Token": csrf},
            json={"display_name": "发布前复检账号"},
        ).json()["data"]
        account = client.post(
            f"/api/v1/publishing/accounts/{account['id']}/test",
            headers={"X-CSRF-Token": csrf},
        ).json()["data"]
        account = client.patch(
            f"/api/v1/publishing/accounts/{account['id']}",
            headers={"X-CSRF-Token": csrf},
            json={"enabled": True, "version": account["version"]},
        ).json()["data"]

        created = client.post(
            f"/api/v1/clients/{client_id}/documents/batch",
            headers={"X-CSRF-Token": csrf},
            json={
                "keyword_ids": [selected["id"]],
                "article_count": 1,
                "length": "medium",
                "style": "auto",
                "content_form": "selection_guide",
                "target_channel_ids": ["toutiao"],
            },
        ).json()["data"]["items"][0]
        run_content_worker(client, tmp_path)
        document = client.get(f"/api/v1/documents/{created['id']}").json()["data"]
        task = client.get(
            f"/api/v1/content-generation-tasks/{created['generation_task_id']}",
        ).json()["data"]
        confirmed = client.post(
            f"/api/v1/content-generation-tasks/{task['id']}/confirm",
            headers={"X-CSRF-Token": csrf},
            json={"version": task["version"]},
        )
        assert confirmed.status_code == 200, confirmed.text

        async def expired_session(*_args: object, **_kwargs: object) -> ConnectionResult:
            return ConnectionResult(
                status="needs_login",
                error_message="头条号登录已失效，请重新登录",
            )

        monkeypatch.setattr(
            publishing_module,
            "verify_publishing_account",
            expired_session,
        )
        accepted = client.post(
            f"/api/v1/documents/{document['id']}/publish",
            headers={
                "X-CSRF-Token": csrf,
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "version": document["version"],
                "account_ids": [account["id"]],
            },
        )
        assert accepted.status_code == 202
        run_content_worker(client, tmp_path)

        result = client.get(f"/api/v1/documents/{document['id']}").json()["data"]
        assert result["latest_publication"]["status"] == "needs_login"
        channels = client.get("/api/v1/publishing/channels").json()["data"]["items"]
        stored_account = next(
            item
            for channel in channels
            for item in channel["accounts"]
            if item["id"] == account["id"]
        )
        assert stored_account["enabled"] is False
        assert stored_account["connection_status"] == "needs_login"
        assert stored_account["session_health"] == "expired"
        assert stored_account["last_checked_at"]
