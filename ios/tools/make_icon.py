#!/usr/bin/env python3
"""Builds the 1024x1024 app icon: the white rabbit head (otc_body.png, see THIRD_PARTY_NOTICES.md) on a blue gradient.

    python3 ios/tools/make_icon.py            # writes ios/Harness/Assets.xcassets/AppIcon.appiconset/icon-1024.png

The icon has no transparency (App Store Connect refuses it); iOS rounds the corners itself.
"""
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "Harness" / "Assets.xcassets" / "AppIcon.appiconset" / "icon-1024.png"
SIZE = 1024
TOP, BOTTOM = (27, 98, 253), (2, 62, 195)            # the blue of the web logo (web/scripts/gen-icons.py)
HEAD_HEIGHT = 690                                    # the head fills about two thirds of the icon

def gradient() -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE))
    px = img.load()
    for y in range(SIZE):
        t = y / (SIZE - 1)
        row = tuple(round(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3))
        for x in range(SIZE):
            px[x, y] = row
    return img

def main() -> None:
    head = Image.open(HERE / "otc_body.png").convert("RGBA")
    scale = HEAD_HEIGHT / head.height
    head = head.resize((round(head.width * scale), HEAD_HEIGHT), Image.LANCZOS)
    x, y = (SIZE - head.width) // 2, (SIZE - head.height) // 2 + 20
    canvas = gradient().convert("RGBA")
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    mask = Image.new("L", canvas.size, 0)
    mask.paste(head.getchannel("A"), (x + 6, y + 22))
    mask = mask.filter(ImageFilter.GaussianBlur(26)).point(lambda v: int(v * 0.35))
    shadow.paste((10, 30, 90, 255), (0, 0), mask)
    canvas = Image.alpha_composite(canvas, shadow)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(head, (x, y), head)
    canvas = Image.alpha_composite(canvas, layer)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT}")

if __name__ == "__main__":
    main()
