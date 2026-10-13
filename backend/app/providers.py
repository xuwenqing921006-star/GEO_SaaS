import asyncio
import base64
import binascii
import json
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from time import perf_counter
from typing import Literal, cast
from uuid import UUID

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import ModelUsage, ProviderSetting
from app.responses import ApiFailure

ProviderName = Literal["qwen", "deepseek", "doubao", "wenxin", "yuanbao", "kimi"]
SourceCapability = Literal["available", "no_sources", "not_supported"]
Purpose = Literal["writer", "strict_writer", "reviewer"]
CHINA_STANDARD_TIME = timezone(timedelta(hours=8), "Asia/Shanghai")
PROVIDER_OFFICIAL_HOSTS: dict[ProviderName, str] = {
    "qwen": "dashscope.aliyuncs.com",
    "deepseek": "api.deepseek.com",
    "doubao": "ark.cn-beijing.volces.com",
    "wenxin": "qianfan.baidubce.com",
    "yuanbao": "tokenhub.tencentmaas.com",
    "kimi": "api.moonshot.cn",
}


class SecretCipher:
    def __init__(self, encoded_key: str) -> None:
        try:
            key = base64.urlsafe_b64decode(encoded_key.encode("ascii"))
        except (UnicodeEncodeError, binascii.Error, ValueError) as error:
            raise ValueError("APP_MASTER_KEY 必须是 URL-safe Base64") from error
        if len(key) != 32:
            raise ValueError("APP_MASTER_KEY 解码后必须为 32 字节")
        self._cipher = AESGCM(key)

    def encrypt(self, provider: ProviderName, secret: str) -> bytes:
        nonce = os.urandom(12)
        encrypted = self._cipher.encrypt(
            nonce,
            secret.encode("utf-8"),
            provider.encode("ascii"),
        )
        return nonce + encrypted

    def decrypt(self, provider: ProviderName, encrypted: bytes) -> str:
        if len(encrypted) < 29:
            raise ValueError("加密密钥数据无效")
        plaintext = self._cipher.decrypt(
            encrypted[:12],
            encrypted[12:],
            provider.encode("ascii"),
        )
        return plaintext.decode("utf-8")


class StructuredProbe(BaseModel):
    ok: Literal[True]
    summary: str


@dataclass(frozen=True)
class ProviderCallResult:
    provider: ProviderName
    model: str
    latency_ms: int
    structured_output_valid: bool
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class ProviderTextResult:
    provider: ProviderName
    model: str
    content: str
    latency_ms: int
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True)
class ProviderSearchSource:
    index: int
    title: str
    url: str
    site_name: str | None = None
    snippet: str | None = None


@dataclass(frozen=True)
class ProviderDiagnosticResult:
    provider: ProviderName
    model: str
    content: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    sources: tuple[ProviderSearchSource, ...]
    source_capability: SourceCapability


@dataclass(frozen=True)
class ModelTarget:
    provider: ProviderName
    model: str


@dataclass(frozen=True)
class ModelRoute:
    primary: ModelTarget
    fallback: ModelTarget


def select_model_route(
    purpose: Purpose,
    *,
    qwen_writer_model: str | None,
    deepseek_reviewer_model: str | None,
    deepseek_fallback_model: str | None,
) -> ModelRoute:
    if purpose == "writer":
        if not deepseek_reviewer_model or not qwen_writer_model:
            raise ApiFailure(
                status_code=422,
                code=42201,
                message="DeepSeek 主写模型或千问备用模型尚未完整配置",
            )
        return ModelRoute(
            primary=ModelTarget(provider="deepseek", model=deepseek_reviewer_model),
            fallback=ModelTarget(provider="qwen", model=qwen_writer_model),
        )
    if not deepseek_reviewer_model or not qwen_writer_model:
        raise ApiFailure(
            status_code=422,
            code=42201,
            message="DeepSeek 主模型或千问备用模型尚未完整配置",
        )
    return ModelRoute(
        primary=ModelTarget(provider="deepseek", model=deepseek_reviewer_model),
        fallback=ModelTarget(provider="qwen", model=qwen_writer_model),
    )


