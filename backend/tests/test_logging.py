import json
import logging
import sys

import pytest

from app.logging import JsonFormatter, redact_text


@pytest.mark.unit
@pytest.mark.parametrize(
    ("unsafe_value", "secret"),
    [
        ("Authorization: Bearer auth-secret", "auth-secret"),
        ("Cookie: session=cookie-secret; theme=dark", "cookie-secret"),
        ("X-API-Key: api-key-secret", "api-key-secret"),
        ("api_key=plain-api-secret", "plain-api-secret"),
        ("APP_MASTER_KEY=master-key-material", "master-key-material"),
        (
            "postgresql+asyncpg://geo_app:db%40%3A%2F%3F%23secret@db/geo_saas",
            "db%40%3A%2F%3F%23secret",
        ),
        ("GET /callback?token=query-secret&safe=yes", "query-secret"),
        ("client_secret=oauth-client-secret", "oauth-client-secret"),
        ("refresh_token=refresh-token-value", "refresh-token-value"),
        ("contact customer@example.com", "customer@example.com"),
        ("contact +86 138-0013-8000", "+86 138-0013-8000"),
        ("customer_text=verbatim-customer-text", "verbatim-customer-text"),
        ("客户原文=不应保留的客户输入", "不应保留的客户输入"),
    ],
)
def test_redact_text_removes_common_secret_shapes(
    unsafe_value: str,
    secret: str,
) -> None:
    redacted = redact_text(unsafe_value)

    assert secret not in redacted
    assert "REDACTED" in redacted or "***:***" in redacted


@pytest.mark.unit
def test_json_logging_keeps_safe_context_and_drops_sensitive_fields() -> None:
    record = logging.makeLogRecord(
        {
            "name": "geo-saas.test",
            "levelno": logging.INFO,
            "levelname": "INFO",
            "msg": "request_completed",
            "request_id": "request-id",
            "status_code": 200,
            "authorization": "Bearer must-not-be-logged",
        }
    )

    payload = json.loads(JsonFormatter().format(record))

    assert payload["request_id"] == "request-id"
    assert payload["status_code"] == 200
    assert "authorization" not in payload


@pytest.mark.unit
def test_json_logging_redacts_an_exception_chain() -> None:
    try:
        try:
            raise ValueError(
                "postgresql+asyncpg://geo_app:database-secret@db/geo_saas?token=query-secret"
            )
        except ValueError as cause:
            raise RuntimeError("Authorization: Bearer exception-secret") from cause
    except RuntimeError:
        record = logging.makeLogRecord(
            {
                "name": "geo-saas.test",
                "levelno": logging.ERROR,
                "levelname": "ERROR",
                "msg": "request_failed",
                "exc_info": sys.exc_info(),
            }
        )

    serialized = JsonFormatter().format(record)

    assert "database-secret" not in serialized
    assert "query-secret" not in serialized
    assert "exception-secret" not in serialized
    assert '"exception":' in serialized


@pytest.mark.unit
def test_production_exception_log_uses_only_controlled_diagnostics() -> None:
    sensitive_values = (
        "oauth-client-secret",
        "refresh-token-value",
        "customer@example.com",
        "+86 138-0013-8000",
        "客户的完整原文",
    )
    try:
        raise RuntimeError(
            "client_secret=oauth-client-secret "
            "refresh_token=refresh-token-value "
            "email=customer@example.com "
            "phone=+86 138-0013-8000 "
            "客户原文=客户的完整原文"
        )
    except RuntimeError:
        record = logging.makeLogRecord(
            {
                "name": "geo-saas.test",
                "levelno": logging.ERROR,
                "levelname": "ERROR",
                "msg": "arbitrary customer message",
                "exc_info": sys.exc_info(),
                "error_category": "user-controlled-category",
                "request_id": "safe-request-id",
                "path": "/customers/customer@example.com",
            }
        )

    payload = json.loads(JsonFormatter("production").format(record))
    serialized = json.dumps(payload, ensure_ascii=False)

    for sensitive_value in sensitive_values:
        assert sensitive_value not in serialized
    assert payload["message"] == "request_failed"
    assert payload["exception_type"] == "RuntimeError"
    assert payload["error_category"] == "internal_error"
    assert payload["request_id"] == "safe-request-id"
    assert "exception" not in payload
    assert "path" not in payload


@pytest.mark.unit
def test_production_non_exception_log_rejects_arbitrary_customer_message_and_path() -> None:
    record = logging.makeLogRecord(
        {
            "name": "geo-saas.test",
            "levelno": logging.INFO,
            "levelname": "INFO",
            "msg": "客户的完整原文 customer@example.com +86 138-0013-8000",
            "request_id": "safe-request-id",
            "path": "/customers/customer@example.com",
            "status_code": 200,
        }
    )

    payload = json.loads(JsonFormatter("production").format(record))
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["message"] == "application_event"
    assert payload["request_id"] == "safe-request-id"
    assert payload["status_code"] == 200
    assert "客户的完整原文" not in serialized
    assert "customer@example.com" not in serialized
    assert "+86 138-0013-8000" not in serialized
    assert "path" not in payload


@pytest.mark.unit
def test_production_event_and_dependency_values_use_allowlists() -> None:
    record = logging.makeLogRecord(
        {
            "name": "geo-saas.test",
            "levelno": logging.INFO,
            "levelname": "INFO",
            "msg": "request_completed",
            "event": "客户原文=任意事件值",
            "dependency": "client_secret=任意依赖值",
            "request_id": "safe-request-id",
        }
    )

    payload = json.loads(JsonFormatter("production").format(record))
    serialized = json.dumps(payload, ensure_ascii=False)

    assert payload["event"] == "application_event"
    assert payload["dependency"] == "unknown_dependency"
    assert "任意事件值" not in serialized
    assert "任意依赖值" not in serialized
