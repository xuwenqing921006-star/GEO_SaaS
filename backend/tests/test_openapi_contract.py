import re
from pathlib import Path
from typing import Any, TypedDict

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.health import ReadinessSnapshot
from app.main import create_app


class ReadyHealthService:
    async def readiness(self) -> ReadinessSnapshot:
        return ReadinessSnapshot(
            status="ready",
            database="ok",
            storage="ok",
            worker_heartbeat="ok",
        )


class DocumentedOperation(TypedDict):
    success_status: str
    success_type: str
    error_statuses: set[str]


def documented_operations() -> dict[tuple[str, str], DocumentedOperation]:
    project_root = Path(__file__).parents[2]
    contract = (project_root / "docs" / "api-contracts.md").read_text(encoding="utf-8")
    matches = list(
        re.finditer(
            r"^###\s+\d+\.\d+\s+(GET|POST|PUT|PATCH|DELETE)\s+`([^`]+)`",
            contract,
            flags=re.MULTILINE,
        )
    )
    operations: dict[tuple[str, str], DocumentedOperation] = {}
    for index, match in enumerate(matches):
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(contract)
        block = contract[match.end() : block_end]
        success = re.search(r"^- 成功\s+(\d{3})", block, flags=re.MULTILINE)
        assert success is not None
        success_type = re.search(
            r"^- 成功\s+\d{3}\uff1a`Success<(.+)>`",
            block,
            flags=re.MULTILINE,
        )
        operations[(match.group(1).lower(), f"/api/v1{match.group(2)}")] = {
            "success_status": success.group(1),
            "success_type": success_type.group(1) if success_type else "binary",
            "error_statuses": set(re.findall(r"^- 错误\s+(\d{3})", block, flags=re.MULTILINE)),
        }
    return operations


def documented_type_shapes() -> dict[str, tuple[set[str], set[str]]]:
    project_root = Path(__file__).parents[2]
    contract = (project_root / "docs" / "api-contracts.md").read_text(encoding="utf-8")
    shapes_by_type: dict[str, tuple[set[str], set[str]]] = {}
    for match in re.finditer(
        r"^type\s+(\w+)(?:<[^>]+>)?\s*=\s*\{\s*$",
        contract,
        flags=re.MULTILINE,
    ):
        depth = 1
        fields: set[str] = set()
        required: set[str] = set()
        cursor = match.end()
        while depth and cursor < len(contract):
            line_end = contract.find("\n", cursor)
            if line_end == -1:
                line_end = len(contract)
            line = contract[cursor:line_end]
            if depth == 1:
                field = re.match(r"^\s{2}([A-Za-z_]\w*)(\?)?\s*:", line)
                if field:
                    fields.add(field.group(1))
                    if field.group(2) is None:
                        required.add(field.group(1))
            depth += line.count("{") - line.count("}")
            cursor = line_end + 1
        shapes_by_type[match.group(1)] = (fields, required)
    return shapes_by_type


def dereference_data_schema(
    schema: dict[str, Any],
    data_schema: dict[str, Any],
) -> dict[str, Any]:
    if "$ref" in data_schema:
        component_name = str(data_schema["$ref"]).rsplit("/", maxsplit=1)[1]
        return schema["components"]["schemas"][component_name]
    for candidate in data_schema.get("anyOf", []):
        if isinstance(candidate, dict) and "$ref" in candidate:
            component_name = str(candidate["$ref"]).rsplit("/", maxsplit=1)[1]
            return schema["components"]["schemas"][component_name]
    raise AssertionError(f"response data schema is not a concrete component: {data_schema}")


INLINE_RESPONSE_MODELS = {
    ("get", "/api/v1/health/live"): "LivenessData",
    ("get", "/api/v1/health/ready"): "ReadinessData",
    ("delete", "/api/v1/auth/session"): "LoggedOutData",
    ("put", "/api/v1/auth/password"): "PasswordChangedData",
    ("post", "/api/v1/clients/{client_id}/materials"): "MaterialsCreatedData",
    ("get", "/api/v1/materials/{material_id}"): "MaterialDetailData",
    ("delete", "/api/v1/materials/{material_id}"): "MaterialDeletedData",
    ("get", "/api/v1/clients/{client_id}/conflicts"): "ItemsData[ConflictData]",
    ("patch", "/api/v1/diagnostic-issues/{issue_id}"): "DiagnosticIssueData",
    ("get", "/api/v1/channels"): "ChannelCatalogData",
    (
        "get",
        "/api/v1/clients/{client_id}/channel-recommendations",
    ): "RecommendationListData",
    ("get", "/api/v1/monitoring/platforms"): "PlatformCatalogData",
    ("get", "/api/v1/clients/{client_id}/question-sets"): "ItemsData[QuestionSetData]",
    (
        "post",
        "/api/v1/monitoring-batches/{batch_id}/manual-samples",
    ): "ItemsData[MonitoringSampleData]",
    (
        "post",
        "/api/v1/monitoring-evaluations/{evaluation_id}/feedback",
    ): "OptimizationFeedbackData",
    (
        "get",
        "/api/v1/clients/{client_id}/optimization-actions",
    ): "ItemsData[OptimizationActionData]",
    ("post", "/api/v1/settings/providers/{provider}/test"): "ProviderTestData",
}

