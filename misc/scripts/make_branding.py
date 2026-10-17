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

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SOURCE = os.path.join(REPO, "misc", "logo", "bfeee0f4-dd7a-48b1-be04-ebff9bc1417a.jpeg")

# --------------------------------------------------------------------------- #
# Brand geometry, measured from the banner artwork itself.
# --------------------------------------------------------------------------- #

# Window of the banner that contains the emblem (gold gear + winged V + crystal).
# Measured on a 20px grid: the gear's outer teeth span x 345..657, y 45..357, so
# this square crop frames the mark tightly without cutting its glow.
EMBLEM_VIEW = (341, 41, 661, 361)
# The banner without the platform row at the bottom, for wide logo slots.
BANNER_VIEW = (0, 0, 1024, 472)
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
    if colors and img.width * img.height > 4096:
        if img.getchannel("A").getextrema()[0] == 255:
            # Opaque: a median-cut palette keeps the smooth glows intact.
            img = img.convert("RGB").quantize(colors=colors, method=Image.MEDIANCUT, dither=Image.NONE)
        else:
            # Transparent artwork (embedded marks): octree handles the alpha
            # channel, and the icons are only ever displayed small.
            img = img.quantize(colors=colors, method=Image.FASTOCTREE, dither=Image.FLOYDSTEINBERG)
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


def write_svg(rel_path, text):
    """Overwrite an SVG, dropping any mark this script embedded in a past run.

    Without this the document / console icons would accumulate a new embedded
    image every time the generator runs."""
    path = os.path.join(REPO, rel_path)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            previous = f.read()
        if previous.lstrip().startswith("<svg"):
            text = EMBEDDED_IMAGE_RE.sub("", text)
    write_text(rel_path, text)


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
    unsharp pass keeps the gold edges crisp instead of soft. Tiny sizes (taskbar,
    favicon) also get a contrast boost and a tighter crop so the mark still reads
    at 16-32 px."""
    if isinstance(size, int):
        size = (size, size)
    scale = size[0] / img.width
    src = img
    small = max(size) <= 64 and img.width > max(size)
    if small:
        w, h = img.size
        margin = int(min(w, h) * 0.07)
        src = img.crop((margin, margin, w - margin, h - margin))
        src = ImageEnhance.Brightness(src).enhance(1.10)
        src = ImageEnhance.Contrast(src).enhance(1.15)
    out = src.resize(size, Image.LANCZOS)
    if scale > 1.3:
        out = out.filter(ImageFilter.UnsharpMask(radius=2.0, percent=55, threshold=3))
    if small:
        out = out.filter(ImageFilter.UnsharpMask(radius=1.2, percent=130, threshold=2))
    return out


def emblem_art(banner):
    """Square artwork of the emblem only, on the banner's own background."""
    return banner.crop(EMBLEM_VIEW)


def wide_art(banner):
    """The wordmark banner: emblem + title + credit line, no platform row."""
    return banner.crop(BANNER_VIEW)


def emblem_mark(art, radius_ratio=0.235):
    """The emblem clipped to a rounded square (the shape used for app icons)."""
    out = art.convert("RGBA").copy()
    out.putalpha(ImageChops.multiply(out.getchannel("A"), rounded_mask(out.width, radius_ratio)))
    return out


def emblem_monochrome(art, size, color=(255, 255, 255)):
    """Single-colour silhouette of the mark, for monochrome/themed icon slots.

    Android tints its monochrome layer by alpha, so only the silhouette matters
    there; the editor only ever shows this small, so the mark's own luminance
    thresholded at a level that skips the circuit-board background reads best."""
    lum = art.convert("L")
    # The banner is a dark photographic render, so the mark and the circuitry
    # behind it overlap in luminance. Threshold well above the background and
    # clip to a rounded square: at 16 px this reads as the product mark rather
    # than as noise, and Android's tint only uses the alpha anyway.
    cut, scale = 120, 3.2
    alpha = lum.point(lambda v: max(0, min(255, int((v - cut) * scale))))
    alpha = ImageChops.multiply(alpha, rounded_mask(art.width, 0.30))
    out = Image.new("RGBA", art.size, color + (0,))
    out.putalpha(alpha)
    out = resize_brand(out, size)
    # Downscaling a thresholded photographic mask washes the alpha out; restore
    # full opacity so the glyph is solid white at 16 px.
    solid = out.getchannel("A").point(lambda v: min(255, int(v * 2.6)))
    out.putalpha(solid)
    return out


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


