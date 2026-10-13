from datetime import UTC, datetime
from typing import Literal

import httpx
from fastapi import APIRouter, Request, Response
from pydantic import (
    AnyHttpUrl,
    BaseModel,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
)
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.auth import Authenticated, CsrfAuthenticated
from app.config import Settings
from app.database import DatabaseSession, ProviderSetting, RuntimeSetting
from app.providers import (
    PROVIDER_OFFICIAL_HOSTS,
    ProviderClient,
    ProviderName,
    SecretCipher,
    finalize_model_usage,
    reserve_model_budget,
)
from app.responses import ApiFailure, success_response

DEFAULT_PROVIDERS: dict[ProviderName, dict[str, object]] = {
    "qwen": {
        "enabled": False,
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "workspace_id": None,
        "writer_model": "qwen3.7-plus",
        "reviewer_model": None,
        "fallback_model": None,
        "daily_budget_cny_fen": 3_000,
        "timeout_seconds": 45,
    },
    "deepseek": {
        "enabled": False,
        "base_url": "https://api.deepseek.com/v1",
        "workspace_id": None,
        "writer_model": None,
        "reviewer_model": "deepseek-v4-pro",
        "fallback_model": "deepseek-v4-flash",
        "daily_budget_cny_fen": 3_000,
        "timeout_seconds": 45,
    },
    "doubao": {
        "enabled": False,
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "workspace_id": None,
        "writer_model": "doubao-seed-2-0-lite-260215",
        "reviewer_model": None,
        "fallback_model": None,
        "daily_budget_cny_fen": 3_000,
        "timeout_seconds": 60,
    },
    "wenxin": {
        "enabled": False,
        "base_url": "https://qianfan.baidubce.com/v2",
        "workspace_id": None,
        "writer_model": "ernie-4.5-turbo-32k",
        "reviewer_model": None,
        "fallback_model": None,
        "daily_budget_cny_fen": 3_000,
        "timeout_seconds": 60,
    },
    "yuanbao": {
        "enabled": False,
        "base_url": "https://tokenhub.tencentmaas.com/v1",
        "workspace_id": None,
        "writer_model": "hy3",
        "reviewer_model": None,
        "fallback_model": None,
        "daily_budget_cny_fen": 3_000,
        "timeout_seconds": 60,
    },
    "kimi": {
        "enabled": False,
        "base_url": "https://api.moonshot.cn/v1",
        "workspace_id": None,
        "writer_model": "kimi-k2.6",
        "reviewer_model": None,
        "fallback_model": None,
        "daily_budget_cny_fen": 3_000,
        "timeout_seconds": 60,
    },
}
ACTIVE_PROVIDER_NAMES: tuple[ProviderName, ...] = (
    "deepseek",
    "qwen",
    "doubao",
    "wenxin",
)
HTTP_URL_ADAPTER = TypeAdapter(AnyHttpUrl)


class RuntimeUpdate(BaseModel):
    version: int = Field(ge=1)
    default_client_monthly_budget_cny_fen: int = Field(ge=0, le=1_000_000)


class ProviderUpdate(BaseModel):
    version: int = Field(ge=1)
    enabled: bool
    base_url: AnyHttpUrl
    workspace_id: str | None = Field(default=None, max_length=200)
    writer_model: str | None = Field(default=None, max_length=100)
    reviewer_model: str | None = Field(default=None, max_length=100)
    fallback_model: str | None = Field(default=None, max_length=100)
    daily_budget_cny_fen: int = Field(ge=0, le=1_000_000)
    timeout_seconds: int = Field(ge=5, le=180)
    api_key: str | None = Field(default=None, min_length=8, max_length=500)

    @field_validator("base_url")
    @classmethod
    def require_secure_provider_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.scheme != "https" or value.username or value.password:
            raise ValueError("模型 API 地址必须使用 HTTPS 且不能包含凭证")
        if value.query or value.fragment:
            raise ValueError("模型 API 地址不能包含查询参数或片段")
        return value


