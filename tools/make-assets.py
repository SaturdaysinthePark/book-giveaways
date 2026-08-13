#!/usr/bin/env python3
"""Rasterise the site's icon and share card.

Both sources are hand-edited and committed (public/favicon.svg, tools/og.html);
this script only renders them to PNG so the site itself stays build-step free.
Headless Chrome does the rendering because the mark and the card both rely on
real type and SVG geometry, and Pillow does the downscaling.

    python3 tools/make-assets.py

Writes public/favicon-16.png, favicon-32.png, apple-touch-icon.png and og.png.
"""

import pathlib
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
PUBLIC = ROOT / "public"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# The icon is drawn on a 32-unit grid; render at 16x and downsample so the
# rounded corners and the perforation dashes land clean at every size.
ICON_MASTER = 512
ICON_SIZES = {"favicon-16.png": 16, "favicon-32.png": 32, "apple-touch-icon.png": 180}

OG_WIDTH, OG_HEIGHT = 1200, 630
# The card is mostly curves now — a punched edge, the nicks at each end of the
# perforation, hairline gaps in the stat strip — and all of them alias at 1x.
# Same answer as the icons: render a 2x master and let Pillow do the downscale.
# 2x is enough, because every value in og.html doubles to a whole device pixel.
OG_SCALE = 2


def shot(html_path, png_path, width, height, scale=1):
    """Screenshot a local HTML file at an exact viewport size.

    width/height stay in CSS pixels; scale multiplies them into device pixels,
    so the output is (width * scale) x (height * scale).
    """
    if not pathlib.Path(CHROME).exists():
        sys.exit("Google Chrome not found at %s" % CHROME)
    subprocess.run(
        [
            CHROME,
            "--headless",
            "--disable-gpu",
            "--hide-scrollbars",
            "--force-device-scale-factor=%d" % scale,
            # The accent already lands on exact sRGB; this just stops a future
            # Chrome tagging P3 on a wide-gamut Mac and shifting the blue.
            "--force-color-profile=srgb",
            "--virtual-time-budget=8000",
            "--screenshot=%s" % png_path,
            "--window-size=%d,%d" % (width, height),
            html_path.as_uri(),
        ],
        check=True,
        capture_output=True,
    )


def render_icons(tmp):
    wrapper = tmp / "icon.html"
    svg = (PUBLIC / "favicon.svg").read_text()
    wrapper.write_text(
        "<!DOCTYPE html><meta charset='utf-8'>"
        "<style>html,body{margin:0;padding:0;background:transparent}"
        "svg{display:block;width:%dpx;height:%dpx}</style>%s" % (ICON_MASTER, ICON_MASTER, svg)
    )
    master_png = tmp / "icon.png"
    shot(wrapper, master_png, ICON_MASTER, ICON_MASTER)

    master = Image.open(master_png).convert("RGBA")
    for name, size in ICON_SIZES.items():
        out = master.resize((size, size), Image.LANCZOS)
        if name == "apple-touch-icon.png":
            # iOS squares off and drops alpha; give it an opaque paper ground.
            flat = Image.new("RGB", out.size, "#EFEFEC")
            flat.paste(out, mask=out.split()[3])
            out = flat
        out.save(PUBLIC / name)
        print("wrote public/%s (%dx%d)" % (name, size, size))


def render_og(tmp):
    out = tmp / "og.png"
    shot(ROOT / "tools" / "og.html", out, OG_WIDTH, OG_HEIGHT, scale=OG_SCALE)
    img = Image.open(out).convert("RGB")
    master = (OG_WIDTH * OG_SCALE, OG_HEIGHT * OG_SCALE)
    if img.size != master:
        img = img.crop((0, 0, min(img.width, master[0]), min(img.height, master[1])))
    # Skipped if a Chrome ever ignores the scale flag and hands back 1x: the
    # card is still correct at that point, only softer.
    if img.size != (OG_WIDTH, OG_HEIGHT):
        img = img.resize((OG_WIDTH, OG_HEIGHT), Image.LANCZOS)
    img.save(PUBLIC / "og.png", optimize=True)
    print("wrote public/og.png (%dx%d, from a %dx%d master)" % (img.size + master))


def main():
    with tempfile.TemporaryDirectory() as td:
        tmp = pathlib.Path(td)
        render_icons(tmp)
        render_og(tmp)


if __name__ == "__main__":
    main()
