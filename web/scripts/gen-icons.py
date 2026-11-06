#!/usr/bin/env python3
"""Generate every logo file (the rabbit head on the accent color), for each accent color.

Run from anywhere: `uv run --with playwright python web/scripts/gen-icons.py` (the PNGs are rendered by Chromium;
set MX_CHROMIUM to a Chromium / chrome-headless-shell binary to skip `playwright install`). Outputs are committed,
so this only runs when the logo or the accents change.

public/icons/logo-<accent>.svg              the logo, vector (sidebar, splash, favicon, sign-in)
public/icons/logo-<accent>-64|128.png       the same, raster (older references, notifications fallback)
public/icons/icon-<accent>-192|512.png      installed app, "any" purpose: rounded square, transparent corners
public/icons/icon-maskable-<accent>-512.png "maskable": full-bleed background, logo inside the 80 % safe zone
                                            (Android cuts its own shape - corners must be filled)
public/icons/apple-touch-icon-<accent>.png  iOS home screen, 180 px, full-bleed and opaque (iOS rounds it)
public/manifest-<accent>.webmanifest        the web app manifest pointing at that accent's icons
The blue files are also written under the historical names (icon-192.png, icon-512.png, icon-maskable-512.png,
apple-touch-icon.png, favicon.svg, manifest.webmanifest) - the defaults before any accent is known.
"""
import base64
import colorsys
import io
import json
import os
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

WEB = Path(__file__).resolve().parent.parent
PUBLIC = WEB / "public"
ICONS = PUBLIC / "icons"

# The logo body is a diagonal gradient; each accent rotates the hue of both stops (lightness and saturation kept).
BLUE_STOPS = ((45, 110, 253), (14, 199, 247))
ACCENT_BODY = {"blue": (42, 128, 254), "violet": (213, 42, 254), "clay": (254, 170, 42), "green": (51, 254, 42),
               "amber": (254, 241, 42), "rose": (254, 82, 42)}
PAPER, INK, METAL = "#faf9f4", "#1d1e24", "#d6d9df"
RADIUS = 112                                     # corner radius of the rounded square, on the 512 grid


def _hue(rgb):
    return colorsys.rgb_to_hls(*[c / 255 for c in rgb])


