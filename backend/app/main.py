import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.auth import build_auth_router
from app.channels import build_channels_router
from app.clients import build_clients_router
from app.config import Settings
from app.content import build_content_router
from app.contract_models import SUCCESS_RESPONSE_MODELS
from app.health import HealthService, HealthServiceProtocol, build_health_router
from app.job_api import build_jobs_router
from app.keyword_workspace import build_keyword_workspace_router
from app.knowledge import build_knowledge_router
from app.logging import configure_json_logging
from app.monitoring import build_monitoring_router
from app.observability import RequestMetrics, build_observability_router
from app.prompt_templates import build_prompt_templates_router
from app.providers import ProviderClient
from app.publishing import build_publishing_router
from app.responses import ApiFailure, error_response, failure_response
from app.schemas import ApiEnvelope, ErrorData
from app.settings_api import build_settings_router
from app.strategy import build_strategy_router

LOGGER = logging.getLogger("geo-saas.api")

SUCCESS_STATUS_CODES = {
    ("post", "/api/v1/clients"): 201,
    ("post", "/api/v1/clients/{client_id}/materials"): 201,
    ("post", "/api/v1/materials/{material_id}/extract"): 202,
    ("post", "/api/v1/clients/{client_id}/facts"): 201,
    ("post", "/api/v1/facts/{fact_id}/evidence"): 201,
    ("post", "/api/v1/clients/{client_id}/diagnostics"): 202,
    ("post", "/api/v1/clients/{client_id}/strategy/generate"): 202,
    ("post", "/api/v1/clients/{client_id}/keyword-generations"): 202,
    ("post", "/api/v1/clients/{client_id}/briefs"): 201,
    ("post", "/api/v1/clients/{client_id}/documents"): 201,
    ("post", "/api/v1/clients/{client_id}/documents/batch"): 201,
    ("post", "/api/v1/documents/{document_id}/publish"): 202,
    ("post", "/api/v1/publishing/channels/{channel_id}/accounts"): 201,
    ("post", "/api/v1/documents/{document_id}/operations"): 202,
    ("post", "/api/v1/documents/{document_id}/versions/{version_id}/restore"): 201,
    ("post", "/api/v1/clients/{client_id}/channel-recommendations/generate"): 202,
    ("post", "/api/v1/clients/{client_id}/question-sets"): 201,
    ("post", "/api/v1/clients/{client_id}/monitoring-batches"): 202,
    ("post", "/api/v1/monitoring-batches/{batch_id}/manual-samples"): 201,
    ("post", "/api/v1/monitoring-evaluations/{evaluation_id}/feedback"): 201,
    ("post", "/api/v1/jobs/{job_id}/retry"): 202,
}
ERROR_STATUS_CODES: dict[tuple[str, str], tuple[int, ...]] = {
    ("get", "/api/v1/health/live"): (500,),
    ("get", "/api/v1/health/ready"): (503,),
    ("post", "/api/v1/auth/login"): (401,),
    ("get", "/api/v1/auth/session"): (401,),
    ("delete", "/api/v1/auth/session"): (403,),
    ("put", "/api/v1/auth/password"): (422,),
    ("get", "/api/v1/clients"): (400,),
    ("post", "/api/v1/clients"): (400,),
    ("get", "/api/v1/clients/{client_id}"): (404,),
    ("patch", "/api/v1/clients/{client_id}"): (409,),
    ("post", "/api/v1/clients/{client_id}/archive"): (409,),
    ("post", "/api/v1/clients/{client_id}/restore"): (409,),
    ("get", "/api/v1/clients/{client_id}/dashboard"): (404,),
    ("get", "/api/v1/clients/{client_id}/materials"): (400,),
    ("post", "/api/v1/clients/{client_id}/materials"): (413, 415),
    ("get", "/api/v1/materials/{material_id}"): (404,),
    ("get", "/api/v1/materials/{material_id}/file"): (404,),
    ("delete", "/api/v1/materials/{material_id}"): (404,),
    ("post", "/api/v1/materials/{material_id}/extract"): (409,),
    ("get", "/api/v1/clients/{client_id}/facts"): (400,),
    ("post", "/api/v1/clients/{client_id}/facts"): (422,),
    ("patch", "/api/v1/facts/{fact_id}"): (409,),
    ("post", "/api/v1/facts/{fact_id}/evidence"): (400,),
    ("post", "/api/v1/facts/{fact_id}/confirm"): (422,),
    ("get", "/api/v1/clients/{client_id}/conflicts"): (404,),
    ("post", "/api/v1/conflicts/{conflict_id}/resolve"): (409,),
    ("get", "/api/v1/clients/{client_id}/knowledge-profile"): (404,),
    ("patch", "/api/v1/clients/{client_id}/knowledge-profile"): (409,),
    ("post", "/api/v1/clients/{client_id}/diagnostics"): (422,),
    ("get", "/api/v1/clients/{client_id}/diagnostics/latest"): (404,),
    ("patch", "/api/v1/diagnostic-issues/{issue_id}"): (409,),
    ("post", "/api/v1/clients/{client_id}/strategy/generate"): (422,),
    ("get", "/api/v1/clients/{client_id}/strategy"): (404,),
    ("patch", "/api/v1/strategy-items/{item_id}"): (409,),
    ("get", "/api/v1/clients/{client_id}/keyword-workspace"): (404,),
    ("put", "/api/v1/clients/{client_id}/keyword-profile"): (404, 409, 422),
    ("post", "/api/v1/clients/{client_id}/keyword-generations"): (404, 409, 422),
    ("get", "/api/v1/keyword-generations/{generation_id}"): (404,),
    ("patch", "/api/v1/keyword-candidates/{candidate_id}"): (404, 409, 422),
    ("post", "/api/v1/keyword-generations/{generation_id}/confirm"): (
        404,
        409,
        422,
    ),
    ("delete", "/api/v1/keyword-generations/{generation_id}"): (404, 409),
    ("post", "/api/v1/clients/{client_id}/briefs"): (422,),
    ("get", "/api/v1/briefs/{brief_id}"): (404,),
    ("patch", "/api/v1/briefs/{brief_id}"): (409,),
    ("get", "/api/v1/clients/{client_id}/documents"): (400,),
    ("get", "/api/v1/clients/{client_id}/content-generation-tasks"): (400,),
    ("get", "/api/v1/content-generation-tasks/{task_id}"): (404,),
    ("post", "/api/v1/content-generation-tasks/{task_id}/confirm"): (
        404,
        409,
        422,
    ),
    ("post", "/api/v1/clients/{client_id}/documents/batch"): (422,),
    ("post", "/api/v1/clients/{client_id}/documents"): (422,),
    ("get", "/api/v1/documents/{document_id}"): (404,),
    ("patch", "/api/v1/documents/{document_id}"): (409, 422),
    ("post", "/api/v1/documents/{document_id}/publish"): (404, 409, 422),
    ("delete", "/api/v1/documents/{document_id}"): (404, 409),
    ("post", "/api/v1/documents/{document_id}/restore"): (404, 409, 422),
    ("post", "/api/v1/documents/{document_id}/operations"): (422, 429),
    ("get", "/api/v1/documents/{document_id}/versions"): (404,),
    ("post", "/api/v1/documents/{document_id}/versions/{version_id}/restore"): (409,),
    ("get", "/api/v1/documents/{document_id}/quality-checks"): (404,),
    (
        "get",
        "/api/v1/documents/{document_id}/versions/{version_id}/cover",
    ): (400, 404),
    ("get", "/api/v1/exports/{export_id}/download"): (404, 409),
    ("get", "/api/v1/channels"): (400,),
    ("get", "/api/v1/publishing/channels"): (400,),
    ("post", "/api/v1/publishing/channels/{channel_id}/accounts"): (409, 422),
    ("patch", "/api/v1/publishing/accounts/{account_id}"): (404, 409, 422),
    ("post", "/api/v1/publishing/accounts/{account_id}/login-window"): (404, 422),
    ("post", "/api/v1/publishing/accounts/{account_id}/test"): (404, 422),
    ("get", "/api/v1/clients/{client_id}/channel-recommendations"): (404,),
    ("post", "/api/v1/clients/{client_id}/channel-recommendations/generate"): (422,),
    ("get", "/api/v1/monitoring/platforms"): (400,),
    ("get", "/api/v1/clients/{client_id}/question-sets"): (404,),
    ("post", "/api/v1/clients/{client_id}/question-sets"): (400,),
    ("patch", "/api/v1/question-sets/{question_set_id}"): (409,),
    ("post", "/api/v1/clients/{client_id}/monitoring-batches"): (422,),
    ("get", "/api/v1/monitoring-batches/{batch_id}"): (404,),
    ("post", "/api/v1/monitoring-batches/{batch_id}/manual-samples"): (400,),
    ("put", "/api/v1/monitoring-samples/{sample_id}/evaluation"): (409,),
    ("get", "/api/v1/clients/{client_id}/monitoring-metrics"): (400,),
    ("post", "/api/v1/monitoring-evaluations/{evaluation_id}/feedback"): (422,),
    ("get", "/api/v1/clients/{client_id}/monitoring-batches/latest"): (404,),
    ("get", "/api/v1/clients/{client_id}/optimization-actions"): (404,),
    ("get", "/api/v1/settings"): (401,),
    ("patch", "/api/v1/settings/runtime"): (409,),
    ("put", "/api/v1/settings/providers/{provider}"): (409,),
    ("post", "/api/v1/settings/providers/{provider}/test"): (502,),
    ("get", "/api/v1/prompt-templates"): (400,),
    ("patch", "/api/v1/prompt-templates/{template_id}"): (404, 409, 422),
    ("post", "/api/v1/prompt-templates/{template_id}/restore"): (404, 409, 422),
    ("get", "/api/v1/prompt-templates/{template_id}/versions"): (404,),
    ("get", "/api/v1/jobs/{job_id}"): (404,),
    ("post", "/api/v1/jobs/{job_id}/retry"): (409,),
    ("post", "/api/v1/jobs/{job_id}/cancel"): (409,),
}


