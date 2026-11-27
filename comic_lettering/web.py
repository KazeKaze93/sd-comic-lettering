"""HTTP side of the editor in A1111 / Forge / reForge: settings, sessions and the routes
the React page (ui/) talks to. The core does not import this module; only the host script does.
"""
import base64
import datetime
import io
import json
import os
import re
import sys
import threading
import time
import uuid
from collections import OrderedDict
from typing import Dict, List, Optional

from PIL import Image, PngImagePlugin

from .core import PLACEMENTS, arrange, draw
from .fonts import font_names, list_fonts
from .render import BUBBLE_SHAPES, BUBBLE_THEMES, EXTRAS, MOODS, PALETTES, TAILS, Style, symbol_tile
from .render import SYMBOLS as MARK_SHAPES

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
# The same marks by what they are for, as the page's picker shows them.
MARK_GROUPS = [
    ("Love", [u"♥", u"♡", u"💕", u"💔", u"💋"]),
    ("Shine", [u"★", u"☆", u"✦", u"✨", u"💥", u"☀", u"🌙"]),
    ("Feelings and weather", [u"💢", u"⚡", u"🔥", u"💧", u"💦", u"♨", u"💨", u"〃", u"〰", u"🌀", u"💤", u"♪", u"♫",
                              u"✿"]),
    ("Signs", [u"♂", u"♀", u"✖", u"○", u"→", u"←", u"↑", u"↓", u"♦", u"♠", u"♣"]),
]
MARK_MASK_PX = 48  # the side of a mark's mask
_marks_cache = None  # type: Optional[List[Dict[str, str]]]


def _check_groups(shapeless):
    # type: (List[str]) -> None
    """Say so when the groups and the list of marks have drifted apart. Never an error: the
    page still works with the marks that are in both."""
    grouped = set(char for _, chars in MARK_GROUPS for char in chars)
    offered = set(SYMBOLS)
    if grouped == offered and not shapeless:
        return

    def named(chars):
        # Code points, since a console may not be able to print the characters themselves.
        return ", ".join("U+%04X" % ord(char) for char in sorted(chars)) or "none"

    sys.stderr.write("comic_lettering: MARK_GROUPS and SYMBOLS differ. Only in the groups: %s. Only in SYMBOLS: %s. "
                     "Without a shape: %s.\n" % (named(grouped - offered), named(offered - grouped), named(shapeless)))


def _marks():
    # type: () -> List[Dict[str, str]]
    """Every mark the page offers, in the order of MARK_GROUPS: its character, the name of its
    shape, its group, and a mask of the shape exactly as the renderer draws it.

    The mask is a PNG as a data: address, white where the shape is and clear elsewhere, so the
    page can paint it in any color (CSS mask-image goes by the alpha). Made once and kept."""
    global _marks_cache
    if _marks_cache is not None:
        return _marks_cache
    marks = []  # type: List[Dict[str, str]]
    shapeless = []  # type: List[str]
    for group, chars in MARK_GROUPS:
        for char in chars:
            try:
                name = MARK_SHAPES[char]
                tile = symbol_tile(name, MARK_MASK_PX)
            except KeyError:
                shapeless.append(char)
                continue
            picture = Image.new("RGBA", tile.size, (255, 255, 255, 0))
            picture.putalpha(tile)
            buffer = io.BytesIO()
            picture.save(buffer, "PNG", optimize=True)
            marks.append({"symbol": char, "name": name, "group": group,
                          "mask": "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")})
    _check_groups(shapeless)
    _marks_cache = marks
    return marks

# The look, remembered between sessions.
DEFAULTS = {
    "placement": "auto", "font": "", "spill": True, "uppercase": True, "erase": True,
    "bubble_size": 9.0, "bubble_min_size": 1.5, "free_size": 5.5, "text_color": "auto",
    "stroke_color": "auto", "stroke_width": 0.12, "shadow": 0.5, "jitter": 0.3, "arc": 0.0,
    "bubble_stroke_color": "auto", "bubble_stroke_width": 0.0,  # 0: no outline, the look of before
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
        "tails": list(TAILS), "placements": list(PLACEMENTS), "symbols": SYMBOLS, "marks": _marks(),
        "defaults": merge_values({}), "settings": load_settings(), "auto": load_auto(),
    }


