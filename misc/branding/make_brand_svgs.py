#!/usr/bin/env python3
"""Game Master Engine -- vector brand asset generator.

Emits every SVG brand asset in the repository from one shared parametric
description of the Game Master badge (six-point gold star, ribbon banner,
steel gamepad) plus a geometric capital-glyph font used to render the
wordmarks as <path> data (Godot's SVG renderer, thorvg, has no reliable
<text> support, so all lettering must be paths).

Run from the repository root:

    python3 misc/branding/make_brand_svgs.py

A raster self-preview of the exact same geometry is written to
misc/branding/preview_vectors.png so the vectors can be eyeballed without
an SVG renderer.
"""

import math
import os

from PIL import Image, ImageDraw

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

GOLD = "#c9a227"
GOLD_LIGHT = "#e6c86e"
GOLD_MID = "#d4af37"
GOLD_DARK = "#7a5c14"
STEEL = "#b8b8bc"
STEEL_DARK = "#6e6e73"
INK = "#26262b"
RIBBON_TEXT = "#2b2013"

C = (512.0, 540.0)  # Badge optical center in the 1024 design space.
YSTRETCH = 1.16


# --------------------------------------------------------------------------- geometry
def star_points(cx, cy, r_out, r_in, n=6, stretch=1.0, rot=90.0):
    pts = []
    for i in range(n * 2):
        ang = math.radians(rot + i * 180.0 / n)
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + r * math.cos(ang), cy - r * math.sin(ang) * stretch))
    return pts


def star5(cx, cy, r_out, r_in, rot=90.0):
    return star_points(cx, cy, r_out, r_in, n=5, stretch=1.0, rot=rot)


def fmt(pts):
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)


STAR = star_points(C[0], C[1], 430, 185, stretch=YSTRETCH)
STAR_INNER = star_points(C[0], C[1], 372, 160, stretch=YSTRETCH)
TIPS = [star_points(C[0], C[1], 464, 185, stretch=YSTRETCH)[i] for i in range(0, 12, 2)]
SMALL_STAR = star5(512, C[1] + 232, 64, 26)

RIBBON_TOP_L = (140, C[1] - 260)
RIBBON_TOP_C = (512, C[1] - 320)
RIBBON_TOP_R = (884, C[1] - 260)
RIBBON_BOT_R = (884, C[1] - 160)
RIBBON_BOT_C = (512, C[1] - 220)
RIBBON_BOT_L = (140, C[1] - 160)
RIBBON_PATH = (
    f"M{RIBBON_TOP_L[0]},{RIBBON_TOP_L[1]} Q{RIBBON_TOP_C[0]},{RIBBON_TOP_C[1]} {RIBBON_TOP_R[0]},{RIBBON_TOP_R[1]} "
    f"L{RIBBON_BOT_R[0]},{RIBBON_BOT_R[1]} Q{RIBBON_BOT_C[0]},{RIBBON_BOT_C[1]} {RIBBON_BOT_L[0]},{RIBBON_BOT_L[1]} Z"
)
TAIL_L = [(140, C[1] - 252), (58, C[1] - 224), (96, C[1] - 192), (58, C[1] - 148), (150, C[1] - 168)]
TAIL_R = [(1024 - x, y) for x, y in TAIL_L]

PAD_BODY = (300, C[1] - 90, 724, C[1] + 110)
PAD_GRIPS = [(372, C[1] + 96, 70), (652, C[1] + 96, 70)]
DPAD_V = (378, C[1] - 38, 422, C[1] + 58)
DPAD_H = (352, C[1] - 12, 448, C[1] + 32)
PLAY = [(500, C[1] - 24), (500, C[1] + 44), (556, C[1] + 10)]
BUTTONS = [(612, C[1] + 34, 26), (652, C[1] - 14, 26)]


