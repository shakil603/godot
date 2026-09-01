# Game Master

<p align="center">
  <img src="misc/logo/game_master_logo_wide.png" width="620" alt="Game Master logo">
</p>

**Game Master is a personal fork of [Godot Engine](https://godotengine.org) that carries its
own brand: name, app icon, boot splash and the per-platform icon sets.** The engine itself is
the upstream code base, kept as close to it as possible so that upstream fixes can still be
merged.

Everything a game needs is here: a feature-packed, cross-platform engine to create 2D and 3D
games from a unified interface, with a comprehensive set of [common tools][upstream-features].
Games export with one click to desktop (Linux, macOS, Windows), mobile (Android, iOS) and the
Web.

## What this fork changes, and what it deliberately does not

Renamed (branding only):

- `version.py` - engine name, short name and the URL printed in the console banner, which
  feeds window titles, the About dialog, the project manager and the user data directories.
- The shipped brand artwork: `main/app_icon.png`, `main/splash.png`, `main/splash_editor.png`,
  `misc/logo/*`, the Web editor's `logo.svg`, the Windows `.ico`, the macOS `.icns`, the Linux
  hicolor icon theme, and a full Android/iOS/Web launcher-icon set under `misc/brand/`.
- Prose in `README.md`, the class-reference XML and `misc/dist/` file descriptions.

**Kept as-is on purpose**, because they are wire/file formats or ABI, not branding:

| Kept | Why renaming it would hurt |
|---|---|
| `project.godot`, the `.godot/` folder | every existing project and add-on would stop opening |
| the `godot` executable name and `bin/godot.*` | build scripts, CI, `--help` examples, `.desktop` `Exec=` |
| `Godot` C++ class names, `GODOT_VERSION_*` macros | an API break for GDExtension and C# bindings |
| the `Godot` JS class in `platform/web/js/` | breaks every exported Web build's HTML shell |
| MIT copyright headers, `AUTHORS.md`, `LICENSE.txt` | legal attribution of the upstream authors |
| `org.godotengine.*` ids, WM_CLASS, Wayland app id | desktop integration: icon grouping, .desktop matching |
| `*.po` translations | msgids must match the source strings they translate |

The rename is driven by a script with those rules encoded, so it can be re-run safely:

```console
./misc/scripts/rebrand_game_master.py --scope docs,dist          # report
./misc/scripts/rebrand_game_master.py --scope docs,dist --apply  # write
./misc/scripts/rebrand_game_master.py --why "Godot Engine"       # rebrand:keep - explain one match
```

## Brand assets

`misc/logo/game_master_source.jpg` is the only artwork to edit. Every other image is derived
from it, at the sizes each platform actually requires (adaptive Android layers with the 66%
safe zone, iOS sizes without alpha, maskable PWA icons, HiDPI ladders for desktop):

```console
./misc/scripts/game_master_assets.py             # regenerate everything (needs: pip install pillow numpy)
./misc/scripts/game_master_assets.py --check     # validate the tree; also catches a JPEG saved as .png
./misc/scripts/game_master_assets.py --preview   # render misc/brand/preview.png and eyeball small sizes
```

`misc/brand/` also holds the per-project icons to point the export presets at - see
`misc/brand/README.md`.

## Getting the engine

There are no published binaries for this fork yet; build it from source:

```console
scons platform=linuxbsd target=editor
```

Compilation instructions for every supported platform are in the
[upstream docs][upstream-compiling]. The resulting binary is still named `godot` (see the
table above), so `./bin/godot.linuxbsd.editor.x86_64`.

## Documentation, community and credits

The manual, the class reference and the community channels belong to upstream Godot, and this <!-- rebrand:keep -->
fork does not pretend otherwise:

- Documentation: [docs.godotengine.org][upstream-docs] (also reachable from the editor's Help
  menu, and generated from the `doc/classes/*.xml` files in this repository).
- Community channels: [godotengine.org/community][upstream-community].
- Engine history and original authors: [Juan Linietsky](https://github.com/reduz) and
  [Ariel Manzur](https://github.com/punto-), who developed the engine in-house before it was
  open sourced in [February 2014](https://github.com/godotengine/godot/commit/0b806ee0fc9097fa7bda7ac0109191c9c5e0a1ac).
  See `AUTHORS.md` and `DONORS.md`; the license is MIT (`LICENSE.txt`).

Contributions to this fork follow the upstream process described in
[CONTRIBUTING.md](CONTRIBUTING.md) - it is left unmodified, because its links, review rules
and bug-report templates point at upstream, which is where engine fixes should come from.

[upstream-features]: https://godotengine.org/features
[upstream-docs]: https://docs.godotengine.org
[upstream-compiling]: https://docs.godotengine.org/en/latest/engine_details/development/compiling
[upstream-community]: https://godotengine.org/community
