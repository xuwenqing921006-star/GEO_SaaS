from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from PIL import Image
from pypdf import PdfWriter

import app.storage as storage
from app.storage import (
    FileValidationError,
    inspect_upload,
    material_path,
    resolve_storage_key,
    safe_original_name,
)


def _office_archive(required_member: str, *, expanded_size: int = 10) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr(required_member, "x" * expanded_size)
    return output.getvalue()


def _pdf() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    writer.write(output)
    return output.getvalue()


def _image(image_format: str) -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), "white").save(output, format=image_format)
    return output.getvalue()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("filename", "content_type", "content", "expected_media_type"),
    [
        ("facts.txt", "text/plain", "企业名称: 莱恩美术".encode(), "text/plain"),
        ("facts.pdf", "application/pdf", _pdf(), "application/pdf"),
        ("photo.png", "image/png", _image("PNG"), "image/png"),
        ("photo.jpg", "image/jpeg", _image("JPEG"), "image/jpeg"),
        (
            "facts.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            _office_archive("word/document.xml"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            "facts.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            _office_archive("xl/workbook.xml"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
    ],
)
def test_inspect_upload_accepts_only_matching_real_signatures(
    filename: str,
    content_type: str,
    content: bytes,
    expected_media_type: str,
) -> None:
    inspected = inspect_upload(filename, content_type, content)
    assert inspected.media_type == expected_media_type
    assert inspected.extension == filename[filename.rfind(".") :]


@pytest.mark.unit
def test_inspect_upload_rejects_disguised_and_dangerous_archives() -> None:
    with pytest.raises(FileValidationError):
        inspect_upload("fake.pdf", "application/pdf", b"<script>alert(1)</script>")
    with pytest.raises(FileValidationError):
        inspect_upload(
            "truncated.png",
            "image/png",
            b"\x89PNG\r\n\x1a\n" + b"x" * 20,
        )
    with pytest.raises(FileValidationError):
        inspect_upload(
            "fake.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            _office_archive("../../escape.txt"),
        )
    with pytest.raises(FileValidationError):
        inspect_upload(
            "bomb.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            _office_archive("xl/workbook.xml", expanded_size=2_000_000),
            max_expanded_bytes=100_000,
        )


@pytest.mark.unit
def test_text_upload_rejects_binary_and_invalid_utf8() -> None:
    with pytest.raises(FileValidationError):
        inspect_upload("binary.txt", "text/plain", b"\x00\x01\x02")
    with pytest.raises(FileValidationError):
        inspect_upload("invalid.txt", "text/plain", b"\xff\xfe\xff")


@pytest.mark.unit
def test_filename_media_size_and_storage_paths_fail_closed(tmp_path) -> None:
    for filename in ("", ".", "..", "\\"):
        with pytest.raises(FileValidationError, match="filename"):
            safe_original_name(filename)

    with pytest.raises(FileValidationError, match="media type"):
        inspect_upload("facts.exe", "application/octet-stream", b"content")
    with pytest.raises(FileValidationError, match="empty or too large"):
        inspect_upload("facts.txt", "text/plain", b"")
    with pytest.raises(FileValidationError, match="outside"):
        material_path(tmp_path, "..", "escape", ".txt")
    with pytest.raises(FileValidationError, match="outside"):
        resolve_storage_key(tmp_path, "../escape.txt")


@pytest.mark.unit
def test_archive_pdf_and_image_policy_limits_are_enforced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(storage, "MAX_ARCHIVE_ENTRIES", 1)
    with pytest.raises(FileValidationError, match="too many entries"):
        inspect_upload(
            "facts.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            _office_archive("word/document.xml"),
        )
    monkeypatch.setattr(storage, "MAX_ARCHIVE_ENTRIES", 10_000)
    with pytest.raises(FileValidationError, match="structure"):
        inspect_upload(
            "facts.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            _office_archive("word/not-document.xml"),
        )

    class UnsafePdf:
        def __init__(self) -> None:
            self.is_encrypted = True
            self.pages: list[object] = []

    monkeypatch.setattr(storage, "PdfReader", lambda _: UnsafePdf())
    with pytest.raises(FileValidationError, match="PDF structure"):
        inspect_upload("facts.pdf", "application/pdf", b"%PDF-not-read")

    monkeypatch.setattr(storage, "MAX_IMAGE_PIXELS", 1)
    with pytest.raises(FileValidationError, match="image"):
        inspect_upload("photo.png", "image/png", _image("PNG"))
    monkeypatch.setattr(storage, "MAX_IMAGE_PIXELS", 40_000_000)

    class WrongImageFormat:
        width = 2
        height = 2
        format = "JPEG"

        def __enter__(self) -> "WrongImageFormat":
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def verify(self) -> None:
            return None

    monkeypatch.setattr(storage.Image, "open", lambda _: WrongImageFormat())
    with pytest.raises(FileValidationError, match="image"):
        inspect_upload("photo.png", "image/png", _image("PNG"))