# --------------------------------------------------------------------------- glyph font
# Blocky engraved capitals, 100x140 em, y down. Shapes are rect tuples
# (x0, y0, x1, y1) or polygon point lists.
G = {}
G["G"] = [(0, 0, 100, 18), (0, 0, 18, 140), (0, 122, 100, 140), (82, 60, 100, 140), (50, 60, 100, 78)]
G["A"] = [
    [(0, 140), (20, 140), (48, 0), (28, 0)],
    [(80, 140), (100, 140), (72, 0), (52, 0)],
    (28, 0, 72, 18),
    (18, 78, 82, 96),
]
G["M"] = [(0, 0, 18, 140), (82, 0, 100, 140), [(12, 0), (30, 0), (59, 92), (41, 92)], [(70, 0), (88, 0), (59, 92), (41, 92)]]
G["E"] = [(0, 0, 100, 18), (0, 0, 18, 140), (0, 61, 80, 79), (0, 122, 100, 140)]
G["S"] = [(0, 0, 100, 18), (0, 0, 18, 79), (0, 61, 100, 79), (82, 61, 100, 140), (0, 122, 100, 140)]
G["T"] = [(0, 0, 100, 18), (41, 0, 59, 140)]
G["R"] = [(0, 0, 18, 140), (0, 0, 82, 18), (82, 0, 100, 79), (0, 61, 82, 79), [(40, 79), (62, 79), (100, 140), (76, 140)]]
G["N"] = [(0, 0, 18, 140), (82, 0, 100, 140), [(8, 0), (26, 0), (92, 140), (74, 140)]]
G["I"] = [(0, 0, 100, 18), (41, 0, 59, 140), (0, 122, 100, 140)]
ADVANCE = 124


def wordmark_paths(text, x, y, height, fill):
    """Return SVG path elements rendering `text` with its baseline box top at y."""
    scale = height / 140.0
    out = []
    cx = x
    for ch in text:
        if ch == " ":
            cx += ADVANCE * scale
            continue
        for shape in G[ch]:
            if isinstance(shape, tuple):
                x0, y0, x1, y1 = shape
                pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
            else:
                pts = shape
            d = "M" + " L".join(f"{cx + px * scale:.1f},{y + py * scale:.1f}" for px, py in pts) + " Z"
            out.append(f'<path fill="{fill}" d="{d}"/>')
        cx += ADVANCE * scale
    return out, cx - x


def wordmark_width(text, height):
    return (len(text) * ADVANCE - 24) * height / 140.0