def ui_html(base=None):
    """The built page with every relative asset address turned into an address of the host.

    base: where the host serves ui/dist from; the A1111 file route by default.
    A fresh ?v= on each call keeps the browser from showing an old build.
    """
    with io.open(os.path.join(BASE_DIR, "ui", "dist", "index.html"), encoding="utf-8") as handle:
        html = handle.read()
    base = base or "/file=extensions/%s/ui/dist" % EXTENSION
    stamp = str(int(time.time()))

    def swap(match):
        return "%s=%s%s/%s?v=%s%s" % (match.group("attr"), match.group("q"), base, match.group("path")[2:],
                                       stamp, match.group("q"))

    return re.sub(r'(?P<attr>\b(?:src|href))=(?P<q>["\'])(?P<path>\./[^"\']+)(?P=q)', swap, html)


MISSING_PAGE = "<p>Comic Lettering: ui/dist is missing. Build the page (npm run build in ui/).</p>"
GONE = "The image is gone from memory. Load it again."

# What each route answers, as (status, payload), free of any web framework: the A1111
# family serves them through FastAPI, ComfyUI through aiohttp.


def answer_settings(body):
    auto = None
    if isinstance(body.get("auto"), dict):
        auto = dict(AUTO_DEFAULTS)
        auto["enabled"] = bool(body["auto"].get("enabled"))
        for key in ("text", "caption", "sfx"):
            if isinstance(body["auto"].get(key), str):
                auto[key] = body["auto"][key]
    save_settings(body.get("settings") or {}, auto)
    return 200, {"ok": True}


def answer_upload(data, name):
    if not data:
        return 400, {"error": "no image"}
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except Exception:
        return 400, {"error": "not an image"}
    session = new_session(image, name)
    return 200, {"session": session["id"], "width": image.width, "height": image.height}


def answer_last(body):
    """A session from the clean copy of an image of the last generation of a tab (or of a ComfyUI node)."""
    tab = str(body.get("tab") or "txt2img")
    images = LAST_CLEAN.get(tab) or []
    index, count = body.get("index"), body.get("count")
    if not isinstance(index, int) or not isinstance(count, int):
        return 404, {"error": "no such image"}
    # A gallery with more images than were generated starts with their grid.
    index -= max(0, count - len(images))
    if index < 0 or index >= len(images):
        return 404, {"error": "no such image"}
    # The same image as the page already has: it keeps its session and what was done there.
    origin = "%s:%d:%d" % (tab, GENERATION.get(tab, 0), index)
    if body.get("known") == origin and get_session(str(body.get("session") or "")) is not None:
        return 200, {"same": True, "origin": origin}
    image = images[index]
    session = new_session(image, "generation")
    return 200, {"session": session["id"], "width": image.width, "height": image.height, "origin": origin}


def answer_render(body):
    session = get_session(str(body.get("session") or ""))
    if session is None:
        return 404, {"error": GONE}
    try:
        return 200, render_session(session, body.get("text"), body.get("caption"), body.get("sfx"), body.get("numbers"),
                                   body.get("settings") or {}, body.get("pins"), body.get("regions"))
    except Exception as error:  # report it on the page instead of a bare 500
        return 500, {"error": "%s: %s" % (type(error).__name__, error)}


def answer_save(body, saver, tab):
    session = get_session(str(body.get("session") or ""))
    if session is None:
        return 404, {"error": GONE}
    try:
        if saver:
            path = saver(session["result"] or session["image"], session["parameters"], tab)
        else:
            path = save_session(session, os.path.join(BASE_DIR, "saved"))
    except Exception as error:  # the host's own saving can fail in its own ways: say so on the page
        return 500, {"error": "Could not save: %s" % error}
    return 200, {"path": os.path.normpath(str(path))}


