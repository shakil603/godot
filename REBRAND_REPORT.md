# Game Master Engine — White-Label Rebrand Report

Branch: `arena/01a0d682-godot` · Base: `30caae98` (Godot 4.8-dev, == upstream master 2026-09-24)
Executed per the "SOURCE-LEVEL REBRANDING & ASSET PROCESSING" specification.

---

## 1. Brand identity applied

| Spec field | Value | Where it lives |
|---|---|---|
| VERSION_NAME | `Game Master` | `version.py` → generated `GODOT_VERSION_NAME` |
| VERSION_SHORT_NAME | `game_master` | `version.py` → `GODOT_VERSION_SHORT_NAME` |
| VERSION_WEBSITE | `https://gamemasterengine.com` | `version.py` → `GODOT_VERSION_WEBSITE` |
| VERSION_DOCS_URL | `https://docs.gamemasterengine.com` | `core/core_builders.py` template |
| Owner | Shakil | splash, About dialog, boot header, .rc, plist |
| Core attribution | "Game Master Engine is built upon the Godot Engine core." | splash, About, boot header, .rc, plist, web manifest |

**Important:** `core/version.h` (the file named in the spec) is *not* editable — it
`#include`s `core/version_generated.gen.h`, which SCons regenerates from `version.py`
on every build (`core/SCsub`). The values were therefore set at the true source of
truth (`version.py` + the generator template in `core/core_builders.py`). Verified by
executing the real builder: the emitted header now contains
`GODOT_VERSION_SHORT_NAME "game_master"`, `GODOT_VERSION_NAME "Game Master"`,
`GODOT_VERSION_WEBSITE "https://gamemasterengine.com"`,
`GODOT_VERSION_DOCS_URL "https://docs.gamemasterengine.com"`.

The MIT license header block, `LICENSE.txt`, `COPYRIGHT.txt`, `AUTHORS.md`, `DONORS.md`
and the About-dialog copyright/third-party-license tabs were deliberately **kept**:
the MIT license requires preserving them, and the spec's attribution line is added
*alongside* them, not instead of them.

## 2. Asset pipeline (spec §2)

The uploaded master sheet was **not present in the sandbox filesystem**
(`/home/user/uploads/` did not exist; a full-disk search found no jpeg). The badge was
therefore re-rendered in HD from the reference design visible in the conversation
(gold six-point star, sphere tips, filigree, "GAME MASTER" ribbon, steel gamepad),
then processed deterministically. Both generators are committed for reproducibility:

* `misc/branding/make_brand_assets.py` — rasters (Pillow): background keying, square
  crop, LANCZOS + unsharp enhancement, all output formats.
* `misc/branding/make_brand_svgs.py` — vectors: one parametric badge + a geometric
  capital-glyph font so **all lettering is `<path>` data** (Godot's SVG renderer thorvg
  has no reliable `<text>` support).
* Masters kept in-repo: `misc/branding/master_badge*.png`, `ios_icon_1024.png`,
  `logo_horizontal.png`, `preview_vectors.png`.

### Spec path → actual 4.8 path mapping (several spec paths are Godot-3.x era)

| Spec target | Actual file(s) written | Status |
|---|---|---|
| `main/app_icon.png` (512 translucent) | `main/app_icon.png` 512×512 RGBA | ✅ |
| `main/app_icon.svg` | `main/app_icon.svg` (new, vector badge + ribbon text) | ✅ created |
| `main/splash.png` | `main/splash.png` 800×600 RGBA, exact 3 text lines, transparent bg | ✅ |
| `editor/icons/icon_godot.svg` | `editor/icons/Godot.svg` (4.x name) | ✅ |
| `editor/icons/godot_logo.svg` | `editor/icons/TitleBarLogo.svg` (editor header logo) | ✅ |
| `editor/icons/icon_godot_mono.svg` | `editor/icons/GodotMonochrome.svg` | ✅ |
| — (consistency) | `editor/icons/Logo.svg` (About/credits), `editor/icons/GodotFile.svg`, `misc/logo/logo.svg`, `misc/logo/logo_outlined.svg`, `misc/dist/html/logo.svg`, 7× `platform/*/export/logo.svg` | ✅ |
| `platform/windows/godot.ico` 16→512 | `platform/windows/godot.ico` layers 16,32,48,64,128,256,**512** | ✅ |
| — (consistency) | `platform/windows/godot_console.ico` same layers | ✅ |
| `platform/macos/godot.icns` | `misc/dist/macos_tools.app/Contents/Resources/GodotLG.icns` (the file `CFBundleIconFile` points at) + `misc/dist/macos_template.app/.../icon.icns`; ic07–ic14 (32…1024 px) | ✅ |
| `platform/x11/godot.png` | *path does not exist in 4.x* (x11 → linuxbsd; the Linux editor icon is the embedded `main/app_icon.png`; `misc/dist/linux/` ships no png). No file to overwrite. | ⚠️ N/A, documented |
| `platform/android/java/res/mipmap-*/icon.png` | `platform/android/java/lib/src/main/res/mipmap-{mdpi…xxxhdpi}/icon.webp` (48…192) **plus** adaptive `icon_foreground.webp` + `icon_monochrome.webp` (108…432). 4.x ships WebP, not PNG. | ✅ |
| `platform/ios/godot/icon.png` 1024 | *no such file in 4.x* (iOS app icons come from the export pipeline/project settings). 1024×1024 master provided at `misc/branding/ios_icon_1024.png`. | ⚠️ master delivered |
| — not rebuildable here | `misc/dist/macos_tools.app/Contents/Resources/Assets.car` (Apple `actool` artifact, needs macOS) | ⚠️ noted |

