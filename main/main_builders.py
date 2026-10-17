"""Functions used to generate source files during build time"""

import methods


def make_splash(target, source, env):
    buffer = methods.get_buffer(str(source[0]))

    with methods.generated_wrapper(str(target[0])) as file:
        # Matches the dark background of the branded boot splash artwork.
        file.write(f"""\
#include "core/math/color.h"

static const Color boot_splash_bg_color = Color(0.055, 0.067, 0.086);
inline constexpr const unsigned char boot_splash_png[] = {{
	{methods.format_buffer(buffer, 1)}
}};
""")


def make_splash_editor(target, source, env):
    buffer = methods.get_buffer(str(source[0]))

    with methods.generated_wrapper(str(target[0])) as file:
        # Matches the dark background of the branded boot splash artwork.
        file.write(f"""\
#include "core/math/color.h"

static const Color boot_splash_editor_bg_color = Color(0.055, 0.067, 0.086);
inline constexpr const unsigned char boot_splash_editor_png[] = {{
	{methods.format_buffer(buffer, 1)}
}};
""")


def make_app_icon(target, source, env):
    buffer = methods.get_buffer(str(source[0]))

    with methods.generated_wrapper(str(target[0])) as file:
        # Use a neutral gray color to better fit various kinds of projects.
        file.write(f"""\
inline constexpr const unsigned char app_icon_png[] = {{
	{methods.format_buffer(buffer, 1)}
}};
""")
