import asyncio
import base64
import json
import os

import httpx
import pytest

from app.providers import (
    ProviderClient,
    SecretCipher,
    enforce_budget,
    execute_with_fallback,
    select_model_route,
)
from app.responses import ApiFailure


@pytest.mark.unit
def test_budget_warns_at_80_percent_and_blocks_at_100_percent() -> None:
    warning = enforce_budget(
        provider="qwen",
        spent_cny_fen=800,
        daily_budget_cny_fen=1_000,
    )
    assert warning.warning is True
    assert warning.ratio == 0.8
    with pytest.raises(ApiFailure) as blocked:
        enforce_budget(
            provider="deepseek",
            spent_cny_fen=950,
            daily_budget_cny_fen=1_000,
            estimated_cny_fen=50,
        )
    assert blocked.value.code == 42902


@pytest.mark.unit
def test_model_routes_match_writer_reviewer_and_bilateral_fallback_policy() -> None:
    writer = select_model_route(
        "writer",
        qwen_writer_model="qwen3.7-plus",
        deepseek_reviewer_model="deepseek-v4-pro",
        deepseek_fallback_model="deepseek-v4-flash",
    )
    assert (writer.primary.provider, writer.primary.model) == (
        "deepseek",
        "deepseek-v4-pro",
    )
    assert (writer.fallback.provider, writer.fallback.model) == (
        "qwen",
        "qwen3.7-plus",
    )

    reviewer = select_model_route(
        "reviewer",
        qwen_writer_model="qwen3.7-plus",
        deepseek_reviewer_model="deepseek-v4-pro",
        deepseek_fallback_model="deepseek-v4-flash",
    )
    assert (reviewer.primary.provider, reviewer.primary.model) == (
        "deepseek",
        "deepseek-v4-pro",
    )
    assert (reviewer.fallback.provider, reviewer.fallback.model) == (
        "qwen",
        "qwen3.7-plus",
    )

    strict_writer = select_model_route(
        "strict_writer",
        qwen_writer_model="qwen3.7-plus",
        deepseek_reviewer_model="deepseek-v4-pro",
        deepseek_fallback_model="deepseek-v4-flash",
    )
    assert (strict_writer.primary.provider, strict_writer.primary.model) == (
        "deepseek",
        "deepseek-v4-pro",
    )
    assert (strict_writer.fallback.provider, strict_writer.fallback.model) == (
        "qwen",
        "qwen3.7-plus",
    )


@pytest.mark.unit
def test_fallback_runs_once_and_both_unavailable_is_generic() -> None:
    async def unavailable() -> str:
        raise ApiFailure(
            status_code=504,
            code=50401,
            message="timeout",
            provider="qwen",
        )

    async def fallback() -> str:
        return "fallback-result"

    result, used_fallback = asyncio.run(execute_with_fallback(unavailable, fallback))
    assert result == "fallback-result"
    assert used_fallback is True

    with pytest.raises(ApiFailure) as both_failed:
        asyncio.run(execute_with_fallback(unavailable, unavailable))
    assert both_failed.value.code == 50201
    assert "均不可用" in both_failed.value.message


@pytest.mark.unit
def test_provider_retries_429_at_most_three_times_and_rejects_invalid_schema() -> None:
    attempts = 0

    def limited(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429, json={"error": {"message": "do not expose"}})

    client = ProviderClient(httpx.MockTransport(limited))
    with pytest.raises(ApiFailure) as limited_error:
        asyncio.run(
            client.test(
                provider="deepseek",
                base_url="https://provider.invalid/v1",
                api_key="temporary-test-key",
                model="deepseek-v4-pro",
                timeout_seconds=5,
                structured=True,
                workspace_id=None,
            ),
        )
    assert limited_error.value.code == 50201
    assert attempts == 3
    assert "do not expose" not in limited_error.value.message

    def invalid(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps({"ok": "yes"})}}]},
        )

    invalid_client = ProviderClient(httpx.MockTransport(invalid))
    with pytest.raises(ApiFailure) as schema_error:
        asyncio.run(
            invalid_client.test(
                provider="qwen",
                base_url="https://provider.invalid/v1",
                api_key="temporary-test-key",
                model="qwen3.7-plus",
                timeout_seconds=5,
                structured=True,
                workspace_id=None,
            ),
        )
    assert schema_error.value.code == 50201
    assert "格式异常" in schema_error.value.message