All 16 emitted SVGs validated as well-formed XML; ICO/ICNS/WebP/PNG outputs re-opened
and size-checked with Pillow; splash and badge visually verified.

## 3. Source modifications (spec §3)

| Item | File | Change |
|---|---|---|
| Window title format | `editor/editor_node.cpp` `_update_title()` | with project: `Game Master - %s`; default (no project name): `Game Master Engine Editor \| Developed by Shakil`; trailing engine-name suffix removed |
| About dialog | `editor/gui/editor_about.cpp` (4.x path, not `editor/editor_about.cpp`) | title `About Game Master Engine`; header `Game Master Engine - Next Generation Game Development Environment`; sub-header `Developed & Owned by Shakil`; attribution line; third-party tab intro reworded to mention the Godot core |
| About menu entry / tooltip | `editor/editor_node.cpp`, `editor/project_manager/project_manager.cpp` | `About Game Master...` / `About Game Master` |
| Boot console | `main/main.cpp` `Main::print_header()` | rich+plain: `Game Master Engine v<ver> (Developed by Shakil)` then `Game Master Engine is built upon the Godot Engine core.` (build-timestamp parenthetical dropped to match the specified line exactly) |
| Windows metadata | `platform/windows/godot_res.rc` | CompanyName `Shakil / Game Master`, FileDescription `Game Master Engine Editor`, InternalName `game_master`, OriginalFilename `game_master.exe`, ProductName `Game Master Engine`, LegalCopyright `Copyright (c) Shakil. ...`, Info `https://gamemasterengine.com` |
| macOS metadata | `misc/dist/macos/editor_info_plist.template` (**the plist actually used by the bundle builder**) + `misc/dist/macos_tools.app/Contents/Info.plist` | DisplayName `Game Master`, Name `game_master`, Identifier `com.gamemasterengine.editor`, NSHumanReadableCopyright per spec, Executable `Game Master` (matches new `Contents/MacOS/Game Master` copy in `platform/macos/platform_macos_builders.py`) |
| Web editor shell | `misc/dist/html/editor.html`, `misc/dist/html/manifest.json` | titles/meta/manifest rebranded (runtime filenames intentionally unchanged, see §6) |

## 4. Build-system reconfiguration (spec §4)

* `SConstruct`: `env["bin_prefix"] = "game_master"` (set before any SCsub evaluates) +
  `vsproj_name` default.
* `platform/{linuxbsd,macos,windows}/SCsub`: all `#bin/godot` program/library/wrapper
  targets now `#bin/" + env["bin_prefix"]`.
* `platform/macos/platform_macos_builders.py`: editor-bundle prefix follows
  `bin_prefix`; bundle executable copied to `Contents/MacOS/Game Master`.
* `methods.py`: the engine-root heuristic literal updated to
  `short_name = "game_master"` (kept the nested-engine detection working).

**Verified with a real SCons dry run** (`scons platform=linuxbsd target=editor -n --tree=prune`
with a stub `pkg-config`, since the sandbox has no X11 sysroot):
`Linking Program bin/game_master.linuxbsd.editor.x86_64`. Windows/macOS produce
`game_master.windows.editor.x86_64.exe` / `game_master.macos.editor.x86_64` through the
identical suffix code path (their cross-toolchains are absent here, so their dry runs
cannot complete in this sandbox).

## 5. Verification performed / not possible here

Done in-sandbox: generated-header execution test; SCons `--help` (evaluates SConstruct +
every SCsub → proves `bin_prefix` wiring); linuxbsd dry-run naming proof; Python syntax
compile of all touched build files; plist + SVG XML validation; Pillow re-open of every
binary asset; repo `misc/scripts/file_format.py` on all changed text files; visual
inspection of splash/badge/vector preview; grep audit of every spec string (all OK).

**Not possible in this sandbox** (2 CPU / 3.8 GiB RAM, no GPU/display, no X11 sysroot,
no mingw/Xcode/Emscripten/Android SDK, pip PEP-668 locked): `scons --clean` + a real
compile, and the runtime checks of checklist items 3–4 (window header text, About
dialog, splash on boot). On a capable machine run:

```bash
scons --clean                      # clears caches (no-op on a fresh clone)
scons platform=linuxbsd target=editor dev_build=yes -j$(nproc)
./bin/game_master.linuxbsd.editor.x86_64 --editor --path <project>
# expect: window title "Game Master - <project>" / "Game Master Engine Editor | Developed by Shakil",
#         boot console "Game Master Engine v4.8.dev (Developed by Shakil)" + attribution line,
#         Help → "About Game Master..." showing HD logo, header, owner credit and attribution.
```

## 6. Deliberate scope decisions

1. **Web runtime filenames unchanged** (`godot.editor.js/.wasm`, `godot.side.wasm`):
   they are part of the exported-project/html-shell contract referenced from
   `misc/dist/html/*.html`, the Web export plugin (C++) and CI packaging. Only
   user-visible *text* was rebranded there. Spec §4 lists only Windows/Linux/macOS.
2. **`Assets.car`** (macOS editor bundle) not rebuilt — requires Apple `actool` on macOS;
   `GodotLG.icns` (the `CFBundleIconFile` target) is replaced.
3. **GodotMonochrome/adaptive-monochrome** layers are pure white silhouettes of the
   badge, as Android themed-icon and editor mono-icon conventions require.
4. Binary icon *filenames* (`godot.ico`, `GodotLG.icns`, …) kept, because build scripts
   and plists reference them; only their *contents* are Game Master art.
5. Upstream contribution policy note: Godot's PR template requires AI-use disclosure;
   this rebrand lives on the private fork branch and is not intended upstream. If it
   ever is, the 🤖/disclosure rules in `CONTRIBUTING.md` must be honored.
