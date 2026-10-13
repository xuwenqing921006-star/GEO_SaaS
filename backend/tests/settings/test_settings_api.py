import asyncio
import base64
import json
import os
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import cast

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import ProviderSetting
from tests.auth.test_auth_api import build_client
from tests.clients.test_clients_api import login


def master_key() -> SecretStr:
    return SecretStr(base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"))


def provider_payload(setting: dict[str, object], api_key: str | None) -> dict[str, object]:
    return {
        "version": setting["version"],
        "enabled": api_key is not None or setting["secret_configured"],
        "base_url": setting["base_url"],
        "workspace_id": setting["workspace_id"],
        "writer_model": setting["writer_model"],
        "reviewer_model": setting["reviewer_model"],
        "fallback_model": setting["fallback_model"],
        "daily_budget_cny_fen": setting["daily_budget_cny_fen"],
        "timeout_seconds": setting["timeout_seconds"],
        "api_key": api_key,
    }


def load_settings(client: TestClient) -> dict[str, object]:
    response = client.get("/api/v1/settings")
    assert response.status_code == 200
    return cast(dict[str, object], response.json()["data"])


@pytest.mark.integration
def test_settings_expose_wenxin_as_diagnostic_provider(tmp_path: Path) -> None:
    with build_client(tmp_path, app_master_key=master_key()) as client:
        login(client)
        settings = load_settings(client)
        providers = cast(list[dict[str, object]], settings["providers"])
        assert [provider["provider"] for provider in providers] == [
            "deepseek",
            "doubao",
            "qwen",
            "wenxin",
        ]
        wenxin = next(provider for provider in providers if provider["provider"] == "wenxin")
        assert wenxin["base_url"] == "https://qianfan.baidubce.com/v2"
        assert wenxin["writer_model"] == "ernie-4.5-turbo-32k"
        assert wenxin["secret_configured"] is False


@pytest.mark.integration
def test_provider_secret_is_write_only_encrypted_and_null_preserves_it(tmp_path: Path) -> None:
    key = secrets.token_urlsafe(32)
    with build_client(tmp_path, app_master_key=master_key()) as client:
        csrf = login(client)
        settings = load_settings(client)
        qwen = next(
            item
            for item in cast(list[dict[str, object]], settings["providers"])
            if item["provider"] == "qwen"
        )
        saved = client.put(
            "/api/v1/settings/providers/qwen",
            headers={"X-CSRF-Token": csrf},
            json=provider_payload(qwen, key),
        )
        assert saved.status_code == 200
        body_text = saved.text
        assert key not in body_text
        assert saved.json()["data"]["secret_configured"] is True
        assert saved.json()["data"]["secret_mask"] == f"••••{key[-4:]}"

        async def assert_encrypted() -> None:
            factory = cast(
                async_sessionmaker,
                cast(FastAPI, client.app).state.session_factory,
            )
            async with factory() as database:
                row = await database.get(ProviderSetting, "qwen")
                assert row is not None
                assert row.encrypted_api_key is not None
                assert key.encode() not in row.encrypted_api_key

        asyncio.run(assert_encrypted())
        current = saved.json()["data"]
        preserved = client.put(
            "/api/v1/settings/providers/qwen",
            headers={"X-CSRF-Token": csrf},
            json=provider_payload(current, None),
        )
        assert preserved.status_code == 200
        assert preserved.json()["data"]["secret_configured"] is True
        reloaded_text = client.get("/api/v1/settings").text
        assert key not in reloaded_text

        stale = client.put(
            "/api/v1/settings/providers/qwen",
            headers={"X-CSRF-Token": csrf},
            json=provider_payload(current, None),
        )
        assert stale.status_code == 409


@pytest.mark.integration
def test_missing_master_key_blocks_secret_save_and_real_success_state(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        settings = load_settings(client)
        qwen = next(
            item
            for item in cast(list[dict[str, object]], settings["providers"])
            if item["provider"] == "qwen"
        )
        response = client.put(
            "/api/v1/settings/providers/qwen",
            headers={"X-CSRF-Token": csrf},
            json=provider_payload(qwen, secrets.token_urlsafe(32)),
        )
        assert response.status_code == 503
        assert "密钥保护" in response.json()["message"]
        reloaded = load_settings(client)
        qwen_after = next(
            item
            for item in cast(list[dict[str, object]], reloaded["providers"])
            if item["provider"] == "qwen"
        )
        assert qwen_after["secret_configured"] is False
        assert qwen_after["last_test_status"] == "not_tested"


@pytest.mark.integration
def test_provider_url_rejects_non_official_hosts_and_unsafe_urls(tmp_path: Path) -> None:
    with build_client(tmp_path, app_master_key=master_key()) as client:
        csrf = login(client)
        settings = load_settings(client)
        qwen = next(
            item
            for item in cast(list[dict[str, object]], settings["providers"])
            if item["provider"] == "qwen"
        )
        for unsafe_url in (
            "http://provider.invalid/v1",
            "https://user:password@provider.invalid/v1",
        ):
            payload = provider_payload(qwen, None)
            payload["base_url"] = unsafe_url
            response = client.put(
                "/api/v1/settings/providers/qwen",
                headers={"X-CSRF-Token": csrf},
                json=payload,
            )
            assert response.status_code == 400
            assert response.json()["message"] == "请求参数校验失败"
        for private_url in (
            "https://127.0.0.1/v1",
            "https://169.254.169.254/v1",
            "https://localhost/v1",
        ):
            payload = provider_payload(qwen, None)
            payload["base_url"] = private_url
            response = client.put(
                "/api/v1/settings/providers/qwen",
                headers={"X-CSRF-Token": csrf},
                json=payload,
            )
            assert response.status_code == 422
            assert "官方域名" in response.json()["message"]


@pytest.mark.integration
def test_structured_provider_probe_uses_saved_secret_without_returning_it(
    tmp_path: Path,
) -> None:
    key = secrets.token_urlsafe(32)
    observed_requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal observed_requests
        observed_requests += 1
        assert request.headers["Authorization"] == f"Bearer {key}"
        payload = json.loads(request.content)
        assert payload["model"] == "qwen3.7-plus"
        assert payload["enable_thinking"] is False
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"ok": True, "summary": "connected"},
                            ),
                        },
                    },
                ],
            },
        )

    transport = httpx.MockTransport(handler)
    with build_client(
        tmp_path,
        app_master_key=master_key(),
        provider_transport=transport,
    ) as client:
        csrf = login(client)
        settings = load_settings(client)
        qwen = next(
            item
            for item in cast(list[dict[str, object]], settings["providers"])
            if item["provider"] == "qwen"
        )
        saved = client.put(
            "/api/v1/settings/providers/qwen",
            headers={"X-CSRF-Token": csrf},
            json=provider_payload(qwen, key),
        )
        assert saved.status_code == 200
        tested = client.post(
            "/api/v1/settings/providers/qwen/test",
            headers={"X-CSRF-Token": csrf},
            json={
                "test_type": "structured_output",
                "use_saved_secret": True,
                "api_key": None,
            },
        )
        assert tested.status_code == 200
        assert tested.json()["data"]["structured_output_valid"] is True
        assert tested.json()["data"]["model"] == "qwen3.7-plus"
        assert key not in tested.text
        assert observed_requests == 1
        after_test = load_settings(client)
        tested_qwen = next(
            item
            for item in cast(list[dict[str, object]], after_test["providers"])
            if item["provider"] == "qwen"
        )
        assert tested_qwen["last_test_status"] == "success"
        changed_payload = provider_payload(tested_qwen, None)
        changed_payload["base_url"] = "https://dashscope.aliyuncs.com/compatible-mode/v2"
        changed = client.put(
            "/api/v1/settings/providers/qwen",
            headers={"X-CSRF-Token": csrf},
            json=changed_payload,
        )
        assert changed.status_code == 200
        assert changed.json()["data"]["last_test_status"] == "not_tested"
        assert changed.json()["data"]["last_tested_at"] is None


