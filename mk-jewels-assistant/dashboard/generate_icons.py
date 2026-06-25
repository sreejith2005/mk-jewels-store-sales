from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


BASE_DIR = Path(__file__).resolve().parent
ICON_DIR = BASE_DIR / "static" / "icons"
GOLD = "#C9A96E"
WHITE = "#FFFFFF"


def _load_font(size: int) -> ImageFont.ImageFont:
    """Load a bold font when available, otherwise fall back to Pillow default."""
    for font_name in ("arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(font_name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _create_icon(size: int) -> None:
    image = Image.new("RGB", (size, size), GOLD)
    draw = ImageDraw.Draw(image)
    font = _load_font(int(size * 0.38))
    text = "MK"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    position = ((size - text_width) / 2, (size - text_height) / 2 - bbox[1])
    draw.text(position, text, fill=WHITE, font=font)
    image.save(ICON_DIR / f"icon-{size}.png")


def main() -> None:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        _create_icon(size)


if __name__ == "__main__":
    main()
