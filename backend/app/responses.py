from typing import Any, cast
from uuid import UUID

from fastapi import Request
from fastapi.responses import JSONResponse


class ApiFailure(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        code: int,
        message: str,
        retryable: bool = False,
        provider: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retryable = retryable
        self.provider = provider


def request_id(request: Request) -> UUID:
    return cast(UUID, request.state.request_id)


def success_response(
    request: Request,
    data: Any,
    *,
    status_code: int = 200,
) -> JSONResponse:
    message = "created" if status_code == 201 else "success"
    return JSONResponse(
        status_code=status_code,
        content={
            "code": status_code,
            "message": message,
            "data": data,
            "request_id": str(request_id(request)),
        },
    )


def error_response(
    request: Request,
    *,
    status_code: int,
    code: int,
    message: str,
    retryable: bool = False,
    provider: str | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "data": {
                "field_errors": [],
                "retryable": retryable,
                "provider": provider,
                "job_id": None,
            },
            "request_id": str(request_id(request)),
        },
    )


def failure_response(request: Request, failure: ApiFailure) -> JSONResponse:
    return error_response(
        request,
        status_code=failure.status_code,
        code=failure.code,
        message=failure.message,
        retryable=failure.retryable,
        provider=failure.provider,
    )
