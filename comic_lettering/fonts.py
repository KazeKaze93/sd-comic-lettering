"""Font discovery: the user's fonts/ folder, the bundled fonts, then a few system fonts."""
import os
from functools import lru_cache
from typing import Dict

from PIL import ImageFont

FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")
BUNDLED_DIR = os.path.join(FONTS_DIR, "bundled")
EXTENSIONS = (".ttf", ".otf", ".ttc")

# Display name -> file name in the system font folder.
SYSTEM_FONTS = [
    ("Comic Sans MS Bold", "comicbd.ttf"),
    ("Comic Sans MS", "comic.ttf"),
    ("Ink Free", "Inkfree.ttf"),
    ("Segoe Print Bold", "segoeprb.ttf"),
    ("Segoe Print", "segoepr.ttf"),
    ("Segoe Script Bold", "segoescb.ttf"),
    ("MV Boli", "mvboli.ttf"),
    ("Impact", "impact.ttf"),
    ("Arial Black", "ariblk.ttf"),
]


def _system_dirs():
    dirs = []
    windir = os.environ.get("WINDIR")
    if windir:
        dirs.append(os.path.join(windir, "Fonts"))
    dirs.extend(["/usr/share/fonts", "/usr/local/share/fonts", "/Library/Fonts",
                 os.path.expanduser("~/.fonts"), os.path.expanduser("~/Library/Fonts")])
    return [d for d in dirs if os.path.isdir(d)]


def _display_name(path):
    """Family and style from the font itself, e.g. "Balsamiq Sans Bold"."""
    try:
        family, style = ImageFont.truetype(path, 12).getname()
    except (OSError, IOError):
        return None
    if not family:
        return os.path.splitext(os.path.basename(path))[0]
    return family if not style or style.lower() == "regular" else "%s %s" % (family, style)


def _scan(directory, fonts):
    if not os.path.isdir(directory):
        return
    for name in sorted(os.listdir(directory)):
        if name.lower().endswith(EXTENSIONS):
            path = os.path.join(directory, name)
            display = _display_name(path)
            if display and display not in fonts:
                fonts[display] = path


@lru_cache(maxsize=1)
def _list_fonts_cached(stamp):
    fonts = {}
    _scan(FONTS_DIR, fonts)      # fonts the user dropped in come first
    _scan(BUNDLED_DIR, fonts)    # then the ones shipped with the repo
    for directory in _system_dirs():
        for display, filename in SYSTEM_FONTS:
            path = os.path.join(directory, filename)
            if display not in fonts and os.path.isfile(path):
                fonts[display] = path
    return fonts


def list_fonts():
    # type: () -> Dict[str, str]
    """Display name -> path. Rescanned when a font folder changes."""
    stamp = tuple(os.path.getmtime(d) if os.path.isdir(d) else 0 for d in (FONTS_DIR, BUNDLED_DIR))
    return _list_fonts_cached(stamp)


DEFAULT_FONT = "Comic Relief Bold"  # bundled, covers Latin and Cyrillic


def font_names():
    """Font names for a dropdown, the default one first."""
    names = list(list_fonts().keys())
    if DEFAULT_FONT in names:
        names.remove(DEFAULT_FONT)
        names.insert(0, DEFAULT_FONT)
    return names or ["default"]


@lru_cache(maxsize=256)
def load_font(name, size):
    path = name if os.path.isfile(name) else list_fonts().get(name)
    size = max(4, int(size))
    if path:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            pass
    try:
        return ImageFont.load_default(size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()
