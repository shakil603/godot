# Game Master brand kit

Everything here is generated - do not edit the files by hand. To change the brand artwork,
replace `misc/logo/game_master_source.jpg` and run:

```console
./misc/scripts/game_master_assets.py
```

`misc/brand/preview.png` renders the whole ladder on dark and light backdrops so the small
sizes can be checked in one look (`--preview` regenerates it).

## What the engine already embeds

| File | Used by |
|---|---|
| `main/app_icon.png` | Editor window/taskbar icon; the fallback icon for exported projects (`main/main.cpp` sets it via `DisplayServer::window_set_icon`) |
| `main/splash.png` | Boot splash for exported templates |
| `main/splash_editor.png` | Boot splash for the editor and the project manager |
| `misc/dist/html/logo.svg` | Loading screen of the Web editor and of exported Web builds |
| `misc/dist/macos_template.app/Contents/Resources/icon.icns` | macOS app bundle icon |

All five must be real 8-bit RGBA PNGs (except the SVG) at the sizes listed in
`misc/scripts/game_master_assets.py`. `--check` enforces that, including the failure mode
that bit this repository once: a JPEG saved with a `.png` name, which the engine's PNG loader
silently refuses to decode.

## For your own projects (this is the part that matters on phones)

The engine cannot ship launcher icons for the games you export - each project supplies its
own. Point the export presets at these files and every density/variant is generated for you:

### Android (`Platform > Android > Icons`)

| Preset option | File |
|---|---|
| `launcher_icons/main_192x192` | `misc/brand/android/main_192x192.png` |
| `launcher_icons/adaptive_foreground_432x432` | `misc/brand/android/adaptive_foreground_432x432.png` |
| `launcher_icons/adaptive_background_432x432` | `misc/brand/android/adaptive_background_432x432.png` |
| `launcher_icons/adaptive_monochrome_432x432` | `misc/brand/android/adaptive_monochrome_432x432.png` |
| `splash_screen/icon` | `misc/brand/android/splash_xxxhdpi_432x432.png` (use the density that matches your target; `mdpi`-`xxxhdpi` are all present) |
| `splash_screen/background_color` | `#181A23` |

The adaptive layers are already inside the 66% safe zone, so no launcher (circle, squircle,
rounded square) can clip the star. The monochrome layer is white-with-alpha, which is what
Android's themed icons require - leave `adaptive_monochrome` unset and themed icons fall back
to the plain icon.

### iOS and visionOS (`Platform > iOS > Icons`)

| Preset option | File |
|---|---|
| `icons/app_store_1024x1024` | `misc/brand/ios/app_store_1024x1024.png` |
| `icons/iphone_120x120`, `icons/iphone_180x180` | `misc/brand/ios/iphone_*.png` |
| `icons/ipad_152x152`, `icons/ipad_167x167` | `misc/brand/ios/ipad_*.png` |
| `icons/spotlight_*`, `icons/settings_*`, `icons/notification_*`, `icons/ios_*` | the matching file in `misc/brand/ios/` |

Every iOS file here is flattened on an opaque background: the App Store rejects icons with an
alpha channel, and iOS applies its own mask, so do not add rounded corners yourself.

### Web (`Platform > Web`)

| Need | File |
|---|---|
| `application/config/icon` | `misc/brand/web/icon-512.png` |
| PWA maskable icon | `misc/brand/web/maskable-icon-512.png` |
| `apple-touch-icon` | `misc/brand/web/apple-touch-icon.png` (180px, opaque) |
| favicon | `misc/brand/web/favicon.ico` (16/24/32/48) and `favicon.png` (256) |

Godot regenerates `<name>.icon.png` and `<name>.apple-touch-icon.png` at export time from
`application/config/icon`, so a single square source is enough - the extra sizes are for
hosting the PWA manifest yourself.

### Desktop

| Need | File |
|---|---|
| Windows installer/exe icon | `misc/brand/windows/game-master.ico` (16-256, PNG-compressed) |
| macOS bundle icon | `misc/brand/macos/game-master.icns` |
| Linux icon theme | install `misc/brand/linux/hicolor/*` under `~/.local/share/icons/hicolor/`, then run `gtk-update-icon-cache ~/.local/share/icons/hicolor` |

`misc/dist/linux/org.godotengine.Godot.desktop` still says `Icon=godot`, and that is a
deliberate choice rather than an oversight: the icon name is looked up in the icon theme, so
keeping `godot` means the entry works whether or not the hicolor set above is installed. If
you would rather have the branded name there, change `Icon=` to `game-master` *and* install
the theme files together, otherwise the launcher shows a generic fallback icon. The same file
keeps `Exec=godot` and `StartupWMClass=Godot`, which must match the real binary name and the
WM_CLASS the engine sets at runtime (`platform/linuxbsd/x11/display_server_x11.cpp`).

### Boot splash (Project Settings > Application > Boot Splash)

| Setting | Suggested value |
|---|---|
| `application/boot_splash/image` | `misc/brand/splash/boot_splash.png` (square) or `boot_splash_wide.png` (16:9) |
| `application/boot_splash/bg_color` | `#181A23` |
| `application/boot_splash/stretch_mode` | `Keep` for the square, `Keep Width` for the wide one |
| `application/boot_splash/use_filter` | `true` (linear filtering - this is what stops the splash from aliasing on 4K and phone screens) |
| `application/boot_splash/minimum_display_time` | `0`-`1000` ms, only to avoid a flash on fast loads |

Why the square variant is the safe default: the splash is drawn once into the boot window at
whatever size that window ends up being, before any project script runs. A square image with
`Keep` looks right on a phone in portrait, a 21:9 monitor and everything between; a fixed
16:9 banner letterboxes or gets cropped on the extremes.
