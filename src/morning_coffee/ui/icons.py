"""Icon-font registration for morning-coffee.

Kivy's SDL2 text provider cannot render color emoji, so we use bundled monochrome
icon fonts: "Weather Icons" (Erik Flowers, SIL OFL 1.1) for weather conditions, and
a small subset of Font Awesome 6 Free Solid (icons CC BY 4.0) for UI glyphs such as
the title's coffee mug and the "mark read" checkmark.

Integrations reference weather glyphs by codepoint and set ``FeedItem.icon`` /
``FeedItem.icon_font`` (see ``integrations/weather.py``). UI code uses ``ICON_FONT``
with the named glyph constants below (``COFFEE_GLYPH``, ``CHECK_GLYPH``).
"""

from __future__ import annotations

from importlib.resources import files

from kivy.core.text import LabelBase

WEATHER_FONT = "weathericons"
ICON_FONT = "iconfont"

# Font Awesome 6 Free Solid glyphs (in the bundled icons.ttf subset).
COFFEE_GLYPH = "\uf7b6"  # mug-hot
CHECK_GLYPH = "\uf00c"  # check
CARET_UP_GLYPH = "\uf0d8"  # caret-up (upvote)
CARET_DOWN_GLYPH = "\uf0d7"  # caret-down (downvote)
GEAR_GLYPH = "\uf013"  # gear (settings)

# name -> bundled ttf, all under this package's assets/ dir.
_FONT_FILES = {
    WEATHER_FONT: "assets/weathericons-regular-webfont.ttf",
    ICON_FONT: "assets/icons.ttf",
}

_registered = False


def register_fonts() -> None:
    """Register bundled icon fonts with Kivy. Idempotent and failure-tolerant.

    A missing/unreadable font must never crash the app: labels simply fall back
    to rendering the raw glyph (a blank box) instead of the icon.
    """
    global _registered
    if _registered:
        return
    for name, rel_path in _FONT_FILES.items():
        try:
            font_path = files("morning_coffee").joinpath(rel_path)
            LabelBase.register(name=name, fn_regular=str(font_path))
        except Exception:  # noqa: BLE001 - icons are cosmetic; never fail startup
            pass
    _registered = True
