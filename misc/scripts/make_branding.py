#!/usr/bin/env python3
"""Generate every branded ("Legend of the Game Engine") asset in this repository.

Single source of truth: the banner image
``misc/logo/bfeee0f4-dd7a-48b1-be04-ebff9bc1417a.jpeg``

Nothing here is hand-drawn: every icon, splash, document icon, installer and
packaging asset is derived from that one picture, so replacing the banner and
re-running this script re-brands the whole engine.

Usage:
    python3 misc/scripts/make_branding.py

Requires Pillow (``pip install Pillow``).
"""

import base64
import io
import json
import os
import re
import struct
import sys
import zipfile

from PIL import Image, ImageChops, ImageDraw, ImageFilter

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SOURCE = os.path.join(REPO, "misc", "logo", "bfeee0f4-dd7a-48b1-be04-ebff9bc1417a.jpeg")

# --------------------------------------------------------------------------- #
# Brand geometry, measured from the banner artwork itself.
# --------------------------------------------------------------------------- #

# Window of the banner that contains the emblem (gold gear + winged V + crystal).
# The banner's wordmark starts at y = 396, so the crop stops just above it and the
# mark itself spans x 400..641, y 81..373.
EMBLEM_VIEW = (339, 45, 691, 397)
# Background of the banner artwork (sampled from its corners).
BG = (0, 0, 4)
# Editor theme background colour (see main_builders.py: boot_splash_editor_bg_color).
EDITOR_BG = (32, 37, 49)
# Neutral boot-splash background colour (see main_builders.py: boot_splash_bg_color).
BOOT_BG = (36, 36, 36)
# Brand accent, sampled from the gold in the artwork.
GOLD = (227, 184, 86)
GOLD_HEX = "#e3b856"

ICON_SIZES = [16, 24, 32, 48, 64, 128, 256, 512, 1024]
ANDROID_LIB_SIZES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
ANDROID_ADAPTIVE_SIZES = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}
DOC_TYPES = ["gdscript", "project", "resource", "scene", "shader"]


def log(msg):
    print(f"  {msg}")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def png_bytes(img, colors=256):
    """Palette-compressed PNG. The artwork is dark with smooth glows, so a 256
    colour palette stays visually identical while keeping the assets small.
    Opaque artwork keeps its palette; artwork with transparency stays RGBA."""
    img = img.convert("RGBA")
    if colors and img.width * img.height > 4096 and img.getchannel("A").getextrema()[0] == 255:
        img = img.convert("RGB").quantize(colors=colors, method=Image.MEDIANCUT, dither=Image.NONE)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def image_element(img, x, y, w, h):
    """An <image> node carrying the artwork as a base64 PNG data URI.

    Godot renders SVGs through ThorVG with embedded-image support enabled
    (modules/svg/SCsub defines THORVG_FILE_IO_SUPPORT), so this is the supported
    path for artwork that has no vector source."""
    b64 = base64.b64encode(png_bytes(img)).decode("ascii")
    uri = f"data:image/png;base64,{b64}"
    return f'<image x="{x:g}" y="{y:g}" width="{w:g}" height="{h:g}" xlink:href="{uri}" href="{uri}"/>'


def svg(width, height, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width:g}" height="{height:g}">{body}</svg>'
    )


def save(img, rel_path, fmt=None):
    path = os.path.join(REPO, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path, format=fmt)
    log(f"{rel_path} ({img.width}x{img.height})")


