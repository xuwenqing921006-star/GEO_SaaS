from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
def test_channel_rule_rollback_is_append_only() -> None:
    source = (
        BACKEND_ROOT / "migrations/versions/0018_channel_publication_safeguards.py"
    ).read_text(encoding="utf-8")

    assert "T-029 回滚至升级前渠道规则" in source
    assert "DELETE FROM prompt_template_versions" not in source
    assert "description = :description" in source
    assert '"description": OLD_DESCRIPTIONS[code]' in source


@pytest.mark.unit
def test_publication_migration_backfills_existing_published_documents() -> None:
    source = (BACKEND_ROOT / "migrations/versions/0019_content_publications.py").read_text(
        encoding="utf-8"
    )

    assert "content_publications" in source
    assert "WHERE d.status = 'published'" in source
    assert "uq_content_publications_document_version" in source