REQUEST_MODEL_CONTRACTS = {
    ("post", "/api/v1/clients/{client_id}/question-sets"): (
        "QuestionSetCreateInput",
        {"name", "frozen", "questions"},
        {"name", "questions"},
    ),
    ("patch", "/api/v1/question-sets/{question_set_id}"): (
        "QuestionSetPatchInput",
        {"version", "name", "frozen", "questions"},
        {"version"},
    ),
    ("post", "/api/v1/clients/{client_id}/monitoring-batches"): (
        "BatchCreateInput",
        {"question_set_id", "platform_ids", "api_sample_count", "manual_placeholders"},
        {"question_set_id", "platform_ids"},
    ),
    ("post", "/api/v1/monitoring-batches/{batch_id}/manual-samples"): (
        "ManualSamplesInput",
        {"items"},
        {"items"},
    ),
    ("put", "/api/v1/monitoring-samples/{sample_id}/evaluation"): (
        "EvaluationInput",
        {
            "version",
            "brand_found",
            "correctly_associated",
            "recommended",
            "recommendation_supported",
            "facts_accurate",
            "source_visible",
            "mentioned_name",
            "reasons",
            "incorrect_facts",
            "visible_sources",
            "note",
        },
        {"brand_found", "correctly_associated", "recommended"},
    ),
    ("post", "/api/v1/monitoring-evaluations/{evaluation_id}/feedback"): (
        "FeedbackInput",
        {"action_type", "reason", "target_page"},
        {"action_type", "reason", "target_page"},
    ),
}

NAMED_REQUEST_TYPE_MAP = {
    ("put", "/api/v1/monitoring-samples/{sample_id}/evaluation"): (
        "EvaluationRequest",
        "EvaluationInput",
    ),
    ("put", "/api/v1/settings/providers/{provider}"): (
        "ProviderSettingRequest",
        "ProviderUpdate",
    ),
}

NESTED_REQUEST_ITEM_CONTRACTS = {
    ("post", "/api/v1/clients/{client_id}/question-sets", "questions"): (
        "QuestionInput",
        "QuestionInput",
    ),
    ("patch", "/api/v1/question-sets/{question_set_id}", "questions"): (
        "QuestionInput",
        "QuestionInput",
    ),
    ("post", "/api/v1/monitoring-batches/{batch_id}/manual-samples", "items"): (
        "ManualSampleInput",
        "ManualSampleInput",
    ),
}


def expected_envelope_title(
    operation: tuple[str, str],
    success_type: str,
) -> str:
    if operation in INLINE_RESPONSE_MODELS:
        data_model = INLINE_RESPONSE_MODELS[operation]
    elif success_type.startswith("Page<") and success_type.endswith(">"):
        data_model = f"PageData[{success_type[5:-1]}]"
    elif success_type.endswith(" | null"):
        data_model = f"Union[{success_type.removesuffix(' | null')}, NoneType]"
    else:
        data_model = success_type
    return f"ApiEnvelope[{data_model}]"


