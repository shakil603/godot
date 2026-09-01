# Brand identity of this fork. These four values are the single source of truth for every
# user-visible engine name: the console banner, window titles, the project manager, the
# editor's About dialog, the Vulkan application name, the PulseAudio context name and the
# per-platform user data directories all read from here (see core/core_builders.py).
#
# short_name is also used for file-system paths:
#   * Linux/BSD:   ~/.local/share/<short_name>, ~/.config/<short_name>, ~/.cache/<short_name>
#   * Windows:     <short_name>.capitalize() -> "Game Master" (OS_Windows::get_godot_dir_name)
#   * macOS:       ~/Library/Application Support/<short_name>
# Renaming it moves the editor settings and the export templates folder, so after the first
# build copy the old ones over:
#   cp -r ~/.local/share/godot/export_templates ~/.local/share/game_master/export_templates
#
# What deliberately keeps the upstream name, because it is a protocol identifier and not
# branding: `project.godot`, the `.godot/` project data folder, the `godot` executable name,
# `https://godotengine.org` links (still the canonical home of the code this fork builds on),
# the class/macro identifiers (GodotPhysics2D, GODOT_VERSION_*), the `Godot` JS class used to
# embed the web build, and the MIT copyright headers in every source file.
short_name = "game_master"
name = "Game Master"
major = 4
minor = 8
patch = 0
status = "dev"
module_config = ""
website = "https://github.com/shakil603/godot"
docs = "latest"
