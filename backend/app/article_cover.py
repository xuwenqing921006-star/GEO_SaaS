from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from PIL import Image, ImageDraw, ImageFont, ImageOps

COVER_RENDER_VERSION = "v4-photo"

ArticleCoverStyle = Literal["azure", "sunrise", "mint"]

COVER_WIDTH = 1200
COVER_HEIGHT = 675
TITLE_BREAK_PUNCTUATION = frozenset("，。\uff01\uff1f\uff1b\uff1a、,.!?;:")


@dataclass(frozen=True)
class CoverPalette:
    background_start: str
    background_end: str
    primary: str
    accent: str
    accent_soft: str
    text: str
    muted: str
    surface: str


PALETTES: dict[ArticleCoverStyle, CoverPalette] = {
    "azure": CoverPalette(
        background_start="#F8FAFF",
        background_end="#E6F0FF",
        primary="#2563EB",
        accent="#38BDF8",
        accent_soft="#DCEBFF",
        text="#12304F",
        muted="#52708C",
        surface="#FFFFFF",
    ),
    "sunrise": CoverPalette(
        background_start="#FFFDF8",
        background_end="#FFF0E4",
        primary="#F97316",
        accent="#FB7185",
        accent_soft="#FFE1D0",
        text="#512714",
        muted="#8B6048",
        surface="#FFFFFF",
    ),
    "mint": CoverPalette(
        background_start="#F7FFFC",
        background_end="#E2F8F2",
        primary="#0F9F8F",
        accent="#3B82F6",
        accent_soft="#D5F3EC",
        text="#123E3B",
        muted="#517A76",
        surface="#FFFFFF",
    ),
}

FONT_CANDIDATES = {
    "regular": (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/Deng.ttf"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ),
    "bold": (
        Path("C:/Windows/Fonts/msyhbd.ttc"),
        Path("C:/Windows/Fonts/Dengb.ttf"),
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"),
    ),
}


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.removeprefix("#")
    return (
        int(value[0:2], 16),
        int(value[2:4], 16),
        int(value[4:6], 16),
    )


def _mix(start: str, end: str, ratio: float) -> tuple[int, int, int]:
    start_rgb = _rgb(start)
    end_rgb = _rgb(end)
    return (
        round(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * ratio),
        round(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * ratio),
        round(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * ratio),
    )


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    weight = "bold" if bold else "regular"
    for path in FONT_CANDIDATES[weight]:
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    raise RuntimeError("未找到可用于生成中文封面的字体")


def _clean_text(value: str, *, fallback: str, max_length: int) -> str:
    cleaned = " ".join(value.replace("\n", " ").split()).strip(" #*-")
    return (cleaned or fallback)[:max_length]


def _wrap_title(
    draw: ImageDraw.ImageDraw,
    title: str,
    *,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
    lines: list[str] = []
    remaining = title
    while remaining and len(lines) < max_lines:
        candidate = ""
        punctuation_break = 0
        for character in remaining:
            next_candidate = candidate + character
            if candidate and draw.textlength(next_candidate, font=font) > max_width:
                if punctuation_break:
                    candidate = remaining[:punctuation_break]
                break
            candidate = next_candidate
            if character in TITLE_BREAK_PUNCTUATION:
                punctuation_break = len(candidate)
        if not candidate:
            candidate = remaining[0]
        lines.append(candidate.strip())
        remaining = remaining[len(candidate) :].lstrip()
    if remaining:
        last = lines[-1].rstrip() + "…"
        while draw.textlength(last, font=font) > max_width and len(last) > 2:
            last = last[:-2] + "…"
        lines[-1] = last
    return lines


def _draw_background(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    palette: CoverPalette,
) -> None:
    for y in range(COVER_HEIGHT):
        ratio = y / max(1, COVER_HEIGHT - 1)
        color = _mix(
            palette.background_start,
            palette.background_end,
            ratio,
        )
        draw.line((0, y, COVER_WIDTH, y), fill=color)

    draw.ellipse((915, -120, 1315, 280), fill=palette.accent_soft)
    draw.ellipse((1000, 35, 1265, 300), fill=palette.surface)
    draw.ellipse((1038, 73, 1227, 262), outline=palette.accent, width=4)
    draw.rounded_rectangle(
        (930, 350, 1215, 625),
        radius=58,
        fill=palette.primary,
    )
    draw.ellipse((1090, 438, 1280, 628), fill=palette.accent)
    for x, y, radius in ((875, 95, 8), (920, 300, 5), (1100, 320, 7), (865, 585, 6)):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=palette.accent)

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for index in range(7):
        alpha = max(12, 38 - index * 4)
        offset = index * 16
        overlay_draw.arc(
            (955 - offset, 370 - offset, 1190 + offset, 605 + offset),
            start=205,
            end=330,
            fill=(*_rgb(palette.surface), alpha),
            width=3,
        )
    image.alpha_composite(overlay)


def _photo_background(background_path: Path | None) -> Image.Image | None:
    if background_path is None or not background_path.is_file():
        return None
    try:
        with Image.open(background_path) as source:
            normalized = ImageOps.exif_transpose(source).convert("RGB")
            fitted = ImageOps.fit(
                normalized,
                (COVER_WIDTH, COVER_HEIGHT),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.5),
            )
            return fitted.convert("RGBA")
    except (OSError, ValueError):
        return None