def write_text(rel_path, text):
    path = os.path.join(REPO, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    log(f"{rel_path} ({len(text) // 1024} KiB)")


def write_bytes(rel_path, data):
    path = os.path.join(REPO, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    log(f"{rel_path} ({len(data) // 1024} KiB)")


def rounded_mask(size, radius_ratio, supersample=4):
    hi = size * supersample
    mask = Image.new("L", (hi, hi), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, hi - 1, hi - 1), radius=int(hi * radius_ratio), fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def circle_mask(size, supersample=4):
    hi = size * supersample
    mask = Image.new("L", (hi, hi), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, hi - 1, hi - 1), fill=255)
    return mask.resize((size, size), Image.LANCZOS)


# --------------------------------------------------------------------------- #
# Brand artwork derived from the banner
# --------------------------------------------------------------------------- #


def resize_brand(img, size):
    """Resize brand artwork, sharpening when the source has to be enlarged.

    The source banner is 1024x559, so 512/1024px icon members are upscaled; a mild
    unsharp pass keeps the gold edges crisp instead of soft."""
    if isinstance(size, int):
        size = (size, size)
    scale = size[0] / img.width
    out = img.resize(size, Image.LANCZOS)
    if scale > 1.3:
        out = out.filter(ImageFilter.UnsharpMask(radius=2.0, percent=55, threshold=3))
    return out


def emblem_art(banner):
    """Square artwork of the emblem only, on the banner's own background."""
    return banner.crop(EMBLEM_VIEW)


def emblem_disc(art, inset=0.94):
    """The emblem inside a transparent circle (round icon variant)."""
    side = art.width
    inner = int(side * inset)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(art.resize((inner, inner), Image.LANCZOS).convert("RGBA"), ((side - inner) // 2, (side - inner) // 2))
    canvas.putalpha(ImageChops.multiply(canvas.getchannel("A"), circle_mask(side)))
    return canvas


def emblem_monochrome(art, size, color=(255, 255, 255)):
    """Monochrome variant of the mark.

    The source artwork is a photographic render, so its mark and the circuitry
    background overlap in both luminance and hue - a thresholded silhouette comes
    out as noise. The monochrome variants therefore carry the mark on an opaque
    disc: Android tints the layer by its alpha (yielding a clean themed icon) and
    the editor's "Monochrome" file icon stays recognisably the product mark."""
    disc = emblem_disc(art)
    disc = resize_brand(disc, size)
    if color == (255, 255, 255):
        return disc
    tinted = Image.new("RGBA", disc.size, color + (0,))
    tinted.putalpha(disc.getchannel("A"))
    return tinted


def brand_plate(size, radius_ratio=0.235, scale=0.80, art=None):
    """Rounded-square brand plate with the emblem on it (launcher-style icon)."""
    plate = Image.new("RGBA", (size, size), BG + (255,))
    if art is not None:
        inner = int(size * scale)
        plate.alpha_composite(
            art.resize((inner, inner), Image.LANCZOS).convert("RGBA"), ((size - inner) // 2, (size - inner) // 2)
        )
    plate.putalpha(ImageChops.multiply(plate.getchannel("A"), rounded_mask(size, radius_ratio)))
    return plate


def brand_background(size):
    """Adaptive-icon background: dark plate with a soft gold glow behind the mark."""
    base = Image.new("RGB", (size, size), BG)
    glow = Image.new("L", (size, size), 0)
    ImageDraw.Draw(glow).ellipse((int(size * 0.16), int(size * 0.16), int(size * 0.84), int(size * 0.84)), fill=96)
    glow = glow.filter(ImageFilter.GaussianBlur(size * 0.10))
    return Image.composite(Image.new("RGB", (size, size), (58, 46, 20)), base, glow)


def document_icon_svg(art, size, accent_hex):
    """Deprecated: document file-type icons are recoloured, not redrawn."""


def splash(banner, size, background):
    canvas = Image.new("RGB", size, background)
    logo = banner.copy()
    logo.thumbnail((int(size[0] * 0.96), int(size[1] * 0.96)), Image.LANCZOS)
    canvas.paste(logo, ((size[0] - logo.width) // 2, (size[1] - logo.height) // 2))
    return canvas


# --------------------------------------------------------------------------- #
# Container formats
# --------------------------------------------------------------------------- #


def write_ico(rel_path, art, sizes=(16, 24, 32, 48, 64, 128, 256)):
    path = rel_path if os.path.isabs(rel_path) else os.path.join(REPO, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    art.resize((256, 256), Image.LANCZOS).convert("RGBA").save(path, format="ICO", sizes=[(s, s) for s in sizes])
    log(f"{rel_path} (ico: {', '.join(str(s) for s in sizes)})")


def write_icns(rel_path, art):
    """Write an .icns with PNG-encoded members (macOS 10.7+)."""

    members = [
        (b"icp4", 16),
        (b"icp5", 32),
        (b"icp6", 64),
        (b"ic07", 128),
        (b"ic08", 256),
        (b"ic09", 512),
        (b"ic10", 1024),
        (b"ic11", 32),
        (b"ic12", 64),
        (b"ic13", 256),
        (b"ic14", 512),
    ]
    chunks = b""
    for tag, size in members:
        data = png_bytes(art.resize((size, size), Image.LANCZOS))
        chunks += tag + struct.pack(">I", len(data) + 8) + data
    write_bytes(rel_path, b"icns" + struct.pack(">I", len(chunks) + 8) + chunks)


# --------------------------------------------------------------------------- #
# Generation steps
# --------------------------------------------------------------------------- #


def gen_logo_set(banner, art):
    save(banner.copy(), "misc/logo/logo.png")

    pad = 24
    plate = Image.new("RGBA", (banner.width + pad * 2, banner.height + pad * 2), (11, 13, 18, 255))
    plate.alpha_composite(banner.convert("RGBA"), (pad, pad))
    ImageDraw.Draw(plate).rounded_rectangle(
        (0, 0, plate.width - 1, plate.height - 1), radius=44, outline=(58, 48, 26, 255), width=4
    )
    save(plate, "misc/logo/logo_outlined.png")

    save(emblem_disc(art), "misc/logo/icon.png")
    save(art.copy(), "misc/logo/icon_outlined.png")

    # SVG counterparts (embed the artwork so it never has to be redrawn).
    write_text(
        "misc/logo/logo.svg",
        svg(
            banner.width,
            banner.height,
            image_element(banner.resize((1024, 559), Image.LANCZOS), 0, 0, banner.width, banner.height),
        ),
    )
    write_text(
        "misc/logo/logo_outlined.svg",
        svg(
            plate.width,
            plate.height,
            image_element(plate.resize((1072, 607), Image.LANCZOS), 0, 0, plate.width, plate.height),
        ),
    )
    write_text(
        "misc/logo/icon.svg",
        svg(128, 128, image_element(emblem_disc(art).resize((256, 256), Image.LANCZOS), 0, 0, 128, 128)),
    )
    write_text(
        "misc/logo/icon_outlined.svg",
        svg(256, 256, image_element(art.resize((512, 512), Image.LANCZOS), 0, 0, 256, 256)),
    )


def gen_steam_icons(art, out_dir):
    """Steam / Linux icon bundle (invoked by misc/scripts/make_icons.sh)."""
    os.makedirs(out_dir, exist_ok=True)
    pngs = []
    for size in ICON_SIZES:
        rel = os.path.join(out_dir, f"icon{size}.png")
        art.resize((size, size), Image.LANCZOS).save(rel)
        pngs.append(rel)
    log(f"{out_dir}/icon{{16..1024}}.png")

    # 16px TGA for the Steam library.
    art.resize((16, 16), Image.LANCZOS).save(os.path.join(out_dir, "icon16.tga"))
    log(f"{out_dir}/icon16.tga")

    with zipfile.ZipFile(os.path.join(out_dir, "godot-icons.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for rel in pngs:
            z.write(rel, os.path.basename(rel))
    log(f"{out_dir}/godot-icons.zip")

    write_ico(os.path.join(out_dir, "godot-icon.ico"), art)
    write_icns(os.path.join(out_dir, "godot-icon.icns"), art)


def gen_engine_icons(art):
    save(resize_brand(emblem_disc(art), 128), "main/app_icon.png")


def gen_splashes(banner):
    save(splash(banner, (800, 600), BOOT_BG), "main/splash.png")
    save(splash(banner, (800, 600), EDITOR_BG), "main/splash_editor.png")

    splash_dir = "misc/dist/apple_embedded_xcode/godot_apple_embedded/Images.xcassets/SplashImage.imageset"
    for name in ("splash@2x.png", "splash@3x.png"):
        save(splash(banner, (800, 600), BOOT_BG), os.path.join(splash_dir, name))

    for rel in (
        "platform/android/java/editor/src/horizonos/assets/vr_splash.png",
        "platform/android/java/editor/src/picoos/assets/vr_splash.png",
    ):
        save(splash(banner, (800, 600), (10, 11, 15)), rel)


def gen_android(art):
    base = "platform/android/java/lib/src/main/res"

    # Legacy launcher icon (also the editor app icon on older Android versions).
    for dpi, size in ANDROID_LIB_SIZES.items():
        save(brand_plate(size, 0.235, 0.90, emblem_disc(art)), f"{base}/mipmap-{dpi}/icon.webp")

    # Adaptive icon layers: the mark must stay inside the launcher's safe zone.
    for dpi, size in ANDROID_ADAPTIVE_SIZES.items():
        fg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        inner = int(size * 0.62)
        fg.alpha_composite(resize_brand(emblem_disc(art), inner), ((size - inner) // 2, (size - inner) // 2))
        save(fg, f"{base}/mipmap-{dpi}/icon_foreground.webp")
        save(brand_background(size), f"{base}/mipmap-{dpi}/icon_background.webp", fmt="WEBP")
        save(emblem_monochrome(art, size), f"{base}/mipmap-{dpi}/icon_monochrome.webp")

    # Default splash used by exported Android projects.
    save(art.resize((432, 432), Image.LANCZOS), f"{base}/drawable/splash_icon.webp")
    save(art.resize((100, 100), Image.LANCZOS), f"{base}/drawable/splash_branding_image.webp")

    # Icon written into instrumented Android builds.
    write_text(
        "platform/android/java/app/src/instrumented/assets/icon.svg",
        svg(128, 128, image_element(art.resize((256, 256), Image.LANCZOS), 0, 0, 128, 128)),
    )


def gen_windows(art):
    write_ico("platform/windows/godot.ico", art)
    write_ico("platform/windows/godot_console.ico", art)

    # Console variant: brand mark on a terminal plate with a ">" prompt.
    size = 1024
    plate = Image.new("RGBA", (size, size), (12, 14, 20, 255))
    plate.alpha_composite(art.resize((768, 768), Image.LANCZOS).convert("RGBA"), (128, 0))
    draw = ImageDraw.Draw(plate)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=int(size * 0.18), outline=(70, 58, 30, 255), width=10)
    draw.line(
        [
            (int(size * 0.16), int(size * 0.80)),
            (int(size * 0.26), int(size * 0.87)),
            (int(size * 0.16), int(size * 0.94)),
        ],
        fill=GOLD + (255,),
        width=int(size * 0.035),
        joint="curve",
    )
    draw.rectangle((int(size * 0.30), int(size * 0.905), int(size * 0.46), int(size * 0.945)), fill=GOLD + (255,))
    write_text(
        "misc/dist/windows/icon_console.svg",
        svg(1024, 1024, image_element(plate.resize((768, 768), Image.LANCZOS), 0, 0, 1024, 1024)),
    )


def gen_macos(art):
    write_icns("misc/dist/macos_template.app/Contents/Resources/icon.icns", art)
    write_icns("misc/dist/macos_tools.app/Contents/Resources/GodotLG.icns", art)

    # Liquid Glass icon source (compiled to Assets.car by Xcode's actool on macOS).
    layers = image_element(art.resize((512, 512), Image.LANCZOS), 0, 0, 1024, 1024)
    for i in range(3):
        write_text(f"misc/dist/macos/GodotLG.icon/Assets/layer_{i}.svg", svg(1024, 1024, layers))

    icon_json = os.path.join(REPO, "misc/dist/macos/GodotLG.icon/icon.json")
    with open(icon_json, encoding="utf-8") as f:
        data = json.load(f)
    for group in data.get("groups", []):
        for layer in group.get("layers", []):
            layer.pop("fill", None)
    write_text("misc/dist/macos/GodotLG.icon/icon.json", json.dumps(data, indent=2) + "\n")


def gen_document_icons(art):
    """File-type icons keep their original artwork (each type stays recognisable),
    but the old Godot blue accent is repainted with the brand gold."""
    changed = 0
    for name in DOC_TYPES:
        for suffix in ("", "_small", "_extra_small"):
            rel = f"misc/dist/document_icons/{name}{suffix}.svg"
            path = os.path.join(REPO, rel)
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                src = f.read()
            if "#478cbf" not in src.lower():
                continue
            src = re.sub("#478cbf", GOLD_HEX, src, flags=re.IGNORECASE)
            write_text(rel, src)
            changed += 1
    if not changed:
        log("document icons already repainted")


def gen_editor_icons(banner, art):
    """Editor theme icons that carry the product mark."""
    # Help menu entry / About window wordmark.
    write_text(
        "editor/icons/Godot.svg", svg(187, 102, image_element(banner.resize((374, 204), Image.LANCZOS), 0, 0, 187, 102))
    )
    write_text(
        "editor/icons/Logo.svg", svg(280, 153, image_element(banner.resize((560, 306), Image.LANCZOS), 0, 0, 280, 153))
    )
    # Project manager title-bar mark.
    write_text(
        "editor/icons/TitleBarLogo.svg",
        svg(100, 24, image_element(emblem_disc(art).resize((96, 96), Image.LANCZOS), 38, 0, 24, 24)),
    )
    # Window icon and project / file thumbnails.
    write_text("editor/icons/GodotMonochrome.svg", svg(16, 16, image_element(emblem_monochrome(art, 64), 0, 0, 16, 16)))
    write_text(
        "editor/icons/GodotFile.svg",
        svg(64, 64, image_element(emblem_disc(art).resize((128, 128), Image.LANCZOS), 0, 0, 64, 64)),
    )
    write_text(
        "editor/icons/DefaultProjectIcon.svg",
        svg(128, 128, image_element(emblem_disc(art).resize((256, 256), Image.LANCZOS), 0, 0, 128, 128)),
    )


def gen_web(banner):
    write_text(
        "misc/dist/html/logo.svg",
        svg(1024, 559, image_element(banner.resize((512, 280), Image.LANCZOS), 0, 0, 1024, 559)),
    )


def main(argv):
    steam_dir = None
    if "--steam-icons" in argv:
        steam_dir = argv[argv.index("--steam-icons") + 1]

    if not os.path.exists(SOURCE):
        sys.exit(f"source banner not found: {SOURCE}")

    banner = Image.open(SOURCE).convert("RGB")
    log(f"source misc/logo/{os.path.basename(SOURCE)} {banner.width}x{banner.height}")

    art = emblem_art(banner).convert("RGBA")

    if steam_dir:
        gen_steam_icons(art, os.path.abspath(steam_dir))
        return 0

    gen_logo_set(banner, art)
    gen_engine_icons(art)
    gen_splashes(banner)
    gen_android(art)
    gen_windows(art)
    gen_macos(art)
    gen_document_icons(art)
    gen_editor_icons(banner, art)
    gen_web(banner)

    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