def register(app, saver=None):
    """Add the routes to the FastAPI app of an A1111-family host.

    saver(image, parameters, tab) saves an image the way the host saves its own and returns
    the file's path. Without one, images go into a "saved" folder beside this package.
    """
    from fastapi import Request
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
    from starlette.concurrency import run_in_threadpool

    def reply(answer):
        return JSONResponse(answer[1], status_code=answer[0])

    @app.get("/comic_lettering/ui")
    async def page():
        try:
            return HTMLResponse(ui_html(), headers={"Cache-Control": "no-store"})
        except (IOError, OSError):
            return HTMLResponse(MISSING_PAGE, status_code=500)

    @app.get("/comic_lettering/options")
    async def options():
        return JSONResponse(await run_in_threadpool(options_payload), headers={"Cache-Control": "no-store"})

    @app.get("/comic_lettering/font")
    async def font(name: str = ""):
        path = list_fonts().get(name)
        if not path or not os.path.isfile(path):
            return reply((404, {"error": "unknown font"}))
        return FileResponse(path, headers={"Cache-Control": "max-age=86400"})

    @app.post("/comic_lettering/settings")
    async def settings(request: Request):
        return reply(await run_in_threadpool(answer_settings, await request.json()))

    @app.post("/comic_lettering/session")
    async def upload(request: Request, name: str = ""):
        return reply(answer_upload(await request.body(), name))

    @app.post("/comic_lettering/session/last")
    async def last(request: Request):
        return reply(answer_last(await request.json()))

    @app.get("/comic_lettering/image/{session_id}/{which}")
    async def image_bytes(session_id: str, which: str):
        session = get_session(session_id)
        if session is None or which not in ("original", "result"):
            return reply((404, {"error": "unknown image"}))
        data = await run_in_threadpool(session_png, session, which)
        return Response(data, media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.post("/comic_lettering/render")
    async def render(request: Request):
        return reply(await run_in_threadpool(answer_render, await request.json()))

    @app.post("/comic_lettering/save")
    async def save(request: Request):
        body = await request.json()
        tab = "img2img" if body.get("tab") == "img2img" else "txt2img"
        return reply(await run_in_threadpool(answer_save, body, saver, tab))


def register_aiohttp(routes, saver=None):
    """Add the same routes to an aiohttp route table: ComfyUI's PromptServer.instance.routes.

    The page's files are served from ui/dist by a route of their own, so they are not in the
    folder ComfyUI loads node scripts from (it would run the page's script on its own page).
    """
    import asyncio
    import mimetypes

    from aiohttp import web as aio

    static = "/comic_lettering/static"
    dist = os.path.realpath(os.path.join(BASE_DIR, "ui", "dist"))

    def reply(answer):
        return aio.json_response(answer[1], status=answer[0])

    async def threaded(function, *args):
        return await asyncio.get_running_loop().run_in_executor(None, function, *args)

    async def body_of(request):
        try:
            body = await request.json()
        except Exception:
            body = None
        return body if isinstance(body, dict) else {}

    @routes.get("/comic_lettering/ui")
    async def page(request):
        try:
            return aio.Response(text=ui_html(static), content_type="text/html", headers={"Cache-Control": "no-store"})
        except (IOError, OSError):
            return aio.Response(text=MISSING_PAGE, content_type="text/html", status=500)

    @routes.get(static + "/{path:.*}")
    async def files(request):
        path = os.path.realpath(os.path.join(dist, request.match_info["path"]))
        if not path.startswith(dist + os.sep) or not os.path.isfile(path):
            return reply((404, {"error": "no such file"}))
        kind = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if path.endswith(".js"):
            kind = "text/javascript"  # Windows sometimes has this as text/plain, and a module then will not load
        with open(path, "rb") as handle:
            return aio.Response(body=handle.read(), content_type=kind, headers={"Cache-Control": "no-cache"})

    @routes.get("/comic_lettering/options")
    async def options(request):
        return aio.json_response(await threaded(options_payload), headers={"Cache-Control": "no-store"})

    @routes.get("/comic_lettering/font")
    async def font(request):
        path = list_fonts().get(request.query.get("name", ""))
        if not path or not os.path.isfile(path):
            return reply((404, {"error": "unknown font"}))
        return aio.FileResponse(path, headers={"Cache-Control": "max-age=86400"})

    @routes.post("/comic_lettering/settings")
    async def settings(request):
        return reply(await threaded(answer_settings, await body_of(request)))

    @routes.post("/comic_lettering/session")
    async def upload(request):
        return reply(answer_upload(await request.read(), request.query.get("name", "")))

    @routes.post("/comic_lettering/session/last")
    async def last(request):
        return reply(answer_last(await body_of(request)))

    @routes.get("/comic_lettering/image/{session_id}/{which}")
    async def image_bytes(request):
        session = get_session(request.match_info["session_id"])
        which = request.match_info["which"]
        if session is None or which not in ("original", "result"):
            return reply((404, {"error": "unknown image"}))
        data = await threaded(session_png, session, which)
        return aio.Response(body=data, content_type="image/png", headers={"Cache-Control": "no-store"})

    @routes.post("/comic_lettering/render")
    async def render(request):
        return reply(await threaded(answer_render, await body_of(request)))

    @routes.post("/comic_lettering/save")
    async def save(request):
        body = await body_of(request)
        return reply(await threaded(answer_save, body, saver, str(body.get("tab") or "")))
