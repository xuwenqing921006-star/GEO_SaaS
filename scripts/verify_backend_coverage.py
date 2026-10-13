import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_TEST_ARGS = [
    "-m",
    "pytest",
    "-c",
    "backend/pyproject.toml",
    "backend/tests",
]
CORE_MODULES = [
    "app.config",
    "app.knowledge_context",
    "app.logging",
    "app.observability",
    "app.providers",
    "app.responses",
    "app.schemas",
    "app.security",
    "app.storage",
]


def run(args: list[str], *, environment: dict[str, str]) -> None:
    completed = subprocess.run(
        [sys.executable, *PROJECT_TEST_ARGS, *args],
        check=False,
        env=environment,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def enforce_report_metric(
    report_path: str,
    metric: str,
    threshold: float,
    label: str,
) -> None:
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    actual = float(report["totals"][metric])
    print(f"{label}: {actual:.2f}% (required {threshold:.2f}%)")
    if actual < threshold:
        raise SystemExit(f"{label} below gate: {actual:.2f}% < {threshold:.2f}%")


def main() -> None:
    statement_environment = os.environ.copy()
    statement_environment["COVERAGE_CORE"] = "sysmon"
    run(
        [
            "--cov=app",
            "--cov-report=term",
            "--cov-report=json:backend/coverage-statements-t013.json",
            "--cov-fail-under=75",
        ],
        environment=statement_environment,
    )
    enforce_report_metric(
        "backend/coverage-statements-t013.json",
        "percent_statements_covered",
        75,
        "Whole-backend statement coverage",
    )

    branch_environment = os.environ.copy()
    branch_environment.pop("COVERAGE_CORE", None)
    run(
        [
            *(item for module in CORE_MODULES for item in ("--cov", module)),
            "--cov-branch",
            "--cov-report=term",
            "--cov-report=json:backend/coverage-core-branches-t013.json",
            "--cov-fail-under=0",
        ],
        environment=branch_environment,
    )
    enforce_report_metric(
        "backend/coverage-core-branches-t013.json",
        "percent_branches_covered",
        85,
        "Core-module branch coverage",
    )


if __name__ == "__main__":
    main()