@pytest.mark.unit
def test_provider_retries_timeout_at_most_three_times() -> None:
    attempts = 0

    def timeout(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("sensitive upstream detail", request=request)

    client = ProviderClient(httpx.MockTransport(timeout))
    with pytest.raises(ApiFailure) as timeout_error:
        asyncio.run(
            client.test(
                provider="qwen",
                base_url="https://provider.invalid/v1",
                api_key="temporary-test-key",
                model="qwen3.7-plus",
                timeout_seconds=5,
                structured=True,
                workspace_id=None,
            ),
        )
    assert attempts == 3
    assert timeout_error.value.code == 50401
    assert "sensitive upstream detail" not in timeout_error.value.message


@pytest.mark.unit
def test_secret_cipher_and_missing_routes_fail_closed() -> None:
    with pytest.raises(ValueError, match="URL-safe Base64"):
        SecretCipher("不是-base64")
    with pytest.raises(ValueError, match="32 字节"):
        SecretCipher(base64.urlsafe_b64encode(b"short").decode("ascii"))

    cipher = SecretCipher(base64.urlsafe_b64encode(os.urandom(32)).decode("ascii"))
    with pytest.raises(ValueError, match="数据无效"):
        cipher.decrypt("qwen", b"short")

    with pytest.raises(ApiFailure, match="主写模型"):
        select_model_route(
            "writer",
            qwen_writer_model=None,
            deepseek_reviewer_model="reviewer",
            deepseek_fallback_model="fallback",
        )
    with pytest.raises(ApiFailure, match="DeepSeek 主模型"):
        select_model_route(
            "reviewer",
            qwen_writer_model="writer",
            deepseek_reviewer_model=None,
            deepseek_fallback_model="fallback",
        )


@pytest.mark.unit
def test_provider_success_payload_variants_and_invalid_chat_are_typed() -> None:
    requests: list[dict[str, object]] = []

    def success(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "connected"}}],
                "usage": "invalid-usage-shape",
            },
        )

    client = ProviderClient(httpx.MockTransport(success))
    probe = asyncio.run(
        client.test(
            provider="deepseek",
            base_url="https://provider.invalid/v1/",
            api_key="temporary-test-key",
            model="deepseek-v4-pro",
            timeout_seconds=5,
            structured=False,
            workspace_id="workspace-id",
        )
    )
    assert probe.input_tokens == 0
    assert probe.output_tokens == 0
    assert requests[0]["thinking"] == {"type": "disabled"}
    assert "response_format" not in requests[0]

    def valid_chat(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"answer":"ok"}'}}],
                "usage": {"prompt_tokens": "bad", "completion_tokens": 7},
            },
        )

    chat_client = ProviderClient(httpx.MockTransport(valid_chat))
    chat = asyncio.run(
        chat_client.chat(
            provider="qwen",
            base_url="https://provider.invalid/v1",
            api_key="temporary-test-key",
            model="qwen3.7-plus",
            timeout_seconds=5,
            system_prompt="system",
            user_prompt="user",
            structured=True,
            workspace_id="workspace-id",
        )
    )
    assert chat.input_tokens == 0
    assert chat.output_tokens == 7
    assert requests[1]["response_format"] == {"type": "json_object"}
    assert requests[1]["enable_thinking"] is False

    invalid_client = ProviderClient(
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={"choices": [{"message": {"content": "   "}}]},
            )
        )
    )
    with pytest.raises(ApiFailure, match="格式异常"):
        asyncio.run(
            invalid_client.chat(
                provider="deepseek",
                base_url="https://provider.invalid/v1",
                api_key="temporary-test-key",
                model="deepseek-v4-pro",
                timeout_seconds=5,
                system_prompt="system",
                user_prompt="user",
                structured=False,
                workspace_id=None,
            )
        )


