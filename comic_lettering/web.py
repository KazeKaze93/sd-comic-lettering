"""HTTP side of the editor in A1111 / Forge / reForge: settings, sessions and the routes
the React page (ui/) talks to. The core does not import this module; only the host script does.
"""
import datetime
import io
import json
import os
import re
import threading
import time
import uuid
from collections import OrderedDict
from typing import Dict, List, Optional

from PIL import Image, PngImagePlugin

from .core import PLACEMENTS, arrange, draw
from .fonts import font_names, list_fonts
from .render import BUBBLE_SHAPES, BUBBLE_THEMES, EXTRAS, MOODS, PALETTES, TAILS, Style

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_FILE = os.path.join(BASE_DIR, "user_settings.json")
EXTENSION = os.path.basename(BASE_DIR)
SAME_FONT = "same as bubbles"
SFX_FONT = "Bangers"
# Marks that are drawn as shapes; the page offers buttons for them, since a keyboard cannot type them.
SYMBOLS = [
    u"♥", u"♡", u"💕", u"💔", u"💋",
    u"★", u"☆", u"✦", u"✨", u"💥",
    u"💢", u"⚡", u"🔥",
    u"💧", u"💦", u"♨", u"💨",
    u"〃", u"〰", u"🌀", u"💤",
    u"♪", u"♫", u"✿", u"🌙", u"☀",
    u"♂", u"♀", u"✖", u"○",
    u"→", u"←", u"↑", u"↓", u"♦", u"♠", u"♣",
]

# The look, remembered between sessions.
DEFAULTS = {
    "placement": "auto", "font": "", "spill": True, "uppercase": True, "erase": True,
    "bubble_size": 9.0, "bubble_min_size": 1.5, "free_size": 5.5, "text_color": "auto",
    "stroke_color": "auto", "stroke_width": 0.12, "shadow": 0.5, "jitter": 0.3, "arc": 0.0,
    "rotation": 0.0, "soften": 0.4, "grain": 0.0, "opacity": 1.0, "margin": 0.08,
    "white_threshold": 120, "seed": 0,
    "sfx_font": "", "sfx_size": 7.0, "sfx_color": "auto", "sfx_tilt": 15.0, "sfx_opacity": 0.95,
    "sfx_seed": 0,
    "caption_font": SAME_FONT, "bubble_colors": "auto", "caption_colors": "auto",
    "sfx_colors": "auto", "bubble_mood": "calm", "caption_mood": "calm", "sfx_mood": "shout",
    "caption_extras": "none", "sfx_extras": "none", "caption_bubble": "none",
    "caption_bubble_theme": "light", "caption_tail": "none", "size_jitter": 0.0,
    "line_tilt": 0.0, "line_shift": 0.0, "rough": 0.0, "line_spacing": 1.08,
}
# Lists a saved value must belong to; anything else falls back to the default.
CHOICES = {
    "placement": PLACEMENTS, "bubble_colors": list(PALETTES), "caption_colors": list(PALETTES),
    "sfx_colors": list(PALETTES), "bubble_mood": list(MOODS), "caption_mood": list(MOODS),
    "sfx_mood": list(MOODS), "caption_extras": list(EXTRAS), "sfx_extras": list(EXTRAS),
    "caption_bubble": BUBBLE_SHAPES, "caption_bubble_theme": BUBBLE_THEMES,
    "caption_tail": list(TAILS),
}
# What is lettered onto every new image while it is generated, when switched on.
AUTO_DEFAULTS = {"enabled": False, "text": "", "caption": "", "sfx": ""}
AUTO_KEY = "_auto"

_lock = threading.Lock()
_sessions = OrderedDict()  # type: OrderedDict
MAX_SESSIONS = 6
# The images of the last generation before any lettering, per tab ("txt2img", "img2img").
LAST_CLEAN = {}  # type: Dict[str, List[Image.Image]]
# Counts the generations per tab, so the page can tell an image it already has from a new one.
GENERATION = {}  # type: Dict[str, int]


def begin_generation(tab):
    """Forget the images of the previous generation of a tab."""
    LAST_CLEAN[tab] = []
    GENERATION[tab] = GENERATION.get(tab, 0) + 1


