from dataclasses import dataclass
from io import BytesIO
from os import replace
from pathlib import Path, PurePosixPath
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_FILE_SIZE = 30 * 1024 * 1024
MAX_EXPANDED_BYTES = 120 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10_000
MAX_COMPRESSION_RATIO = 100
MAX_PDF_PAGES = 500
MAX_IMAGE_PIXELS = 40_000_000

MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}
REQUIRED_ARCHIVE_MEMBERS = {
    ".docx": "word/document.xml",
    ".xlsx": "xl/workbook.xml",
}


class FileValidationError(ValueError):
    pass


@dataclass(frozen=True)
class InspectedUpload:
    safe_name: str
    extension: str
    media_type: str


def safe_original_name(filename: str) -> str:
    normalized = filename.replace("\\", "/")
    name = PurePosixPath(normalized).name
    cleaned = "".join(character for character in name if character.isprintable()).strip()
    if not cleaned or cleaned in {".", ".."}:
        raise FileValidationError("invalid filename")
    return cleaned[:255]


def _validate_archive(
    content: bytes,
    required_member: str,
    *,
    max_expanded_bytes: int,
) -> None:
    try:
        with ZipFile(BytesIO(content)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_ARCHIVE_ENTRIES:
                raise FileValidationError("archive contains too many entries")
            expanded_size = 0
            names: set[str] = set()
            for entry in entries:
                path = PurePosixPath(entry.filename.replace("\\", "/"))
                if path.is_absolute() or ".." in path.parts:
                    raise FileValidationError("archive path is unsafe")
                expanded_size += entry.file_size
                if expanded_size > max_expanded_bytes:
                    raise FileValidationError("archive expands beyond the allowed size")
                if entry.compress_size == 0 and entry.file_size > 0:
                    raise FileValidationError("archive compression ratio is unsafe")
                if (
                    entry.compress_size > 0
                    and entry.file_size / entry.compress_size > MAX_COMPRESSION_RATIO
                ):
                    raise FileValidationError("archive compression ratio is unsafe")
                names.add(entry.filename)
            if "[Content_Types].xml" not in names or required_member not in names:
                raise FileValidationError("office document structure is invalid")
    except BadZipFile as error:
        raise FileValidationError("office document is not a valid zip archive") from error


def inspect_upload(
    filename: str,
    content_type: str | None,
    content: bytes,
    *,
    max_expanded_bytes: int = MAX_EXPANDED_BYTES,
) -> InspectedUpload:
    safe_name = safe_original_name(filename)
    extension = Path(safe_name).suffix.casefold()
    expected_media_type = MEDIA_TYPES.get(extension)
    if expected_media_type is None or content_type != expected_media_type:
        raise FileValidationError("extension and declared media type do not match")
    if not content or len(content) > MAX_FILE_SIZE:
        raise FileValidationError("file is empty or too large")
    if extension == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise FileValidationError("PDF signature is invalid")
        try:
            reader = PdfReader(BytesIO(content))
            if reader.is_encrypted or len(reader.pages) > MAX_PDF_PAGES:
                raise FileValidationError("PDF structure is not allowed")
        except (PdfReadError, OSError, ValueError) as error:
            raise FileValidationError("PDF structure is invalid") from error
    if extension in {".png", ".jpg", ".jpeg"}:
        expected_signature = b"\x89PNG\r\n\x1a\n" if extension == ".png" else b"\xff\xd8\xff"
        if not content.startswith(expected_signature):
            raise FileValidationError("image signature is invalid")
        try:
            with Image.open(BytesIO(content)) as image:
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise FileValidationError("image dimensions exceed the safe limit")
                expected_format = "PNG" if extension == ".png" else "JPEG"
                if image.format != expected_format:
                    raise FileValidationError("image format does not match its extension")
                image.verify()
        except (UnidentifiedImageError, OSError, ValueError) as error:
            raise FileValidationError("image structure is invalid") from error
    if extension == ".txt":
        if b"\x00" in content:
            raise FileValidationError("text file contains binary null bytes")
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise FileValidationError("text file must use UTF-8") from error
    required_member = REQUIRED_ARCHIVE_MEMBERS.get(extension)
    if required_member is not None:
        _validate_archive(
            content,
            required_member,
            max_expanded_bytes=max_expanded_bytes,
        )
    return InspectedUpload(
        safe_name=safe_name,
        extension=extension,
        media_type=expected_media_type,
    )


def material_path(
    storage_root: Path,
    client_id: str,
    material_id: str,
    extension: str,
) -> Path:
    root = (storage_root / "materials").resolve()
    candidate = (root / client_id / f"{material_id}{extension}").resolve()
    if root not in candidate.parents:
        raise FileValidationError("resolved storage path is outside the material root")
    return candidate


def write_material_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary_path.write_bytes(content)
        replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def remove_material_file(path: Path) -> None:
    path.unlink(missing_ok=True)


def resolve_storage_key(storage_root: Path, storage_key: str) -> Path:
    root = storage_root.resolve()
    candidate = (root / storage_key).resolve()
    if root not in candidate.parents:
        raise FileValidationError("stored material path is outside the storage root")
    return candidate
