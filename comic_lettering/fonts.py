"""Font discovery: the repo's fonts/ folder plus a few comic-looking system fonts."""
import os
from functools import lru_cache
from typing import Dict

from PIL import ImageFont

FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")

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


def list_fonts():
    # type: () -> Dict[str, str]
    """Display name -> path. Fonts dropped into fonts/ come first."""
    fonts = {}
    if os.path.isdir(FONTS_DIR):
        for name in sorted(os.listdir(FONTS_DIR)):
            if name.lower().endswith((".ttf", ".otf", ".ttc")):
                fonts[os.path.splitext(name)[0]] = os.path.join(FONTS_DIR, name)
    for directory in _system_dirs():
        for display, filename in SYSTEM_FONTS:
            path = os.path.join(directory, filename)
            if display not in fonts and os.path.isfile(path):
                fonts[display] = path
    return fonts


def font_names():
    names = list(list_fonts().keys())
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
