# Branding assets

This engine is branded **Legend of the Game Engine**, using the artwork in
[`bfeee0f4-dd7a-48b1-be04-ebff9bc1417a.jpeg`](bfeee0f4-dd7a-48b1-be04-ebff9bc1417a.jpeg)
as the single source of truth.

Everything in this folder is an icon or logo surface that the engine ships
(window icon, editor logo, project manager wordmark, splash screens, platform
app icons, package icon bundles), and everything is generated from that one
picture so the branding cannot drift apart.

## Files

| File | Purpose |
| --- | --- |
| `bfeee0f4-...jpeg` | Source artwork. The emblem (gear + winged "V" + crystal) is cropped out of it for square icon surfaces. |
| `icon.png`, `icon_outlined.png` | Round emblem and the emblem on its background. |
| `logo.png`, `logo_outlined.png` | Wide banner artwork (with and without the dark plate). |
| `icon.svg`, `icon_outlined.svg`, `logo.svg`, `logo_outlined.svg` | Editor-facing variants. Godot's SVG loader renders embedded raster images (`modules/svg/SCsub` enables `THORVG_FILE_IO_SUPPORT`), so the artwork is embedded as a data URI instead of being redrawn as vector shapes. |

## Regenerating

All branded assets in the repository (not just this folder) are produced by:

```sh
python3 misc/scripts/make_branding.py
```

Replace the JPEG above with new artwork that keeps the same framing and re-run
the script to re-brand the whole engine.

The Steam/Linux icon bundle (`icon16.png` … `icon1024.png`, `godot-icon.ico`,
`godot-icon.icns`, `godot-icons.zip`) is written to an output directory on
demand:

```sh
bash misc/scripts/make_icons.sh /tmp/godot-icons
```

## Licensing note

[`LICENSE.txt`](LICENSE.txt) is the upstream Creative Commons Attribution 4.0
notice for the original Godot Engine logo by Andrea Calabró. The files listed
above are no longer that artwork; the notice is kept for the historical
branding and for the engine's MIT licensing obligations.
