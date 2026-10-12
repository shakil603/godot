#!/usr/bin/env bash

# Generate the .ico, .icns and .zip icon set used for Steam and Linux packages.
#
# All artwork comes from the single brand banner (misc/logo/*.jpeg) through
# misc/scripts/make_branding.py, so the icons always match the engine branding.

set -e

CURDIR="$(cd "$(dirname "$0")" && pwd)"
OUTDIR="${1:-.}"

mkdir -p "$OUTDIR"
python3 "$CURDIR/make_branding.py" --steam-icons "$OUTDIR"

echo "Wrote icon16..icon1024.png, godot-icon.ico, godot-icon.icns and godot-icons.zip to $OUTDIR"