def include_contract_router(app: FastAPI, router: APIRouter) -> None:
    """Attach the approved envelope, status and error contract before route cloning."""
    for route in router.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = {method.lower() for method in (route.methods or set())}
        if len(methods) != 1:
            raise RuntimeError(f"contract route must have exactly one method: {route.path}")
        method = next(iter(methods))
        operation = (method, route.path)
        error_statuses = ERROR_STATUS_CODES.get(operation)
        if error_statuses is None:
            raise RuntimeError(f"route is missing from the approved contract: {operation}")
        route.responses = {
            status_code: {"model": ApiEnvelope[ErrorData]} for status_code in error_statuses
        }
        if route.path == "/api/v1/exports/{export_id}/download":
            route.responses[200] = {
                "description": "Markdown or DOCX export",
                "content": {
                    "text/markdown": {},
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {},
                },
            }
        elif route.path == ("/api/v1/documents/{document_id}/versions/{version_id}/cover"):
            route.responses[200] = {
                "description": "Article cover PNG",
                "content": {"image/png": {}},
            }
        elif route.path == "/api/v1/materials/{material_id}/file":
            route.responses[200] = {
                "description": "Enterprise knowledge-base image",
                "content": {
                    "image/png": {},
                    "image/jpeg": {},
                },
            }
        elif route.response_model is None:
            response_model = SUCCESS_RESPONSE_MODELS.get(operation)
            if response_model is None:
                raise RuntimeError(f"route is missing a concrete success DTO: {operation}")
            route.response_model = response_model
        route.status_code = SUCCESS_STATUS_CODES.get(operation, 200)
    app.include_router(router)


