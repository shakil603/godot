#!/usr/bin/env python3

"""Generates every "Game Master" brand asset from one source artwork.

The engine only embeds three bitmaps (`main/app_icon.png`, `main/splash.png`,
`main/splash_editor.png`), but a brand is used in many more places: Windows `.ico`,
macOS `.icns`, Linux hicolor, Android adaptive launcher icons, iOS per-device icons,
Web/PWA icons and the HTML shell logo. Regenerating all of them from one file is how
broken assets (too small, no alpha, JPEG bytes inside a `.png`) get introduced, so
this script keeps a single source of truth.

Usage:
    ./misc/scripts/game_master_assets.py           # regenerate every asset
    ./misc/scripts/game_master_assets.py --check   # validate the tree (used by CI)
    ./misc/scripts/game_master_assets.py --list    # print the generated paths
    ./misc/scripts/game_master_assets.py --svg-only  # only rewrite the vector icon

`--check` and `--svg-only` need no third-party modules. Regeneration requires:
    pip install pillow numpy
"""

from __future__ import annotations

import argparse
import math
import struct
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "misc/logo/game_master_source.jpg"

BRAND_NAME = "Game Master"
# Sampled from the source artwork; keep the dark tone in sync with the splash background.
COLOR_DARK = (24, 26, 35, 255)
COLOR_GOLD = (201, 162, 74, 255)

# Embedded into every binary by main/SCsub. Must be square power-of-two RGBA PNGs,
# large enough for a 5x HiDPI display, because the boot splash scales per monitor.
ENGINE_ASSETS = {
    "main/app_icon.png": 512,
    "main/splash.png": 1024,
    "main/splash_editor.png": (1920, 1080),
}

HICOLOR_SIZES = (16, 24, 32, 48, 64, 128, 256, 512)
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
# icns OSType -> pixel size (https://iconhandbook.co.uk/reference/chart/osx/).
ICNS_TYPES = (
    ("icp4", 16),
    ("icp5", 32),
    ("icp6", 64),
    ("ic07", 128),
    ("ic08", 256),
    ("ic09", 512),
    ("ic10", 1024),
    ("ic11", 32),
    ("ic12", 64),
    ("ic13", 512),
    ("ic14", 1024),
)
# Android adaptive icons are 432px wide but only the central 66% circle is visible.
ANDROID_ADAPTIVE_SAFE_RATIO = 0.66
# Android splash densities (the "icon" layer, centered on the background color).
ANDROID_SPLASH_DENSITIES = (("mdpi", 108), ("hdpi", 162), ("xhdpi", 216), ("xxhdpi", 324), ("xxxhdpi", 432))
# iOS export settings, mirroring `application/icons/*` in platform/ios/export/export_plugin.cpp.
IOS_ICONS = (
    ("settings_58x58", 58),
    ("settings_87x87", 87),
    ("notification_40x40", 40),
    ("notification_60x60", 60),
    ("notification_76x76", 76),
    ("notification_114x114", 114),
    ("spotlight_80x80", 80),
    ("spotlight_120x120", 120),
    ("iphone_120x120", 120),
    ("iphone_180x180", 180),
    ("ipad_152x152", 152),
    ("ipad_167x167", 167),
    ("ios_128x128", 128),
    ("ios_136x136", 136),
    ("ios_192x192", 192),
    ("app_store_1024x1024", 1024),
)


def _png_info(data: bytes) -> tuple[int, int, int, int, int]:
    """Return (width, height, bit depth, color type, interlace) for a PNG buffer."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    return struct.unpack(">IIBBBBB", data[16:29])[:5]


def sniff_image(data: bytes) -> str:
    """Return the real format of a buffer, ignoring what the extension claims."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:4] == b"GIF8":
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:2] == b"BM":
        return "bmp"
    if b"<svg" in data[:4096]:
        return "svg"
    return "unknown"