@pytest.mark.unit
def test_provider_http_failures_and_budget_edge_paths_are_explicit() -> None:
    def connection_error(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sensitive transport detail", request=request)

    client = ProviderClient(httpx.MockTransport(connection_error))
    with pytest.raises(ApiFailure) as unavailable:
        asyncio.run(
            client.test(
                provider="qwen",
                base_url="https://provider.invalid/v1",
                api_key="temporary-test-key",
                model="qwen3.7-plus",
                timeout_seconds=5,
                structured=False,
                workspace_id=None,
            )
        )
    assert unavailable.value.retryable is True
    assert "sensitive transport detail" not in unavailable.value.message

    for status_code, retryable in ((400, False), (500, True)):
        error_client = ProviderClient(
            httpx.MockTransport(lambda _, code=status_code: httpx.Response(code))
        )
        with pytest.raises(ApiFailure) as response_error:
            asyncio.run(
                error_client.test(
                    provider="qwen",
                    base_url="https://provider.invalid/v1",
                    api_key="temporary-test-key",
                    model="qwen3.7-plus",
                    timeout_seconds=5,
                    structured=False,
                    workspace_id=None,
                )
            )
        assert response_error.value.retryable is retryable

    attempts = 0

    def retry_then_succeed(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "connected"}}]},
        )

    retry_client = ProviderClient(httpx.MockTransport(retry_then_succeed))
    asyncio.run(
        retry_client.test(
            provider="qwen",
            base_url="https://provider.invalid/v1",
            api_key="temporary-test-key",
            model="qwen3.7-plus",
            timeout_seconds=5,
            structured=False,
            workspace_id=None,
        )
    )
    assert attempts == 2

    assert (
        enforce_budget(
            provider="qwen",
            spent_cny_fen=999,
            daily_budget_cny_fen=0,
        ).ratio
        == 0
    )

    async def primary_success() -> str:
        return "primary"

    async def must_not_run() -> str:
        raise AssertionError("fallback should not run")

    assert asyncio.run(execute_with_fallback(primary_success, must_not_run)) == (
        "primary",
        False,
    )

    async def non_retryable() -> str:
        raise ApiFailure(status_code=422, code=42201, message="blocked")

    with pytest.raises(ApiFailure, match="blocked"):
        asyncio.run(execute_with_fallback(non_retryable, must_not_run))


@pytest.mark.unit
def test_diagnostic_provider_calls_retain_only_real_search_sources() -> None:
    requests: list[tuple[str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append((request.url.path, payload))
        if request.url.host == "dashscope.aliyuncs.com":
            return httpx.Response(
                200,
                json={
                    "output": {
                        "choices": [{"message": {"content": "千问回答 [1]"}}],
                        "search_info": {
                            "search_results": [
                                {
                                    "index": 1,
                                    "title": "即墨少儿美术机构观察",
                                    "url": "https://baijiahao.baidu.com/s?id=1",
                                    "site_name": "百家号",
                                    "snippet": "包含课程、师资与试听信息。",
                                },
                            ],
                        },
                    },
                    "usage": {"prompt_tokens": 20, "completion_tokens": 10},
                },
            )
        if request.url.host == "qianfan.baidubce.com":
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "文心回答 [1]"}}],
                    "search_results": [
                        {
                            "index": 1,
                            "title": "本地美术课程怎么选",
                            "url": "https://www.sohu.com/a/1_2",
                        },
                    ],
                    "usage": {"prompt_tokens": 18, "completion_tokens": 9},
                },
            )
        if request.url.path.endswith("/responses"):
            return httpx.Response(
                200,
                json={
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "豆包回答",
                                    "annotations": [
                                        {
                                            "type": "url_citation",
                                            "url": "https://www.toutiao.com/article/1/",
                                            "title": "少儿美术学习建议",
                                        },
                                    ],
                                },
                            ],
                        },
                    ],
                    "usage": {"input_tokens": 22, "output_tokens": 11},
                },
            )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "DeepSeek 回答"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8},
            },
        )

    client = ProviderClient(httpx.MockTransport(handler))
    common = {
        "api_key": "temporary-test-key",
        "timeout_seconds": 5,
        "system_prompt": "system",
        "user_prompt": "即墨少儿美术哪家好",
        "workspace_id": None,
    }
    qwen = asyncio.run(
        client.diagnostic_chat(
            provider="qwen",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            model="qwen-plus",
            **common,
        ),
    )
    assert qwen.source_capability == "available"
    assert qwen.sources[0].site_name == "百家号"
    assert qwen.sources[0].snippet == "包含课程、师资与试听信息。"
    assert requests[0][0].endswith("/text-generation/generation")
    assert requests[0][1]["parameters"] == {
        "enable_search": True,
        "search_options": {"enable_source": True, "enable_citation": True},
        "result_format": "message",
        "max_tokens": 1_200,
    }

    wenxin = asyncio.run(
        client.diagnostic_chat(
            provider="wenxin",
            base_url="https://qianfan.baidubce.com/v2",
            model="ernie-4.5-turbo-32k",
            **common,
        ),
    )
    assert wenxin.sources[0].url == "https://www.sohu.com/a/1_2"
    assert requests[1][1]["web_search"] == {
        "enable": True,
        "enable_trace": True,
        "enable_status": False,
        "enable_citation": True,
        "search_number": 10,
        "reference_number": 5,
    }

    doubao = asyncio.run(
        client.diagnostic_chat(
            provider="doubao",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            model="doubao-seed-2-1-pro-260628",
            **common,
        ),
    )
    assert doubao.sources[0].title == "少儿美术学习建议"
    assert requests[2][1]["tools"] == [
        {"type": "web_search", "max_keyword": 3, "limit": 10},
    ]

    deepseek = asyncio.run(
        client.diagnostic_chat(
            provider="deepseek",
            base_url="https://api.deepseek.com/v1",
            model="deepseek-v4-pro",
            **common,
        ),
    )
    assert deepseek.source_capability == "not_supported"
    assert deepseek.sources == ()