@pytest.mark.integration
def test_temporary_probe_key_is_never_persisted(tmp_path: Path) -> None:
    key = secrets.token_urlsafe(32)
    observed_models: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == f"Bearer {key}"
        observed_models.append(cast(str, json.loads(request.content)["model"]))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"ok": True, "summary": "connected"},
                            ),
                        },
                    },
                ],
            },
        )

    with build_client(
        tmp_path,
        app_master_key=master_key(),
        provider_transport=httpx.MockTransport(handler),
    ) as client:
        csrf = login(client)
        tested = client.post(
            "/api/v1/settings/providers/deepseek/test",
            headers={"X-CSRF-Token": csrf},
            json={
                "test_type": "structured_output",
                "use_saved_secret": False,
                "api_key": key,
            },
        )
        assert tested.status_code == 200
        assert tested.json()["data"]["model"] == ("deepseek-v4-pro + deepseek-v4-flash")
        assert observed_models == ["deepseek-v4-pro", "deepseek-v4-flash"]
        assert key not in tested.text
        settings = load_settings(client)
        deepseek = next(
            item
            for item in cast(list[dict[str, object]], settings["providers"])
            if item["provider"] == "deepseek"
        )
        assert deepseek["secret_configured"] is False
        assert deepseek["secret_mask"] is None


