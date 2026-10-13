from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.publishing_specs import PUBLISHING_PLATFORM_SPECS


class PublishingImageError(ValueError):
    pass


def _rgb_image(image: Image.Image) -> Image.Image:
    transposed = ImageOps.exif_transpose(image)
    if transposed.mode == "RGB":
        return transposed.copy()
    if "A" in transposed.getbands():
        rgba = transposed.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return transposed.convert("RGB")


def _save_with_limit(image: Image.Image, destination: Path, max_bytes: int) -> None:
    working = image
    quality = 90
    for _ in range(12):
        working.save(
            destination,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
        )
        if destination.stat().st_size <= max_bytes:
            return
        if quality > 68:
            quality -= 6
            continue
        width = max(640, round(working.width * 0.85))
        height = max(360, round(working.height * 0.85))
        if (width, height) == working.size:
            break
        working = working.resize((width, height), Image.Resampling.LANCZOS)
    raise PublishingImageError("图片压缩后仍超过平台大小限制")


def prepare_publishing_image(
    source: Path,
    destination: Path,
    *,
    channel_id: str,
    role: str,
) -> Path:
    platform_spec = PUBLISHING_PLATFORM_SPECS.get(channel_id)
    if platform_spec is None:
        raise PublishingImageError("发布平台没有配置图片规则")
    policy = platform_spec.image
    if not source.is_file():
        raise PublishingImageError("待发布图片文件不存在")

    try:
        with Image.open(source) as opened:
            image = _rgb_image(opened)
    except (OSError, UnidentifiedImageError) as error:
        raise PublishingImageError("图片格式无法识别或文件已损坏") from error

    if role == "cover":
        image = ImageOps.fit(
            image,
            policy.cover_size,
            method=Image.Resampling.LANCZOS,
        )
    elif role == "body":
        image.thumbnail(
            (policy.max_width, policy.max_height),
            Image.Resampling.LANCZOS,
        )
    else:
        raise PublishingImageError("未知的发布图片用途")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = destination.with_suffix(".jpg")
    _save_with_limit(image, destination, policy.max_bytes)
    return destination