def check_assets() -> int:
    """Validate the brand assets in the tree. Returns a process exit code."""
    failures: list[str] = []
    for rel, expected in ENGINE_ASSETS.items():
        path = ROOT / rel
        if not path.is_file():
            failures.append(f"{rel}: missing - main/SCsub embeds this into every binary, so the build stops")
            continue
        data = path.read_bytes()
        kind = sniff_image(data)
        if kind != "png":
            failures.append(
                f"{rel}: extension is .png but the bytes are {kind.upper()}; the engine decodes the "
                "embedded buffer with its PNG loader, so the image silently fails to load"
            )
            continue
        try:
            width, height, depth, color_type, interlace = _png_info(data)
        except ValueError as exc:
            failures.append(f"{rel}: {exc}")
            continue
        if color_type not in (2, 6):
            failures.append(f"{rel}: color type {color_type}, expected RGB (2) or RGBA (6) truecolor")
        if depth != 8:
            failures.append(f"{rel}: bit depth {depth}, expected 8")
        if interlace:
            failures.append(f"{rel}: interlaced PNG, which the boot splash cannot decode progressively")
        if isinstance(expected, tuple):
            if (width, height) != expected:
                failures.append(f"{rel}: {width}x{height}, expected {expected[0]}x{expected[1]}")
        elif width != height or width < expected:
            failures.append(
                f"{rel}: {width}x{height}, expected a square of at least {expected}px - smaller icons "
                "blur on HiDPI/retina displays and on Android adaptive icons"
            )
        elif width & (width - 1):
            failures.append(f"{rel}: {width}px is not a power of two")

    html_logo = ROOT / "misc/dist/html/logo.svg"
    if html_logo.is_file() and b"godot" in html_logo.read_bytes().lower():
        failures.append("misc/dist/html/logo.svg: Web export still shows the previous brand")

    if failures:
        print("Game Master brand assets: FAILED")
        for line in failures:
            print(f"  - {line}")
        print("\nRegenerate with: ./misc/scripts/game_master_assets.py")
        return 1
    print("Game Master brand assets: OK")
    return 0


def _pillow():
    try:
        import numpy
        from PIL import Image
    except ImportError:
        sys.exit(
            "Regenerating assets requires Pillow and NumPy:\n    pip install pillow numpy\n"
            "(`--check` and `--svg-only` run without them)"
        )
    return numpy, Image


