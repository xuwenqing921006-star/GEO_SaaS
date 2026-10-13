import json
import logging
import re
from datetime import UTC, datetime
from typing import Literal

SAFE_LOG_FIELDS = (
    "request_id",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "event",
    "dependency",
    "alert_code",
    "value",
    "threshold",
)
PRODUCTION_SAFE_LOG_FIELDS = (
    "request_id",
    "method",
    "status_code",
    "duration_ms",
    "event",
    "dependency",
    "alert_code",
    "value",
    "threshold",
)
PRODUCTION_MESSAGE_ALLOWLIST = frozenset(
    {
        "request_completed",
        "request_failed",
        "worker_heartbeat",
        "worker_heartbeat_failed",
        "operational_alert",
        "operational_alert_resolved",
    }
)
PRODUCTION_EVENT_ALLOWLIST = frozenset(
    {
        "http_request",
        "http_request_failed",
        "worker_heartbeat",
        "worker_heartbeat_failed",
        "operational_alert",
        "operational_alert_resolved",
    }
)
PRODUCTION_DEPENDENCY_ALLOWLIST = frozenset(
    {
        "database",
        "storage",
        "worker_heartbeat",
    }
)

ERROR_CATEGORY_ALLOWLIST = frozenset(
    {
        "dependency_unavailable",
        "internal_error",
        "unhandled_exception",
        "worker_heartbeat",
    }
)
DATABASE_URL_PATTERN = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s:@]+(?::[^@\s/]*)?@")
COOKIE_PATTERN = re.compile(r"(?i)\b(set-cookie|cookie)\s*:\s*[^\r\n]*")
AUTHORIZATION_PATTERN = re.compile(r"(?i)\b(authorization|proxy-authorization)\s*:\s*[^\r\n]*")
BEARER_PATTERN = re.compile(r"(?i)\bbearer\s+[a-z0-9._~+/=-]+")
QUERY_SECRET_PATTERN = re.compile(
    r"(?i)([?&](?:access[_-]?token|api[_-]?key|client[_-]?secret|key|password|"
    r"refresh[_-]?token|secret|token)=)[^&#\s]*"
)
LABELED_SECRET_PATTERN = re.compile(
    r"""(?ix)
    \b(api[-_\s]?key|app[-_\s]?master[-_\s]?key|client[-_\s]?secret|
    customer[-_\s]?text|password|passwd|
    refresh[-_\s]?token|secret|token|x-api-key|客户原文)\b
    (\s*[:=]\s*)
    ("[^"]*"|'[^']*'|[^\s,;]+)
    """
)
EMAIL_PATTERN = re.compile(r"(?i)\b[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
PHONE_PATTERN = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)")


def redact_text(value: str) -> str:
    redacted = DATABASE_URL_PATTERN.sub(r"\1***:***@", value)
    redacted = COOKIE_PATTERN.sub(r"\1: [REDACTED]", redacted)
    redacted = AUTHORIZATION_PATTERN.sub(r"\1: [REDACTED]", redacted)
    redacted = BEARER_PATTERN.sub("Bearer [REDACTED]", redacted)
    redacted = QUERY_SECRET_PATTERN.sub(r"\1[REDACTED]", redacted)
    redacted = LABELED_SECRET_PATTERN.sub(r"\1\2[REDACTED]", redacted)
    redacted = EMAIL_PATTERN.sub("[REDACTED_EMAIL]", redacted)
    return PHONE_PATTERN.sub("[REDACTED_PHONE]", redacted)


class JsonFormatter(logging.Formatter):
    def __init__(
        self,
        environment: Literal["development", "test", "production"] = "development",
    ) -> None:
        super().__init__()
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        if self._environment == "production" and record.exc_info is not None:
            error_category = getattr(record, "error_category", "internal_error")
            if error_category not in ERROR_CATEGORY_ALLOWLIST:
                error_category = "internal_error"
            exception_class = record.exc_info[0]
            exception_type = (
                exception_class.__name__ if exception_class is not None else "Exception"
            )
            payload: dict[str, object] = {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": "request_failed",
                "exception_type": exception_type,
                "error_category": error_category,
            }
            request_id = getattr(record, "request_id", None)
            if request_id is not None:
                payload["request_id"] = redact_text(str(request_id))
            return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

        raw_message = record.getMessage()
        message = (
            raw_message
            if self._environment != "production" or raw_message in PRODUCTION_MESSAGE_ALLOWLIST
            else "application_event"
        )
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_text(message),
        }
        safe_fields = (
            PRODUCTION_SAFE_LOG_FIELDS if self._environment == "production" else SAFE_LOG_FIELDS
        )
        for field_name in safe_fields:
            field_value = getattr(record, field_name, None)
            if field_value is None:
                continue
            if self._environment == "production" and field_name == "event":
                field_value = (
                    field_value
                    if field_value in PRODUCTION_EVENT_ALLOWLIST
                    else "application_event"
                )
            if self._environment == "production" and field_name == "dependency":
                field_value = (
                    field_value
                    if field_value in PRODUCTION_DEPENDENCY_ALLOWLIST
                    else "unknown_dependency"
                )
            payload[field_name] = (
                redact_text(field_value) if isinstance(field_value, str) else field_value
            )
        if record.exc_info is not None:
            payload["exception"] = redact_text(self.formatException(record.exc_info))
        elif record.exc_text:
            payload["exception"] = redact_text(record.exc_text)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_json_logging(
    environment: Literal["development", "test", "production"] = "development",
) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter(environment))
    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy"):
        managed_logger = logging.getLogger(logger_name)
        managed_logger.handlers.clear()
        managed_logger.propagate = True