# --------------------------------------------------------------------------- svg pieces
def badge_elements(with_ribbon_text=True, mono=None):
    fill = mono
    els = []
    if fill:
        els.append(f'<polygon fill="{fill}" points="{fmt(STAR)}"/>')
        for x, y in TIPS:
            els.append(f'<circle fill="{fill}" cx="{x:.1f}" cy="{y:.1f}" r="36"/>')
        els.append(f'<path fill="{fill}" d="{RIBBON_PATH}"/>')
        els.append(f'<polygon fill="{fill}" points="{fmt(TAIL_L)}"/>')
        els.append(f'<polygon fill="{fill}" points="{fmt(TAIL_R)}"/>')
        x0, y0, x1, y1 = PAD_BODY
        els.append(f'<rect fill="{fill}" x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" rx="88"/>')
        for gx, gy, gr in PAD_GRIPS:
            els.append(f'<circle fill="{fill}" cx="{gx}" cy="{gy}" r="{gr}"/>')
        els.append(f'<polygon fill="{fill}" points="{fmt(SMALL_STAR)}"/>')
        return els
    els.append(f'<polygon fill="{GOLD}" stroke="{GOLD_DARK}" stroke-width="10" points="{fmt(STAR)}"/>')
    els.append(f'<polygon fill="{GOLD_LIGHT}" points="{fmt(STAR_INNER)}"/>')
    els.append(f'<polygon fill="{GOLD}" points="{fmt(star_points(C[0], C[1], 300, 130, stretch=YSTRETCH))}"/>')
    for x, y in TIPS:
        els.append(f'<circle fill="{GOLD_LIGHT}" stroke="{GOLD_DARK}" stroke-width="8" cx="{x:.1f}" cy="{y:.1f}" r="36"/>')
    els.append(f'<polygon fill="{GOLD_MID}" stroke="{GOLD_DARK}" stroke-width="8" points="{fmt(TAIL_L)}"/>')
    els.append(f'<polygon fill="{GOLD_MID}" stroke="{GOLD_DARK}" stroke-width="8" points="{fmt(TAIL_R)}"/>')
    els.append(f'<path fill="{GOLD_MID}" stroke="{GOLD_DARK}" stroke-width="8" d="{RIBBON_PATH}"/>')
    if with_ribbon_text:
        paths, w = wordmark_paths("GAME MASTER", 512 - wordmark_width("GAME MASTER", 92) / 2, C[1] - 258, 92, RIBBON_TEXT)
        els.extend(paths)
    x0, y0, x1, y1 = PAD_BODY
    els.append(f'<rect fill="{STEEL}" stroke="{STEEL_DARK}" stroke-width="10" x="{x0}" y="{y0}" width="{x1 - x0}" height="{y1 - y0}" rx="88"/>')
    for gx, gy, gr in PAD_GRIPS:
        els.append(f'<circle fill="{STEEL}" stroke="{STEEL_DARK}" stroke-width="10" cx="{gx}" cy="{gy}" r="{gr}"/>')
    els.append(f'<rect fill="{INK}" x="{DPAD_V[0]}" y="{DPAD_V[1]}" width="{DPAD_V[2] - DPAD_V[0]}" height="{DPAD_V[3] - DPAD_V[1]}" rx="10"/>')
    els.append(f'<rect fill="{INK}" x="{DPAD_H[0]}" y="{DPAD_H[1]}" width="{DPAD_H[2] - DPAD_H[0]}" height="{DPAD_H[3] - DPAD_H[1]}" rx="10"/>')
    els.append(f'<polygon fill="{INK}" points="{fmt(PLAY)}"/>')
    for bx, by, br in BUTTONS:
        els.append(f'<circle fill="{INK}" cx="{bx}" cy="{by}" r="{br}"/>')
    els.append(f'<polygon fill="{GOLD_LIGHT}" stroke="{GOLD_DARK}" stroke-width="6" points="{fmt(SMALL_STAR)}"/>')
    return els


def svg_doc(width, height, viewBox, elements):
    body = "".join(elements)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="{viewBox}">{body}</svg>\n'
    )


def horizontal_logo(vb_w, vb_h, mono=None, outline=False):
    """Badge on the left + GAME MASTER wordmark on the right."""
    els = []
    s = vb_h / 1024.0
    els.append(f'<g transform="matrix({s:.6f} 0 0 {s:.6f} 0 0)">')
    els.extend(badge_elements(with_ribbon_text=vb_h >= 200, mono=mono))
    els.append("</g>")
    h = vb_h * 0.42
    x = vb_h + vb_w * 0.04
    fill = mono or (GOLD_DARK if outline else GOLD_MID)
    paths, _ = wordmark_paths("GAME MASTER", x, (vb_h - h) / 2, h, fill)
    els.extend(paths)
    return els


def write(rel, content):
    path = os.path.join(ROOT, rel)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[brand] wrote {rel}")