def create_app(
    settings: Settings | None = None,
    health_service: HealthServiceProtocol | None = None,
    engine_override: AsyncEngine | None = None,
    provider_transport: httpx.AsyncBaseTransport | None = None,
) -> FastAPI:
    app_settings = settings or Settings()
    configure_json_logging(app_settings.app_env)
    engine = engine_override

    if health_service is None:
        engine = engine or create_async_engine(app_settings.database_url, pool_pre_ping=True)
        active_health_service: HealthServiceProtocol = HealthService(engine, app_settings)
    else:
        active_health_service = health_service

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        if engine is not None:
            await engine.dispose()

    app = FastAPI(
        title="GEO SaaS API",
        version=app_settings.app_version,
        lifespan=lifespan,
    )
    if engine is None:
        engine = create_async_engine(app_settings.database_url, pool_pre_ping=True)
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    request_metrics = RequestMetrics()

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, _: RequestValidationError) -> JSONResponse:
        if "keyword-" in request.url.path:
            return error_response(
                request,
                status_code=422,
                code=42201,
                message="关键词参数校验失败",
            )
        if request.url.path == "/api/v1/auth/password":
            return error_response(
                request,
                status_code=422,
                code=40001,
                message="新密码不符合安全要求",
            )
        if request.method == "GET" and request.url.path.endswith("/materials"):
            return error_response(
                request,
                status_code=400,
                code=40001,
                message="资料筛选参数无效",
            )
        if request.method == "GET" and request.url.path.endswith("/facts"):
            return error_response(
                request,
                status_code=400,
                code=40001,
                message="事实筛选参数无效",
            )
        if request.method == "GET" and request.url.path == "/api/v1/channels":
            return error_response(
                request,
                status_code=400,
                code=40001,
                message="渠道筛选参数无效",
            )
        if request.url.path.startswith("/api/v1/clients"):
            message = (
                "分页或筛选参数无效"
                if request.method == "GET" and request.url.path == "/api/v1/clients"
                else "客户资料校验失败"
            )
            return error_response(
                request,
                status_code=400,
                code=40001,
                message=message,
            )
        return error_response(
            request,
            status_code=400,
            code=40001,
            message="请求参数校验失败",
        )

    @app.exception_handler(ApiFailure)
    async def api_failure(request: Request, failure: ApiFailure) -> JSONResponse:
        return failure_response(request, failure)

    @app.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = uuid4()
        request.state.request_id = request_id
        started_at = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            LOGGER.exception(
                "request_failed",
                extra={
                    "event": "http_request_failed",
                    "request_id": str(request_id),
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": 500,
                    "error_category": "unhandled_exception",
                },
            )
            envelope = ApiEnvelope[ErrorData](
                code=50001,
                message="系统内部错误",
                data=ErrorData(retryable=False),
                request_id=request_id,
            )
            response = JSONResponse(
                status_code=500,
                content=envelope.model_dump(mode="json"),
            )

        response.headers["X-Request-ID"] = str(request_id)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Cache-Control"] = "no-store"
        if app_settings.app_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        LOGGER.info(
            "request_completed",
            extra={
                "event": "http_request",
                "request_id": str(request_id),
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((perf_counter() - started_at) * 1000, 2),
            },
        )
        request_metrics.observe(
            path=request.url.path,
            status_code=response.status_code,
            duration_seconds=perf_counter() - started_at,
        )
        return response

    app.include_router(build_observability_router(app_settings, request_metrics))
    include_contract_router(
        app,
        build_health_router(app_settings, active_health_service),
    )
    include_contract_router(app, build_auth_router(app_settings))
    include_contract_router(app, build_clients_router())
    include_contract_router(app, build_knowledge_router(app_settings))
    include_contract_router(app, build_strategy_router())
    include_contract_router(app, build_keyword_workspace_router())
    include_contract_router(
        app,
        build_content_router(
            app_settings,
            ProviderClient(provider_transport),
        ),
    )
    include_contract_router(app, build_channels_router())
    include_contract_router(app, build_publishing_router(app_settings))
    include_contract_router(app, build_monitoring_router())
    include_contract_router(
        app,
        build_settings_router(app_settings, provider_transport),
    )
    include_contract_router(app, build_prompt_templates_router())
    include_contract_router(app, build_jobs_router())

    def contract_openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            routes=app.routes,
        )
        paths = schema["paths"]
        for operation, error_statuses in ERROR_STATUS_CODES.items():
            method, path = operation
            responses = paths[path][method]["responses"]
            success_status = str(SUCCESS_STATUS_CODES.get(operation, 200))
            allowed = {success_status, *(str(status) for status in error_statuses)}
            for status in set(responses) - allowed:
                del responses[status]
        app.openapi_schema = schema
        return schema

    app.openapi = contract_openapi  # type: ignore[method-assign]
    return app


app = create_app()
