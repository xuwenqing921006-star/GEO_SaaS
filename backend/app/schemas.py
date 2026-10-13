from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ApiEnvelope[PayloadT](BaseModel):
    code: int
    message: str
    data: PayloadT
    request_id: UUID


class LivenessData(BaseModel):
    status: str = "ok"
    service: str
    version: str


class ReadinessData(BaseModel):
    status: Literal["ready"]
    database: Literal["ok"]
    storage: Literal["ok"]
    worker_heartbeat: Literal["ok", "stale"]


class ErrorData(BaseModel):
    field_errors: list[dict[str, str]] = Field(default_factory=list)
    retryable: bool
    provider: str | None = None
    job_id: str | None = None