class ProviderTestInput(BaseModel):
    test_type: Literal["connectivity", "structured_output"]
    use_saved_secret: bool = True
    api_key: str | None = Field(default=None, min_length=8, max_length=500)


def _provider_data(setting: ProviderSetting) -> dict[str, object]:
    configured = setting.encrypted_api_key is not None
    return {
        "provider": setting.provider,
        "enabled": setting.enabled,
        "base_url": setting.base_url,
        "workspace_id": setting.workspace_id,
        "writer_model": setting.writer_model,
        "reviewer_model": setting.reviewer_model,
        "fallback_model": setting.fallback_model,
        "daily_budget_cny_fen": setting.daily_budget_cny_fen,
        "timeout_seconds": setting.timeout_seconds,
        "secret_configured": configured,
        "secret_mask": f"••••{setting.secret_suffix}" if configured else None,
        "last_tested_at": (
            setting.last_tested_at.isoformat() if setting.last_tested_at is not None else None
        ),
        "last_test_status": setting.last_test_status,
        "version": setting.version,
    }


def _runtime_data(setting: RuntimeSetting) -> dict[str, object]:
    return {
        "timezone": "Asia/Shanghai",
        "max_upload_mb": 30,
        "max_upload_files": 20,
        "job_retry_limit": 3,
        "job_poll_seconds": 2,
        "default_client_monthly_budget_cny_fen": (setting.default_client_monthly_budget_cny_fen),
        "version": setting.version,
    }


async def _load_or_create_defaults(
    database: DatabaseSession,
) -> tuple[list[ProviderSetting], RuntimeSetting]:
    existing = {
        item.provider: item
        for item in (
            await database.scalars(
                select(ProviderSetting).order_by(ProviderSetting.provider),
            )
        ).all()
    }
    for provider, defaults in DEFAULT_PROVIDERS.items():
        if provider not in existing:
            item = ProviderSetting(provider=provider, **defaults)
            database.add(item)
            existing[provider] = item
    runtime = await database.get(RuntimeSetting, 1)
    if runtime is None:
        runtime = RuntimeSetting(singleton_key=1)
        database.add(runtime)
    try:
        await database.commit()
    except IntegrityError:
        await database.rollback()
        providers = (
            await database.scalars(
                select(ProviderSetting).order_by(ProviderSetting.provider),
            )
        ).all()
        runtime = await database.get(RuntimeSetting, 1)
        if runtime is None or len(providers) != len(DEFAULT_PROVIDERS):
            raise
        return list(providers), runtime
    return list(existing.values()), runtime


def _cipher(settings: Settings) -> SecretCipher:
    if settings.app_master_key is None:
        raise ApiFailure(
            status_code=503,
            code=50301,
            message="服务端尚未配置密钥保护能力，不能保存或使用模型密钥",
        )
    try:
        return SecretCipher(settings.app_master_key.get_secret_value())
    except ValueError as error:
        raise ApiFailure(
            status_code=503,
            code=50301,
            message="服务端密钥保护配置无效，请联系系统管理员",
        ) from error