# ---------------------------------------------------------------- settings

def clean_values(values):
    """Make every value usable: known fonts, known list entries, the right number types."""
    fonts = font_names()
    if values.get("font") not in fonts:
        values["font"] = fonts[0]
    if values.get("sfx_font") not in fonts:
        values["sfx_font"] = SFX_FONT if SFX_FONT in fonts else fonts[0]
    if values.get("caption_font") not in fonts:
        values["caption_font"] = SAME_FONT
    for key, allowed in CHOICES.items():
        if values.get(key) not in allowed:
            values[key] = DEFAULTS[key]
    for key in ("seed", "sfx_seed", "white_threshold"):
        values[key] = int(values.get(key) or 0)
    return values


def merge_values(given):
    """The defaults overlaid with what is given, as far as the types agree."""
    values = dict(DEFAULTS)
    for key in DEFAULTS:
        if key not in (given or {}):
            continue
        value = given[key]
        if isinstance(DEFAULTS[key], bool):
            if isinstance(value, bool):
                values[key] = value
        elif isinstance(DEFAULTS[key], float):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values[key] = float(value)
        elif isinstance(DEFAULTS[key], int):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values[key] = int(value)
        elif isinstance(value, type(DEFAULTS[key])) or isinstance(value, str):
            values[key] = value
    return clean_values(values)


def _read_file():
    try:
        with io.open(SETTINGS_FILE, encoding="utf-8") as handle:
            saved = json.load(handle)
        return saved if isinstance(saved, dict) else {}
    except (IOError, OSError, ValueError):
        return {}


def load_settings():
    return merge_values(_read_file())


def load_auto():
    auto = dict(AUTO_DEFAULTS)
    saved = _read_file().get(AUTO_KEY)
    if isinstance(saved, dict):
        auto["enabled"] = bool(saved.get("enabled"))
        for key in ("text", "caption", "sfx"):
            if isinstance(saved.get(key), str):
                auto[key] = saved[key]
    return auto


def save_settings(values, auto=None):
    """Write the look and, when given, what is lettered onto new images."""
    with _lock:
        data = dict(merge_values(values))
        data[AUTO_KEY] = auto if auto is not None else load_auto()
        try:
            with io.open(SETTINGS_FILE, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(data, indent=2, sort_keys=True))
        except (IOError, OSError):
            pass


def make_style(s):
    style = Style()
    for key, value in s.items():
        if key in ("placement", "spill", "erase", "white_threshold"):
            continue  # arguments of arrange(), not style options
        if hasattr(style, key):
            setattr(style, key, value)
    if s["caption_font"] == SAME_FONT:
        style.caption_font = ""
    return style


def make_scene(image, text, caption, numbers, s, sfx="", pins=None, regions=None):
    return arrange(image, text, caption=caption, spill=s["spill"], placement=s["placement"],
                   style=make_style(s), erase=s["erase"], white_threshold=s["white_threshold"],
                   numbers=numbers, sfx=sfx, pins=pins, regions=regions)


def describe(info):
    """What was done with an image: (message, is it a warning)."""
    message = "Bubbles found: %d, filled: %d%s%s." % (
        info.get("bubbles_found", 0), info.get("bubbles_filled", 0),
        ", plus a caption" if info.get("free_text") else "",
        ", sound effects: %d" % info["sfx"] if info.get("sfx") else "")
    if info.get("characters") is False:
        return (message + " Character detection is off (no ultralytics or no person_yolov8*-seg.pt"
                " found), so text may land on a character.", True)
    return message, False


# ---------------------------------------------------------------- sessions

def new_session(image, name=""):
    """Keep an image to letter; returns the id the page refers to it by."""
    info = image.info.get("parameters") if isinstance(image.info, dict) else None
    session = {"id": uuid.uuid4().hex, "image": image.convert("RGB"), "result": None, "name": name,
               "parameters": info if isinstance(info, str) else None, "version": 0, "png": {}}
    with _lock:
        _sessions[session["id"]] = session
        while len(_sessions) > MAX_SESSIONS:
            _sessions.popitem(last=False)
    return session


def get_session(session_id):
    with _lock:
        session = _sessions.get(session_id)
        if session is not None:
            _sessions.move_to_end(session_id)
        return session