def stops(accent: str) -> list[str]:
    shift = _hue(ACCENT_BODY[accent])[0] - _hue(ACCENT_BODY["blue"])[0]
    out = []
    for rgb in BLUE_STOPS:
        h, l, s = _hue(rgb)
        r, g, b = colorsys.hls_to_rgb((h + shift) % 1, l, s)
        out.append("#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255)))
    return out


RABBIT_SRC = WEB.parent / "ios" / "tools" / "rabbit_logo.png"   # white rabbit head, see THIRD_PARTY_NOTICES.md
RABBIT_H, RABBIT_W = 330, 330 * 768 / 916                    # its size on the 512 grid
HEAD_CX = 300 / 768                                          # the face (not the ears) is centred: x of its centre / image width
_rabbit: dict[int, str] = {}


def rabbit_uri(height: int) -> str:
    """The rabbit as a PNG data URI `height` px tall (small for the vector logo file, large for the raster icons)."""
    if height not in _rabbit:
        im = Image.open(RABBIT_SRC).convert("RGBA")
        im = im.resize((round(im.width * height / im.height), height), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "PNG", optimize=True)
        _rabbit[height] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return _rabbit[height]


def background(accent: str) -> tuple[str, str]:
    """Top and bottom of the tile: the accent, darkened towards the bottom so the white head stands out."""
    h, light, sat = _hue(tuple(round(int(stops(accent)[0][i:i + 2], 16)) for i in (1, 3, 5)))
    out = []
    for k in (0.94, 0.66):
        r, g, b = colorsys.hls_to_rgb(h, light * k, sat)
        out.append("#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255)))
    return out[0], out[1]


def svg(accent: str, *, size: int | None = None, rounded: bool = True, scale: float = 1.0, embed: int = 160) -> str:
    """The logo on a 512 grid: the rabbit head on the accent color. `rounded`: transparent corners (else full bleed);
    `scale` shrinks the drawing around the center (maskable safe zone); `embed`: pixel height of the embedded head."""
    c0, c1 = background(accent)
    rx = RADIUS if rounded else 0
    wh = f' width="{size}" height="{size}"' if size else ""
    t = 256 * (1 - scale)
    x, y = 256 - HEAD_CX * RABBIT_W, (512 - RABBIT_H) / 2 + 14
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 512 512"{wh}>'
        f'<defs><linearGradient id="g" x1="0" y1="0" x2="120" y2="512" gradientUnits="userSpaceOnUse">'
        f'<stop offset="0" stop-color="{c0}"/><stop offset="1" stop-color="{c1}"/></linearGradient>'
        '<filter id="s" x="-20%" y="-20%" width="140%" height="150%">'
        '<feDropShadow dx="0" dy="9" stdDeviation="12" flood-color="#06143c" flood-opacity=".4"/></filter>'
        f'<clipPath id="c"><rect width="512" height="512" rx="{rx}"/></clipPath></defs>'
        f'<g clip-path="url(#c)"><rect width="512" height="512" fill="url(#g)"/>'
        f'<g transform="translate({t:g} {t:g}) scale({scale:g})">'
        f'<image x="{x:g}" y="{y:g}" width="{RABBIT_W:g}" height="{RABBIT_H}" filter="url(#s)" '
        f'xlink:href="{rabbit_uri(embed)}"/>'
        "</g></g></svg>"
    )


def manifest(accent: str) -> dict:
    m = json.loads((PUBLIC / "manifest.webmanifest").read_text())
    m["icons"] = [
        {"src": f"/icons/icon-{accent}-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": f"/icons/icon-{accent}-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": f"/icons/icon-maskable-{accent}-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ]
    for s in m.get("shortcuts", []):
        s["icons"] = [{"src": f"/icons/icon-{accent}-192.png", "sizes": "192x192"}]
    return m


def main():
    ICONS.mkdir(parents=True, exist_ok=True)
    launch = {"executable_path": os.environ["MX_CHROMIUM"]} if os.environ.get("MX_CHROMIUM") else {}
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch)
        page = browser.new_page()

        def png(markup: str, size: int, path: Path):
            page.set_viewport_size({"width": size, "height": size})
            page.set_content(f'<html><body style="margin:0;background:transparent">{markup}</body></html>')
            page.locator("svg").screenshot(path=str(path), omit_background=True)

        for a in ACCENT_BODY:
            (ICONS / f"logo-{a}.svg").write_text(svg(a) + "\n")
            for size in (64, 128):
                png(svg(a, size=size, embed=300), size, ICONS / f"logo-{a}-{size}.png")
            for size in (192, 512):
                png(svg(a, size=size, embed=700), size, ICONS / f"icon-{a}-{size}.png")
            png(svg(a, size=512, rounded=False, scale=0.78, embed=700), 512, ICONS / f"icon-maskable-{a}-512.png")
            png(svg(a, size=180, rounded=False, scale=0.94, embed=500), 180, ICONS / f"apple-touch-icon-{a}.png")
            (PUBLIC / f"manifest-{a}.webmanifest").write_text(json.dumps(manifest(a), indent=2, ensure_ascii=False) + "\n")
            print("wrote", a)
        browser.close()

    for blue, default in (("icon-blue-192.png", "icon-192.png"), ("icon-blue-512.png", "icon-512.png"),
                          ("icon-maskable-blue-512.png", "icon-maskable-512.png"),
                          ("apple-touch-icon-blue.png", "apple-touch-icon.png")):
        (ICONS / default).write_bytes((ICONS / blue).read_bytes())
    (PUBLIC / "favicon.svg").write_text(svg("blue") + "\n")


if __name__ == "__main__":
    main()