def splash(banner, size, background=None):
    """Boot splash: the wide wordmark centred on the canvas.

    The canvas is transparent by default so the boot background colour shows
    through and the artwork blends into the window; pass ``background`` for the
    platforms that expect an opaque image."""
    artwork = banner.crop(BANNER_VIEW)
    if background is None:
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    else:
        canvas = Image.new("RGB", size, background).convert("RGBA")
    artwork.thumbnail((int(size[0] * 0.96), int(size[1] * 0.96)), Image.LANCZOS)
    canvas.alpha_composite(artwork.convert("RGBA"), ((size[0] - artwork.width) // 2, (size[1] - artwork.height) // 2))
    return canvas


# --------------------------------------------------------------------------- #
# Container formats
# --------------------------------------------------------------------------- #


def write_ico(rel_path, art, sizes=(16, 24, 32, 48, 64, 128, 256), make=None):
    """Write a multi-resolution .ico from individually rendered frames."""
    path = rel_path if os.path.isabs(rel_path) else os.path.join(REPO, rel_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    frames = [(make(s) if make else art.resize((s, s), Image.LANCZOS)).convert("RGBA") for s in sizes]
    frames[-1].save(path, format="ICO", sizes=[(s, s) for s in sizes], append_images=frames[:-1])
    log(f"{rel_path} (ico: {', '.join(str(s) for s in sizes)})")


def write_icns(rel_path, art):
    """Write an .icns with PNG-encoded members (macOS 10.7+)."""
    write_bytes(rel_path, _icns_bytes(art))


# --------------------------------------------------------------------------- #
# Generation steps
# --------------------------------------------------------------------------- #


def gen_logo_set(banner, art):
    wide = banner.crop(BANNER_VIEW)
    save(wide.copy(), "misc/logo/logo.png")

    pad = 24
    plate = Image.new("RGBA", (wide.width + pad * 2, wide.height + pad * 2), (11, 13, 18, 255))
    plate.alpha_composite(wide.convert("RGBA"), (pad, pad))
    ImageDraw.Draw(plate).rounded_rectangle(
        (0, 0, plate.width - 1, plate.height - 1), radius=44, outline=(58, 48, 26, 255), width=4
    )
    save(plate, "misc/logo/logo_outlined.png")

    save(emblem_mark(art), "misc/logo/icon.png")
    save(art.copy(), "misc/logo/icon_outlined.png")

    # SVG counterparts (embed the artwork so it never has to be redrawn).
    write_text(
        "misc/logo/logo.svg",
        svg(
            1024,
            472,
            image_element(wide.resize((1024, 472), Image.LANCZOS), 0, 0, 1024, 472),
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
        svg(128, 128, image_element(emblem_mark(art).resize((256, 256), Image.LANCZOS), 0, 0, 128, 128)),
    )
    write_text(
        "misc/logo/icon_outlined.svg",
        svg(256, 256, image_element(art.resize((512, 512), Image.LANCZOS), 0, 0, 256, 256)),
    )


def gen_steam_icons(art, out_dir):
    """Steam / Linux icon bundle (invoked by misc/scripts/make_icons.sh)."""
    os.makedirs(out_dir, exist_ok=True)
    pngs = []
    icon = emblem_mark(art)
    for size in ICON_SIZES:
        rel = os.path.join(out_dir, f"icon{size}.png")
        resize_brand(icon, size).save(rel)
        pngs.append(rel)
    log(f"{out_dir}/icon{{16..1024}}.png")

    # 16px TGA for the Steam library.
    resize_brand(icon, 16).save(os.path.join(out_dir, "icon16.tga"))
    log(f"{out_dir}/icon16.tga")

    with zipfile.ZipFile(os.path.join(out_dir, "godot-icons.zip"), "w", zipfile.ZIP_DEFLATED) as z:
        for rel in pngs:
            z.write(rel, os.path.basename(rel))
    log(f"{out_dir}/godot-icons.zip")

    write_ico(os.path.join(out_dir, "godot-icon.ico"), icon)
    write_icns(os.path.join(out_dir, "godot-icon.icns"), icon)


def gen_engine_icons(art):
    save(resize_brand(emblem_mark(art), 128), "main/app_icon.png")


def gen_splashes(banner):
    # Transparent artwork: the boot background colour (main_builders.py) is the
    # artwork's own near-black, so the splash blends into the window edge-to-edge.
    save(splash(banner, (800, 600)), "main/splash.png")
    save(splash(banner, (800, 600)), "main/splash_editor.png")

    splash_dir = "misc/dist/apple_embedded_xcode/godot_apple_embedded/Images.xcassets/SplashImage.imageset"
    for name in ("splash@2x.png", "splash@3x.png"):
        save(splash(banner, (800, 600)), os.path.join(splash_dir, name))

    for rel in (
        "platform/android/java/editor/src/horizonos/assets/vr_splash.png",
        "platform/android/java/editor/src/picoos/assets/vr_splash.png",
    ):
        save(splash(banner, (800, 600), (10, 11, 15)), rel)


def gen_android(art):
    base = "platform/android/java/lib/src/main/res"

    # Legacy launcher icon (also the editor app icon on older Android versions).
    for dpi, size in ANDROID_LIB_SIZES.items():
        save(brand_plate(size, 0.235, 0.90, emblem_mark(art)), f"{base}/mipmap-{dpi}/icon.webp")

    # Adaptive icon layers: the mark must stay inside the launcher's safe zone.
    for dpi, size in ANDROID_ADAPTIVE_SIZES.items():
        fg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        inner = int(size * 0.62)
        fg.alpha_composite(resize_brand(emblem_mark(art), inner), ((size - inner) // 2, (size - inner) // 2))
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


def console_icon(art, size):
    """Brand mark plus a small terminal badge (console builds)."""
    icon = emblem_mark(art).resize((size, size), Image.LANCZOS).convert("RGBA")
    badge = int(size * 0.42)
    pad = int(size * 0.04)
    tile = Image.new("RGBA", (badge, badge), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)
    draw.rounded_rectangle(
        (0, 0, badge - 1, badge - 1),
        radius=int(badge * 0.16),
        fill=(33, 37, 43, 255),
        outline=(255, 255, 255, 255),
        width=max(1, size // 96),
    )
    w = max(1, int(badge * 0.10))
    draw.line(
        [(badge * 0.18, badge * 0.32), (badge * 0.36, badge * 0.52), (badge * 0.18, badge * 0.72)],
        fill=(255, 255, 255, 255),
        width=w,
        joint="curve",
    )
    draw.line([(badge * 0.48, badge * 0.72), (badge * 0.78, badge * 0.72)], fill=(255, 255, 255, 255), width=w)
    icon.alpha_composite(tile, (size - badge - pad, size - badge - pad))
    return icon


def gen_windows(art):
    mark = emblem_mark(art)
    write_ico("platform/windows/godot.ico", mark, make=lambda s: resize_brand(mark, s))
    write_ico("platform/windows/godot_console.ico", mark, make=lambda s: console_icon(art, s))

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
        svg(1024, 1024, image_element(plate.resize((512, 512), Image.LANCZOS), 0, 0, 1024, 1024)),
    )


def gen_macos_document_icon(art):
    """Replace the mascot inside the macOS "Project" document icon.

    The other document icons (GDScript, Resource, Scene, Shader) use neutral
    glyphs and are left untouched. The pristine icon is kept under
    misc/dist/macos/document_icons_src so this stays repeatable."""
    src = os.path.join(REPO, "misc/dist/macos/document_icons_src/Project.icns")
    if not os.path.exists(src):
        log("skipped Project.icns (no pristine source)")
        return
    template = Image.open(src)
    frame = max(template.info.get("sizes", [(template.width, template.height, 1)]), key=lambda s: s[0] * s[1])
    template.size = (frame[0], frame[1])
    template.load()
    icon = template.convert("RGBA")

    px = icon.load()
    xs, ys = [], []
    for y in range(0, int(icon.height * 0.77)):
        for x in range(icon.width):
            r, g, b, a = px[x, y]
            if b - r > 40 and b > 120 and a > 200:
                xs.append(x)
                ys.append(y)
    if not xs:
        log("skipped Project.icns (mascot not found)")
        return
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    pad = 4
    ImageDraw.Draw(icon).rectangle((x0 - pad, y0 - pad, x1 + pad, y1 + pad), fill=(255, 255, 255, 255))
    inset = int(min(x1 - x0, y1 - y0) * 0.02)
    box = (x0 + inset, y0 + inset, x1 - inset, y1 - inset)
    mark = emblem_mark(art, 0.18).resize((box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
    icon.paste(mark, (box[0], box[1]), mark)

    write_bytes("misc/dist/macos_tools.app/Contents/Resources/Project.icns", _icns_bytes(icon))


def _icns_bytes(icon):
    members = [
        (b"icp4", 16), (b"icp5", 32), (b"icp6", 64), (b"ic07", 128),
        (b"ic08", 256), (b"ic09", 512), (b"ic10", 1024),
        (b"ic11", 32), (b"ic12", 64), (b"ic13", 256), (b"ic14", 512),
    ]
    chunks = b""
    for tag, size in members:
        data = png_bytes(resize_brand(icon, size))
        chunks += tag + struct.pack(">I", len(data) + 8) + data
    return b"icns" + struct.pack(">I", len(chunks) + 8) + chunks


def gen_macos(art):
    write_icns("misc/dist/macos_template.app/Contents/Resources/icon.icns", emblem_mark(art))
    write_icns("misc/dist/macos_tools.app/Contents/Resources/GodotLG.icns", emblem_mark(art))
    gen_macos_document_icon(emblem_mark(art))

    # The compiled Assets.car shipped with the app template still contains the
    # Godot artwork, and actool only runs on macOS. Drop it and let macOS fall
    # back to CFBundleIconFile (the .icns above), which is branded.
    stale_car = os.path.join(REPO, "misc/dist/macos_tools.app/Contents/Resources/Assets.car")
    if os.path.exists(stale_car):
        os.remove(stale_car)
        log("removed stale misc/dist/macos_tools.app/Contents/Resources/Assets.car")
    for rel in (
        "misc/dist/macos_tools.app/Contents/Info.plist",
        "misc/dist/macos_tools.app/Contents/Info_arm64.plist",
        "misc/dist/macos_tools.app/Contents/Info_x86_64.plist",
        "misc/dist/macos/editor_info_plist.template",
    ):
        path = os.path.join(REPO, rel)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            plist = f.read()
        stripped = re.sub(r"\t<key>CFBundleIconName</key>\n\t<string>[^<]*</string>\n", "", plist)
        if stripped != plist:
            write_text(rel, stripped)

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


# Where the Godot mascot sits in the project document icons, and how the brand
# mark should fill that space (measured by diffing against the mascot-free icon).
PROJECT_DOC_MASCOT = {
    "": ((283, 326), (458, 432), 384),
    "_small": ((9, 11), (14, 14), 96),
    "_extra_small": ((3, 5), (10, 9), 64),
}

EMBEDDED_IMAGE_RE = re.compile(r'<image\b[^>]*data:image/png;base64[^>]*/>')


def _pristine_document_icon(rel):
    """The document icon as committed in git, so re-runs never stack edits."""
    try:
        import subprocess

        out = subprocess.run(
            ["git", "-C", REPO, "show", f"HEAD~1:{rel}"],
            capture_output=True,
            check=False,
        )
        if out.returncode == 0:
            return out.stdout.decode("utf-8")
    except Exception:  # pragma: no cover - git is optional
        pass
    return None


def gen_document_icons(banner, art):
    """File-type icons keep their original shapes (each type stays recognisable),
    but the Godot blue accent is repainted with the brand gold and the mascot in
    the project icons is replaced by the product mark."""
    changed = 0
    for name in DOC_TYPES:
        for suffix in ("", "_small", "_extra_small"):
            rel = f"misc/dist/document_icons/{name}{suffix}.svg"
            path = os.path.join(REPO, rel)
            if not os.path.exists(path):
                continue
            with open(path, encoding="utf-8") as f:
                src = f.read()
            # Idempotent: rebuild from the pristine SVG (first run only uses the
            # working copy as its own source, which is already pristine).
            pristine = _pristine_document_icon(rel)
            if pristine is not None:
                src = pristine
            if name == "project" and suffix in PROJECT_DOC_MASCOT:
                (x, y), (w, h), render = PROJECT_DOC_MASCOT[suffix]
                # The mascot is the trailing <g stroke-width=".32"> group.
                idx = src.rfind('<g stroke-width=".32">')
                if idx != -1:
                    end = src.find("</g>", idx) + 4
                    src = src[:idx] + src[end:]
                mark = emblem_mark(art, 0.18)
                mark = resize_brand(mark, render)
                src = src.replace(
                    "</svg>", image_element(mark, x, y, w, h) + "</svg>"
                )
            src = re.sub("#478cbf", GOLD_HEX, src, flags=re.IGNORECASE)
            write_text(rel, src)
            changed += 1
    if not changed:
        log("document icons already up to date")


def gen_editor_icons(wide, art):
    """Editor theme icons that carry the product mark."""
    # Help menu entry / About window wordmark.
    write_text(
        "editor/icons/Godot.svg", svg(187, 87, image_element(wide.resize((374, 172), Image.LANCZOS), 0, 0, 187, 86))
    )
    write_text(
        "editor/icons/Logo.svg", svg(280, 129, image_element(wide.resize((560, 258), Image.LANCZOS), 0, 0, 280, 129))
    )
    # Project manager title-bar mark.
    write_text(
        "editor/icons/TitleBarLogo.svg",
        svg(100, 24, image_element(emblem_mark(art).resize((96, 96), Image.LANCZOS), 38, 0, 24, 24)),
    )
    # Window icon and project / file thumbnails.
    write_text("editor/icons/GodotMonochrome.svg", svg(16, 16, image_element(emblem_monochrome(art, 64), 0, 0, 16, 16)))
    write_text(
        "editor/icons/GodotFile.svg",
        svg(64, 64, image_element(emblem_mark(art).resize((128, 128), Image.LANCZOS), 0, 0, 64, 64)),
    )
    write_text(
        "editor/icons/DefaultProjectIcon.svg",
        svg(128, 128, image_element(emblem_mark(art).resize((256, 256), Image.LANCZOS), 0, 0, 128, 128)),
    )


def gen_web(wide):
    write_text(
        "misc/dist/html/logo.svg",
        svg(1024, 472, image_element(wide.resize((512, 236), Image.LANCZOS), 0, 0, 1024, 472)),
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
    gen_document_icons(banner, art)
    gen_editor_icons(wide_art(banner).convert("RGB"), art)
    gen_web(wide_art(banner).convert("RGB"))

    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