def _background_mask(image, threshold: int, step: int):
    """Return a full-resolution mask of the background.

    The area is flood-filled only from the border, which keeps white highlights
    *inside* the artwork (the controller's silver parts) opaque. The fill runs on a
    downsampled grid, then the result is expanded back, so it stays fast on
    multi-megapixel sources.
    """
    numpy, _ = _pillow()
    width, height = image.size
    small = image.convert("RGB").resize((max(2, width // step), max(2, height // step)))
    rgb = numpy.asarray(small).astype(numpy.int16)
    whiteish = (rgb.min(axis=2) >= threshold) & ((rgb.max(axis=2) - rgb.min(axis=2)) <= 18)

    mask = numpy.zeros(whiteish.shape, dtype=bool)
    queue = deque()
    rows, cols = whiteish.shape

    def seed(y: int, x: int) -> None:
        if whiteish[y, x] and not mask[y, x]:
            mask[y, x] = True
            queue.append((y, x))

    for x in range(cols):
        seed(0, x)
        seed(rows - 1, x)
    for y in range(rows):
        seed(y, 0)
        seed(y, cols - 1)

    while queue:
        y, x = queue.popleft()
        for ny, nx in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= ny < rows and 0 <= nx < cols and whiteish[ny, nx] and not mask[ny, nx]:
                mask[ny, nx] = True
                queue.append((ny, nx))

    ys = numpy.minimum((numpy.arange(height) * (rows / height)).astype(numpy.int32), rows - 1)
    xs = numpy.minimum((numpy.arange(width) * (cols / width)).astype(numpy.int32), cols - 1)
    return mask[ys][:, xs]


def keyed_source(threshold: int = 232, step: int = 2):
    """Load the artwork, knock out the background, return (badge, wordmark) RGBA images.

    Two different keys are used on purpose. The badge is knocked out with a border
    flood fill so its white and silver highlights survive. The wordmark is flat text
    on white, so it is keyed by color distance from white: a flood fill cannot reach
    the enclosed counters of letters like "a" or "e", and eroding thin strokes to hide
    the JPEG fringe would eat the letters themselves.
    """
    numpy, Image = _pillow()
    from PIL import ImageFilter

    if not SOURCE.is_file():
        sys.exit(f"Source artwork not found: {SOURCE.relative_to(ROOT)}")
    source = Image.open(SOURCE)
    if source.format == "JPEG" and SOURCE.suffix.lower() == ".png":
        print("warning: the source is a JPEG inside a .png file - re-encoding it as PNG now")
    image = source.convert("RGB")

    background = _background_mask(image, threshold, step)
    # Erode the kept area by one pixel so JPEG ringing does not leave a white fringe.
    hard = Image.fromarray(numpy.where(background, 0, 255).astype(numpy.uint8), "L").filter(ImageFilter.MinFilter(3))

    box = hard.getbbox()
    if box is None:
        sys.exit("Source artwork is empty after background removal")
    base = image.crop(box)
    keyed = Image.merge("RGBA", (*base.split()[:3], hard.crop(box)))

    # The wordmark sits below the badge, separated by whitespace: split at the widest gap.
    solid = (numpy.asarray(keyed.split()[-1]) > 16).any(axis=1)
    runs = []
    start = None
    for y, filled in enumerate(solid):
        if not filled and start is None:
            start = y
        elif filled and start is not None:
            runs.append((start, y))
            start = None
    if start is not None:
        runs.append((start, len(solid)))
    gaps = [run for run in runs if run[1] - run[0] > 8 and run[0] > len(solid) // 2]
    split = max(gaps, key=lambda run: run[1] - run[0])[0] if gaps else len(solid)

    badge = keyed.crop((0, 0, keyed.width, split))
    if badge.getbbox():
        badge = badge.crop(badge.getbbox())

    ramp = max(48, 2 * (255 - threshold))
    distance = 255 - numpy.asarray(base).astype(numpy.int16).min(axis=2)
    soft = numpy.where(numpy.asarray(hard.crop(box)) > 0, numpy.clip(distance * 255 // ramp, 0, 255), 0)
    wordmark_full = Image.merge("RGBA", (*base.split()[:3], Image.fromarray(soft.astype(numpy.uint8), "L")))
    wordmark = wordmark_full.crop((0, split, keyed.width, keyed.height))
    if wordmark.getbbox():
        wordmark = wordmark.crop(wordmark.getbbox())
    else:
        wordmark = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    return badge, wordmark


def square(badge, size: int, margin: float = 0.08):
    """Fit the badge into a transparent square, centered, keeping the aspect ratio."""
    _, Image = _pillow()
    inner = max(1, int(size * (1.0 - 2.0 * margin)))
    ratio = min(inner / badge.width, inner / badge.height)
    small = badge.resize((max(1, round(badge.width * ratio)), max(1, round(badge.height * ratio))), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    canvas.alpha_composite(small, ((size - small.width) // 2, (size - small.height) // 2))
    return canvas


def rounded_plate(badge, size: int, radius: int = 0, opaque_background=COLOR_DARK):
    """Opaque square for launchers and stores that reject transparency."""
    _, Image = _pillow()
    from PIL import ImageDraw

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if opaque_background is not None:
        draw = ImageDraw.Draw(canvas)
        draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius or int(size * 0.22), fill=opaque_background)
    canvas.alpha_composite(square(badge, size, margin=0.14))
    return canvas


def flattened(badge, size: int, background=COLOR_DARK):
    """Flatten onto a solid color: the App Store icon must contain no alpha."""
    _, Image = _pillow()
    canvas = Image.new("RGBA", (size, size), background)
    canvas.alpha_composite(badge.resize((size, size), Image.LANCZOS))
    return canvas.convert("RGB")


def wide_logo(badge, wordmark, size=(1920, 1080)):
    """Horizontal lockup (badge + wordmark) for the editor boot splash and banners."""
    _, Image = _pillow()
    width, height = size
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    badge_image = square(badge, int(height * 0.66), margin=0.0)
    if wordmark.width > 1:
        ratio = min((width * 0.40) / wordmark.width, (height * 0.18) / wordmark.height)
        word = wordmark.resize(
            (max(1, round(wordmark.width * ratio)), max(1, round(wordmark.height * ratio))), Image.LANCZOS
        )
    else:
        word = wordmark
    gap = int(height * 0.05)
    left = (width - badge_image.width - word.width - gap) // 2
    canvas.alpha_composite(badge_image, (left, (height - badge_image.height) // 2))
    canvas.alpha_composite(word, (left + badge_image.width + gap, (height - word.height) // 2))
    return canvas


VECTOR_BELOW = 64  # at or under this size the photo artwork is mush, so the vector is used


def icon_geometry(v: float) -> dict:
    """The whole small-size icon as plain numbers, so the SVG and the raster never drift.

    Only solid fills and simple shapes: no text (Godot's SVG loader has no <text>, and a
    wordmark is unreadable at 16px anyway) and no gradients (they band at launcher sizes).
    """
    cx = cy = v / 2.0
    outer, inner, tip = v * 0.47, v * 0.235, v * 0.052
    star = []
    tips = []
    for i in range(12):
        angle = math.pi / 6 * i - math.pi / 2
        radius = outer if i % 2 == 0 else inner
        star.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    for i in range(6):
        angle = math.pi / 3 * i - math.pi / 2
        tips.append((cx + outer * math.cos(angle), cy + outer * math.sin(angle), tip))
    pad_w, pad_h = v * 0.46, v * 0.21
    stick, half, button = v * 0.048, v * 0.014, v * 0.028
    pad_x, pad_y = cx - pad_w / 2.0, cy + v * 0.015 - pad_h / 2.0
    dpad_x = cx - pad_w * 0.30
    dpad_y = pad_y + pad_h * 0.5
    buttons = [
        (cx + pad_w * 0.17 + col * stick * 1.9, dpad_y + (row - 0.5) * stick * 1.9, button)
        for row in range(2)
        for col in range(2)
    ]
    return {
        "star": star,
        "tips": tips,
        "pad": (pad_x, pad_y, pad_w, pad_h, pad_h * 0.45),
        "dpad": [
            (dpad_x - half, dpad_y - stick, half * 2, stick * 2),
            (dpad_x - stick, dpad_y - half, stick * 2, half * 2),
        ],
        "buttons": buttons,
        "gold": "#c9a24a",
        "gold_dark": "#8a6f2e",
        "ink": "#171921",
        "stroke": v * 0.014,
    }


def icon_svg(size: int = 64, intrinsic: int = 512) -> str:
    """Vector form of the small-size icon.

    `intrinsic` is larger than the viewBox on purpose: the Web editor shell sizes its logo with
    `width: auto`, so an intrinsic 64px would render a postage stamp on a big canvas.
    """
    g = icon_geometry(float(size))
    v = float(size)

    def points(items):
        return " ".join(f"{x:.2f},{y:.2f}" for x, y in items)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{intrinsic}" height="{intrinsic}" viewBox="0 0 {v:g} {v:g}" '
        f'role="img" aria-label="{BRAND_NAME} logo">',
        f'  <polygon points="{points(g["star"])}" fill="{g["gold"]}" stroke="{g["gold_dark"]}" '
        f'stroke-width="{g["stroke"]:.2f}" stroke-linejoin="round"/>',
    ]
    parts += [f'  <circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" fill="{g["gold"]}"/>' for x, y, r in g["tips"]]
    pad_x, pad_y, pad_w, pad_h, pad_r = g["pad"]
    parts.append(
        f'  <rect x="{pad_x:.2f}" y="{pad_y:.2f}" width="{pad_w:.2f}" height="{pad_h:.2f}" '
        f'rx="{pad_r:.2f}" fill="{g["ink"]}"/>'
    )
    parts += [
        f'  <rect x="{x:.2f}" y="{y:.2f}" width="{w:g}" height="{h:.2f}" rx="{half:.2f}" fill="{g["gold"]}"/>'
        for (x, y, w, h), half in zip(g["dpad"], (g["dpad"][0][2] * 0.3, g["dpad"][1][3] * 0.3))
    ]
    parts += [f'  <circle cx="{x:.2f}" cy="{y:.2f}" r="{r:.2f}" fill="{g["gold"]}"/>' for x, y, r in g["buttons"]]
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def icon_raster(size: int, background=None, mono: bool = False):
    """Raster form of the same geometry, drawn at exactly `size` pixels (no resampling)."""
    _, Image = _pillow()
    from PIL import ImageDraw

    canvas = Image.new("RGBA", (size, size), background or (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    g = icon_geometry(float(size))
    # A themed/monochrome layer is a flat silhouette: one color, no inner detail.
    gold = (255, 255, 255, 255) if mono else tuple(_hex_to_rgba(g["gold"]))
    ink = gold if mono else tuple(_hex_to_rgba(g["ink"]))
    half = max(1.0, g["stroke"] / 2.0)
    outline = None if mono else tuple(_hex_to_rgba(g["gold_dark"]))
    draw.polygon(g["star"], fill=gold, outline=outline, width=max(1, round(half)))
    for x, y, r in g["tips"]:
        draw.ellipse((x - r, y - r, x + r, y + r), fill=gold)
    pad_x, pad_y, pad_w, pad_h, pad_r = g["pad"]
    # The controller plate is knocked out of the silhouette so the glyph keeps its shape.
    draw.rounded_rectangle((pad_x, pad_y, pad_x + pad_w, pad_y + pad_h), radius=pad_r, fill=ink)
    for x, y, w, h in g["dpad"]:
        draw.rounded_rectangle((x, y, x + w, y + h), radius=min(w, h) * 0.3, fill=gold if not mono else ink)
    for x, y, r in g["buttons"]:
        draw.ellipse((x - r, y - r, x + r, y + r), fill=gold if not mono else ink)
    return canvas


def _star_points(v: float) -> str:
    """SVG `points` string for the 12-point brand star, centered in a `v` box."""
    g = icon_geometry(v)
    return " ".join(f"{x:.3f},{y:.3f}" for x, y in g["star"])


def _brand_mark_svg(units: int, fill: str, stroke: str | None = None, sw: float = 0.9) -> str:
    """The brand star as a self-contained SVG group (no `<text>`, see icon_geometry).

    Used both standalone and nested inside the editor lockup icons, so it returns
    the inner markup rather than a full document.
    """
    g = icon_geometry(float(units))
    stroke_attr = f' stroke="{stroke}" stroke-width="{sw}" stroke-linejoin="round"' if stroke else ""
    parts = [f'<polygon points="{_star_points(units)}" fill="{fill}"{stroke_attr}/>']
    pad_x, pad_y, pad_w, pad_h, pad_r = g["pad"]
    plate = "#ffffff" if fill == "#ffffff" else g["ink"]
    button = "#ffffff" if fill == "#ffffff" else g["gold"]
    parts.append(
        f'<rect x="{pad_x:.3f}" y="{pad_y:.3f}" width="{pad_w:.3f}" height="{pad_h:.3f}" '
        f'rx="{pad_r:.3f}" fill="{plate}"/>'
    )
    for x, y, w, h in g["dpad"]:
        parts.append(
            f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" rx="{min(w, h) * 0.3:.3f}" fill="{button}"/>'
        )
    for x, y, r in g["buttons"]:
        parts.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{r:.3f}" fill="{button}"/>')
    return "".join(parts)


def _document(width: int, height: int, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{BRAND_NAME}">{body}</svg>\n'
    )


def editor_icon_svgs() -> dict[str, str]:
    """The in-editor brand icons. Filenames stay `Godot*`/`Logo` so the C++ that
    references them by theme name is untouched; only the artwork changes. Every
    icon is gold (#c9a24a) on the dark ink plate, so none still reads as the
    upstream blue brand.
    """
    gold, ink, gold_dark = "#c9a24a", "#171921", "#8a6f2e"

    def square_mark(size: int, mono: bool, intrinsic: int | None = None) -> str:
        w = intrinsic or size
        # Scale the 64-unit mark to the full square with a small transparent margin.
        margin = 0.06 * size
        s = (size - 2 * margin) / 64.0
        tx, ty = margin, margin
        if mono:
            body = (
                f'<g transform="translate({tx:.3f},{ty:.3f})scale({s:.5f})">'
                f'<polygon points="{_star_points(64)}" fill="#ffffff"/></g>'
            )
        else:
            body = (
                f'<g transform="translate({tx:.3f},{ty:.3f})scale({s:.5f})">'
                f"{_brand_mark_svg(64, gold, stroke=gold_dark, sw=0.9)}</g>"
            )
        return _document(w, w, body)

    def wide_lockup(width: int, height: int) -> str:
        # Square badge on the left, a gold rule beside it (no <text>: the editor's
        # SVG loader renders no fonts, and these marks sit next to a real title bar).
        m = height * 0.12
        box = height - 2 * m
        s = box / 64.0
        body = (
            f'<g transform="translate({m:.2f},{m:.2f})scale({s:.5f})">'
            f"{_brand_mark_svg(64, gold, stroke=gold_dark, sw=0.9)}</g>"
        )
        bar_x = m + box + height * 0.18
        bar_w = width - bar_x - m
        bar_h = max(2.0, height * 0.06)
        bar_y = (height - bar_h) / 2
        body += (
            f'<rect x="{bar_x:.2f}" y="{bar_y:.2f}" width="{bar_w:.2f}" height="{bar_h:.2f}" '
            f'rx="{bar_h / 2:.2f}" fill="{gold}" opacity="0.9"/>'
        )
        return _document(width, height, body)

    def file_icon(size: int) -> str:
        # Folded-corner file (white, semi-transparent to read as a document) with the
        # brand mark inset where the upstream logo sat.
        body = (
            '<path fill="#ffffff" fill-opacity="0.92" d="M14 5a4 4 0 0 0-4 4v46a4 4 0 0 0 4 4h36a4 4 0 0 0 4-4V22'
            'a1 1 0 0 0-.29-.71l-16-16A1 1 0 0 0 37 5zm0 2h22v12a4 4 0 0 0 4 4h12v32a2 2 0 0 1-2 2H14a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z"/>'
        )
        m = size * 0.30
        s = (size - 2 * m) / 64.0
        body += (
            f'<g transform="translate({m:.2f},{m:.2f})scale({s:.5f})">'
            f"{_brand_mark_svg(64, gold, stroke=gold_dark, sw=1.4)}</g>"
        )
        return _document(size, size, body)

    def default_project_icon(size: int) -> str:
        # New projects' default icon: a dark plate with the gold brand mark, so the
        # Godot blue that used to ship here is gone too.
        body = f'<rect width="{size}" height="{size}" rx="{size * 0.18:.2f}" fill="{ink}"/>'
        m = size * 0.16
        s = (size - 2 * m) / 64.0
        body += (
            f'<g transform="translate({m:.2f},{m:.2f})scale({s:.5f})">'
            f"{_brand_mark_svg(64, gold, stroke=gold_dark, sw=1.0)}</g>"
        )
        return _document(size, size, body)

    return {
        "editor/icons/Godot.svg": square_mark(16, mono=False),
        "editor/icons/GodotMonochrome.svg": square_mark(16, mono=True),
        "editor/icons/GodotFile.svg": file_icon(64),
        "editor/icons/DefaultProjectIcon.svg": default_project_icon(128),
        "editor/icons/Logo.svg": wide_lockup(187, 69),
        "editor/icons/TitleBarLogo.svg": wide_lockup(100, 24),
    }


def emit_editor_icons(written: list[Path]) -> None:
    """Write the in-editor brand icons from icon_geometry (no Pillow needed)."""
    for rel, svg in editor_icon_svgs().items():
        if not svg:
            continue
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(svg, encoding="utf-8", newline="")
        written.append(path)


def _hex_to_rgba(value: str) -> tuple:
    """`#rrggbb` (or a brand tuple) as an RGBA tuple."""
    if isinstance(value, tuple):
        return value
    return (int(value[1:3], 16), int(value[3:5], 16), int(value[5:7], 16), 255)


def brand_mark(size: int, margin: float = 0.0, badge=None, detail: bool = True):
    """The brand mark at `size`, picking artwork that actually survives that size."""
    if not detail or size < VECTOR_BELOW:
        return icon_raster(size)
    if badge is None:
        raise ValueError("badge artwork is required above the vector threshold")
    return square(badge, size, margin=margin)


def _save(image, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG", optimize=True)
    return path


def write_ico(images: list, path: Path) -> Path:
    """Container of PNG-compressed .ico entries (Vista and later)."""
    import io

    path.parent.mkdir(parents=True, exist_ok=True)
    payloads = [io.BytesIO() for _ in images]
    for image, buffer in zip(images, payloads):
        image.save(buffer, "PNG")
    directory = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    body = b""
    for image, buffer in zip(images, payloads):
        data = buffer.getvalue()
        width = 0 if image.width >= 256 else image.width
        height = 0 if image.height >= 256 else image.height
        directory += struct.pack("<BBBBHHII", width, height, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
        body += data
    path.write_bytes(directory + body)
    return path


def write_icns(images: dict, path: Path) -> Path:
    """`icns` container: each entry is a PNG payload tagged with an OSType."""
    import io

    path.parent.mkdir(parents=True, exist_ok=True)
    body = b""
    for ostype, image in images.items():
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
        data = buffer.getvalue()
        body += ostype.encode("ascii") + struct.pack(">I", len(data) + 8) + data
    path.write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)
    return path


def generate(threshold: int) -> int:
    badge, wordmark = keyed_source(threshold=threshold)
    written: list[Path] = []

    def emit(image, rel: str) -> None:
        written.append(_save(image, ROOT / rel))

    # Engine binaries embed these three; they are also the fallback icon for exports.
    emit(square(badge, ENGINE_ASSETS["main/app_icon.png"], margin=0.06), "main/app_icon.png")
    emit(square(badge, ENGINE_ASSETS["main/splash.png"], margin=0.10), "main/splash.png")
    emit(wide_logo(badge, wordmark, ENGINE_ASSETS["main/splash_editor.png"]), "main/splash_editor.png")

    # Masters.
    emit(square(badge, 1024, margin=0.0), "misc/logo/game_master_badge.png")
    emit(wordmark, "misc/logo/game_master_wordmark.png")
    emit(wide_logo(badge, wordmark), "misc/logo/game_master_logo_wide.png")
    svg = icon_svg(64)
    for rel in ("misc/logo/game_master_icon.svg", "misc/dist/html/logo.svg"):
        (ROOT / rel).parent.mkdir(parents=True, exist_ok=True)
        (ROOT / rel).write_text(svg, encoding="utf-8", newline="\n")
        written.append(ROOT / rel)

    # In-editor brand icons (About menu/dialog, project manager title bar, project
    # file icons, default project icon). Pure SVG from icon_geometry; no Pillow.
    emit_editor_icons(written)

    # Linux: the hicolor ladder plus a scalable entry for the .desktop Icon= key.
    for size in HICOLOR_SIZES:
        emit(
            brand_mark(size, margin=0.0 if size <= 24 else 0.05, badge=badge),
            f"misc/brand/linux/hicolor/{size}x{size}/apps/game-master.png",
        )
    (ROOT / "misc/brand/linux/hicolor/scalable/apps").mkdir(parents=True, exist_ok=True)
    (ROOT / "misc/brand/linux/hicolor/scalable/apps/game-master.svg").write_text(svg, encoding="utf-8", newline="\n")
    written.append(ROOT / "misc/brand/linux/hicolor/scalable/apps/game-master.svg")

    # Windows and macOS containers.
    written.append(
        write_ico([brand_mark(size, badge=badge) for size in ICO_SIZES], ROOT / "misc/brand/windows/game-master.ico")
    )
    icns = {ostype: square(badge, image_size, margin=0.0) for ostype, image_size in ICNS_TYPES}
    written.append(write_icns(icns, ROOT / "misc/brand/macos/game-master.icns"))
    written.append(write_icns(icns, ROOT / "misc/dist/macos_template.app/Contents/Resources/icon.icns"))

    # Android: opaque legacy icon, adaptive layers, splash per density.
    emit(rounded_plate(badge, 192), "misc/brand/android/main_192x192.png")
    margin = (1.0 - ANDROID_ADAPTIVE_SAFE_RATIO) / 2.0
    emit(square(badge, 432, margin=margin), "misc/brand/android/adaptive_foreground_432x432.png")
    _, Image = _pillow()
    emit(Image.new("RGBA", (432, 432), COLOR_DARK), "misc/brand/android/adaptive_background_432x432.png")
    emit(icon_raster(432, mono=True), "misc/brand/android/adaptive_monochrome_432x432.png")
    for name, size in ANDROID_SPLASH_DENSITIES:
        emit(brand_mark(size, margin=0.17, badge=badge), f"misc/brand/android/splash_{name}_{size}x{size}.png")

    # iOS and visionOS: one file per export setting, all opaque.
    for setting, size in IOS_ICONS:
        emit(flattened(brand_mark(size, margin=0.06, badge=badge), size), f"misc/brand/ios/{setting}.png")

    # Web / PWA.
    emit(brand_mark(192, margin=0.06, badge=badge), "misc/brand/web/icon-192.png")
    emit(square(badge, 512, margin=0.06), "misc/brand/web/icon-512.png")
    emit(rounded_plate(badge, 512, radius=0), "misc/brand/web/maskable-icon-512.png")
    emit(flattened(square(badge, 180, margin=0.08), 180), "misc/brand/web/apple-touch-icon.png")
    emit(square(badge, 256, margin=0.0), "misc/brand/web/favicon.png")
    written.append(
        write_ico([brand_mark(size, badge=badge) for size in (16, 24, 32, 48)], ROOT / "misc/brand/web/favicon.ico")
    )

    # Boot splash for projects exported with this engine.
    emit(square(badge, 1024, margin=0.12), "misc/brand/splash/boot_splash.png")
    emit(wide_logo(badge, wordmark), "misc/brand/splash/boot_splash_wide.png")

    print(
        f"Generated {len(written)} files from {SOURCE.relative_to(ROOT)} (badge cut out at {badge.width}x{badge.height})."
    )
    preview()  # keep the size-check sheet in step with the assets
    return 0


def preview() -> int:
    """Render `misc/brand/preview.png`: every size on a dark and a light backdrop.

    Icons are usually broken at the small end (blurred, clipped by the launcher's
    circle, invisible on a light desktop), and that is exactly what is hard to spot
    by opening one PNG at a time. This sheet shows the ladder, the Android adaptive
    composite and the maskable crop together.
    """
    numpy, Image = _pillow()
    from PIL import ImageDraw, ImageFont

    sizes = (16, 24, 32, 48, 64, 128, 256)
    cell = 128
    pad = 16
    width = pad * 2 + cell * len(sizes)
    height = pad * 3 + cell * 4
    sheet = Image.new("RGBA", (width, height), (32, 34, 44, 255))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default()
    except Exception:  # noqa: BLE001
        font = None

    def label(text: str, x: int, y: int, fill=(230, 230, 235, 255)) -> None:
        if font is not None:
            draw.text((x, y), text, fill=fill, font=font)

    for row, (backdrop, name) in enumerate(((COLOR_DARK, "dark backdrop"), ((245, 245, 245, 255), "light backdrop"))):
        for column, size in enumerate(sizes):
            source = ROOT / f"misc/brand/linux/hicolor/{size}x{size}/apps/game-master.png"
            if not source.is_file():
                continue
            icon = Image.open(source).convert("RGBA")
            tile = Image.new("RGBA", (cell, cell), backdrop)
            tile.alpha_composite(
                icon.resize((cell - 2 * pad, cell - 2 * pad), Image.NEAREST if size < 64 else Image.LANCZOS), (pad, pad)
            )
            sheet.alpha_composite(tile, (pad + column * cell, pad + row * cell))
        label(name, pad, pad + (row + 0.75) * cell, fill=(230, 230, 235, 255) if row == 0 else (40, 42, 50, 255))

    # Android adaptive: circular mask over the layered icon, plus the monochrome layer.
    adaptive_row = 2
    foreground = Image.open(ROOT / "misc/brand/android/adaptive_foreground_432x432.png").convert("RGBA")
    background = Image.open(ROOT / "misc/brand/android/adaptive_background_432x432.png").convert("RGBA")
    monochrome = Image.open(ROOT / "misc/brand/android/adaptive_monochrome_432x432.png").convert("RGBA")
    legacy = Image.open(ROOT / "misc/brand/android/main_192x192.png").convert("RGBA")
    mask = Image.new("L", (cell, cell), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, cell - 1, cell - 1), fill=255)

    def layer(source_image: Image.Image, tint=None) -> Image.Image:
        scaled = source_image.resize((cell, cell), Image.LANCZOS)
        canvas = background.resize((cell, cell), Image.LANCZOS).copy()
        if tint is not None:
            canvas = Image.new("RGBA", (cell, cell), tint)
        canvas.alpha_composite(scaled)
        out = Image.new("RGBA", (cell, cell), (0, 0, 0, 0))
        out.paste(canvas, (0, 0), mask)
        return out

    cells = (
        (legacy, "Android legacy"),
        (layer(foreground), "adaptive (circle)"),
        (layer(monochrome, (96, 99, 116, 255)), "themed/monochrome"),
        (
            Image
            .open(ROOT / "misc/brand/web/maskable-icon-512.png")
            .convert("RGBA")
            .resize((cell, cell), Image.LANCZOS),
            "web maskable",
        ),
        (
            Image.open(ROOT / "misc/brand/web/icon-192.png").convert("RGBA").resize((cell, cell), Image.LANCZOS),
            "PWA 192",
        ),
        (
            Image
            .open(ROOT / "misc/brand/ios/app_store_1024x1024.png")
            .convert("RGBA")
            .resize((cell, cell), Image.LANCZOS),
            "iOS app store",
        ),
    )
    for column, (image, name) in enumerate(cells):
        x = pad + column * cell
        draw.rectangle(
            (x, pad + adaptive_row * cell, x + cell, pad + (adaptive_row + 1) * cell), outline=(90, 92, 104, 255)
        )
        sheet.alpha_composite(image, (x, pad + adaptive_row * cell))
        label(name, x + 4, pad + (adaptive_row + 0.78) * cell)

    out = ROOT / "misc/brand/preview.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, "PNG", optimize=True)
    print(f"wrote {out.relative_to(ROOT)} ({width}x{height})")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the Game Master brand asset set.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="validate the assets in the tree (no dependencies)")
    group.add_argument("--list", action="store_true", help="list generated asset paths")
    group.add_argument("--svg-only", action="store_true", help="rewrite only the generated vector icon")
    group.add_argument("--preview", action="store_true", help="render the size-check contact sheet only")
    parser.add_argument("--threshold", type=int, default=232, help="white point used to knock out the background")
    args = parser.parse_args()

    if args.check:
        return check_assets()
    if args.list:
        for rel in sorted(str(p.relative_to(ROOT)) for p in (ROOT / "misc/brand").rglob("*") if p.is_file()):
            print(rel)
        for rel in sorted(ENGINE_ASSETS):
            print(rel)
        return 0
    if args.svg_only:
        svg = icon_svg(64)
        written: list[Path] = []
        for rel in ("misc/logo/game_master_icon.svg", "misc/dist/html/logo.svg"):
            path = ROOT / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(svg, encoding="utf-8", newline="\n")
            written.append(path)
        # The in-editor icons are pure SVG from icon_geometry too, so they can be
        # regenerated without Pillow.
        emit_editor_icons(written)
        for path in written:
            print(f"wrote {path.relative_to(ROOT)}")
        return 0
    if args.preview:
        return preview()
    return generate(args.threshold)


if __name__ == "__main__":
    sys.exit(main())
