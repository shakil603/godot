# Game Master

<p align="center">
  <img src="misc/logo/game_master_logo_wide.png" width="620" alt="Game Master logo">
</p>

**Game Master** is a complete 2D and 3D game creation studio. Black, white and gold
branding. One editor, one-click export to desktop, mobile and the Web.

The runtime is the same battle-tested engine used by thousands of shipped games;
everyday users only see **Game Master**.

## Build

```console
scons platform=linuxbsd target=editor
```

The editor binary is produced under `bin/`. Compilation notes for every platform
are in this repository under `doc/` and `platform/`.

## Brand

Name, window titles, splash, icons and the default editor theme (black / gold /
white) come from `version.py` and `editor/themes/`. File formats and internal
IDs stay compatible with existing projects so nothing breaks when you open a
game.

## License

MIT. See `LICENSE.txt`, `AUTHORS.md` and `DONORS.md`.
