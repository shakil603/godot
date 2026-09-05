#!/usr/bin/env python3
"""One-shot writer for every user-visible Game Master mark.

Replaces the leftover Godot robot / GODOT wordmark in editor icons, dist logos,
default project icons, Windows/macOS containers and Android splash/mipmaps.

After regenerating, minify the vectors so the svgo static check stays green:
    npx svgo --config misc/utility/svgo.config.mjs <file.svg>
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
GOLD = "#c9a24a"
GOLD_DARK = "#8a6f2e"
INK = "#171921"
WHITE = "#f4efe4"
PLATE = "#1b1d27"
PLATE_EDGE = "#12141c"

# Stencil letters in a unit square (y down). Width is the advance.
# Each glyph is a list of (kind, ...) where kind is "rect" or "poly".
_LETTERS: dict[str, tuple[float, list[Any]]] = {
    "A": (
        0.82,
        [
            ("poly", [(0.00, 1.00), (0.20, 1.00), (0.41, 0.00), (0.23, 0.00)]),
            ("poly", [(0.59, 0.00), (0.77, 0.00), (0.98, 1.00), (0.78, 1.00)]),
            ("rect", 0.22, 0.58, 0.38, 0.16),
        ],
    ),
    "E": (
        0.70,
        [
            ("rect", 0.00, 0.00, 0.20, 1.00),
            ("rect", 0.18, 0.00, 0.52, 0.16),
            ("rect", 0.18, 0.42, 0.42, 0.16),
            ("rect", 0.18, 0.84, 0.52, 0.16),
        ],
    ),
    "G": (
        0.80,
        [
            ("rect", 0.18, 0.00, 0.58, 0.16),
            ("rect", 0.00, 0.14, 0.20, 0.72),
            ("rect", 0.18, 0.84, 0.58, 0.16),
            ("rect", 0.78, 0.48, 0.20, 0.52),
            ("rect", 0.46, 0.44, 0.52, 0.16),
        ],
    ),
    "M": (
        0.96,
        [
            ("rect", 0.00, 0.00, 0.18, 1.00),
            ("rect", 0.78, 0.00, 0.18, 1.00),
            ("poly", [(0.16, 0.00), (0.34, 0.00), (0.48, 0.52), (0.30, 0.52)]),
            ("poly", [(0.80, 0.00), (0.62, 0.00), (0.48, 0.52), (0.66, 0.52)]),
        ],
    ),
    "R": (
        0.78,
        [
            ("rect", 0.00, 0.00, 0.20, 1.00),
            ("rect", 0.18, 0.00, 0.42, 0.16),
            ("rect", 0.52, 0.14, 0.20, 0.36),
            ("rect", 0.18, 0.42, 0.42, 0.16),
            ("poly", [(0.40, 0.56), (0.58, 0.56), (0.86, 1.00), (0.64, 1.00)]),
        ],
    ),
    "S": (
        0.72,
        [
            ("rect", 0.16, 0.00, 0.52, 0.16),
            ("rect", 0.00, 0.14, 0.20, 0.36),
            ("rect", 0.16, 0.42, 0.40, 0.16),
            ("rect", 0.52, 0.50, 0.20, 0.36),
            ("rect", 0.04, 0.84, 0.52, 0.16),
        ],
    ),
    "T": (
        0.72,
        [
            ("rect", 0.00, 0.00, 0.72, 0.16),
            ("rect", 0.26, 0.14, 0.20, 0.86),
        ],
    ),
    " ": (0.32, []),
}


def _star_inner(
    v: float = 64.0, gold: str = GOLD, gold_dark: str = GOLD_DARK, ink: str = INK, mono: bool = False
) -> str:
    cx = cy = v / 2.0
    outer, inner, tip = v * 0.47, v * 0.235, v * 0.052
    pts: list[str] = []
    for i in range(12):
        angle = math.pi / 6 * i - math.pi / 2
        radius = outer if i % 2 == 0 else inner
        pts.append(f"{cx + radius * math.cos(angle):.2f},{cy + radius * math.sin(angle):.2f}")
    fill = "#ffffff" if mono else gold
    stroke = "none" if mono else gold_dark
    stroke_w = 0 if mono else v * 0.014
    parts = [
        f'<polygon points="{" ".join(pts)}" fill="{fill}" stroke="{stroke}" stroke-width="{stroke_w:.2f}" stroke-linejoin="round"/>'
    ]
    if not mono:
        for i in range(6):
            angle = math.pi / 3 * i - math.pi / 2
            x, y = cx + outer * math.cos(angle), cy + outer * math.sin(angle)
            parts.append(f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{tip:.2f}" fill="{gold}"/>')
        pad_w, pad_h = v * 0.46, v * 0.21
        stick, half, button = v * 0.048, v * 0.014, v * 0.028
        pad_x, pad_y = cx - pad_w / 2.0, cy + v * 0.015 - pad_h / 2.0
        parts.append(
            f'<rect x="{pad_x:.2f}" y="{pad_y:.2f}" width="{pad_w:.2f}" height="{pad_h:.2f}" rx="{pad_h * 0.45:.2f}" fill="{ink}"/>'
        )
        dpad_x = cx - pad_w * 0.30
        dpad_y = pad_y + pad_h * 0.5
        parts.append(
            f'<rect x="{dpad_x - half:.2f}" y="{dpad_y - stick:.2f}" width="{half * 2:.2f}" height="{stick * 2:.2f}" rx="{half * 0.6:.2f}" fill="{gold}"/>'
        )
        parts.append(
            f'<rect x="{dpad_x - stick:.2f}" y="{dpad_y - half:.2f}" width="{stick * 2:.2f}" height="{half * 2:.2f}" rx="{half * 0.6:.2f}" fill="{gold}"/>'
        )
        for row in range(2):
            for col in range(2):
                bx = cx + pad_w * 0.17 + col * stick * 1.9
                by = dpad_y + (row - 0.5) * stick * 1.9
                parts.append(f'<circle cx="{bx:.2f}" cy="{by:.2f}" r="{button:.2f}" fill="{gold}"/>')
    return "\n".join(parts)


def _star_group(x: float, y: float, size: float, **kwargs: Any) -> str:
    scale = size / 64.0
    return f'<g transform="translate({x:.2f} {y:.2f}) scale({scale:.5f})">\n{_star_inner(64.0, **kwargs)}\n</g>'


def _wordmark(text: str, x: float, y: float, h: float, fill: str, tracking: float = 0.14) -> tuple[str, float]:
    parts: list[str] = []
    cursor = x
    for ch in text.upper():
        width, glyphs = _LETTERS.get(ch, (0.32, []))
        for glyph in glyphs:
            if glyph[0] == "rect":
                _, gx, gy, gw, gh = glyph
                parts.append(
                    f'<rect x="{cursor + gx * h:.2f}" y="{y + gy * h:.2f}" width="{gw * h:.2f}" height="{gh * h:.2f}" fill="{fill}"/>'
                )
            else:
                _, pts = glyph
                mapped = " ".join(f"{cursor + px * h:.2f},{y + py * h:.2f}" for px, py in pts)
                parts.append(f'<polygon points="{mapped}" fill="{fill}"/>')
        cursor += h * (width + tracking)
    return "\n".join(parts), cursor - x - h * tracking


def _svg(width: int, height: int, body: str, label: str = "Game Master") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{label}">\n{body}\n</svg>\n'
    )


def logo_lockup(width: int = 320, height: int = 80, subtitle: bool = True) -> str:
    star = height * 0.90
    sx, sy = height * 0.05, (height - star) / 2
    word_h = height * (0.28 if subtitle else 0.36)
    wx = sx + star + height * 0.10
    wy = height * (0.22 if subtitle else 0.32)
    word, _ = _wordmark("GAME MASTER", wx, wy, word_h, WHITE, tracking=0.12)
    body = [_star_group(sx, sy, star), word]
    if subtitle:
        sub_h = height * 0.14
        sub, _ = _wordmark("GAME ENGINE", wx, wy + word_h + height * 0.10, sub_h, GOLD, tracking=0.16)
        body.append(sub)
    return _svg(width, height, "\n".join(body), "Game Master")


def titlebar_lockup(width: int = 168, height: int = 24) -> str:
    star = height * 0.92
    sx, sy = 1.0, (height - star) / 2
    word_h = height * 0.52
    wx = sx + star + 5.0
    wy = (height - word_h) / 2
    word, _ = _wordmark("GAME MASTER", wx, wy, word_h, WHITE, tracking=0.12)
    return _svg(width, height, _star_group(sx, sy, star) + "\n" + word, "Game Master")


def square_icon(size: int = 16, mono: bool = False) -> str:
    return _svg(size, size, _star_inner(float(size), mono=mono), "Game Master")


def default_project_icon() -> str:
    body = (
        f'<rect width="124" height="124" x="2" y="2" fill="{PLATE}" stroke="{PLATE_EDGE}" stroke-width="4" rx="14"/>\n'
        + _star_group(14, 14, 100)
    )
    return _svg(128, 128, body, "Game Master project")


def file_icon() -> str:
    body = (
        '<path fill="#2a2d3a" d="M14 5a4 4 0 0 0-4 4v46a4 4 0 0 0 4 4h36a4 4 0 0 0 4-4V22a1 1 0 0 0-.285-.707l-16-16A1 1 0 0 0 37 5z"/>'
        f'<path fill="{PLATE}" d="M14 7h22v12a4 4 0 0 0 4 4h12v32a2 2 0 0 1-2 2H14a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z"/>'
        + "\n"
        + _star_group(18, 26, 28)
    )
    return _svg(64, 64, body, "Game Master project file")


def console_icon() -> str:
    body = (
        _star_inner(1024)
        + f'<rect width="430" height="330" x="550" y="650" fill="{INK}" stroke="{WHITE}" stroke-width="20" rx="20"/>'
        f'<path fill="{WHITE}" d="M590 750a10 10 0 0 0 0 14.142l70 70-70 70a10 10 0 0 0 0 14.142l20 20a10 10 0 0 0 14.142 0l97.071-97.071a10 10 0 0 0 0-14.142L624.142 730A10 10 0 0 0 610 730zm180 145a10 10 0 0 0-10 10v25a10 10 0 0 0 10 10h160a10 10 0 0 0 10-10v-25a10 10 0 0 0-10-10z"/>'
    )
    return _svg(1024, 1024, body, "Game Master console")


def outlined_icon() -> str:
    return _svg(1024, 1024, _star_inner(1024), "Game Master")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size} bytes)")


def main() -> int:
    write(ROOT / "editor/icons/Logo.svg", logo_lockup(320, 80, subtitle=False))
    write(ROOT / "editor/icons/TitleBarLogo.svg", titlebar_lockup(168, 24))
    write(ROOT / "editor/icons/Godot.svg", square_icon(16, mono=False))
    write(ROOT / "editor/icons/GodotMonochrome.svg", square_icon(16, mono=True))
    write(ROOT / "editor/icons/GodotFile.svg", file_icon())
    write(ROOT / "editor/icons/DefaultProjectIcon.svg", default_project_icon())
    write(ROOT / "misc/logo/logo.svg", logo_lockup(640, 160, subtitle=True))
    write(ROOT / "misc/logo/logo_outlined.svg", logo_lockup(640, 160, subtitle=True))
    write(ROOT / "misc/logo/icon.svg", _svg(1024, 1024, _star_inner(1024), "Game Master"))
    write(ROOT / "misc/logo/icon_outlined.svg", _svg(1024, 1024, _star_inner(1024), "Game Master"))
    write(ROOT / "misc/logo/game_master_icon.svg", _svg(512, 512, _star_inner(64), "Game Master"))
    write(ROOT / "misc/dist/html/logo.svg", logo_lockup(640, 160, subtitle=False))
    write(ROOT / "misc/dist/windows/icon_console.svg", console_icon())
    write(
        ROOT / "misc/brand/linux/hicolor/scalable/apps/game-master.svg", _svg(512, 512, _star_inner(64), "Game Master")
    )
    write(ROOT / "platform/android/java/app/src/instrumented/assets/icon.svg", default_project_icon())
    write(
        ROOT / "misc/logo/LICENSE.txt",
        "Game Master brand artwork\nCopyright (c) Game Master\n\nOriginal mark for this fork. Not the Godot Engine logo.\n",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