@pytest.mark.integration
def test_temporary_probe_also_fails_closed_without_master_key(tmp_path: Path) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={})

    with build_client(
        tmp_path,
        provider_transport=httpx.MockTransport(handler),
    ) as client:
        csrf = login(client)
        response = client.post(
            "/api/v1/settings/providers/qwen/test",
            headers={"X-CSRF-Token": csrf},
            json={
                "test_type": "structured_output",
                "use_saved_secret": False,
                "api_key": secrets.token_urlsafe(32),
            },
        )
        assert response.status_code == 503
        assert calls == 0


@pytest.mark.integration
def test_provider_update_uses_atomic_compare_and_swap(tmp_path: Path) -> None:
    with build_client(tmp_path, app_master_key=master_key()) as client:
        csrf = login(client)
        settings = load_settings(client)
        qwen = next(
            item
            for item in cast(list[dict[str, object]], settings["providers"])
            if item["provider"] == "qwen"
        )
        barrier = Barrier(2)

        def update_budget(amount: int) -> int:
            payload = provider_payload(qwen, None)
            payload["daily_budget_cny_fen"] = amount
            barrier.wait()
            return client.put(
                "/api/v1/settings/providers/qwen",
                headers={"X-CSRF-Token": csrf},
                json=payload,
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = sorted(executor.map(update_budget, (4_000, 5_000)))
        assert statuses == [200, 409]


@pytest.mark.integration
def test_runtime_budget_update_is_versioned_and_validated(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        runtime = cast(dict[str, object], load_settings(client)["runtime"])
        updated = client.patch(
            "/api/v1/settings/runtime",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": runtime["version"],
                "default_client_monthly_budget_cny_fen": 45_000,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["default_client_monthly_budget_cny_fen"] == 45_000
        stale = client.patch(
            "/api/v1/settings/runtime",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": runtime["version"],
                "default_client_monthly_budget_cny_fen": 50_000,
            },
        )
        assert stale.status_code == 409


@pytest.mark.integration
def test_runtime_update_uses_atomic_compare_and_swap(tmp_path: Path) -> None:
    with build_client(tmp_path) as client:
        csrf = login(client)
        runtime = cast(dict[str, object], load_settings(client)["runtime"])
        barrier = Barrier(2)

        def update_budget(amount: int) -> int:
            barrier.wait()
            return client.patch(
                "/api/v1/settings/runtime",
                headers={"X-CSRF-Token": csrf},
                json={
                    "version": runtime["version"],
                    "default_client_monthly_budget_cny_fen": amount,
                },
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = sorted(executor.map(update_budget, (40_000, 50_000)))
        assert statuses == [200, 409]