@pytest.mark.unit
def test_doubao_diagnostic_falls_back_when_model_has_no_web_search_tool() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/responses"):
            return httpx.Response(400, json={"error": {"message": "tool unsupported"}})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "普通豆包回答"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8},
            },
        )

    result = asyncio.run(
        ProviderClient(httpx.MockTransport(handler)).diagnostic_chat(
            provider="doubao",
            base_url="https://ark.cn-beijing.volces.com/api/v3",
            api_key="temporary-test-key",
            model="doubao-seed-2-0-lite-260215",
            timeout_seconds=5,
            system_prompt="system",
            user_prompt="即墨少儿美术哪家好",
            workspace_id=None,
        ),
    )
    assert paths == ["/api/v3/responses", "/api/v3/chat/completions"]
    assert result.content == "普通豆包回答"
    assert result.source_capability == "no_sources"
    assert result.sources == ()


@pytest.mark.unit
def test_qwen_37_diagnostic_uses_compatible_search_endpoint_directly() -> None:
    requests: list[tuple[str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append((request.url.path, payload))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "千问回答 [1]"}}],
                "search_results": [
                    {
                        "index": 1,
                        "title": "即墨少儿美术机构观察",
                        "url": "https://baijiahao.baidu.com/s?id=1",
                        "site_name": "百家号",
                    },
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10},
            },
        )

    result = asyncio.run(
        ProviderClient(httpx.MockTransport(handler)).diagnostic_chat(
            provider="qwen",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key="temporary-test-key",
            model="qwen3.7-plus",
            timeout_seconds=5,
            system_prompt="system",
            user_prompt="即墨少儿美术哪家好",
            workspace_id=None,
        ),
    )

    assert requests[0][0] == "/compatible-mode/v1/chat/completions"
    assert requests[0][1]["enable_search"] is True
    assert result.source_capability == "available"
    assert result.sources[0].site_name == "百家号"


@pytest.mark.unit
def test_doubao_diagnostic_remembers_rejected_responses_capability() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/responses"):
            return httpx.Response(404, json={"error": {"message": "not found"}})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "普通豆包回答"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8},
            },
        )

    client = ProviderClient(httpx.MockTransport(handler))
    common = {
        "provider": "doubao",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "api_key": "temporary-test-key",
        "model": "doubao-seed-2-0-lite-260215",
        "timeout_seconds": 5,
        "system_prompt": "system",
        "workspace_id": None,
    }

    asyncio.run(client.diagnostic_chat(user_prompt="问题一", **common))
    asyncio.run(client.diagnostic_chat(user_prompt="问题二", **common))

    assert paths == [
        "/api/v3/responses",
        "/api/v3/chat/completions",
        "/api/v3/chat/completions",
    ]