def _validate_provider_host(
    provider: ProviderName,
    base_url: AnyHttpUrl | str,
) -> None:
    try:
        parsed = HTTP_URL_ADAPTER.validate_python(base_url)
    except ValidationError as error:
        raise ApiFailure(
            status_code=422,
            code=42201,
            message="模型 API 地址无效",
        ) from error
    if (
        parsed.scheme != "https"
        or parsed.host != PROVIDER_OFFICIAL_HOSTS[provider]
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ApiFailure(
            status_code=422,
            code=42201,
            message="模型 API 地址必须使用该供应商的官方域名",
        )


async def _record_test_status(
    database: DatabaseSession,
    *,
    provider: ProviderName,
    expected_version: int,
    status: Literal["success", "failed"],
) -> bool:
    tested_at = datetime.now(UTC)
    result = await database.execute(
        update(ProviderSetting)
        .where(
            ProviderSetting.provider == provider,
            ProviderSetting.version == expected_version,
        )
        .values(
            last_test_status=status,
            last_tested_at=tested_at,
            version=expected_version + 1,
            updated_at=tested_at,
        )
        .returning(ProviderSetting.provider),
    )
    if result.scalar_one_or_none() is None:
        await database.rollback()
        return False
    await database.commit()
    return True


def build_settings_router(
    settings: Settings,
    provider_transport: httpx.AsyncBaseTransport | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/settings", tags=["settings"])
    provider_client = ProviderClient(provider_transport)

    @router.get("")
    async def get_settings(
        request: Request,
        database: DatabaseSession,
        authentication: Authenticated,
    ) -> Response:
        del authentication
        providers, runtime = await _load_or_create_defaults(database)
        return success_response(
            request,
            {
                "providers": [
                    _provider_data(item)
                    for item in sorted(providers, key=lambda value: value.provider)
                    if item.provider in ACTIVE_PROVIDER_NAMES
                ],
                "runtime": _runtime_data(runtime),
                "catalogs": {
                    "provider_catalog_version": "2026-08-04-four-platform-diagnostic",
                    "model_policy_version": "v4-evidence-based-diagnostic",
                },
            },
        )

    @router.patch("/runtime")
    async def update_runtime(
        request: Request,
        body: RuntimeUpdate,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        del authentication
        providers, runtime = await _load_or_create_defaults(database)
        del providers
        if runtime.version != body.version:
            raise ApiFailure(
                status_code=409,
                code=40901,
                message="运行设置已被更新，请刷新后重试",
            )
        result = await database.execute(
            update(RuntimeSetting)
            .where(
                RuntimeSetting.singleton_key == 1,
                RuntimeSetting.version == body.version,
            )
            .values(
                default_client_monthly_budget_cny_fen=(body.default_client_monthly_budget_cny_fen),
                version=body.version + 1,
                updated_at=datetime.now(UTC),
            )
            .returning(RuntimeSetting),
        )
        updated_runtime = result.scalar_one_or_none()
        if updated_runtime is None:
            await database.rollback()
            raise ApiFailure(
                status_code=409,
                code=40901,
                message="运行设置已被更新，请刷新后重试",
            )
        await database.commit()
        return success_response(request, _runtime_data(updated_runtime))

    @router.put("/providers/{provider}")
    async def update_provider(
        provider: ProviderName,
        request: Request,
        body: ProviderUpdate,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        del authentication
        await _load_or_create_defaults(database)
        setting = await database.get(ProviderSetting, provider)
        if setting is None:
            raise ApiFailure(status_code=404, code=40401, message="模型供应商不存在")
        if setting.version != body.version:
            raise ApiFailure(
                status_code=409,
                code=40901,
                message="模型配置已被更新，请刷新后重试",
            )
        _validate_provider_host(provider, body.base_url)
        if body.enabled and body.api_key is None and setting.encrypted_api_key is None:
            raise ApiFailure(
                status_code=422,
                code=42201,
                message="启用真实模型前必须先配置 API 密钥",
            )
        normalized_base_url = str(body.base_url).rstrip("/")
        connection_changed = (
            setting.base_url != normalized_base_url
            or setting.workspace_id != (body.workspace_id or None)
            or setting.writer_model != (body.writer_model or None)
            or setting.reviewer_model != (body.reviewer_model or None)
            or setting.fallback_model != (body.fallback_model or None)
            or body.api_key is not None
        )
        values: dict[str, object] = {
            "enabled": body.enabled,
            "base_url": normalized_base_url,
            "workspace_id": body.workspace_id or None,
            "writer_model": body.writer_model or None,
            "reviewer_model": body.reviewer_model or None,
            "fallback_model": body.fallback_model or None,
            "daily_budget_cny_fen": body.daily_budget_cny_fen,
            "timeout_seconds": body.timeout_seconds,
            "version": body.version + 1,
            "updated_at": datetime.now(UTC),
        }
        if body.api_key is not None:
            values["encrypted_api_key"] = _cipher(settings).encrypt(provider, body.api_key)
            values["secret_suffix"] = body.api_key[-4:]
        if connection_changed:
            values["last_test_status"] = "not_tested"
            values["last_tested_at"] = None
        result = await database.execute(
            update(ProviderSetting)
            .where(
                ProviderSetting.provider == provider,
                ProviderSetting.version == body.version,
            )
            .values(**values)
            .returning(ProviderSetting),
        )
        updated_setting = result.scalar_one_or_none()
        if updated_setting is None:
            await database.rollback()
            raise ApiFailure(
                status_code=409,
                code=40901,
                message="模型配置已被更新，请刷新后重试",
            )
        await database.commit()
        return success_response(request, _provider_data(updated_setting))

    @router.post("/providers/{provider}/test")
    async def test_provider(
        provider: ProviderName,
        request: Request,
        body: ProviderTestInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        del authentication
        await _load_or_create_defaults(database)
        setting = await database.get(ProviderSetting, provider)
        if setting is None:
            raise ApiFailure(status_code=404, code=40401, message="模型供应商不存在")
        cipher = _cipher(settings)
        _validate_provider_host(provider, setting.base_url)
        expected_version = setting.version
        api_key = body.api_key
        if body.use_saved_secret:
            if setting.encrypted_api_key is None:
                raise ApiFailure(
                    status_code=422,
                    code=42201,
                    message="尚未保存模型密钥，无法执行连接测试",
                )
            api_key = cipher.decrypt(provider, setting.encrypted_api_key)
        if api_key is None:
            raise ApiFailure(
                status_code=422,
                code=42201,
                message="连接测试需要临时密钥或已保存密钥",
            )
        models = (
            [setting.reviewer_model, setting.fallback_model]
            if provider == "deepseek"
            else [setting.writer_model]
        )
        if any(model is None for model in models):
            raise ApiFailure(
                status_code=422,
                code=42201,
                message="请先完整配置该供应商的主模型与备用模型",
            )
        results = []
        budget_warning = False
        outbound_failed = False
        try:
            for model in models:
                if model is None:
                    continue
                reservation = await reserve_model_budget(
                    database,
                    provider=provider,
                    model=model,
                    purpose="provider_test",
                    estimated_cny_fen=0,
                    require_enabled_secret=False,
                )
                budget_warning = budget_warning or reservation.decision.warning
                try:
                    result = await provider_client.test(
                        provider=provider,
                        base_url=setting.base_url,
                        api_key=api_key,
                        model=model,
                        timeout_seconds=setting.timeout_seconds,
                        structured=body.test_type == "structured_output",
                        workspace_id=setting.workspace_id,
                    )
                except ApiFailure:
                    outbound_failed = True
                    await finalize_model_usage(
                        database,
                        usage_id=reservation.usage_id,
                        status="failed",
                        actual_cny_fen=0,
                        input_tokens=0,
                        output_tokens=0,
                        latency_ms=None,
                    )
                    raise
                await finalize_model_usage(
                    database,
                    usage_id=reservation.usage_id,
                    status="succeeded",
                    actual_cny_fen=0,
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    latency_ms=result.latency_ms,
                )
                results.append(result)
        except ApiFailure as failure:
            if outbound_failed:
                if not await _record_test_status(
                    database,
                    provider=provider,
                    expected_version=expected_version,
                    status="failed",
                ):
                    raise ApiFailure(
                        status_code=409,
                        code=40901,
                        message="测试期间模型配置已变化，请重新测试",
                    ) from failure
            raise
        if not await _record_test_status(
            database,
            provider=provider,
            expected_version=expected_version,
            status="success",
        ):
            raise ApiFailure(
                status_code=409,
                code=40901,
                message="测试期间模型配置已变化，请重新测试",
            )
        return success_response(
            request,
            {
                "provider": provider,
                "status": "success",
                "model": " + ".join(result.model for result in results),
                "latency_ms": sum(result.latency_ms for result in results),
                "structured_output_valid": all(
                    result.structured_output_valid for result in results
                ),
                "budget_warning": budget_warning,
            },
        )

    return router
