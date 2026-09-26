#!/usr/bin/env python3
"""Game Master Engine -- raster brand asset pipeline.

Regenerates every raster brand asset in the repository from the HD master
badge render (``master_badge_raw.png``, produced from the official brand
sheet design).  Run from the repository root:

    python3 misc/branding/make_brand_assets.py

Requires Pillow (``python3 -m pip install --user pillow`` or a venv).

Outputs
-------
* main/app_icon.png                       512x512 translucent editor/engine icon
* main/splash.png                         800x600 boot splash with owner credits
* platform/windows/godot.ico              multi-layer Windows icon (16..512)
* platform/windows/godot_console.ico      console window icon
* misc/dist/macos_tools.app/.../GodotLG.icns    macOS editor bundle icon
* misc/dist/macos_template.app/.../icon.icns    exported-game bundle icon
* platform/android/java/lib/src/main/res/mipmap-*/icon.webp           launcher icons
* platform/android/java/lib/src/main/res/mipmap-*/icon_foreground.webp adaptive foreground
* platform/android/java/lib/src/main/res/mipmap-*/icon_monochrome.webp themed monochrome
* misc/branding/master_badge.png          1024x1024 keyed master (source of truth)
* misc/branding/ios_icon_1024.png         1024x1024 iOS-style store icon master
* misc/branding/logo_horizontal.png       badge + wordmark raster master
"""

import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BRAND = os.path.join(ROOT, "misc", "branding")
RAW = os.path.join(BRAND, "master_badge_raw.png")

GOLD = (212, 175, 55)
GOLD_LIGHT = (232, 200, 110)
GOLD_DIM = (184, 160, 106)

FONT_SERIF_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
FONT_SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def log(msg):
    print(f"[brand] {msg}")


def key_background(img, thresh=60):
    """Flood-fill the pure-black surround from the corners and turn it transparent."""
    rgb = img.convert("RGB")
    magenta = (255, 0, 255)
    for corner in ((0, 0), (rgb.width - 1, 0), (0, rgb.height - 1), (rgb.width - 1, rgb.height - 1)):
        if rgb.getpixel(corner) == magenta:
            continue
        ImageDraw.floodfill(rgb, corner, magenta, thresh=thresh)
    r, g, b = rgb.split()
    m_r = r.point(lambda v: 255 if v == 255 else 0)
    m_g = g.point(lambda v: 255 if v == 0 else 0)
    m_b = b.point(lambda v: 255 if v == 255 else 0)
    mask = ImageChops.multiply(ImageChops.multiply(m_r, m_g), m_b)
    alpha = ImageOps.invert(mask).filter(ImageFilter.GaussianBlur(0.8))
    out = img.convert("RGBA")
    out.putalpha(alpha)
    return out


def square_crop(img):
    bbox = img.getchannel("A").getbbox()
    img = img.crop(bbox)
    side = max(img.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - img.width) // 2, (side - img.height) // 2), img)
    return canvas


def resize_sharp(img, size):
    out = img.resize((size, size), Image.LANCZOS)
    if size >= 64:
        rgb = out.convert("RGB").filter(ImageFilter.UnsharpMask(radius=2, percent=110, threshold=2))
        out = rgb.convert("RGBA")
        out.putalpha(img.resize((size, size), Image.LANCZOS).getchannel("A"))
    return out


def text_centered(draw, y, text, font, fill, width):
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.text(((width - (right - left)) / 2 - left, y), text, font=font, fill=fill)
    return bottom - top


