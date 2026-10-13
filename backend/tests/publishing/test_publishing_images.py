from pathlib import Path

import pytest
from PIL import Image

from app.publishing_images import PublishingImageError, prepare_publishing_image


def _make_image(path: Path, *, size: tuple[int, int], mode: str = "RGBA") -> None:
    color = (30, 120, 220, 120) if mode == "RGBA" else (30, 120, 220)
    Image.new(mode, size, color).save(path, format="PNG")


@pytest.mark.parametrize(
    "channel_id",
    ("toutiao", "sohu", "baijia", "netease", "penguin", "yidian"),
)
def test_platform_image_is_normalized_before_upload(tmp_path: Path, channel_id: str) -> None:
    source = tmp_path / "source.png"
    _make_image(source, size=(5200, 3600))

    output = prepare_publishing_image(
        source,
        tmp_path / channel_id / "body",
        channel_id=channel_id,
        role="body",
    )

    assert output.suffix == ".jpg"
    with Image.open(output) as rendered:
        assert rendered.format == "JPEG"
        assert rendered.mode == "RGB"
        assert rendered.width <= 4096
        assert rendered.height <= 4096


def test_cover_is_rendered_to_safe_sixteen_by_nine_size(tmp_path: Path) -> None:
    source = tmp_path / "cover.png"
    _make_image(source, size=(700, 1400))

    output = prepare_publishing_image(
        source,
        tmp_path / "cover",
        channel_id="sohu",
        role="cover",
    )

    with Image.open(output) as rendered:
        assert rendered.size == (1200, 675)
        assert rendered.mode == "RGB"


def test_baijia_cover_matches_the_live_editor_three_by_two_preview(tmp_path: Path) -> None:
    source = tmp_path / "cover.png"
    _make_image(source, size=(700, 1400))

    output = prepare_publishing_image(
        source,
        tmp_path / "baijia-cover",
        channel_id="baijia",
        role="cover",
    )

    with Image.open(output) as rendered:
        assert rendered.size == (1200, 800)
        assert rendered.mode == "RGB"


def test_netease_cover_matches_the_live_single_cover_four_by_three_preview(
    tmp_path: Path,
) -> None:
    source = tmp_path / "cover.png"
    _make_image(source, size=(700, 1400))

    output = prepare_publishing_image(
        source,
        tmp_path / "netease-cover",
        channel_id="netease",
        role="cover",
    )

    with Image.open(output) as rendered:
        assert rendered.size == (1200, 900)
        assert rendered.mode == "RGB"


def test_yidian_cover_uses_the_conservative_editorial_default_until_live_validation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "cover.png"
    _make_image(source, size=(700, 1400))

    output = prepare_publishing_image(
        source,
        tmp_path / "yidian-cover",
        channel_id="yidian",
        role="cover",
    )

    with Image.open(output) as rendered:
        assert rendered.size == (1200, 675)
        assert rendered.mode == "RGB"


def test_unknown_platform_is_rejected_before_browser_upload(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    _make_image(source, size=(640, 480))

    with pytest.raises(PublishingImageError, match="没有配置图片规则"):
        prepare_publishing_image(
            source,
            tmp_path / "output",
            channel_id="unknown",
            role="body",
        )