def render_session(session, text, caption, sfx, numbers, settings, pins=None, regions=None):
    """Letter the session's image; returns what the page needs to show the result.

    pins, regions: what was placed and drawn by hand on the page, see arrange().
    """
    s = merge_values(settings)
    scene = make_scene(session["image"], text or "", caption or "", bool(numbers), s, sfx or "", pins, regions)
    result = draw(session["image"], scene)
    with _lock:
        session["result"] = None if scene.get("empty") else result
        session["version"] += 1
        session["png"].pop("result", None)
    message, warning = describe(scene["info"])
    if scene["info"].get("regions"):
        message = message.rstrip(".") + ", areas filled: %d." % scene["info"]["regions"]
    if scene.get("empty"):
        message, warning = "No text: this is the original image.", False
    return {"version": session["version"], "status": message, "warning": warning, "empty": bool(scene.get("empty")),
            "info": scene["info"], "items": scene["items"], "bubbles": scene.get("bubbles", [])}


def session_png(session, which):
    """PNG bytes of the session's original or lettered image, encoded once."""
    image = session["image"] if which == "original" or session["result"] is None else session["result"]
    key = "original" if image is session["image"] else "result"
    with _lock:
        cached = session["png"].get(key)
    if cached is None:
        buffer = io.BytesIO()
        image.save(buffer, "PNG", compress_level=1)
        cached = buffer.getvalue()
        with _lock:
            session["png"][key] = cached
    return cached


