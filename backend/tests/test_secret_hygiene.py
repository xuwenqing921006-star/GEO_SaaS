import re
from pathlib import Path

import pytest


@pytest.mark.contract
def test_business_sources_do_not_contain_live_secret_shapes() -> None:
    project_root = Path(__file__).parents[2]
    roots = [
        project_root / "backend" / "app",
        project_root / "backend" / "migrations",
        project_root / "frontend" / "src",
        project_root / "frontend" / "e2e",
        project_root / "docs",
        project_root / "ops",
    ]
    standalone = [
        project_root / "compose.yaml",
        project_root / "compose.production.yaml",
        project_root / ".env.example",
        project_root / ".env.production.example",
    ]
    text_suffixes = {
        ".css",
        ".html",
        ".js",
        ".json",
        ".md",
        ".mjs",
        ".py",
        ".sh",
        ".ts",
        ".vue",
        ".yaml",
        ".yml",
    }
    secret_patterns = [
        re.compile(r"\b" + "sk-" + r"(?:ws-)?[A-Za-z0-9._-]{20,}"),
        re.compile("AGE-" + r"SECRET-KEY-1[A-Z0-9]+"),
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r"\bAKIA[A-Z0-9]{16}\b"),
        re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
        re.compile(
            r"\bpostgres(?:ql)?(?:\+[a-z0-9]+)?://[^:\s/]+:[^@\s/]+@",
            flags=re.IGNORECASE,
        ),
    ]
    files = [
        path
        for root in roots
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in text_suffixes
    ] + standalone
    findings: list[str] = []

    for path in files:
        content = path.read_text(encoding="utf-8")
        if any(pattern.search(content) for pattern in secret_patterns):
            findings.append(path.relative_to(project_root).as_posix())

    assert findings == []
