from pathlib import Path
from random import SystemRandom
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Material
from app.storage import FileValidationError, resolve_storage_key

IMAGE_MEDIA_TYPES = {"image/jpeg", "image/png"}
IMAGE_MATERIAL_CATEGORY = "image"
DEFAULT_ARTICLE_IMAGE_COUNT = 2


async def select_content_image_ids(
    database: AsyncSession,
    client_id: UUID,
    *,
    count: int = DEFAULT_ARTICLE_IMAGE_COUNT,
) -> list[str]:
    rows = list(
        (
            await database.scalars(
                select(Material)
                .where(
                    Material.client_id == client_id,
                    Material.category == IMAGE_MATERIAL_CATEGORY,
                    Material.media_type.in_(IMAGE_MEDIA_TYPES),
                    Material.authorization_status.in_(("authorized", "not_required")),
                )
                .order_by(Material.uploaded_at.desc(), Material.id),
            )
        ).all(),
    )
    if len(rows) <= count:
        selected = rows
    else:
        selected = SystemRandom().sample(rows, count)
    return [str(material.id) for material in selected]


async def resolve_content_image_paths(
    database: AsyncSession,
    *,
    storage_root: Path,
    client_id: UUID,
    material_ids: list[str],
) -> list[Path]:
    parsed_ids: list[UUID] = []
    for raw_material_id in material_ids:
        try:
            parsed_ids.append(UUID(raw_material_id))
        except (TypeError, ValueError):
            continue
    if not parsed_ids:
        return []
    rows = list(
        (
            await database.scalars(
                select(Material).where(
                    Material.client_id == client_id,
                    Material.id.in_(parsed_ids),
                    Material.category == IMAGE_MATERIAL_CATEGORY,
                    Material.media_type.in_(IMAGE_MEDIA_TYPES),
                    Material.authorization_status.in_(("authorized", "not_required")),
                ),
            )
        ).all(),
    )
    by_id = {material.id: material for material in rows}
    paths: list[Path] = []
    for parsed_id in parsed_ids:
        material = by_id.get(parsed_id)
        if material is None:
            continue
        try:
            path = resolve_storage_key(storage_root, material.storage_key)
        except FileValidationError:
            continue
        if path.is_file():
            paths.append(path)
    return paths
