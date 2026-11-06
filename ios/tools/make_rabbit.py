#!/usr/bin/env python3
"""Draws the eyes on the rabbit head: otc_body.png (GrokBot's Otc, eyeless) -> rabbit_logo.png, the artwork the logo
and the app icon use (web/scripts/gen-icons.py, ios/tools/make_icon.py).

    python3 ios/tools/make_rabbit.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
INK = (20, 22, 31, 255)
SS = 4                                                    # supersampling: smooth edges
# on the 768x916 source: head centre about (300, 640), radius about 300
EYES = [(212, 622), (388, 622)]
RX, RY = 27, 38


def main() -> None:
    base = Image.open(HERE / "otc_body.png").convert("RGBA")
    over = Image.new("RGBA", (base.width * SS, base.height * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    for cx, cy in EYES:
        cx, cy, rx, ry = cx * SS, cy * SS, RX * SS, RY * SS
        d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=INK)
        hr = 9 * SS                                       # a small highlight, upper right
        hx, hy = cx + 9 * SS, cy - 14 * SS
        d.ellipse((hx - hr, hy - hr, hx + hr, hy + hr), fill=(255, 255, 255, 255))
    over = over.resize(base.size, Image.LANCZOS)
    out = Image.alpha_composite(base, over)
    out.putalpha(base.getchannel("A"))                    # nothing outside the head
    out.save(HERE / "rabbit_logo.png", optimize=True)
    print("wrote", HERE / "rabbit_logo.png")


if __name__ == "__main__":
    main()
