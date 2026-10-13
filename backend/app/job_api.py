from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.auth import Authenticated, CsrfAuthenticated
from app.database import Client, DatabaseSession, Job, Material, utc_now
from app.responses import error_response, success_response


class JobReasonInput(BaseModel):
    reason: str = Field(min_length=2, max_length=500)


def _job_data(job: Job) -> dict[str, object]:
    return {
        "id": str(job.id),
        "client_id": str(job.client_id),
        "type": job.job_type,
        "status": job.status,
        "progress": job.progress,
        "current_step": (
            "等待处理"
            if job.status == "queued"
            else (
                "生成 GEO 诊断"
                if job.job_type == "diagnostic"
                else "生成问题与内容策略"
                if job.job_type == "strategy_generate"
                else "生成、检查或导出内容"
                if job.job_type == "document_operation"
                else "自动发布到目标渠道"
                if job.job_type == "content_publish"
                else "分析客户内容与发布渠道"
                if job.job_type == "channel_recommend"
                else "采样并分析 AI 回答"
                if job.job_type == "monitoring_batch"
                else "解析企业资料"
            )
            if job.status == "running"
            else "已完成"
            if job.status == "succeeded"
            else "已取消"
            if job.status == "cancelled"
            else "处理失败"
        ),
        "attempt": job.attempts,
        "max_attempts": job.max_attempts,
        "result_resource_type": (
            "material"
            if job.material_id
            else "export"
            if job.payload.get("export_id")
            else "document"
            if job.job_type in {"document_operation", "content_publish"}
            else "channel_recommendation"
            if job.job_type == "channel_recommend"
            else "monitoring_batch"
            if job.job_type == "monitoring_batch"
            else None
        ),
        "result_resource_id": (
            str(job.material_id)
            if job.material_id
            else str(job.payload["export_id"])
            if job.payload.get("export_id")
            else str(job.payload.get("document_id"))
            if job.job_type in {"document_operation", "content_publish"}
            else str(job.payload.get("batch_id"))
            if job.job_type == "monitoring_batch"
            else None
        ),
        "error_code": None,
        "error_message": job.error_message,
        "retryable": job.status == "failed" and job.attempts < job.max_attempts,
        "created_at": job.created_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def build_jobs_router() -> APIRouter:
    router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

    @router.get("/{job_id}")
    async def get_job(
        request: Request,
        job_id: UUID,
        database: DatabaseSession,
        authentication: Authenticated,
    ) -> Response:
        job = await database.get(Job, job_id)
        if job is None:
            return error_response(request, status_code=404, code=40401, message="任务不存在")
        return success_response(request, _job_data(job))

    @router.post("/{job_id}/retry")
    async def retry_job(
        request: Request,
        job_id: UUID,
        body: JobReasonInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
        idempotency_key: Annotated[UUID, Header(alias="Idempotency-Key")],
    ) -> Response:
        original = await database.get(Job, job_id)
        if original is None:
            return error_response(request, status_code=404, code=40401, message="任务不存在")
        client = await database.scalar(
            select(Client).where(Client.id == original.client_id).with_for_update(),
        )
        original = await database.scalar(
            select(Job).where(Job.id == job_id).with_for_update(),
        )
        if original is None:
            return error_response(request, status_code=404, code=40401, message="任务不存在")
        key = str(idempotency_key)
        existing = await database.scalar(
            select(Job).where(
                Job.client_id == original.client_id,
                Job.job_type == original.job_type,
                Job.idempotency_key == key,
            ),
        )
        if existing is not None:
            if existing.payload.get("retry_of") != str(original.id):
                return error_response(
                    request,
                    status_code=409,
                    code=40903,
                    message="幂等键已用于其他任务",
                )
            return success_response(
                request,
                {
                    "job_id": str(existing.id),
                    "status": existing.status,
                    "progress": existing.progress,
                },
                status_code=202,
            )
        if (
            original.status != "failed"
            or original.attempts >= original.max_attempts
            or client is None
            or client.status != "active"
        ):
            return error_response(
                request,
                status_code=409,
                code=40902,
                message="任务不可重试或已达到最大重试次数",
            )
        payload = {
            **original.payload,
            "retry_of": str(original.id),
            "retry_reason": body.reason,
        }
        retried = Job(
            client_id=original.client_id,
            material_id=original.material_id,
            job_type=original.job_type,
            idempotency_key=key,
            payload=payload,
            max_attempts=original.max_attempts,
        )
        database.add(retried)
        material = (
            await database.get(Material, original.material_id) if original.material_id else None
        )
        if material is not None:
            material.extraction_status = "queued"
            material.extraction_error = None
            material.version += 1
        try:
            await database.commit()
        except IntegrityError:
            await database.rollback()
            return error_response(
                request,
                status_code=409,
                code=40902,
                message="任务不可重试或已达到最大重试次数",
            )
        await database.refresh(retried)
        return success_response(
            request,
            {
                "job_id": str(retried.id),
                "status": retried.status,
                "progress": retried.progress,
            },
            status_code=202,
        )

    @router.post("/{job_id}/cancel")
    async def cancel_job(
        request: Request,
        job_id: UUID,
        body: JobReasonInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        result = await database.execute(
            update(Job)
            .where(Job.id == job_id, Job.status == "queued")
            .values(
                status="cancelled",
                progress=100,
                error_message=body.reason,
                completed_at=utc_now(),
            )
            .returning(Job),
        )
        cancelled = result.scalar_one_or_none()
        if cancelled is None:
            current = await database.get(Job, job_id)
            if current is None:
                return error_response(
                    request,
                    status_code=404,
                    code=40401,
                    message="任务不存在",
                )
            return error_response(
                request,
                status_code=409,
                code=40902,
                message="任务已开始执行或已经结束，不能取消",
            )
        if cancelled.material_id is not None:
            material = await database.get(Material, cancelled.material_id)
            if material is not None:
                material.extraction_status = "not_started"
                material.extraction_error = None
                material.version += 1
        await database.commit()
        return success_response(request, _job_data(cancelled))

    return router