def _draw_photo_overlay(image: Image.Image, palette: CoverPalette) -> None:
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    primary = _rgb(palette.primary)
    draw.rectangle(
        (0, 0, COVER_WIDTH, COVER_HEIGHT),
        fill=(*primary, 24),
    )
    for x in range(COVER_WIDTH):
        ratio = x / max(1, COVER_WIDTH - 1)
        alpha = round(206 - ratio * 150)
        draw.line((x, 0, x, COVER_HEIGHT), fill=(8, 24, 43, alpha))
    draw.rectangle((0, 530, COVER_WIDTH, COVER_HEIGHT), fill=(7, 18, 32, 88))
    image.alpha_composite(overlay)


def render_article_cover(
    *,
    title: str,
    brand_name: str,
    context_line: str,
    style: ArticleCoverStyle,
    background_path: Path | None = None,
) -> bytes:
    palette = PALETTES[style]
    image = _photo_background(background_path)
    uses_photo = image is not None
    if image is None:
        image = Image.new("RGBA", (COVER_WIDTH, COVER_HEIGHT), palette.background_start)
    draw = ImageDraw.Draw(image)
    if uses_photo:
        _draw_photo_overlay(image, palette)
        draw = ImageDraw.Draw(image)
    else:
        _draw_background(image, draw, palette)

    label_font = _font(23, bold=True)
    title_font = _font(60, bold=True)
    meta_font = _font(27)
    brand_font = _font(30, bold=True)
    monogram_font = _font(120, bold=True)

    safe_title = _clean_text(title, fallback="企业服务内容", max_length=90)
    safe_brand = _clean_text(brand_name, fallback="企业内容", max_length=32)
    safe_context = _clean_text(context_line, fallback=safe_brand, max_length=50)

    title_lines = _wrap_title(
        draw,
        safe_title,
        font=title_font,
        max_width=1040 if uses_photo else 790,
        max_lines=3,
    )
    if uses_photo:
        draw.rounded_rectangle(
            (68, 56, 68 + min(650, 34 + len(safe_context) * 29), 108),
            radius=25,
            fill=palette.primary,
        )
        draw.text((92, 68), safe_context, font=label_font, fill=palette.surface)
        title_y = 174
        for line in title_lines:
            draw.text(
                (68, title_y),
                line,
                font=title_font,
                fill=palette.surface,
                stroke_width=1,
                stroke_fill=(15, 30, 45),
            )
            title_y += 84
        draw.rounded_rectangle((68, 566, 76, 626), radius=4, fill=palette.accent)
        draw.text((100, 568), safe_brand, font=brand_font, fill=palette.surface)
        draw.text((100, 610), safe_context, font=meta_font, fill="#E2E8F0")
    else:
        draw.text((70, 72), safe_context, font=meta_font, fill=palette.muted)
        title_y = 184
        for line in title_lines:
            draw.text((68, title_y), line, font=title_font, fill=palette.text)
            title_y += 82
        draw.rounded_rectangle((70, 554, 825, 556), radius=1, fill=palette.accent_soft)
        draw.ellipse((70, 589, 88, 607), fill=palette.accent)
        draw.text((104, 575), safe_brand, font=brand_font, fill=palette.text)
        draw.text(
            (1010, 240),
            safe_brand[:1],
            font=monogram_font,
            fill=palette.surface,
        )

    output = BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()


def article_cover_path(
    storage_root: Path,
    *,
    document_id: UUID,
    version_id: UUID,
    style: ArticleCoverStyle,
) -> Path:
    root = (storage_root / "covers").resolve()
    filename = f"{version_id}-{style}-{COVER_RENDER_VERSION}.png"
    path = (root / str(document_id) / filename).resolve()
    if root not in path.parents:
        raise RuntimeError("article cover path escaped storage root")
    return path


def ensure_article_cover(
    path: Path,
    *,
    title: str,
    brand_name: str,
    context_line: str,
    style: ArticleCoverStyle,
    background_path: Path | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = render_article_cover(
        title=title,
        brand_name=brand_name,
        context_line=context_line,
        style=style,
        background_path=background_path,
    )
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_bytes(payload)
    temporary.replace(path)
