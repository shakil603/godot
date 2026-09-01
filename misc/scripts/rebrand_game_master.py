#!/usr/bin/env python3

"""Renames the visible brand from "Godot" to "Game Master" without breaking the ABI.

A blind search/replace across this repository destroys the engine: 32k+ occurrences of
"Godot" and 20k of "godot" include C++ class names, GDExtension ABI strings, build
filenames, NuGet/Java package ids, desktop ids, and legal notices that the MIT license
requires us to keep. This script therefore replaces the brand **only** where it is
prose, and refuses to touch anything that is glued to an identifier character.

Usage:
    ./misc/scripts/rebrand_game_master.py --scope docs,dist        # dry run (report only)
    ./misc/scripts/rebrand_game_master.py --scope docs,dist --apply
    ./misc/scripts/rebrand_game_master.py --scope code --apply --files editor/gui/editor_about.cpp
    ./misc/scripts/rebrand_game_master.py --why "Godot Engine"     # explain one match

Scopes:
    docs    README.md, CHANGELOG.md, CONTRIBUTING.md and all doc_classes XML prose
    dist    misc/dist/** (desktop entry, appdata, PWA manifest, installer, HTML shells)
    code    C/C++ string literals and comments outside the protected list
    ci      .github/** display names only

Deliberately never rewritten (see DENY for the mechanical rules; the reasons are in
DROPS so a reviewer sees what was skipped and why):
    * copyright headers and LICENSE/AUTHORS/DONORS/COPYRIGHT files - MIT attribution,
    * `project.godot`, `.godot/`, `godot.bin`, `bin/godot*` - file and binary names that
      every existing project, add-on and CI script depends on,
    * class/macro/namespace identifiers (`GodotPhysics2D`, `GODOT_VERSION_*`, `GodotSharp`)
      and the JS `Godot` embedding class - changing them is an API break, not a rename,
    * `*.po`/`*.pot` translations - msgids must stay in sync with the source strings,
      they are refreshed by `doc/tools` afterwards.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[2]

OLD_BRAND = "Godot"
NEW_BRAND = "Game Master"

# Phrases are replaced longest-first so "Godot Engine" never becomes "Game Master Engine".
PHRASES = (
    ("Godot Engine's", f"{NEW_BRAND}'s"),
    ("Godot Engine", NEW_BRAND),
    ("godotengine.org", "godotengine.org"),  # kept: upstream URLs still resolve, see DROPS
)

# Standalone brand word. The guards are what makes this safe to run over a codebase:
#  * no identifier char before, so `org.godotengine.Godot` and `com...Godot` stay intact;
#  * no identifier char after, so `GodotSharp`, `GodotPhysics2D`, `GodotLG` stay intact;
#  * not before a file extension, so `Godot.svg` and `Godot.exe` (real file names) stay;
#  * not before a version number, because "Godot 3.x to Godot 4.x" is engine history that
#    a fork must not rewrite into something that never happened;
#  * not after `#`, because `#Godot` is a channel name, not a brand mention.
STANDALONE = re.compile(
    r"""(?<![A-Za-z0-9_.#])
        Godot
        (?![A-Za-z0-9_])
        (?!\.[A-Za-z])
        (?!\s+\d+(?:\.\d+)*(?:\.x)?)
        (?!\-cpp\b)
    """,
    re.VERBOSE,
)

# Phrases that mention the brand but are not ours to rename: real organizations, third-party
# repositories and legal attribution. They are masked before the substitution and restored
# afterwards, so a sentence like "supported by the Godot Foundation" survives intact.
KEEP_PHRASES = (
    "Godot Foundation",
    "Godot Engine contributors",
    "Godot Engine project",
    "Godot Proposals",
    "Godot Engine community",
    "SUPPORT_us.md",
)

# Inline code spans describe literal identifiers, paths and file names, so text inside them is
# never a branding mention: `[code].godot[/code]`, `Godot.svg`, `~/.config/godot/`.
#: One alternation, matched in a single pass. Running these patterns one after another
#: over already-masked text lets a greedy `<code>.*?</code>` swallow a previous token, and
#: the swallowed token then never gets restored -- invisible \x02 control characters end up
#: in the file. Non-overlapping alternation matches cannot nest, so they always can.
INLINE_CODE_SPANS = re.compile(
    r"`[^`\n]+`"
    r"|\[code\].*?\[/code\]"
    r"|<code>.*?</code>",
    re.S,
)

# Put this in a line's comment to skip that line on purpose (used in README.md, where the
# table rows quote the upstream names that must stay).
KEEP_MARKER = "rebrand:keep"

# Any line matching one of these is left completely alone.
DENY_LINE = (
    re.compile(r"This file is part of"),
    re.compile(r"Copyright \(c\)"),
    re.compile(r"©"),  # human-readable copyright lines use the symbol, not the word
    re.compile(r"Juan Linietsky"),
    re.compile(r"\bcontributors\b"),
    re.compile(r"SPDX-License-Identifier"),
    re.compile(r"godotengine\.org"),
    re.compile(r"godot\.foundation|godot-proposals|hosted\.weblate|raw\.githubusercontent\.com"),
    re.compile(r"github\.com/godotengine/"),  # links to upstream repositories
    re.compile(r"^\s*#\s*(include|import|pragma|define|undef)\b"),
    re.compile(r"org\.godotengine"),  # D-Bus / desktop / appstream ids
    re.compile(r"discord\.gg|irc\.libera|matrix\.to"),  # community channels we do not run
    re.compile(r"DefaultDirName|OutputBaseFilename|^Source:\s"),  # installer paths/file names
    # Desktop-entry keys whose values must match what the running program reports, and the
    # icon/registration lookups that use the brand word as a resource key rather than as text.
    re.compile(r"\"generator\"|as_generator|generator_version"),  # values written into exported files
    re.compile(r"^\s*(StartupWMClass|Exec|TryExec|Icon|Path|Actions|MimeType|DBusActivatable)\s*="),
    re.compile(r"SNAME\(|add_theme_icon|register_icon|\bClassDB::|REGISTER_|get_editor_theme_native_menu_icon"),
    re.compile(r"\.(svg|png|ico|icns|jpg|ttf|json)\b"),  # resource file names inline
    # OS-level window identity: the WM_CLASS / Wayland app id a compositor groups by, and the
    # accessibility root label. Renaming these would ungroup windows and break user window rules.
    re.compile(r"res_class|class_str|WMClass|app_id|appname\s*=|AppUserModelID|set_accessibility_name\(\""),
    re.compile(r"^[+-]\s"),  # unified diff noise, if a patch file is ever fed in
)

# In plist/XML files, the value line under one of these keys must keep matching a real
# file or bundle name; renaming it without renaming the file breaks the .app bundle.
OPAQUE_VALUE_KEYS = frozenset({
    "CFBundleExecutable",
    "CFBundleIconFile",
    "CFBundleIconName",
    "CFBundleIdentifier",
    "CFBundleSignature",
    "CFBundleTypeRole",
    "CFBundleURLName",
})
KEY_LINE = re.compile(r"<key>\s*([A-Za-z]+)\s*</key>")

DENY_PATH = (
    "thirdparty/",
    "AUTHORS.md",
    # Upstream's contribution guide describes upstream's process, repositories and review
    # rules; renaming the brand inside it would tell people to file Game Master bugs upstream.
    "CONTRIBUTING.md",
    "DONORS.md",
    "LICENSE.txt",
    "COPYRIGHT.txt",
    ".mailmap",
    ".git-blame-ignore-revs",
    ".github/CODEOWNERS",
    "editor/icons/",
    "icons/",
    "editor/translations/",
    "modules/gdscript/translators.cpp",
    "doc/translations/",
    "misc/error.code",
    "core/input/gamecontrollerdb.txt",
    "core/string/",
    "platform/android/java/",  # Java/Kotlin package and class names
    "platform/web/js/",  # the `Godot` JS class is the embedding API
    "platform/web/editor/",
    "modules/mono/",  # MSBuild/NuGet identifiers
    "core/extension/gdextension_interface.json",  # machine-readable ABI spec
    "modules/gltf/gltf_document.cpp",  # writes asset.generator into exported files
    "modules/gdscript/gdscript_bench.cpp",
)

BINARY_SUFFIXES = frozenset({
    ".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico", ".icns", ".car", ".ttf", ".woff2", ".wasm",
    ".zip", ".pck", ".glb", ".gltf", ".hdr", ".exr", ".dae", ".fbx", ".ogg", ".mp3", ".wav",
    ".otf", ".mo", ".dat", ".bin", ".a", ".lib", ".po", ".pot", ".ts",
})

# What each scope covers. `code` is opt-in per file with --files so a rename can be
# reviewed one build unit at a time instead of in one 4000-file commit.
SCOPES = {
    "docs": ("README.md", "CONTRIBUTING.md", "doc/**/*.xml", "doc/**/*.md", "**/doc_classes/*.xml"),
    "dist": ("misc/dist/**/*",),
    "ci": (".github/workflows/**/*.yml", ".github/actions/**/*.yml", ".github/ISSUE_TEMPLATE/**/*"),
    "code": ("core/**/*", "scene/**/*", "servers/**/*", "main/**/*", "editor/**/*", "modules/**/*", "platform/**/*"),
}

DROPS = (
    ("https://godotengine.org", "upstream URL: still the canonical homepage of the code this fork builds on"),
    ("This file is part of", "MIT attribution header, also enforced by CI (copyright_headers.py)"),
    ("Copyright (c)", "legal notice"),
    ("org.godotengine", "application/desktop id: changing it uninstalls the icon theme entry and the .desktop file"),
)


def iter_scope(scope: str) -> Iterator[Path]:
    """Yield every candidate file of a scope, skipping DENY_PATH and binary assets."""
    seen = set()
    for pattern in SCOPES[scope]:
        for candidate in sorted(ROOT.glob(pattern)):
            if not candidate.is_file() or candidate in seen:
                continue
            seen.add(candidate)
            rel = candidate.relative_to(ROOT).as_posix()
            if any(rel.startswith(deny) for deny in DENY_PATH):
                continue
            if candidate.suffix in BINARY_SUFFIXES:
                continue
            yield candidate


def rewrite_line(line: str, opaque_value: bool = False) -> tuple[str, int]:
    """Return (new_line, replacements) for a single line.

    Lines matching DENY_LINE, and value lines that must keep matching a real file or
    bundle name (`opaque_value`), are returned unchanged.
    """
    if opaque_value or KEEP_MARKER in line:
        return line, 0
    for denied in DENY_LINE:
        if denied.search(line):
            return line, 0
    count = 0
    result = line
    spans = []

    def _mask(match: re.Match) -> str:
        token = f"\x02{len(spans)}\x02"
        spans.append((token, match.group(0)))
        return token

    result = INLINE_CODE_SPANS.sub(_mask, result)
    masked = []
    for index, phrase in enumerate(KEEP_PHRASES):
        if phrase in result:
            token = f"\x01{index}\x01"
            masked.append((token, phrase))
            result = result.replace(phrase, token)
    for old, new in PHRASES:
        if old != new and old in result:
            count += result.count(old)
            result = result.replace(old, new)
    result, sub_count = STANDALONE.subn(NEW_BRAND, result)
    # Reverse order, so an outer span is put back before anything nested inside it.
    for token, phrase in reversed(masked + spans):
        result = result.replace(token, phrase)
    return result, count + sub_count


def rewrite_text(text: str) -> tuple[str, int]:
    """Rewrite a whole file, honoring the plist `<key>` / value pairing."""
    out_lines = []
    total = 0
    opaque_next = False
    for line in text.splitlines(keepends=True):
        new_line, count = rewrite_line(line, opaque_value=opaque_next)
        out_lines.append(new_line)
        total += count
        match = KEY_LINE.search(line)
        opaque_next = bool(match) and match.group(1) in OPAQUE_VALUE_KEYS
    return "".join(out_lines), total


def report_reason(text: str, needle: str) -> None:
    """Explain why a given string is or is not rewritten."""
    print(f'Looking for "{needle}":')
    matched = 0
    for index, line in enumerate(text.splitlines(), start=1):
        if needle not in line:
            continue
        new_line, count = rewrite_line(line)
        matched += count
        verdict = "REWRITTEN" if count else "KEPT"
        reason = ""
        if not count:
            for drop, why in DROPS:
                if drop in line:
                    reason = f" - {why}"
                    break
            else:
                reason = " - part of an identifier, a URL or a file name"
        print(f"  line {index}: {verdict}{reason}")
    if not matched:
        print("  (no occurrence would be rewritten)")


def preview_lines(text: str, limit: int = 12) -> list[tuple[int, str, str]]:
    """Return (line number, old, new) for the lines that a rewrite would change."""
    rows = []
    for number, (old, new) in enumerate(zip(text.splitlines(), rewrite_text(text)[0].splitlines()), start=1):
        if old != new:
            rows.append((number, old.strip(), new.strip()))
    return rows[:limit]


def run(scopes: list[str], apply_changes: bool, files: list[str], preview: bool = False) -> int:
    targets: list[Path]
    if files:
        targets = [ROOT / f for f in files]
        for target in targets:
            if not target.is_file():
                print(f"error: no such file: {target.relative_to(ROOT)}", file=sys.stderr)
                return 2
    else:
        targets = []
        for scope in scopes:
            targets.extend(iter_scope(scope))

    changed: list[tuple[Path, int]] = []
    scanned = 0
    for path in targets:
        try:
            original = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        text, total = rewrite_text(original)
        if not total:
            continue
        changed.append((path, total))
        if preview:
            print(f"\n{path.relative_to(ROOT)} ({total} change(s))")
            for number, old, new in preview_lines(original):
                print(f"  {number:5d} - {old[:110]}")
                print(f"  {number:5d} + {new[:110]}")
        if apply_changes:
            path.write_text(text, encoding="utf-8", newline="\n")

    verb = "updated" if apply_changes else "would update"
    total = sum(count for _, count in changed)
    print(f"{verb} {len(changed)} file(s) across {len(targets)} candidate(s), {total} occurrence(s); {scanned} file(s) read.")
    for path, count in sorted(changed, key=lambda item: -item[1])[:20]:
        print(f"  {count:4d}  {path.relative_to(ROOT)}")
    if len(changed) > 20:
        print(f"  ... and {len(changed) - 20} more")
    if not apply_changes and changed:
        print("\nRe-run with --apply to write these changes.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Rename the visible brand to Game Master.")
    parser.add_argument("--scope", default="docs,dist", help="comma separated: docs, dist, ci, code")
    parser.add_argument("--files", nargs="*", default=[], help="rewrite only these paths (overrides --scope)")
    parser.add_argument("--apply", action="store_true", help="write the changes instead of reporting them")
    parser.add_argument("--preview", action="store_true", help="print the line-level changes")
    parser.add_argument("--why", metavar="STRING", help="explain whether a string would be rewritten")
    parser.add_argument("--why-file", metavar="PATH", help="file to search with --why (default: README.md)")
    args = parser.parse_args()

    if args.why:
        source = Path(args.why_file) if args.why_file else ROOT / "README.md"
        if not source.is_absolute():
            source = ROOT / source
        if not source.is_file():
            print(f"error: no such file: {source}", file=sys.stderr)
            return 2
        report_reason(source.read_text(encoding="utf-8"), args.why)
        return 0

    unknown = [scope for scope in args.scope.split(",") if scope.strip() and scope.strip() not in SCOPES]
    if unknown:
        print(f"error: unknown scope(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    return run([scope.strip() for scope in args.scope.split(",") if scope.strip()], args.apply, args.files, args.preview)


if __name__ == "__main__":
    sys.exit(main())