def save_session(session, folder):
    """Write the lettered image (or the original, if nothing is lettered) into a folder."""
    image = session["result"] or session["image"]
    os.makedirs(folder, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", os.path.splitext(session["name"] or "")[0]).strip("_")[:40]
    name = "lettered-%s%s.png" % (datetime.datetime.now().strftime("%Y%m%d-%H%M%S"), "-" + stem if stem else "")
    path = os.path.normpath(os.path.join(folder, name))
    extra = None
    if session["parameters"]:
        extra = PngImagePlugin.PngInfo()
        extra.add_text("parameters", session["parameters"])
    image.save(path, "PNG", pnginfo=extra)
    return path


def result_image(session_id):
    # type: (str) -> Optional[Image.Image]
    session = get_session(session_id or "")
    if session is None:
        return None
    return session["result"] or session["image"]


# ---------------------------------------------------------------- routes

def options_payload():
    fonts = font_names()
    return {
        "fonts": fonts, "sameFont": SAME_FONT, "palettes": list(PALETTES), "moods": list(MOODS),
        "extras": list(EXTRAS), "shapes": list(BUBBLE_SHAPES), "themes": list(BUBBLE_THEMES),
        "tails": list(TAILS), "placements": list(PLACEMENTS), "symbols": SYMBOLS,
        "defaults": merge_values({}), "settings": load_settings(), "auto": load_auto(),
    }


def ui_html():
    """The built page with every relative asset address turned into a host file address.

    A fresh ?v= on each call keeps the browser from showing an old build.
    """
    with io.open(os.path.join(BASE_DIR, "ui", "dist", "index.html"), encoding="utf-8") as handle:
        html = handle.read()
    base = "/file=extensions/%s/ui/dist" % EXTENSION
    stamp = str(int(time.time()))

    def swap(match):
        return "%s=%s%s/%s?v=%s%s" % (match.group("attr"), match.group("q"), base, match.group("path")[2:],
                                       stamp, match.group("q"))

    return re.sub(r'(?P<attr>\b(?:src|href))=(?P<q>["\'])(?P<path>\./[^"\']+)(?P=q)', swap, html)


def register(app, saver=None):
    """Add the routes to the host's FastAPI app.

    saver(image, parameters, tab) saves an image the way the host saves its own and returns
    the file's path. Without one, images go into a "saved" folder beside this package.
    """
    from fastapi import Request
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
    from starlette.concurrency import run_in_threadpool

    def fail(message, status=400):
        return JSONResponse({"error": message}, status_code=status)

    @app.get("/comic_lettering/ui")
    async def page():
        try:
            return HTMLResponse(ui_html(), headers={"Cache-Control": "no-store"})
        except (IOError, OSError):
            return HTMLResponse("<p>Comic Lettering: ui/dist is missing. Build the page (npm run build in ui/).</p>",
                                status_code=500)

    @app.get("/comic_lettering/options")
    async def options():
        return JSONResponse(await run_in_threadpool(options_payload), headers={"Cache-Control": "no-store"})

    @app.get("/comic_lettering/font")
    async def font(name: str = ""):
        path = list_fonts().get(name)
        if not path or not os.path.isfile(path):
            return fail("unknown font", 404)
        return FileResponse(path, headers={"Cache-Control": "max-age=86400"})

    @app.post("/comic_lettering/settings")
    async def settings(request: Request):
        body = await request.json()
        auto = None
        if isinstance(body.get("auto"), dict):
            auto = dict(AUTO_DEFAULTS)
            auto["enabled"] = bool(body["auto"].get("enabled"))
            for key in ("text", "caption", "sfx"):
                if isinstance(body["auto"].get(key), str):
                    auto[key] = body["auto"][key]
        await run_in_threadpool(save_settings, body.get("settings") or {}, auto)
        return JSONResponse({"ok": True})

    @app.post("/comic_lettering/session")
    async def upload(request: Request, name: str = ""):
        data = await request.body()
        if not data:
            return fail("no image")
        try:
            image = Image.open(io.BytesIO(data))
            image.load()
        except Exception:
            return fail("not an image")
        session = new_session(image, name)
        return JSONResponse({"session": session["id"], "width": image.width, "height": image.height})

    @app.post("/comic_lettering/session/last")
    async def last(request: Request):
        """A session from the clean copy of an image of the last generation."""
        body = await request.json()
        tab = str(body.get("tab") or "txt2img")
        images = LAST_CLEAN.get(tab) or []
        index, count = body.get("index"), body.get("count")
        if not isinstance(index, int) or not isinstance(count, int):
            return fail("no such image", 404)
        # A gallery with more images than were generated starts with their grid.
        index -= max(0, count - len(images))
        if index < 0 or index >= len(images):
            return fail("no such image", 404)
        # The same image as the page already has: it keeps its session and what was done there.
        origin = "%s:%d:%d" % (tab, GENERATION.get(tab, 0), index)
        if body.get("known") == origin and get_session(str(body.get("session") or "")) is not None:
            return JSONResponse({"same": True, "origin": origin})
        image = images[index]
        session = new_session(image, "generation")
        return JSONResponse({"session": session["id"], "width": image.width, "height": image.height, "origin": origin})

    @app.get("/comic_lettering/image/{session_id}/{which}")
    async def image_bytes(session_id: str, which: str):
        session = get_session(session_id)
        if session is None or which not in ("original", "result"):
            return fail("unknown image", 404)
        data = await run_in_threadpool(session_png, session, which)
        return Response(data, media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.post("/comic_lettering/render")
    async def render(request: Request):
        body = await request.json()
        session = get_session(str(body.get("session") or ""))
        if session is None:
            return fail("The image is gone from memory. Load it again.", 404)
        try:
            payload = await run_in_threadpool(render_session, session, body.get("text"), body.get("caption"),
                                              body.get("sfx"), body.get("numbers"), body.get("settings") or {},
                                              body.get("pins"), body.get("regions"))
        except Exception as error:  # report it on the page instead of a bare 500
            return fail("%s: %s" % (type(error).__name__, error), 500)
        return JSONResponse(payload)

    @app.post("/comic_lettering/save")
    async def save(request: Request):
        body = await request.json()
        session = get_session(str(body.get("session") or ""))
        if session is None:
            return fail("The image is gone from memory. Load it again.", 404)
        tab = "img2img" if body.get("tab") == "img2img" else "txt2img"
        try:
            if saver:
                image = session["result"] or session["image"]
                path = await run_in_threadpool(saver, image, session["parameters"], tab)
            else:
                path = await run_in_threadpool(save_session, session, os.path.join(BASE_DIR, "saved"))
        except Exception as error:  # the host's own saving can fail in its own ways: say so on the page
            return fail("Could not save: %s" % error, 500)
        return JSONResponse({"path": os.path.normpath(str(path))})
