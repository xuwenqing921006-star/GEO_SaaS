from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from app.article_cover import COVER_RENDER_VERSION, article_cover_path, render_article_cover


@pytest.mark.unit
def test_render_article_cover_creates_publishable_png_for_each_style() -> None:
    rendered = {
        style: render_article_cover(
            title="在即墨给孩子选美术班，先想清楚这几点再试听",
            brand_name="莱恩美术",
            context_line="即墨区 · 少儿美术培训",
            style=style,
        )
        for style in ("azure", "sunrise", "mint")
    }

    for image_bytes in rendered.values():
        image = Image.open(BytesIO(image_bytes))
        assert image.format == "PNG"
        assert image.size == (1200, 675)
        assert image.mode == "RGB"

    assert len(set(rendered.values())) == 3


@pytest.mark.unit
def test_render_article_cover_uses_enterprise_photo_when_available(
    tmp_path: Path,
) -> None:
    background = tmp_path / "课堂现场.png"
    Image.new("RGB", (900, 1200), "#E66F51").save(background, format="PNG")

    rendered = render_article_cover(
        title="即墨少儿美术培训怎么选",
        brand_name="莱恩美术",
        context_line="即墨区 · 少儿美术培训",
        style="azure",
        background_path=background,
    )
    image = Image.open(BytesIO(rendered))

    assert image.getpixel((1150, 220))[0] > image.getpixel((1150, 220))[2]
    assert rendered != render_article_cover(
        title="即墨少儿美术培训怎么选",
        brand_name="莱恩美术",
        context_line="即墨区 · 少儿美术培训",
        style="azure",
    )


@pytest.mark.unit
def test_article_cover_path_is_scoped_below_storage_root(tmp_path: Path) -> None:
    document_id = uuid4()
    version_id = uuid4()

    result = article_cover_path(
        tmp_path,
        document_id=document_id,
        version_id=version_id,
        style="azure",
    )

    assert result == (
        tmp_path.resolve()
        / "covers"
        / str(document_id)
        / f"{version_id}-azure-{COVER_RENDER_VERSION}.png"
    )
    assert tmp_path.resolve() in result.parents
