from pathlib import Path

import pytest
from openpyxl import Workbook

from app.parsers import MAX_TOTAL_CHARS, ParseFailure, _parse_pdf, parse_material


@pytest.mark.unit
def test_long_text_is_split_without_silent_truncation(tmp_path: Path) -> None:
    path = tmp_path / "long.txt"
    content = "企业服务资料" * 5_000
    path.write_text(content, encoding="utf-8")
    parsed = parse_material(path, "text/plain")
    assert len(parsed.fragments) > 1
    assert "".join(fragment.text for fragment in parsed.fragments) == content


@pytest.mark.unit
def test_text_over_total_limit_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "too-long.txt"
    path.write_text("x" * (MAX_TOTAL_CHARS + 1), encoding="utf-8")
    with pytest.raises(ParseFailure, match="safe processing limit"):
        parse_material(path, "text/plain")


@pytest.mark.unit
def test_sparse_spreadsheet_dimension_bomb_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "sparse.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet["XFD5000"] = "稀疏单元格"
    workbook.save(path)
    workbook.close()
    with pytest.raises(ParseFailure, match="dimensions"):
        parse_material(
            path,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


@pytest.mark.unit
def test_geo_customer_template_returns_one_fragment_per_filled_field(
    tmp_path: Path,
) -> None:
    path = tmp_path / "customer-template.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet["A1"] = "企业资料采集表"
    sheet.append([])
    sheet.append([])
    sheet.append(["序号", "资料项目", "客户填写", "填写说明 / 示例"])
    sheet.append([1, "* 企业或机构标准名称", "莱恩美术", ""])
    sheet.append([2, "对外简称 / 品牌名", "", ""])
    sheet.append([3, "* 所属行业 / 主营类别", "少儿美术培训", ""])
    workbook.save(path)
    workbook.close()

    parsed = parse_material(
        path,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

    assert [fragment.extraction_method for fragment in parsed.fragments] == [
        "geo_template",
        "geo_template",
    ]
    assert [fragment.text for fragment in parsed.fragments] == [
        "企业或机构标准名称: 莱恩美术",
        "所属行业 / 主营类别: 少儿美术培训",
    ]


@pytest.mark.unit
def test_pdf_stops_extracting_pages_as_soon_as_total_limit_is_exceeded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    class FakePage:
        def extract_text(self) -> str:
            nonlocal calls
            calls += 1
            return "x" * 1_100_000

    class FakeReader:
        def __init__(self) -> None:
            self.is_encrypted = False
            self.pages = [FakePage() for _ in range(10)]

    monkeypatch.setattr("app.parsers.PdfReader", lambda _path: FakeReader())
    with pytest.raises(ParseFailure, match="safe processing limit"):
        _parse_pdf(tmp_path / "oversized.pdf")
    assert calls == 2