# --------------------------------------------------------------------------- targets
def main():
    # Editor icons.
    write("editor/icons/Godot.svg", svg_doc(16, 16, "0 0 1024 1024", badge_elements(with_ribbon_text=False)))
    write("editor/icons/GodotMonochrome.svg", svg_doc(16, 16, "0 0 1024 1024", badge_elements(mono="#ffffff")))
    write("editor/icons/TitleBarLogo.svg", svg_doc(100, 24, "0 0 1000 240", horizontal_logo(1000, 240)))
    write("editor/icons/Logo.svg", svg_doc(187, 69, "0 0 1870 690", horizontal_logo(1870, 690)))
    file_icon = [
        '<path fill="#ffffff" d="M12 2 h28 l12 12 v48 h-40 z"/>',
        '<path fill="#cfcfcf" d="M40 2 l12 12 h-12 z"/>',
        '<g transform="matrix(0.033 0 0 0.033 15 20)">',
        *badge_elements(with_ribbon_text=False),
        "</g>",
    ]
    write("editor/icons/GodotFile.svg", svg_doc(64, 64, "0 0 64 64", file_icon))

    # Engine app icon vector master.
    write("main/app_icon.svg", svg_doc(512, 512, "0 0 1024 1024", badge_elements()))

    # Brand logos.
    write("misc/logo/logo.svg", svg_doc(1024, 414, "0 0 1024 414", horizontal_logo(1024, 414)))
    write("misc/logo/logo_outlined.svg", svg_doc(1024, 414, "0 0 1024 414", horizontal_logo(1024, 414, outline=True)))
    write("misc/dist/html/logo.svg", svg_doc(1024, 414, "0 0 1024 414", horizontal_logo(1024, 414)))

    # Per-platform export logos (square badge, keep original pixel sizes).
    sizes = {
        "platform/android/export/logo.svg": (32, 32),
        "platform/ios/export/logo.svg": (32, 32),
        "platform/linuxbsd/export/logo.svg": (32, 32),
        "platform/macos/export/logo.svg": (32, 32),
        "platform/visionos/export/logo.svg": (32, 32),
        "platform/web/export/logo.svg": (32, 32),
        "platform/windows/export/logo.svg": (32, 32),
    }
    for rel, (w, h) in sizes.items():
        write(rel, svg_doc(w, h, "0 0 1024 1024", badge_elements(with_ribbon_text=False)))

    # ------------------------------------------------------------------ preview
    img = Image.new("RGBA", (1400, 560), (24, 24, 26, 255))
    d = ImageDraw.Draw(img)

    def hexc(h):
        h = h.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)

    def poly(pts, fill, off=(0, 0), s=1.0):
        d.polygon([(x * s + off[0], y * s + off[1]) for x, y in pts], fill=hexc(fill))

    def rect(r, fill, off=(0, 0), s=1.0):
        d.rectangle([r[0] * s + off[0], r[1] * s + off[1], r[2] * s + off[0], r[3] * s + off[1]], fill=hexc(fill))

    s = 0.5
    off = (20, 20)
    poly(STAR, GOLD, off, s)
    poly(STAR_INNER, GOLD_LIGHT, off, s)
    for x, y in TIPS:
        d.ellipse([(x - 36) * s + off[0], (y - 36) * s + off[1], (x + 36) * s + off[0], (y + 36) * s + off[1]], fill=hexc(GOLD_LIGHT))
    poly(TAIL_L, GOLD_MID, off, s)
    poly(TAIL_R, GOLD_MID, off, s)
    d.pieslice([RIBBON_TOP_L[0] * s + off[0], (C[1] - 320) * s + off[1], RIBBON_TOP_R[0] * s + off[0], (C[1] - 100) * s + off[1]], 180, 360, fill=hexc(GOLD_MID))
    rect(PAD_BODY, STEEL, off, s)
    for gx, gy, gr in PAD_GRIPS:
        d.ellipse([(gx - gr) * s + off[0], (gy - gr) * s + off[1], (gx + gr) * s + off[0], (gy + gr) * s + off[1]], fill=hexc(STEEL))
    rect(DPAD_V, INK, off, s)
    rect(DPAD_H, INK, off, s)
    poly(PLAY, INK, off, s)
    for bx, by, br in BUTTONS:
        d.ellipse([(bx - br) * s + off[0], (by - br) * s + off[1], (bx + br) * s + off[0], (by + br) * s + off[1]], fill=hexc(INK))
    poly(SMALL_STAR, GOLD_LIGHT, off, s)
    # Wordmark preview next to the badge.
    cx = 600
    for ch in "GAME MASTER":
        if ch != " ":
            for shape in G[ch]:
                if isinstance(shape, tuple):
                    pts = [(shape[0], shape[1]), (shape[2], shape[1]), (shape[2], shape[3]), (shape[0], shape[3])]
                else:
                    pts = shape
                poly(pts, GOLD_MID, (cx, 120), 1.1)
        cx += ADVANCE * 1.1
    img.save(os.path.join(ROOT, "misc", "branding", "preview_vectors.png"))
    print("[brand] wrote misc/branding/preview_vectors.png")


if __name__ == "__main__":
    main()
