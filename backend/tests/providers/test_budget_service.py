import asyncio
import base64
import os
import secrets
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.providers import finalize_model_usage, reserve_model_budget
from app.responses import ApiFailure
from tests.auth.test_auth_api import build_client
from tests.clients.test_clients_api import login


@pytest.mark.integration
def test_budget_reservation_is_persisted_warns_and_blocks(tmp_path: Path) -> None:
    master = SecretStr(base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"))
    with build_client(tmp_path, app_master_key=master) as client:
        csrf = login(client)
        settings = client.get("/api/v1/settings").json()["data"]
        qwen = next(item for item in settings["providers"] if item["provider"] == "qwen")
        configured = client.put(
            "/api/v1/settings/providers/qwen",
            headers={"X-CSRF-Token": csrf},
            json={
                "version": qwen["version"],
                "enabled": True,
                "base_url": qwen["base_url"],
                "workspace_id": qwen["workspace_id"],
                "writer_model": qwen["writer_model"],
                "reviewer_model": qwen["reviewer_model"],
                "fallback_model": qwen["fallback_model"],
                "daily_budget_cny_fen": 1_000,
                "timeout_seconds": qwen["timeout_seconds"],
                "api_key": secrets.token_urlsafe(32),
            },
        )
        assert configured.status_code == 200
        factory = cast(
            async_sessionmaker,
            cast(FastAPI, client.app).state.session_factory,
        )

        async def exercise() -> None:
            async with factory() as database:
                first = await reserve_model_budget(
                    database,
                    provider="qwen",
                    model="qwen3.7-plus",
                    purpose="content_generate",
                    estimated_cny_fen=800,
                )
                assert first.decision.warning is True
                assert first.decision.ratio == 0.8
                await finalize_model_usage(
                    database,
                    usage_id=first.usage_id,
                    status="succeeded",
                    actual_cny_fen=800,
                    input_tokens=1_200,
                    output_tokens=600,
                    latency_ms=950,
                )
            async with factory() as database:
                second = await reserve_model_budget(
                    database,
                    provider="qwen",
                    model="qwen3.7-plus",
                    purpose="content_generate",
                    estimated_cny_fen=100,
                )
                assert second.decision.warning is True
                await finalize_model_usage(
                    database,
                    usage_id=second.usage_id,
                    status="failed",
                    actual_cny_fen=100,
                    input_tokens=300,
                    output_tokens=0,
                    latency_ms=450,
                )
            async with factory() as database:
                third = await reserve_model_budget(
                    database,
                    provider="qwen",
                    model="qwen3.7-plus",
                    purpose="content_generate",
                    estimated_cny_fen=99,
                )
                assert third.decision.warning is True
            async with factory() as database:
                with pytest.raises(ApiFailure) as blocked:
                    await reserve_model_budget(
                        database,
                        provider="qwen",
                        model="qwen3.7-plus",
                        purpose="content_generate",
                        estimated_cny_fen=1,
                    )
                assert blocked.value.code == 42902

        asyncio.run(exercise())