def main():
    if not os.path.exists(RAW):
        sys.exit(f"missing master render: {RAW}")
    raw = Image.open(RAW)
    log(f"master render: {raw.size}")
    badge = square_crop(key_background(raw))
    badge.save(os.path.join(BRAND, "master_badge.png"))
    log("wrote misc/branding/master_badge.png (1024 master)")

    b1024 = resize_sharp(badge, 1024)

    # --- engine / editor icon (512 translucent) -------------------------------
    app_icon = resize_sharp(badge, 512)
    app_icon.save(os.path.join(ROOT, "main", "app_icon.png"))
    log("wrote main/app_icon.png (512x512 RGBA)")

    # --- iOS-style store master ------------------------------------------------
    b1024.save(os.path.join(BRAND, "ios_icon_1024.png"))
    log("wrote misc/branding/ios_icon_1024.png")

    # --- boot splash (800x600, transparent background) -------------------------
    splash = Image.new("RGBA", (800, 600), (0, 0, 0, 0))
    badge_s = resize_sharp(badge, 300)
    splash.paste(badge_s, (250, 24), badge_s)
    d = ImageDraw.Draw(splash)
    y = 340
    y += text_centered(d, y, "GAME MASTER ENGINE", ImageFont.truetype(FONT_SERIF_BOLD, 52), GOLD, 800) + 18
    y += text_centered(d, y, "Developed & Owned by Shakil", ImageFont.truetype(FONT_SERIF_BOLD, 26), GOLD_LIGHT, 800) + 14
    text_centered(d, y, "Game Master Engine is built upon the Godot Engine core.", ImageFont.truetype(FONT_SANS, 19), GOLD_DIM, 800)
    splash.save(os.path.join(ROOT, "main", "splash.png"))
    log("wrote main/splash.png (800x600 RGBA)")

    # --- horizontal logo raster master ----------------------------------------
    logo = Image.new("RGBA", (1024, 256), (0, 0, 0, 0))
    lb = resize_sharp(badge, 240)
    logo.paste(lb, (12, 8), lb)
    dl = ImageDraw.Draw(logo)
    dl.text((280, 78), "GAME MASTER", font=ImageFont.truetype(FONT_SERIF_BOLD, 72), fill=GOLD)
    logo.save(os.path.join(BRAND, "logo_horizontal.png"))
    log("wrote misc/branding/logo_horizontal.png")

    # --- Windows .ico ------------------------------------------------------------
    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256), (512, 512)]
    layers = [resize_sharp(badge, s[0]) for s in ico_sizes]
    for ico in ("platform/windows/godot.ico", "platform/windows/godot_console.ico"):
        path = os.path.join(ROOT, ico)
        layers[0].save(path, format="ICO", sizes=ico_sizes, append_images=layers[1:])
        log(f"wrote {ico} ({len(ico_sizes)} layers, 16..512)")

    # --- macOS .icns --------------------------------------------------------------
    icns_sets = {
        "misc/dist/macos_tools.app/Contents/Resources/GodotLG.icns": [1024, 512, 256, 128, 64, 32],
        "misc/dist/macos_template.app/Contents/Resources/icon.icns": [1024, 512, 256, 128, 64, 32],
    }
    for rel, sizes in icns_sets.items():
        path = os.path.join(ROOT, rel)
        biggest = resize_sharp(badge, sizes[0])
        rest = [resize_sharp(badge, s) for s in sizes[1:]]
        biggest.save(path, format="ICNS", append_images=rest)
        log(f"wrote {rel} ({sizes})")

    # --- Android mipmaps (webp) ----------------------------------------------------
    android = os.path.join(ROOT, "platform", "android", "java", "lib", "src", "main", "res")
    icon_sizes = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
    layer_sizes = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}
    for dpi, size in icon_sizes.items():
        p = os.path.join(android, f"mipmap-{dpi}", "icon.webp")
        resize_sharp(badge, size).save(p, format="WEBP", quality=90, method=6)
        log(f"wrote mipmap-{dpi}/icon.webp ({size})")
    for dpi, lsize in layer_sizes.items():
        d = os.path.join(android, f"mipmap-{dpi}")
        # Adaptive-icon foreground: badge occupies the inner 66% safe zone.
        fg_canvas = Image.new("RGBA", (lsize, lsize), (0, 0, 0, 0))
        inner = resize_sharp(badge, int(lsize * 0.66))
        off = (lsize - inner.width) // 2
        fg_canvas.paste(inner, (off, off), inner)
        mono = Image.new("RGBA", (lsize, lsize), (0, 0, 0, 0))
        mono.paste((255, 255, 255, 255), (0, 0), fg_canvas.getchannel("A"))
        fg_canvas.save(os.path.join(d, "icon_foreground.webp"), format="WEBP", quality=90, method=6)
        mono.save(os.path.join(d, "icon_monochrome.webp"), format="WEBP", quality=90, method=6)
    log("wrote adaptive icon_foreground.webp + icon_monochrome.webp (all densities)")

    log("done.")


if __name__ == "__main__":
    main()