@pytest.mark.contract
def test_openapi_operations_match_the_approved_contract(tmp_path: Path) -> None:
    app = create_app(
        settings=Settings(
            app_env="test",
            db_password=SecretStr("unused"),
            storage_root=tmp_path,
        ),
        health_service=ReadyHealthService(),
    )
    schema = app.openapi()
    actual = {
        (method.lower(), path)
        for path, operations in schema["paths"].items()
        for method in operations
        if method.lower() in {"get", "post", "put", "patch", "delete"}
    }
    documented = documented_operations()
    type_shapes = documented_type_shapes()
    type_fields = {name: shape[0] for name, shape in type_shapes.items()}
    expected = set(documented)

    # Explicit operation-count baseline: adding or removing an endpoint requires
    # updating both the contract catalogue and this review checkpoint.
    assert len(expected) == 92
    assert actual == expected

    unauthenticated = {
        ("get", "/api/v1/health/live"),
        ("get", "/api/v1/health/ready"),
        ("post", "/api/v1/auth/login"),
    }
    csrf_methods = {"post", "put", "patch", "delete"}
    field_drifts: list[str] = []

    for (method, path), contract in documented.items():
        operation = schema["paths"][path][method]
        success = operation["responses"][contract["success_status"]]

        if path == "/api/v1/exports/{export_id}/download":
            content = success["content"]
            assert "text/markdown" in content
            assert (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document" in content
            )
        elif path == "/api/v1/documents/{document_id}/versions/{version_id}/cover":
            assert "image/png" in success["content"]
        elif path == "/api/v1/materials/{material_id}/file":
            assert "image/png" in success["content"]
            assert "image/jpeg" in success["content"]
        else:
            success_schema = success["content"]["application/json"]["schema"]
            component_name = success_schema["$ref"].rsplit("/", maxsplit=1)[1]
            envelope_schema = schema["components"]["schemas"][component_name]
            assert envelope_schema["title"] == expected_envelope_title(
                (method, path),
                contract["success_type"],
            )
            assert "dict[str, Any]" not in envelope_schema["title"]
            documented_type = contract["success_type"].removesuffix(" | null")
            if documented_type.startswith("Page<"):
                documented_type = "Page"
            if documented_type in type_fields:
                data_schema = dereference_data_schema(
                    schema,
                    envelope_schema["properties"]["data"],
                )
                actual_fields = set(data_schema["properties"])
                expected_fields = type_fields[documented_type]
                if actual_fields != expected_fields:
                    field_drifts.append(
                        f"{method.upper()} {path} {documented_type}: "
                        f"missing={sorted(expected_fields - actual_fields)}, "
                        f"extra={sorted(actual_fields - expected_fields)}"
                    )

        actual_statuses = set(operation["responses"])
        expected_statuses = {
            contract["success_status"],
            *contract["error_statuses"],
        }
        assert actual_statuses == expected_statuses
        for error_status in contract["error_statuses"]:
            error_schema = operation["responses"][error_status]["content"]["application/json"][
                "schema"
            ]
            assert "ApiEnvelope_ErrorData" in error_schema["$ref"]

        if (method, path) in unauthenticated:
            assert "security" not in operation
        else:
            assert operation["security"] == [{"APIKeyCookie": []}]

        if method in csrf_methods and path != "/api/v1/auth/login":
            parameters = operation.get("parameters", [])
            assert any(
                parameter["in"] == "header" and parameter["name"].lower() == "x-csrf-token"
                for parameter in parameters
            )

    for operation_key, (
        title,
        expected_fields,
        expected_required,
    ) in REQUEST_MODEL_CONTRACTS.items():
        method, path = operation_key
        body_schema = schema["paths"][path][method]["requestBody"]["content"]["application/json"][
            "schema"
        ]
        component = dereference_data_schema(schema, body_schema)
        assert component["title"] == title
        assert set(component["properties"]) == expected_fields
        assert set(component.get("required", [])) == expected_required

    for operation_key, (documented_type, component_title) in NAMED_REQUEST_TYPE_MAP.items():
        method, path = operation_key
        body_schema = schema["paths"][path][method]["requestBody"]["content"]["application/json"][
            "schema"
        ]
        component = dereference_data_schema(schema, body_schema)
        assert component["title"] == component_title
        expected_fields, expected_required = type_shapes[documented_type]
        assert set(component["properties"]) == expected_fields
        assert set(component.get("required", [])) == expected_required

    for (
        method,
        path,
        property_name,
    ), (
        documented_type,
        component_title,
    ) in NESTED_REQUEST_ITEM_CONTRACTS.items():
        body_schema = schema["paths"][path][method]["requestBody"]["content"]["application/json"][
            "schema"
        ]
        body_component = dereference_data_schema(schema, body_schema)
        property_schema = body_component["properties"][property_name]
        array_schema = property_schema
        if "anyOf" in property_schema:
            array_schema = next(
                candidate
                for candidate in property_schema["anyOf"]
                if candidate.get("type") == "array"
            )
        assert array_schema["type"] == "array"
        item_component = dereference_data_schema(schema, array_schema["items"])
        assert item_component["title"] == component_title
        expected_fields, expected_required = type_shapes[documented_type]
        assert set(item_component["properties"]) == expected_fields
        assert set(item_component.get("required", [])) == expected_required

    components_by_title = {
        component.get("title"): component
        for component in schema["components"]["schemas"].values()
        if component.get("title")
    }
    for type_name, expected_fields in type_fields.items():
        documented_component = components_by_title.get(type_name)
        if documented_component is None or "properties" not in documented_component:
            continue
        actual_fields = set(documented_component["properties"])
        if actual_fields != expected_fields:
            field_drifts.append(
                f"type {type_name}: missing={sorted(expected_fields - actual_fields)}, "
                f"extra={sorted(actual_fields - expected_fields)}"
            )
        expected_required = type_shapes[type_name][1]
        actual_required = set(documented_component.get("required", []))
        if actual_required != expected_required:
            field_drifts.append(
                f"type {type_name} required: "
                f"missing={sorted(expected_required - actual_required)}, "
                f"extra={sorted(actual_required - expected_required)}"
            )

    assert not field_drifts, "\n".join(dict.fromkeys(field_drifts))
    assert schema["components"]["securitySchemes"]["APIKeyCookie"] == {
        "type": "apiKey",
        "in": "cookie",
        "name": "geo_session",
    }