class ProviderClient:
    def __init__(self, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport
        self._rejected_diagnostic_source_routes: set[tuple[ProviderName, str, str]] = set()

    async def test(
        self,
        *,
        provider: ProviderName,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
        structured: bool,
        workspace_id: str | None,
    ) -> ProviderCallResult:
        payload: dict[str, object] = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        '仅输出 JSON: {"ok":true,"summary":"connected"}'
                        if structured
                        else "只回复 connected"
                    ),
                },
                {"role": "user", "content": "connection probe"},
            ],
            "temperature": 0.6 if provider == "kimi" else 0,
            "max_tokens": 80,
        }
        if structured:
            payload["response_format"] = {"type": "json_object"}
        if provider == "qwen":
            payload["enable_thinking"] = False
        elif provider in {"deepseek", "kimi"}:
            payload["thinking"] = {"type": "disabled"}
        headers = {"Authorization": f"Bearer {api_key}"}
        if workspace_id:
            headers["X-DashScope-Workspace"] = workspace_id
        started = perf_counter()
        response = await self._post_with_retry(
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            payload=payload,
            timeout_seconds=timeout_seconds,
            provider=provider,
        )
        latency_ms = round((perf_counter() - started) * 1000)
        try:
            response_body = response.json()
            content = response_body["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise TypeError
            if structured:
                StructuredProbe.model_validate(json.loads(content))
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as error:
            raise ApiFailure(
                status_code=502,
                code=50201,
                message="模型返回格式异常，请稍后重试",
                retryable=True,
                provider=provider,
            ) from error
        usage = response_body.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0
        output_tokens = usage.get("completion_tokens", 0) if isinstance(usage, dict) else 0
        return ProviderCallResult(
            provider=provider,
            model=model,
            latency_ms=latency_ms,
            structured_output_valid=structured,
            input_tokens=input_tokens if isinstance(input_tokens, int) else 0,
            output_tokens=output_tokens if isinstance(output_tokens, int) else 0,
        )

    async def chat(
        self,
        *,
        provider: ProviderName,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
        system_prompt: str,
        user_prompt: str,
        structured: bool,
        workspace_id: str | None,
        max_tokens: int = 4_000,
    ) -> ProviderTextResult:
        payload: dict[str, object] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.6 if provider == "kimi" else 0.2,
            "max_tokens": max_tokens,
        }
        if structured:
            payload["response_format"] = {"type": "json_object"}
        if provider == "qwen":
            payload["enable_thinking"] = False
        elif provider in {"deepseek", "kimi"}:
            payload["thinking"] = {"type": "disabled"}
        headers = {"Authorization": f"Bearer {api_key}"}
        if workspace_id:
            headers["X-DashScope-Workspace"] = workspace_id
        started = perf_counter()
        response = await self._post_with_retry(
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            payload=payload,
            timeout_seconds=timeout_seconds,
            provider=provider,
        )
        latency_ms = round((perf_counter() - started) * 1000)
        try:
            response_body = response.json()
            content = response_body["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise TypeError
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise ApiFailure(
                status_code=502,
                code=50201,
                message="模型返回格式异常，请稍后重试",
                retryable=True,
                provider=provider,
            ) from error
        usage = response_body.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0) if isinstance(usage, dict) else 0
        output_tokens = usage.get("completion_tokens", 0) if isinstance(usage, dict) else 0
        return ProviderTextResult(
            provider=provider,
            model=model,
            content=content,
            latency_ms=latency_ms,
            input_tokens=input_tokens if isinstance(input_tokens, int) else 0,
            output_tokens=output_tokens if isinstance(output_tokens, int) else 0,
        )

    async def diagnostic_chat(
        self,
        *,
        provider: ProviderName,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
        system_prompt: str,
        user_prompt: str,
        workspace_id: str | None,
        max_tokens: int = 1_200,
    ) -> ProviderDiagnosticResult:
        """Run one GEO probe and retain only provider-returned source evidence."""

        route_key = (provider, base_url.rstrip("/"), model)
        if provider == "qwen":
            if re.match(r"qwen3\.(?:5|6|7)", model.casefold()):
                return await self._qwen_compatible_diagnostic_chat(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    timeout_seconds=timeout_seconds,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    workspace_id=workspace_id,
                    max_tokens=max_tokens,
                )
            if route_key in self._rejected_diagnostic_source_routes:
                return await self._diagnostic_without_sources(
                    provider=provider,
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    timeout_seconds=timeout_seconds,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    workspace_id=workspace_id,
                    max_tokens=max_tokens,
                    source_capability="no_sources",
                )
            try:
                return await self._dashscope_diagnostic_chat(
                    api_key=api_key,
                    model=model,
                    timeout_seconds=timeout_seconds,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    workspace_id=workspace_id,
                    max_tokens=max_tokens,
                )
            except ApiFailure:
                self._rejected_diagnostic_source_routes.add(route_key)
                return await self._diagnostic_without_sources(
                    provider=provider,
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    timeout_seconds=timeout_seconds,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    workspace_id=workspace_id,
                    max_tokens=max_tokens,
                    source_capability="no_sources",
                )
        if provider == "doubao":
            if route_key in self._rejected_diagnostic_source_routes:
                return await self._diagnostic_without_sources(
                    provider=provider,
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    timeout_seconds=timeout_seconds,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    workspace_id=workspace_id,
                    max_tokens=max_tokens,
                    source_capability="no_sources",
                )
            try:
                return await self._responses_diagnostic_chat(
                    provider=provider,
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    timeout_seconds=timeout_seconds,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=max_tokens,
                )
            except ApiFailure:
                self._rejected_diagnostic_source_routes.add(route_key)
                return await self._diagnostic_without_sources(
                    provider=provider,
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    timeout_seconds=timeout_seconds,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    workspace_id=workspace_id,
                    max_tokens=max_tokens,
                    source_capability="no_sources",
                )
        if provider == "wenxin":
            try:
                return await self._wenxin_diagnostic_chat(
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    timeout_seconds=timeout_seconds,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=max_tokens,
                )
            except ApiFailure:
                return await self._diagnostic_without_sources(
                    provider=provider,
                    base_url=base_url,
                    api_key=api_key,
                    model=model,
                    timeout_seconds=timeout_seconds,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    workspace_id=workspace_id,
                    max_tokens=max_tokens,
                    source_capability="no_sources",
                )
        return await self._diagnostic_without_sources(
            provider=provider,
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            workspace_id=workspace_id,
            max_tokens=max_tokens,
            source_capability="not_supported",
        )

    async def _diagnostic_without_sources(
        self,
        *,
        provider: ProviderName,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
        system_prompt: str,
        user_prompt: str,
        workspace_id: str | None,
        max_tokens: int,
        source_capability: SourceCapability,
    ) -> ProviderDiagnosticResult:
        result = await self.chat(
            provider=provider,
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            structured=False,
            workspace_id=workspace_id,
            max_tokens=max_tokens,
        )
        return ProviderDiagnosticResult(
            provider=result.provider,
            model=result.model,
            content=result.content,
            latency_ms=result.latency_ms,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            sources=(),
            source_capability=source_capability,
        )

    async def _qwen_compatible_diagnostic_chat(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
        system_prompt: str,
        user_prompt: str,
        workspace_id: str | None,
        max_tokens: int,
    ) -> ProviderDiagnosticResult:
        payload: dict[str, object] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "enable_thinking": False,
            "enable_search": True,
            "search_options": {
                "enable_source": True,
                "enable_citation": True,
            },
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        if workspace_id:
            headers["X-DashScope-Workspace"] = workspace_id
        started = perf_counter()
        response = await self._post_with_retry(
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            payload=payload,
            timeout_seconds=timeout_seconds,
            provider="qwen",
        )
        latency_ms = round((perf_counter() - started) * 1000)
        body = self._response_json(response, "qwen")
        try:
            choices = cast(list[dict[str, object]], body["choices"])
            message = cast(dict[str, object], choices[0]["message"])
            content = message["content"]
            if not isinstance(content, str) or not content.strip():
                raise TypeError
        except (KeyError, IndexError, TypeError) as error:
            raise self._format_error("qwen") from error
        raw_sources: object = body.get("search_results", [])
        search_info = body.get("search_info")
        if isinstance(search_info, dict):
            raw_sources = search_info.get("search_results", raw_sources)
        message_search_info = message.get("search_info")
        if isinstance(message_search_info, dict):
            raw_sources = message_search_info.get("search_results", raw_sources)
        if isinstance(message.get("search_results"), list):
            raw_sources = message["search_results"]
        sources = self._normalize_sources(raw_sources)
        usage = body.get("usage", {})
        return ProviderDiagnosticResult(
            provider="qwen",
            model=model,
            content=content,
            latency_ms=latency_ms,
            input_tokens=self._usage_value(usage, "prompt_tokens", "input_tokens"),
            output_tokens=self._usage_value(usage, "completion_tokens", "output_tokens"),
            sources=sources,
            source_capability="available" if sources else "no_sources",
        )

    async def _dashscope_diagnostic_chat(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: int,
        system_prompt: str,
        user_prompt: str,
        workspace_id: str | None,
        max_tokens: int,
    ) -> ProviderDiagnosticResult:
        payload: dict[str, object] = {
            "model": model,
            "input": {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            "parameters": {
                "enable_search": True,
                "search_options": {
                    "enable_source": True,
                    "enable_citation": True,
                },
                "result_format": "message",
                "max_tokens": max_tokens,
            },
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        if workspace_id:
            headers["X-DashScope-Workspace"] = workspace_id
        started = perf_counter()
        response = await self._post_with_retry(
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation",
            headers=headers,
            payload=payload,
            timeout_seconds=timeout_seconds,
            provider="qwen",
        )
        latency_ms = round((perf_counter() - started) * 1000)
        body = self._response_json(response, "qwen")
        try:
            output = cast(dict[str, object], body["output"])
            choices = cast(list[dict[str, object]], output["choices"])
            message = cast(dict[str, object], choices[0]["message"])
            content = message["content"]
            if not isinstance(content, str) or not content.strip():
                raise TypeError
        except (KeyError, IndexError, TypeError) as error:
            raise self._format_error("qwen") from error
        search_info = output.get("search_info")
        source_rows = (
            cast(dict[str, object], search_info).get("search_results", [])
            if isinstance(search_info, dict)
            else []
        )
        sources = self._normalize_sources(source_rows)
        usage = body.get("usage", {})
        return ProviderDiagnosticResult(
            provider="qwen",
            model=model,
            content=content,
            latency_ms=latency_ms,
            input_tokens=self._usage_value(usage, "input_tokens", "prompt_tokens"),
            output_tokens=self._usage_value(usage, "output_tokens", "completion_tokens"),
            sources=sources,
            source_capability="available" if sources else "no_sources",
        )

    async def _wenxin_diagnostic_chat(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> ProviderDiagnosticResult:
        payload: dict[str, object] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "stream": False,
            "web_search": {
                "enable": True,
                "enable_trace": True,
                "enable_status": False,
                "enable_citation": True,
                "search_number": 10,
                "reference_number": 5,
            },
        }
        started = perf_counter()
        response = await self._post_with_retry(
            f"{base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            payload=payload,
            timeout_seconds=timeout_seconds,
            provider="wenxin",
        )
        latency_ms = round((perf_counter() - started) * 1000)
        body = self._response_json(response, "wenxin")
        try:
            choices = cast(list[dict[str, object]], body["choices"])
            message = cast(dict[str, object], choices[0]["message"])
            content = message["content"]
            if not isinstance(content, str) or not content.strip():
                raise TypeError
        except (KeyError, IndexError, TypeError) as error:
            raise self._format_error("wenxin") from error
        sources = self._normalize_sources(body.get("search_results", []))
        usage = body.get("usage", {})
        return ProviderDiagnosticResult(
            provider="wenxin",
            model=model,
            content=content,
            latency_ms=latency_ms,
            input_tokens=self._usage_value(usage, "prompt_tokens", "input_tokens"),
            output_tokens=self._usage_value(usage, "completion_tokens", "output_tokens"),
            sources=sources,
            source_capability="available" if sources else "no_sources",
        )

    async def _responses_diagnostic_chat(
        self,
        *,
        provider: ProviderName,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int,
    ) -> ProviderDiagnosticResult:
        payload: dict[str, object] = {
            "model": model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "tools": [{"type": "web_search", "max_keyword": 3, "limit": 10}],
            "max_output_tokens": max_tokens,
            "stream": False,
        }
        started = perf_counter()
        response = await self._post_with_retry(
            f"{base_url.rstrip('/')}/responses",
            headers={"Authorization": f"Bearer {api_key}"},
            payload=payload,
            timeout_seconds=timeout_seconds,
            provider=provider,
        )
        latency_ms = round((perf_counter() - started) * 1000)
        body = self._response_json(response, provider)
        content_parts: list[str] = []
        raw_sources: list[object] = []
        output = body.get("output", [])
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                action = item.get("action")
                if isinstance(action, dict) and isinstance(action.get("sources"), list):
                    raw_sources.extend(cast(list[object], action["sources"]))
                item_content = item.get("content")
                if not isinstance(item_content, list):
                    continue
                for part in item_content:
                    if not isinstance(part, dict):
                        continue
                    text_value = part.get("text")
                    if isinstance(text_value, str) and text_value.strip():
                        content_parts.append(text_value)
                    annotations = part.get("annotations")
                    if isinstance(annotations, list):
                        raw_sources.extend(cast(list[object], annotations))
        content = "\n".join(content_parts).strip()
        if not content:
            output_text = body.get("output_text")
            content = output_text.strip() if isinstance(output_text, str) else ""
        if not content:
            raise self._format_error(provider)
        sources = self._normalize_sources(raw_sources)
        if not sources:
            sources = self._sources_from_text(content)
        usage = body.get("usage", {})
        return ProviderDiagnosticResult(
            provider=provider,
            model=model,
            content=content,
            latency_ms=latency_ms,
            input_tokens=self._usage_value(usage, "input_tokens", "prompt_tokens"),
            output_tokens=self._usage_value(usage, "output_tokens", "completion_tokens"),
            sources=sources,
            source_capability="available" if sources else "no_sources",
        )

    @staticmethod
    def _response_json(
        response: httpx.Response,
        provider: ProviderName,
    ) -> dict[str, object]:
        try:
            body = response.json()
            if not isinstance(body, dict):
                raise TypeError
            return cast(dict[str, object], body)
        except (TypeError, ValueError) as error:
            raise ProviderClient._format_error(provider) from error

    @staticmethod
    def _format_error(provider: ProviderName) -> ApiFailure:
        return ApiFailure(
            status_code=502,
            code=50201,
            message="模型返回格式异常，请稍后重试",
            retryable=True,
            provider=provider,
        )

    @staticmethod
    def _usage_value(usage: object, *keys: str) -> int:
        if not isinstance(usage, dict):
            return 0
        for key in keys:
            value = usage.get(key)
            if isinstance(value, int):
                return value
        return 0

    @staticmethod
    def _normalize_sources(raw_rows: object) -> tuple[ProviderSearchSource, ...]:
        if not isinstance(raw_rows, list):
            return ()
        sources: list[ProviderSearchSource] = []
        seen: set[str] = set()
        for offset, row in enumerate(raw_rows, start=1):
            if not isinstance(row, dict):
                continue
            nested = row.get("url_citation")
            source = nested if isinstance(nested, dict) else row
            url = source.get("url")
            if not isinstance(url, str) or not url.startswith(("https://", "http://")):
                continue
            normalized_url = url.strip()
            if normalized_url in seen:
                continue
            title = source.get("title")
            site_name = source.get("site_name")
            index = source.get("index")
            snippet_value = next(
                (
                    source.get(key)
                    for key in ("snippet", "summary", "content", "text")
                    if isinstance(source.get(key), str) and str(source.get(key)).strip()
                ),
                None,
            )
            snippet = (
                re.sub(r"\s+", " ", cast(str, snippet_value)).strip()[:500]
                if snippet_value is not None
                else None
            )
            sources.append(
                ProviderSearchSource(
                    index=index if isinstance(index, int) else offset,
                    title=(
                        title.strip()
                        if isinstance(title, str) and title.strip()
                        else normalized_url
                    ),
                    url=normalized_url,
                    site_name=(
                        site_name.strip()
                        if isinstance(site_name, str) and site_name.strip()
                        else None
                    ),
                    snippet=snippet,
                ),
            )
            seen.add(normalized_url)
        return tuple(sources)

    @staticmethod
    def _sources_from_text(content: str) -> tuple[ProviderSearchSource, ...]:
        urls = list(
            dict.fromkeys(
                match.rstrip(".,\uff0c\u3002\uff1b;\uff09)>")
                for match in re.findall(r"https?://[^\s\])>]+", content)
            ),
        )
        return tuple(
            ProviderSearchSource(index=index, title=url, url=url)
            for index, url in enumerate(urls, start=1)
        )

    async def _post_with_retry(
        self,
        url: str,
        *,
        headers: dict[str, str],
        payload: dict[str, object],
        timeout_seconds: int,
        provider: ProviderName,
    ) -> httpx.Response:
        async with httpx.AsyncClient(
            transport=self._transport,
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            for attempt in range(3):
                try:
                    response = await client.post(url, headers=headers, json=payload)
                except httpx.TimeoutException as error:
                    if attempt < 2:
                        await asyncio.sleep(0.1 * (2**attempt))
                        continue
                    raise ApiFailure(
                        status_code=504,
                        code=50401,
                        message="模型服务响应超时，请稍后重试",
                        retryable=True,
                        provider=provider,
                    ) from error
                except httpx.HTTPError as error:
                    raise ApiFailure(
                        status_code=502,
                        code=50201,
                        message="模型服务暂时不可用，请检查配置后重试",
                        retryable=True,
                        provider=provider,
                    ) from error
                if response.status_code == 429 and attempt < 2:
                    retry_after = response.headers.get("Retry-After", "")
                    delay = (
                        min(float(retry_after), 2.0)
                        if retry_after.replace(".", "", 1).isdigit()
                        else 0.1 * (2**attempt)
                    )
                    await asyncio.sleep(delay)
                    continue
                if response.status_code == 429:
                    raise ApiFailure(
                        status_code=502,
                        code=50201,
                        message="模型服务限流，请稍后重试",
                        retryable=True,
                        provider=provider,
                    )
                if response.is_error:
                    raise ApiFailure(
                        status_code=502,
                        code=50201,
                        message="模型服务暂时不可用，请检查配置后重试",
                        retryable=response.status_code >= 500,
                        provider=provider,
                    )
                return response
        raise RuntimeError("provider retry loop exited unexpectedly")


@dataclass(frozen=True)
class BudgetDecision:
    ratio: float
    warning: bool


@dataclass(frozen=True)
class BudgetReservation:
    usage_id: UUID
    decision: BudgetDecision


def _budget_lock_key(provider: ProviderName, usage_date: object) -> int:
    digest = sha256(f"model-budget:{provider}:{usage_date}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


async def reserve_model_budget(
    database: AsyncSession,
    *,
    provider: ProviderName,
    model: str,
    purpose: str,
    estimated_cny_fen: int,
    client_id: UUID | None = None,
    fact_snapshot_id: UUID | None = None,
    prompt_version: str | None = None,
    pricing_version: str | None = None,
    require_enabled_secret: bool = True,
    commit: bool = True,
) -> BudgetReservation:
    if estimated_cny_fen < 0:
        raise ValueError("estimated_cny_fen cannot be negative")
    usage_date = datetime.now(CHINA_STANDARD_TIME).date()
    bind = database.get_bind()
    if bind.dialect.name == "postgresql":
        await database.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _budget_lock_key(provider, usage_date)},
        )
    setting = await database.get(ProviderSetting, provider)
    if setting is None:
        raise ApiFailure(
            status_code=422,
            code=42201,
            message="模型供应商尚未启用或密钥未配置",
            provider=provider,
        )
    if require_enabled_secret and (not setting.enabled or setting.encrypted_api_key is None):
        raise ApiFailure(
            status_code=422,
            code=42201,
            message="模型供应商尚未启用或密钥未配置",
            provider=provider,
        )
    spent = await database.scalar(
        select(func.coalesce(func.sum(ModelUsage.cost_cny_fen), 0)).where(
            ModelUsage.provider == provider,
            ModelUsage.usage_date == usage_date,
        ),
    )
    decision = enforce_budget(
        provider=provider,
        spent_cny_fen=int(spent or 0),
        daily_budget_cny_fen=setting.daily_budget_cny_fen,
        estimated_cny_fen=estimated_cny_fen,
    )
    usage = ModelUsage(
        client_id=client_id,
        provider=provider,
        model=model,
        purpose=purpose,
        fact_snapshot_id=fact_snapshot_id,
        prompt_version=prompt_version,
        pricing_version=pricing_version,
        usage_date=usage_date,
        input_tokens=0,
        output_tokens=0,
        cost_cny_fen=estimated_cny_fen,
        status="reserved",
    )
    database.add(usage)
    if commit:
        await database.commit()
    else:
        await database.flush()
    return BudgetReservation(usage_id=usage.id, decision=decision)


async def finalize_model_usage(
    database: AsyncSession,
    *,
    usage_id: UUID,
    status: Literal["succeeded", "failed"],
    actual_cny_fen: int,
    input_tokens: int,
    output_tokens: int,
    latency_ms: int | None,
    input_hash: str | None = None,
    output_hash: str | None = None,
    fallback_reason: str | None = None,
    commit: bool = True,
) -> None:
    if min(actual_cny_fen, input_tokens, output_tokens) < 0:
        raise ValueError("usage values cannot be negative")
    result = await database.execute(
        update(ModelUsage)
        .where(ModelUsage.id == usage_id, ModelUsage.status == "reserved")
        .values(
            status=status,
            cost_cny_fen=actual_cny_fen,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            input_hash=input_hash,
            output_hash=output_hash,
            fallback_reason=fallback_reason,
        )
        .returning(ModelUsage.id),
    )
    if result.scalar_one_or_none() is None:
        if commit:
            await database.rollback()
        raise ApiFailure(
            status_code=409,
            code=40901,
            message="模型用量记录已完成或不存在",
        )
    if commit:
        await database.commit()
    else:
        await database.flush()


def enforce_budget(
    *,
    provider: ProviderName,
    spent_cny_fen: int,
    daily_budget_cny_fen: int,
    estimated_cny_fen: int = 0,
) -> BudgetDecision:
    if daily_budget_cny_fen <= 0:
        return BudgetDecision(ratio=0, warning=False)
    projected = spent_cny_fen + estimated_cny_fen
    ratio = projected / daily_budget_cny_fen
    if ratio >= 1:
        raise ApiFailure(
            status_code=429,
            code=42902,
            message="今日模型预算已用尽，请调整预算或次日再试",
            provider=provider,
        )
    return BudgetDecision(ratio=ratio, warning=ratio >= 0.8)


async def execute_with_fallback[ResultT](
    primary: Callable[[], Awaitable[ResultT]],
    fallback: Callable[[], Awaitable[ResultT]],
) -> tuple[ResultT, bool]:
    try:
        return await primary(), False
    except ApiFailure as primary_error:
        if primary_error.status_code not in {502, 504}:
            raise
    try:
        return await fallback(), True
    except ApiFailure as fallback_error:
        raise ApiFailure(
            status_code=502,
            code=50201,
            message="主模型与备用模型均不可用，请稍后重试",
            retryable=True,
        ) from fallback_error
