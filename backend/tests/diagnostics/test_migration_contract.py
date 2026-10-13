from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
def test_diagnostic_scope_is_added_by_a_forward_compatible_revision() -> None:
    revision_0005 = (BACKEND_ROOT / "migrations/versions/0005_diagnostics_strategy.py").read_text(
        encoding="utf-8"
    )
    revision_0006 = (BACKEND_ROOT / "migrations/versions/0006_diagnostic_scope.py").read_text(
        encoding="utf-8"
    )

    assert 'revision: str = "0005"' in revision_0005
    assert '"monitoring_window_days"' not in revision_0005
    assert 'revision: str = "0006"' in revision_0006
    assert 'down_revision: str | None = "0005"' in revision_0006
    assert 'op.add_column(\n        "diagnostic_runs"' in revision_0006
    assert "diagnostic_runs.update().values(" in revision_0006
    assert 'op.alter_column("diagnostic_runs", "scope", nullable=False)' in revision_0006
