"""Entry point: put the user's text into detected bubbles, or straight onto the art."""
import colorsys
import copy
import math
import random
import re
from typing import Dict, List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy import ndimage as ndi

from .detect import detect_bubbles, edge_energy, erase_letters, luminance
from .people import person_mask
from .render import (EXTRAS, MOODS, PALETTES, SYMBOLS, Paint, Style, _solid, block_size, bubble_shape,
                     decorate, get_fonts, layout, layout_shaped, line_heights, parse_color,
                     parse_text, paste_centered, render_block, shape_score, stem_ratio)

PLACEMENTS = ["auto", "top", "bottom", "center", "top-left", "top-right", "bottom-left",
              "bottom-right"]
SHAPE_WEIGHT = 0.6   # how much font size a better line shape is worth
SHAPE_REACH = 0.8    # look for a better shape down to this share of the largest size
MAX_LINES = 8        # more lines than this in one bubble is a wall of text: it goes to the caption
SAMPLE_TEXT = u"Hello! Привет! 123"
REPEAT = re.compile(u"^(.*?\\S)\\s*[xX×]\\s*(\\d{1,2})$")  # "FAP x5"


def letter(image, text="", caption="", spill=True, placement="auto", style=None, erase=True,
           white_threshold=120, rtl=False, numbers=False, sfx=""):
    # type: (Image.Image, str, str, bool, str, Style, bool, int, bool, bool, str) -> Tuple[Image.Image, Dict]
    """Letter an image: arrange() decides where everything goes, draw() draws it.

    text: one line per bubble, in reading order (top to bottom, left to right). An
    empty line leaves its bubble alone.
    caption: free text drawn straight onto the art, outside the bubbles, or inside a
    bubble drawn for it (style.caption_bubble).
    spill: a line goes into a bubble only if it fits at a readable size
    (style.bubble_min_size); a bubble too small for it is passed over, and lines left
    without a bubble are added to the caption. Off: always write into the bubbles,
    however small, and drop the lines left over.
    numbers: draw each bubble's number instead of any text, to see the order.
    sfx: sound effects, one per line ("SLAP", "THUD", "FAP x5"). Each is drawn big and
    tilted in a calm, empty part of the art, clear of the bubbles, the caption and each
    other. "WORD x5" stacks the word five times in a column.

    Text that is placed automatically also keeps off the characters when a person
    segmentation model is available (see people.py); info["characters"] tells.
    """
    scene = arrange(image, text, caption, spill, placement, style, erase, white_threshold, rtl, numbers, sfx)
    return draw(image, scene), scene["info"]


def arrange(image, text="", caption="", spill=True, placement="auto", style=None, erase=True,
            white_threshold=120, rtl=False, numbers=False, sfx="", pins=None, regions=None):
    # type: (Image.Image, str, str, bool, str, Style, bool, int, bool, bool, str, Dict, List) -> Dict
    """Decide what goes where, without drawing anything. Arguments as for letter().

    pins: what was set by hand, by item id ("caption" for the caption or its balloon,
    "sfx:0" for the first sound effect): {"cx", "cy"} the middle of the item in pixels,
    {"size"} its font size in pixels, {"rotation"} its tilt in degrees, counter-clockwise.
    Whatever a pin leaves out is still decided here. Things placed after a pinned item
    keep off it where it now stands. The caption's "reach" and the balloon's "tall", as
    the scene reported them, keep the line breaks the item had when it was pinned.

    regions: areas drawn on the image by hand, a list of
      {"id", "kind", "shapes", "text", "fill"}
    kind "text": the text is fitted into the area as into a bubble; with fill "light" or
    "dark" the area is painted as a bubble first, with "none" the text gets the caption's
    outline. kind "sfx": the text is a sound effect, sized to the area and put in its
    middle. kind "keepout": nothing that is placed automatically may land there.
    shapes: {"type": "polygon", "points": [[x, y], ...]} for an outline that is closed and
    filled, {"type": "stroke", "points": [...], "width": w} for a brush stroke; a region is
    all of its shapes together. Whatever is placed automatically keeps off every region.
    Optional: "rotation", the tilt of the text or effect in degrees, counter-clockwise
    (an effect is tilted at random without it), and "scale", how large it is against
    what the area would give it (1 by default; above 1 it may reach out of the area).
    "follow": the text runs along the region's longest brush stroke, bending with it, in
    the direction the stroke was drawn (left to right if it was drawn leftwards); its
    letters are about as tall as the brush is wide. "flip" turns that direction round.
    A shape {"type": "erase", "points": [...], "width": w} rubs out what the shapes before
    it painted.

    Returns the scene: a dict of plain values (it survives a trip through JSON) that
    draw() turns into the lettered image. scene["items"] lists what is drawn, in order:

      {"kind": "bubble", "bubble": n, ...}   text inside the n-th bubble found in the art
      {"kind": "caption", ...}               text straight on the art
      {"kind": "balloon", ...}               text inside a bubble drawn for it
      {"kind": "sfx", "index": n, ...}       a sound effect

    Every item has its text, its font size in pixels and its place in pixels. "lines"
    is the text already broken into lines and measured: draw() takes it as it is.
    scene["info"] is what letter() returns as info.
    """
    style = style or Style()
    info = {"bubbles_found": 0, "bubbles_filled": 0, "free_text": False, "font_sizes": []}
    items = []
    scene = {"version": 1, "size": [image.width, image.height], "style": dict(vars(style)),
             "white_threshold": int(white_threshold), "rtl": bool(rtl), "erase": bool(erase),
             "people": False, "empty": False, "bubbles": [], "items": items, "info": info,
             "regions": _regions(regions)}
    areas = scene["regions"]
    lines = [line.strip() for line in (text or "").replace("\r", "").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    caption = (caption or "").replace("\r", "").strip()
    effects = [line.strip() for line in (sfx or "").replace("\r", "").split("\n") if line.strip()]
    if not lines and not caption and not numbers and not effects and not any(area["text"] for area in areas):
        scene["empty"] = True  # nothing asked for: draw() hands the image back untouched
        return scene
    rgb = np.array(image.convert("RGB"))
    height = rgb.shape[0]
    bubbles = detect_bubbles(rgb, white_threshold, rtl=rtl)  # also so nothing lands on them
    info["bubbles_found"] = len(bubbles)
    scene["bubbles"] = [[int(v) for v in bubble.bbox()] for bubble in bubbles]  # x0, y0, x1, y1, in reading order
    strict = bool(spill)
    if numbers:
        lines = [str(i + 1) for i in range(len(bubbles))]
        caption = ""
        erase = False
        strict = False
    scene["erase"] = bool(erase)
    accent = None
    if "from the art" in (style.bubble_colors, style.caption_colors, style.sfx_colors):
        accent = accent_palette(rgb)
    bubble_look = voice(style, "bubble")

    def fit(index, line):
        return _fit_bubble(height, bubbles[index], line, bubble_look, strict)

    plans, rest = _assign(lines, len(bubbles), fit)
    for index, (laid_out, size, cx, cy), line in plans:
        items.append({"kind": "bubble", "bubble": index, "text": line, "lines": _plain(laid_out),
                      "size": int(size), "cx": float(cx), "cy": float(cy)})
        info["font_sizes"].append(size)
        info["bubbles_filled"] += 1
    if erase:
        # Everything below reads the art as it will be once the letters are erased.
        for index, _, _ in plans:
            erase_letters(rgb, bubbles[index])
    free = (rest if spill and not numbers else []) + ([caption] if caption else [])
    effects = [] if numbers else effects
    automatic = bool(effects or (free and (placement == "auto" or style.caption_bubble != "none")))
    scene["people"] = automatic
    static, precious, known = _obstacles(rgb, bubbles, automatic)
    if automatic:
        info["characters"] = known
    energy = _energy(rgb) if (effects or (free and style.caption_bubble != "none")) else None
    pins = pins if isinstance(pins, dict) else {}
    masks = _region_masks(areas, rgb.shape[1], rgb.shape[0], static, precious)
    held = []  # sound effects that belong to a region: (text, pin)
    for number, (area, mask) in enumerate(zip(areas, masks)):
        if numbers or not area["text"] or not mask.any():
            continue
        line = _stroke_line(area) if area.get("follow") else None
        if line is not None:
            item = _place_along(area, line, number, style, accent)
            items.append(item)
            info["font_sizes"].append(item["size"])
            info["regions"] = info.get("regions", 0) + 1
        elif area["kind"] == "text":
            item = _place_region(height, area, mask, number, style, palette(style, "caption", accent))
            items.append(item)
            info["font_sizes"].append(item["size"])
            info["regions"] = info.get("regions", 0) + 1
        elif area["kind"] == "sfx":
            held.append((area, _region_pin(area, mask)))
            info["regions"] = info.get("regions", 0) + 1
    caption_box = None
    if free:
        item = _place_free(rgb, "\n".join(free), placement, style, static,
                           palette(style, "caption", accent), energy, precious, _pin(pins.get("caption")))
        items.append(item)
        caption_box = item["box"]
        info["free_text"] = True
        info["font_sizes"].append(item["size"])
    if effects or held:
        taken = np.zeros(rgb.shape[:2], dtype=bool)  # the caption and the effects placed so far
        _reserve(taken, caption_box)
    if effects:
        items.extend(_place_sfx(rgb, effects, static, taken, style, energy, precious, pins))
        info["sfx"] = len(effects)
    if held:
        # Effects of the regions come after the others and are numbered apart from them,
        # so adding or removing an ordinary effect does not change how these are drawn.
        own = dict(("sfx:%d" % (REGION_SFX + n), pin) for n, (_, pin) in enumerate(held))
        placed = _place_sfx(rgb, [area["text"] for area, _ in held], static, taken, style, energy, precious, own,
                            REGION_SFX)
        for item, (area, _) in zip(placed, held):
            item["region"] = area["id"]
        items.extend(placed)
    return scene


def draw(image, scene):
    # type: (Image.Image, Dict) -> Image.Image
    """Draw a scene made by arrange() onto the image it was made for."""
    if scene.get("empty"):
        return image
    style = Style()
    for key, value in scene["style"].items():
        setattr(style, key, value)
    items = scene["items"]
    rgb = np.array(image.convert("RGB"))
    height, width = rgb.shape[:2]
    bubbles = detect_bubbles(rgb, scene["white_threshold"], rtl=scene["rtl"])
    accent = None
    if "from the art" in (style.bubble_colors, style.caption_colors, style.sfx_colors):
        accent = accent_palette(rgb)
    spoken = [item for item in items if item["kind"] == "bubble" and item["bubble"] < len(bubbles)]
    if scene["erase"]:
        for item in spoken:
            erase_letters(rgb, bubbles[item["bubble"]])
    out = Image.fromarray(rgb)
    bubble_look = voice(style, "bubble")
    for item in spoken:
        ink = _bubble_ink(style, bubbles[item["bubble"]], palette(style, "bubble", accent))
        out = paste_centered(out, render_block(_lines(item), item["size"], bubble_look, Paint(ink)),
                             item["cx"], item["cy"])
    # The marks around a text keep off the same things the placement kept off.
    static, precious, _ = _obstacles(rgb, bubbles, scene["people"])
    areas = scene.get("regions") or []
    masks = _region_masks(areas, width, height, static, precious)
    taken = np.zeros(rgb.shape[:2], dtype=bool)
    for item in items:
        if item["kind"] == "region":
            if item["region"] < len(masks):
                out = _draw_region(out, item, masks[item["region"]], style, accent)
        elif item["kind"] == "path":
            if item["region"] < len(masks):
                out = _draw_along(out, item, masks[item["region"]], style, accent)
        elif item["kind"] == "caption":
            out = _draw_caption(out, item, style, palette(style, "caption", accent), precious)
            _reserve(taken, item["box"])
        elif item["kind"] == "balloon":
            out = _draw_balloon(out, item, style, palette(style, "caption", accent), precious)
            _reserve(taken, item["box"])
        elif item["kind"] == "sfx":
            out = _draw_sfx(out, item, static, taken, style, palette(style, "sfx", accent), width, height)
            _reserve(taken, item["room"])
    return out.convert("RGB")


REGION_SFX = 1000  # the sound effects of regions are numbered from here


def _regions(regions):
    """The regions with only what they may carry; see arrange()."""
    clean = []
    for number, region in enumerate(regions if isinstance(regions, list) else []):
        if not isinstance(region, dict) or region.get("kind") not in ("text", "sfx", "keepout"):
            continue
        shapes = []
        for shape in region.get("shapes") if isinstance(region.get("shapes"), list) else []:
            if not isinstance(shape, dict) or not isinstance(shape.get("points"), list):
                continue
            points = [[float(p[0]), float(p[1])] for p in shape["points"][:4000]
                      if isinstance(p, (list, tuple)) and len(p) == 2
                      and all(isinstance(v, (int, float)) and not isinstance(v, bool) and v == v for v in p)]
            if shape.get("type") == "polygon" and len(points) >= 3:
                shapes.append({"type": "polygon", "points": points})
            elif shape.get("type") in ("stroke", "erase") and points:
                wide = shape.get("width")
                wide = float(wide) if isinstance(wide, (int, float)) and not isinstance(wide, bool) and wide == wide else 20.0
                shapes.append({"type": shape["type"], "points": points, "width": max(2.0, min(2000.0, wide))})
        if not any(shape["type"] != "erase" for shape in shapes):
            continue
        kind = region["kind"]
        text = region.get("text") if isinstance(region.get("text"), str) else ""

        def number_of(key, low, high, default):
            value = region.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value == value:
                return max(low, min(high, float(value)))
            return default

        clean.append({"id": str(region.get("id") or number)[:40], "kind": kind, "shapes": shapes[:200],
                      "text": "" if kind == "keepout" else text.replace("\r", "").strip(),
                      "fill": region.get("fill") if kind == "text" and region.get("fill") in ("light", "dark") else "none",
                      "rotation": number_of("rotation", -180.0, 180.0, None), "scale": number_of("scale", 0.2, 4.0, 1.0),
                      "follow": kind != "keepout" and region.get("follow") is True,
                      "flip": region.get("flip") is True})
        if len(clean) >= 40:
            break
    return clean


def _region_masks(areas, width, height, static=None, precious=None):
    """The area of every region as a mask. Each is also added to static and precious,
    when given: whatever is placed automatically keeps off the regions."""
    masks = []
    for area in areas:
        canvas = Image.new("L", (width, height), 0)
        pen = ImageDraw.Draw(canvas)
        for shape in area["shapes"]:
            points = [(x, y) for x, y in shape["points"]]
            if shape["type"] == "polygon":
                pen.polygon(points, fill=255)
            else:
                ink = 0 if shape["type"] == "erase" else 255  # shapes apply in the order they were drawn
                wide = shape["width"]
                if len(points) > 1:
                    pen.line(points, fill=ink, width=int(round(wide)))
                for x, y in points:  # round ends and joints
                    pen.ellipse((x - wide / 2.0, y - wide / 2.0, x + wide / 2.0, y + wide / 2.0), fill=ink)
        # A hand is not steady: round the outline off a little.
        soft = canvas.filter(ImageFilter.GaussianBlur(max(1.5, 0.004 * min(width, height))))
        mask = np.asarray(soft) > 127
        masks.append(mask)
        if static is not None:
            static |= mask
        if precious is not None:
            precious |= mask
    return masks


class _Area(object):
    """A region in the form the bubble fitter takes: a mask cut to its box, and where the box is."""

    def __init__(self, mask):
        ys, xs = np.nonzero(mask)
        self.y0, self.x0 = int(ys.min()), int(xs.min())
        self.body = mask[self.y0:int(ys.max()) + 1, self.x0:int(xs.max()) + 1]


def _region_look(style, filled, pal):
    """Text in a painted region is bubble text; on bare art it is caption text."""
    look = voice(style, "bubble") if filled else _caption_look(style, pal)
    look.bubble_size = 30.0  # as large as the area allows
    return look


def _place_region(height, area, mask, number, style, pal):
    """The scene item for a text fitted into a region."""
    filled = area["fill"] != "none"
    look = _region_look(style, filled, pal)
    room = mask
    scale = area.get("scale") or 1.0
    turn = math.radians(area.get("rotation") or 0.0)
    my, mx = ndi.center_of_mass(mask)
    if scale != 1.0 or turn:
        # The text is fitted in a frame of its own. Larger or smaller than the area gives:
        # the area is blown up, or shrunk, about its middle. Tilted: the area is turned back
        # by the tilt, so the lines are laid out level and fill the area once they are
        # turned with it. Each point of the frame reads the area at the point it came from.
        cos, sin = math.cos(turn) / scale, math.sin(turn) / scale
        matrix = np.array([[cos, -sin], [sin, cos]])  # rows and columns: y, x
        middle = np.array([my, mx])
        room = ndi.affine_transform(mask.astype(np.uint8), matrix, offset=middle - matrix.dot(middle), order=0) > 0
        if not room.any():
            room = mask
    lines, size, cx, cy = _fit_text(height, _Area(room), parse_text(area["text"], style.uppercase), look, False)
    if turn and room is not mask:
        # Back from the level frame to where the text stands on the image.
        dx, dy = cx - mx, cy - my
        cx = mx + dx * math.cos(turn) + dy * math.sin(turn)
        cy = my - dx * math.sin(turn) + dy * math.cos(turn)
    item = {"kind": "region", "id": "region:%s" % area["id"], "region": number, "text": area["text"],
            "lines": _plain(lines), "size": int(size), "cx": float(cx), "cy": float(cy), "fill": area["fill"]}
    if area.get("rotation") is not None:
        item["rotation"] = float(area["rotation"])
    return item


def _stroke_line(area):
    """(points, brush width) of the centre line of a region's longest brush stroke, evened
    out and smoothed; None if there is no stroke long enough to write along."""
    best = None
    for shape in area["shapes"]:
        if shape["type"] != "stroke" or len(shape["points"]) < 2:
            continue
        points = np.array(shape["points"], dtype=np.float64)
        length = float(np.hypot(*np.diff(points, axis=0).T).sum())
        if best is None or length > best[0]:
            best = (length, points, float(shape["width"]))
    if best is None or best[0] < 0.8 * best[2]:
        return None
    length, points, wide = best
    steps = np.hypot(*np.diff(points, axis=0).T)
    points = points[np.concatenate([[True], steps > 1e-6])]
    along = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(points, axis=0).T))])
    count = max(8, int(length / 4.0))
    marks = np.linspace(0.0, along[-1], count)
    line = np.stack([np.interp(marks, along, points[:, 0]), np.interp(marks, along, points[:, 1])], axis=1)
    # A hand shakes: average over about half the brush width. The ends are padded with
    # themselves so the line keeps its length.
    window = max(1, int(wide / 2.0 / max(along[-1] / count, 1e-6))) | 1
    if window > 1 and count > window:
        padded = np.pad(line, ((window // 2, window // 2), (0, 0)), mode="edge")
        kernel = np.ones(window) / window
        line = np.stack([np.convolve(padded[:, 0], kernel, mode="valid"),
                         np.convolve(padded[:, 1], kernel, mode="valid")], axis=1)
    # Text reads left to right: a stroke drawn leftwards is taken the other way round.
    run = line[-1] - line[0]
    if abs(run[0]) > abs(run[1]) and run[0] < 0:
        line = line[::-1]
    if area.get("flip"):
        line = line[::-1]  # asked for: the other way round, which also turns the letters over
    return line, wide


def _along_look(style, voice_name, pal):
    """The style of a text that runs along a stroke: straight here, the stroke bends it."""
    if voice_name == "sfx":
        look = voice(style, "sfx")
        look.opacity = style.sfx_opacity
        look.line_spacing += 1.2 * (0.14 + (0.07 if pal and pal.get("outer") else 0.0))
    elif voice_name == "bubble":
        look = voice(style, "bubble")
    else:
        look = _caption_look(style, pal)
    look.rotation = 0.0
    look.arc = 0.0
    return look


def _along_voice(area):
    return "sfx" if area["kind"] == "sfx" else ("bubble" if area["fill"] != "none" else "caption")


def _place_along(area, line, number, style, accent):
    """The scene item for a text that runs along a region's brush stroke."""
    points, wide = line
    voice_name = _along_voice(area)
    pal = palette(style, "sfx" if voice_name == "sfx" else "bubble" if voice_name == "bubble" else "caption", accent)
    look = _along_look(style, voice_name, pal)
    paragraphs = [[word for words in parse_text(area["text"], style.uppercase) for word in words]]
    length = float(np.hypot(*np.diff(points, axis=0).T).sum())
    size = max(8, int(0.6 * wide * (area.get("scale") or 1.0)))
    lines = layout(paragraphs, get_fonts(look, size), 1e9)
    if lines[0][1] > 0.94 * length and size > 8:
        # Too long for the stroke at this size: as large as fits its length.
        size = max(8, int(size * 0.94 * length / lines[0][1]))
        lines = layout(paragraphs, get_fonts(look, size), 1e9)
    return {"kind": "path", "id": "region:%s" % area["id"], "region": number, "text": area["text"],
            "lines": _plain(lines), "size": int(size), "voice": voice_name, "fill": area["fill"],
            "path": [[round(float(x), 2), round(float(y), 2)] for x, y in points]}


def _draw_along(image, item, mask, style, accent):
    """Draw a text bent along its stroke: the straight text is cut into thin slices and
    each slice is set on the line, turned the way the line runs there."""
    size, voice_name = item["size"], item["voice"]
    if voice_name == "bubble":
        image = _paint_area(image, mask, item["fill"] == "dark")
        pal = palette(style, "bubble", accent)
        dark = item["fill"] == "dark"
        plain = (255, 255, 255) if dark else (0, 0, 0)
        paint = Paint((pal["fill"] if dark else pal["ink"]) if pal else _own_color(style, "bubble", style.text_color, plain))
        look = _along_look(style, "bubble", None)
    else:
        pal = palette(style, "sfx" if voice_name == "sfx" else "caption", accent)
        look = _along_look(style, voice_name, pal)
        paint = _paint(style, voice_name, pal, size, look.font)
    layer = render_block(_lines(item), size, look, paint)
    bounds = layer.getbbox()
    if bounds is None:
        return image
    layer = layer.crop(bounds)
    points = np.array(item["path"], dtype=np.float64)
    along = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(points, axis=0).T))])
    length = along[-1]
    if length <= 0:
        return image

    def at(distance):
        distance = min(max(distance, 0.0), length)
        return np.interp(distance, along, points[:, 0]), np.interp(distance, along, points[:, 1])

    pad = layer.height + layer.width // 8 + 8
    canvas = Image.new("RGBA", (image.width + 2 * pad, image.height + 2 * pad), (0, 0, 0, 0))
    start = (length - layer.width) / 2.0  # the text sits in the middle of the stroke
    step = 3
    reach = max(6.0, 0.25 * size)  # the direction is read over this much of the line
    for left in range(0, layer.width, step):
        piece = layer.crop((max(0, left - 1), 0, min(layer.width, left + step + 1), layer.height))
        if piece.getbbox() is None:
            continue
        where = start + left + step / 2.0
        x, y = at(where)
        x0, y0 = at(where - reach)
        x1, y1 = at(where + reach)
        turned = piece.rotate(-math.degrees(math.atan2(y1 - y0, x1 - x0)), resample=Image.BICUBIC, expand=True)
        corner = (int(round(x - turned.width / 2.0)) + pad, int(round(y - turned.height / 2.0)) + pad)
        if 0 <= corner[0] <= canvas.width - turned.width and 0 <= corner[1] <= canvas.height - turned.height:
            canvas.alpha_composite(turned, corner)
    bent = canvas.crop((pad, pad, pad + image.width, pad + image.height))
    return Image.alpha_composite(image.convert("RGBA"), bent)


def _paint_area(image, mask, dark):
    """Paint a region as a bubble: a body with an outline around it."""
    body, line = ((14, 14, 18), (245, 245, 245)) if dark else ((250, 250, 250), (15, 15, 15))
    wide = max(2, int(round(0.004 * image.height)))
    edge = Image.fromarray((ndi.binary_dilation(mask, iterations=wide) * 255).astype(np.uint8))
    fill = Image.fromarray((mask * 255).astype(np.uint8))
    soft = ImageFilter.GaussianBlur(0.8)
    painted = Image.alpha_composite(_solid(line, edge.filter(soft)), _solid(body, fill.filter(soft)))
    return Image.alpha_composite(image.convert("RGBA"), painted)


def _draw_region(image, item, mask, style, accent):
    size = item["size"]
    if item["fill"] == "none":
        pal = palette(style, "caption", accent)
        look = _region_look(style, False, pal)
        look.rotation = item.get("rotation", look.rotation)
        paint = _paint(style, "caption", pal, size, look.font)
        return paste_centered(image, render_block(_lines(item), size, look, paint), item["cx"], item["cy"])
    dark = item["fill"] == "dark"
    image = _paint_area(image, mask, dark)
    pal = palette(style, "bubble", accent)
    plain = (255, 255, 255) if dark else (0, 0, 0)
    ink = (pal["fill"] if dark else pal["ink"]) if pal else _own_color(style, "bubble", style.text_color, plain)
    look = _region_look(style, True, None)
    look.rotation = item.get("rotation", look.rotation)
    return paste_centered(image, render_block(_lines(item), size, look, Paint(ink)), item["cx"], item["cy"])


def _sfx_units(word):
    """The width of a sound effect in letters, estimated without a font."""
    return sum(0.95 if ch in SYMBOLS else 0.3 if ch.isspace() else 0.5 for ch in word.replace("*", ""))


def _region_pin(area, mask):
    """The pin that puts a region's sound effect into it: its middle, the size that fills it, its tilt if set."""
    ys, xs = np.nonzero(mask)
    box_w, box_h = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
    word, count = _repeat(area["text"])
    size = min(box_w / (_sfx_units(word) + 0.8), box_h / (1.4 if count == 1 else 0.75 * count + 0.8))
    cy, cx = ndi.center_of_mass(mask)
    pin = {"cx": float(cx), "cy": float(cy), "size": max(10, int(size * 0.9 * (area.get("scale") or 1.0)))}
    if area.get("rotation") is not None:
        pin["rotation"] = float(area["rotation"])
    return pin


def _pin(pin):
    """A pin with only the numbers it may carry; {} for anything else."""
    clean = {}
    if isinstance(pin, dict):
        for key in ("cx", "cy", "size", "rotation", "reach"):
            value = pin.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and value == value:
                clean[key] = float(value)
        if "size" in clean:
            clean["size"] = max(8, min(2000, int(round(clean["size"]))))
        if "cx" not in clean or "cy" not in clean:
            clean.pop("cx", None)
            clean.pop("cy", None)
        if isinstance(pin.get("tall"), bool):
            clean["tall"] = pin["tall"]
    return clean


def _plain(lines):
    """Laid-out lines as plain lists, for the scene: [[[word, emphasized, width, glued], ...], width]."""
    return [[[[word, bool(emph), float(word_w), bool(glue)] for word, emph, word_w, glue in words], float(line_w)]
            for words, line_w in lines]


def _lines(item):
    """The lines of a scene item in the form the renderer takes."""
    return [([tuple(word) for word in words], line_w) for words, line_w in item["lines"]]


def _obstacles(rgb, bubbles, with_people):
    """(static, precious, characters known): what text must keep off.

    static: the bubbles found in the art and, when asked for and known, the characters.
    precious: what must not be covered even when there is no free place: bubbles and heads.
    """
    static = np.zeros(rgb.shape[:2], dtype=bool)
    for bubble in bubbles:
        h, w = bubble.filled.shape
        static[bubble.y0:bubble.y0 + h, bubble.x0:bubble.x0 + w] |= bubble.filled
    precious = static.copy()
    known = None
    if with_people:
        people = person_mask(rgb)
        known = people is not None
        if people is not None:
            static |= people
            precious |= _heads(people)
    return static, precious, known


def _reserve(taken, box):
    """Mark a box (x0, y0, x1, y1), or nothing for None, in the mask of places already used."""
    if box is not None:
        x0, y0, x1, y1 = box
        taken[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True


# ---------------------------------------------------------------- looks and colors# ---------------------------------------------------------------- looks and colors

def _heads(people):
    """The top part of every character in a person mask: roughly the head and hair."""
    labels, count = ndi.label(people)
    heads = np.zeros_like(people)
    smallest = 0.01 * people.size
    for index, box in enumerate(ndi.find_objects(labels), start=1):
        rows, cols = box
        if (rows.stop - rows.start) * (cols.stop - cols.start) < smallest:
            continue
        top = slice(rows.start, rows.start + max(1, int(0.28 * (rows.stop - rows.start))))
        heads[top, cols] |= labels[top, cols] == index
    return heads


def voice(style, which):
    """The style for one kind of text (bubble, caption, sfx): its font and its mood."""
    look = copy.copy(style)
    if which == "caption" and style.caption_font:
        look.font = style.caption_font
    elif which == "sfx":
        look.font = style.sfx_font or style.font
    mood = MOODS.get(getattr(style, which + "_mood", "custom"))
    if mood:
        for key, value in mood.items():
            setattr(look, key, value)
    return look


def palette(style, which, accent):
    """The color preset for one kind of text: a dict, or None for the plain defaults."""
    spec = PALETTES.get(getattr(style, which + "_colors", "auto"))
    if spec == "custom":
        return None  # no preset: the color fields decide, see _own_color
    return accent if spec == "accent" else spec


def _own_color(style, which, value, default):
    """A color field (text_color and the like): it counts only with the colors set to "custom"."""
    if getattr(style, which + "_colors", "auto") != "custom":
        return default
    return parse_color(value, default)


def accent_palette(rgb):
    """Colors taken from the art: its strongest saturated hue. None if the art is gray."""
    pixels = rgb[::4, ::4].reshape(-1, 3).astype(np.float32) / 255.0
    high = pixels.max(axis=1)
    low = pixels.min(axis=1)
    spread = high - low
    saturation = np.where(high > 0, spread / np.maximum(high, 1e-6), 0)
    keep = (saturation > 0.35) & (high > 0.35)
    if keep.sum() < 50:
        return None
    r, g, b = pixels[keep, 0], pixels[keep, 1], pixels[keep, 2]
    top, delta = high[keep], np.maximum(spread[keep], 1e-6)
    hue = np.where(top == r, ((g - b) / delta) % 6, np.where(top == g, (b - r) / delta + 2,
                                                             (r - g) / delta + 4)) / 6.0
    weights = saturation[keep] * top
    counts, edges = np.histogram(hue, bins=36, range=(0, 1), weights=weights)
    peak = int(counts.argmax())
    center = (edges[peak] + edges[peak + 1]) / 2.0

    def color(s, v):
        return tuple(int(round(c * 255)) for c in colorsys.hsv_to_rgb(center, s, v))

    return dict(fill=color(0.55, 1.0), stroke=color(0.85, 0.14), ink=color(0.85, 0.6))


def _brightness(color):
    return color[0] * 0.299 + color[1] * 0.587 + color[2] * 0.114


def _bubble_ink(style, bubble, pal):
    """Text color inside a found bubble."""
    light = _brightness(bubble.color) > 128
    plain = (0, 0, 0) if light else (getattr(bubble, "outline_color", None) or (255, 255, 255))
    if pal is None:
        return _own_color(style, "bubble", style.text_color, plain)
    return pal["ink"] if light else pal["fill"]


def _paint(style, which, pal, size, font=None):
    """Colors and outline widths for a caption or a sound effect."""
    stroke_px = int(round(size * max(0.0, style.stroke_width if which == "caption" else 0.14)))
    shadow = style.shadow if which == "caption" else 0.0
    if pal is None:
        fill = _own_color(style, which, style.text_color if which == "caption" else style.sfx_color,
                          (255, 255, 255))
        stroke = (0, 0, 0) if _brightness(fill) > 128 else (255, 255, 255)
        if which == "caption":
            stroke = _own_color(style, which, style.stroke_color, stroke)
        return Paint(fill, stroke, stroke_px, shadow=shadow)
    # A colored fill needs body: on a thin font the outlines would be wider than the
    # letters and drown the color. Thicken the fill and keep the outlines modest.
    bold_px = 0
    thin = 0.1 - stem_ratio(font or style.font)
    if thin > 0:
        bold_px = int(round(thin * size * 0.55))
        stroke_px = min(stroke_px, max(2, int(round(size * 0.07))))
    outer = pal.get("outer")
    outer_px = max(2, int(round(size * (0.05 if thin > 0 else 0.07)))) if outer else 0
    return Paint(pal["fill"], pal.get("stroke"), stroke_px, outer, outer_px, pal.get("fill2"),
                 pal.get("glow"), shadow, bold_px)


# ---------------------------------------------------------------- bubbles

def _assign(lines, count, fit):
    """Map text lines to bubbles, in order.

    fit(index, text) returns a layout, or None if the text does not fit that bubble;
    the line then tries the next bubble. An empty line uses up one bubble; a line that
    fits no bubble uses up none.
    Returns ([(bubble index, layout, line)], leftover lines).
    """
    taken = [False] * count
    plans = []
    rest = []
    for line in lines:
        placed = False
        passed = []
        for index in range(count):
            if taken[index]:
                continue
            taken[index] = True
            passed.append(index)
            if not line:
                placed = True
                break
            result = fit(index, line)
            if result is not None:
                plans.append((index, result, line))
                placed = True
                break
        if not placed and line:
            rest.append(line)
            # It fits nowhere: the bubbles it passed over stay free for the next lines.
            for index in passed:
                taken[index] = False
    return plans, rest


def font_sample(style, text="", size=(640, 110)):
    """A strip showing the font both ways: in a bubble and as a caption."""
    first = [line.strip() for line in (text or "").split("\n") if line.strip()]
    paragraphs = parse_text(first[0] if first else SAMPLE_TEXT, style.uppercase)
    width, height = size
    image = Image.new("RGB", size, (112, 118, 126))
    pad = max(3, height // 14)
    ImageDraw.Draw(image).rounded_rectangle([pad, pad, width // 2 - pad, height - pad],
                                            radius=height // 4, fill=(250, 250, 250),
                                            outline=(15, 15, 15), width=max(2, height // 28))
    font_size = int(height * 0.36)
    while True:
        lines = layout(paragraphs, get_fonts(style, font_size), 10 ** 6)
        if block_size(lines, font_size, style)[0] <= width / 2.0 - 6 * pad or font_size <= 8:
            break
        font_size -= 2
    image = paste_centered(image, render_block(lines, font_size, style, Paint((0, 0, 0))),
                           width * 0.25, height / 2.0)
    free = render_block(lines, font_size, style, _paint(style, "caption", None, font_size))
    return paste_centered(image, free, width * 0.75, height / 2.0).convert("RGB")


def _fits(lines, size, style, inner, cy, cx):
    heights = line_heights(lines, size, style)
    top = cy - sum(heights) / 2.0
    for index, (words, width) in enumerate(lines):
        line_top = top
        top += heights[index]
        if not words:
            continue
        ink = int(heights[index] / style.line_spacing * 0.78)  # capitals, not the full em box
        y0 = int(line_top + (heights[index] - ink) / 2.0)
        y1 = y0 + ink
        x0 = int(cx - width / 2.0)
        x1 = int(math.ceil(cx + width / 2.0))
        if y0 < 0 or x0 < 0 or y1 > inner.shape[0] or x1 > inner.shape[1]:
            return False
        if inner[y0:y1, x0:x1].mean() < 0.97:
            return False
    return True


def _fit_bubble(image_height, bubble, text, style, strict):
    """_fit_text, and when *emphasis* is all that keeps the text out of the bubble, without it."""
    paragraphs = parse_text(text, style.uppercase)
    result = _fit_text(image_height, bubble, paragraphs, style, strict)
    if result is None and any(emph for words in paragraphs for _, emph, _ in words):
        paragraphs = [[(word, False, glue) for word, _, glue in words] for words in paragraphs]
        result = _fit_text(image_height, bubble, paragraphs, style, strict)
    # Still out: break the longest word with a hyphen, then the two longest, then three.
    # A broken word can only help when it lands on two lines, so no hyphen is ever
    # shown inside a line.
    for count in (1, 2, 3):
        if result is not None:
            break
        broken = _hyphenated(paragraphs, count)
        if broken is None:
            break
        result = _fit_text(image_height, bubble, broken, style, strict)
    return result


VOWELS = u"AEIOUYaeiouy\u0410\u0415\u0401\u0418\u041e\u0423\u042b\u042d\u042e\u042f\u0430\u0435\u0451\u0438\u043e\u0443\u044b\u044d\u044e\u044f"


def _split_word(word):
    """("unbe-", "lievable") for a long word, or None. The break is near the middle, after a
    vowel that a consonant follows where there is one, with three letters or more on each side."""
    letters = [i for i, ch in enumerate(word) if ch.isalpha()]
    if len(letters) < 6 or "-" in word:
        return None
    places = letters[3:len(letters) - 2]  # index of the first letter of the second half
    middle = (letters[0] + letters[-1] + 1) / 2.0

    def badness(i):
        natural = word[i - 1] in VOWELS and word[i] not in VOWELS
        return abs(i - middle) + (0.0 if natural else 1.5)

    places = [i for i in places if word[i - 1].isalpha()]
    if not places:
        return None
    at = min(places, key=badness)
    return word[:at] + "-", word[at:]


def _hyphenated(paragraphs, count):
    """The paragraphs with their `count` longest words broken in two, or None if there are
    fewer words that can be broken."""
    words = [(len(word), p, i) for p, para in enumerate(paragraphs) for i, (word, _, glue) in enumerate(para)
             if not glue and _split_word(word)]
    words.sort(key=lambda item: -item[0])
    if len(words) < count:
        return None
    chosen = set((p, i) for _, p, i in words[:count])
    result = []
    for p, para in enumerate(paragraphs):
        pieces = []
        for i, (word, emph, glue) in enumerate(para):
            if (p, i) in chosen:
                head, tail = _split_word(word)
                pieces.extend([(head, emph, glue), (tail, emph, True)])
            else:
                pieces.append((word, emph, glue))
        result.append(pieces)
    return result


def _fit_text(image_height, bubble, paragraphs, style, strict):
    """Largest layout of text that fits the bubble: (lines, size, cx, cy).

    Several ways to break the lines are tried, at the largest size that fits and a
    little below it. The winner balances size against shape: a layout close to a
    diamond (short lines at the top and bottom, long in the middle) may win over a
    slightly bigger one that stacks single words or leaves a lone last word.

    strict: return None when it only fits below the readable minimum. Otherwise fall
    back to the smallest size even if it overflows.
    """
    body = bubble.body
    ys, xs = np.nonzero(body)
    body_h = ys.max() - ys.min() + 1
    body_w = xs.max() - xs.min() + 1
    margin = max(2.0, style.margin * min(body_h, body_w))
    inner = ndi.distance_transform_edt(np.pad(body, 1))[1:-1, 1:-1] > margin
    if not inner.any():
        inner = body
    cy, cx = ndi.center_of_mass(inner)
    smallest = max(8, int(0.012 * image_height))
    if strict:
        smallest = max(smallest, int(round(style.bubble_min_size / 100.0 * image_height)))
    size = max(smallest, int(style.bubble_size / 100.0 * image_height))
    largest = None   # the largest size at which anything fits
    best = None      # (quality, lines, size)
    while True:
        fonts = get_fonts(style, size)
        candidates = [layout(paragraphs, fonts, body_w * fraction)
                      for fraction in (0.95, 0.82, 0.7, 0.58, 0.46)]
        candidates += [layout_shaped(paragraphs, fonts, count) for count in range(2, 7)]
        for lines in candidates:
            if lines is None or not _fits(lines, size, style, inner, cy, cx):
                continue
            if strict and len(lines) > MAX_LINES:
                continue
            if largest is None:
                largest = size
            quality = size / float(largest) - SHAPE_WEIGHT * shape_score(lines)
            if best is None or quality > best[0]:
                best = (quality, lines, size)
        # Keep looking a little below the largest fit: a better shape may be worth it.
        if largest is not None and (size <= smallest or size * 0.93 < largest * SHAPE_REACH):
            return best[1], best[2], bubble.x0 + cx, bubble.y0 + cy
        if size <= smallest:
            if strict:
                return None
            return layout(paragraphs, fonts, body_w * 0.82), size, bubble.x0 + cx, bubble.y0 + cy
        size = max(smallest, min(size - 1, int(size * 0.93)))


# ---------------------------------------------------------------- caption

def _anchor(placement, box_w, box_h, width, height):
    """Center of a box for a named placement."""
    edge = int(0.04 * height)
    cx = width / 2.0
    if placement.endswith("left"):
        cx = edge + box_w / 2.0
    elif placement.endswith("right"):
        cx = width - edge - box_w / 2.0
    cy = height / 2.0
    if placement.startswith("top"):
        cy = edge + box_h / 2.0
    elif placement.startswith("bottom"):
        cy = height - edge - box_h / 2.0
    return cx, cy


def _caption_look(style, pal):
    """The caption's style. Outlines make the lines taller: leave room for them."""
    look = voice(style, "caption")
    look.line_spacing += 1.2 * (max(0.0, style.stroke_width) + (0.07 if pal and pal.get("outer") else 0.0))
    return look


def _draw_caption(image, item, style, pal, precious):
    look = _caption_look(style, pal)
    look.rotation = item.get("rotation", look.rotation)
    size = item["size"]
    paint = _paint(style, "caption", pal, size, look.font)
    layer = render_block(_lines(item), size, look, paint)
    layer = decorate(layer, EXTRAS.get(style.caption_extras), size, paint, style.seed, precious,
                     (item["cx"], item["cy"]))
    return paste_centered(image, layer, item["cx"], item["cy"])


def _place_free(rgb, text, placement, style, static, pal, energy, precious=None, pin=None):
    """The scene item for the free text: a caption, or a balloon drawn for it."""
    pin = pin or {}
    if style.caption_bubble != "none":
        return _place_balloon(rgb, text, placement, style, static, energy, precious, pin)
    height, width = rgb.shape[:2]
    look = _caption_look(style, pal)
    look.rotation = pin.get("rotation", look.rotation)
    paragraphs = parse_text(text, style.uppercase)
    full = pin["size"] if "size" in pin else max(8, int(style.free_size / 100.0 * height))
    # A size set by hand is kept: no smaller one is tried to find a clear place.
    factors = (1.0,) if "size" in pin else (1.0, 0.85, 0.72)
    reach = 0.46 if "-" in placement else 0.88

    def fitted(size, reach):
        while True:
            lines = layout(paragraphs, get_fonts(look, size), width * reach)
            block_w, block_h = block_size(lines, size, look)
            # A size set by hand is taken as it is, even if the block comes out large.
            if (block_h <= height * 0.36 and block_w <= width * (reach + 0.04)) or size <= 8 or "size" in pin:
                if look.rotation or look.arc or look.line_tilt:
                    # Tilted or bent, the text takes more room than its straight block:
                    # measure what is really drawn, so the place is chosen for that.
                    drawn = render_block(lines, size, look, _paint(style, "caption", pal, size, look.font)).getbbox()
                    if drawn:
                        block_w, block_h = max(block_w, drawn[2] - drawn[0]), max(block_h, drawn[3] - drawn[1])
                return lines, size, block_w, block_h
            size = max(8, min(size - 1, int(size * 0.92)))

    if "cx" in pin:
        # A place set by hand: the line breaks stay as wide as they were when it was pinned.
        reach = 0.46 if pin.get("reach", 0.88) < 0.5 else 0.88
        lines, size, block_w, block_h = fitted(full, reach)
    elif placement == "auto":
        # A band at the top or the bottom, or a narrower block in a corner; if none of
        # them is clear of bubbles and characters, the same a little smaller. The calmest
        # clear one wins. If nothing is clear, the full-size one that covers the least,
        # a head counting most: a caption across the legs is fine, across the face it is not.
        options = []  # (smaller, narrow, cost, clear, name, fit), in order of preference
        for factor in factors:
            for names, wide in ((("top", "bottom"), 0.88),
                                (("top-left", "top-right", "bottom-left", "bottom-right"), 0.46)):
                fit = fitted(max(8, int(full * factor)), wide)
                for name in names:
                    cx, cy = _anchor(name, fit[2], fit[3], width, height)
                    x0, y0 = int(cx - fit[2] / 2.0), int(cy - fit[3] / 2.0)
                    rows = (max(0, y0), min(height, y0 + int(fit[3])))
                    cols = slice(max(0, x0), max(0, x0 + int(fit[2])))
                    covered = static[rows[0]:rows[1], cols]
                    share = float(covered.mean()) if covered.size else 1.0
                    total = edge_energy(rgb, *rows) + 1000.0 * share
                    clear = share < 0.02
                    if precious is not None:
                        total += 3000.0 * float(precious[rows[0]:rows[1], cols].mean())
                        # A small bubble is far below 2% of the block: none of it may be
                        # touched, the outline and the shadow around the letters included.
                        pad = int(0.5 * fit[1])
                        if precious[max(0, rows[0] - pad):rows[1] + pad,
                                    max(0, x0 - pad):max(0, x0 + int(fit[2]) + pad)].any():
                            clear = False
                            total += 400.0  # when nothing is clear: rather on a body than on a bubble
                    options.append((factor < 1.0, wide < 0.5, total, clear, name, fit))
            if any(option[3] for option in options):
                break
        clear = [option for option in options if option[3]]
        if clear:
            kind = clear[0][:2]
            best = min((option for option in clear if option[:2] == kind), key=lambda option: option[2])
        else:
            best = min((option for option in options if not option[0]), key=lambda option: option[2])
        placement, (lines, size, block_w, block_h) = best[4], best[5]
        reach = 0.46 if best[1] else 0.88
    else:
        lines, size, block_w, block_h = fitted(full, reach)
    if "cx" in pin:
        cx, cy = min(max(pin["cx"], 0.0), float(width)), min(max(pin["cy"], 0.0), float(height))
    else:
        cx, cy = _anchor(placement, block_w, block_h, width, height)
    box = [int(cx - block_w / 2.0 - size), int(cy - block_h / 2.0 - size * 0.5),
           int(cx + block_w / 2.0 + size), int(cy + block_h / 2.0 + size * 0.5)]
    return {"kind": "caption", "id": "caption", "text": text, "placement": placement, "lines": _plain(lines),
            "size": int(size), "cx": float(cx), "cy": float(cy), "box": box, "rotation": float(look.rotation),
            "reach": reach}


def _covered(static, precious, x, y, box_w, box_h):
    """How much of a box lies on bubbles and characters; heads and bubbles count four times."""
    rows, cols = slice(max(0, int(y)), max(0, int(y + box_h))), slice(max(0, int(x)), max(0, int(x + box_w)))
    part = static[rows, cols]
    if not part.size:
        return 1.0
    score = float(part.mean())
    if precious is not None:
        score += 3.0 * float(precious[rows, cols].mean())
    return score


def _drawn_bubble(paragraphs, look, style, size, width, height, tall=False):
    """Lay the text out and draw a bubble around it, trimmed to what is drawn.

    tall: a narrow bubble with more lines, for the strips of background beside a character.
    """
    shares, counts, aspect = ((0.12, 0.16, 0.2), range(3, 9), 0.75) if tall else ((0.24, 0.32, 0.42), range(2, 7), 1.7)
    while True:
        fonts = get_fonts(look, size)
        candidates = [layout(paragraphs, fonts, width * share) for share in shares]
        candidates += [shaped for shaped in (layout_shaped(paragraphs, fonts, n) for n in counts)
                       if shaped is not None and block_size(shaped, size, look)[0] <= width * 0.46]

        def unfit(candidate):
            # A good bubble is a diamond of text, about 1.7 times wider than tall (or
            # taller than wide when a tall one is asked for).
            w, h = block_size(candidate, size, look)
            return shape_score(candidate) + 0.3 * abs(math.log(max(w, 1.0) / (aspect * max(h, 1.0))))

        lines = min(candidates, key=unfit)
        block_w, block_h = block_size(lines, size, look)
        if (block_w <= width * 0.5 and block_h <= height * 0.3) or size <= 8:
            break
        size = max(8, min(size - 1, int(size * 0.92)))
    fill_mask, outline, bx, by = _balloon_shape(lines, size, look, style)
    return lines, size, fill_mask, outline, bx, by


def _balloon_shape(lines, size, look, style):
    """The bubble drawn around laid-out text, trimmed to what is drawn: (fill, outline, text x, text y)."""
    block_w, block_h = block_size(lines, size, look)
    fill_mask, outline, (bx, by) = bubble_shape(style.caption_bubble, block_w, block_h, size,
                                                style.caption_tail, style.seed)
    # The bubble is placed by what is drawn, tail and spikes included.
    bounds = outline.getbbox()
    if bounds:
        fill_mask, outline = fill_mask.crop(bounds), outline.crop(bounds)
        bx, by = bx - bounds[0], by - bounds[1]
    return fill_mask, outline, bx, by


def _place_balloon(rgb, text, placement, style, static, energy, precious=None, pin=None):
    """The scene item for a caption inside a bubble drawn for it."""
    pin = pin or {}
    height, width = rgb.shape[:2]
    look = voice(style, "caption")
    paragraphs = parse_text(text, style.uppercase)
    full = pin["size"] if "size" in pin else max(8, int(style.free_size / 100.0 * height))
    sized = "size" in pin  # a size set by hand is kept: no smaller one is tried
    tall = False
    if "cx" in pin:
        # A place set by hand: the bubble keeps the shape it had when it was pinned.
        tall = bool(pin.get("tall"))
        lines, size, fill_mask, outline, bx, by = _drawn_bubble(paragraphs, look, style, full, width, height, tall)
        x, y = int(pin["cx"] - fill_mask.width / 2.0), int(pin["cy"] - fill_mask.height / 2.0)
    elif placement == "auto":
        # Try the bubble wide, then tall and narrow, each time a little smaller (down to
        # half), until it fits clear of bubbles and characters. If nothing fits, take
        # the one that covers the least, heads counting most.
        table = _integral(static)
        heavy = _integral(precious) if precious is not None else None
        chosen = None
        for factor in ((1.0,) if sized else (1.0, 0.85, 0.72, 0.6, 0.5)):
            for shape in (False, True):
                drawn = _drawn_bubble(paragraphs, look, style, max(8, int(full * factor)), width, height, shape)
                x, y, clear, score = _calm_spot(energy, table, None, drawn[2].width, drawn[2].height,
                                                width, height, random.Random(style.seed), heavy)
                if clear or chosen is None or score < chosen[0]:
                    chosen = (score, drawn, x, y, shape)
                if clear:
                    break
            if clear:
                break
        _, (lines, size, fill_mask, outline, bx, by), x, y, tall = chosen
    else:
        # A fixed place: smaller sizes are tried there until the bubble is clear of bubbles
        # and characters. If none is, it lands on them anyway: then a moderately smaller
        # one is drawn, not the smallest, which would only be harder to read.
        tried = []
        for factor in ((1.0,) if sized else (1.0, 0.85, 0.72, 0.6)):
            drawn = _drawn_bubble(paragraphs, look, style, max(8, int(full * factor)), width, height)
            cx, cy = _anchor(placement, drawn[2].width, drawn[2].height, width, height)
            x, y = int(cx - drawn[2].width / 2.0), int(cy - drawn[2].height / 2.0)
            tried.append((drawn, x, y))
            clear = _covered(static, precious, x, y, drawn[2].width, drawn[2].height) < 0.02
            if clear and precious is not None:
                clear = not precious[max(0, y):max(0, y + drawn[2].height), max(0, x):max(0, x + drawn[2].width)].any()
            if clear:
                break
        (lines, size, fill_mask, outline, bx, by), x, y = tried[-1] if clear else tried[min(2, len(tried) - 1)]
    x = max(0, min(x, width - fill_mask.width))
    y = max(0, min(y, height - fill_mask.height))
    return {"kind": "balloon", "id": "caption", "text": text, "lines": _plain(lines), "size": int(size),
            "x": int(x), "y": int(y), "tall": bool(tall),
            "box": [int(x), int(y), int(x + fill_mask.width), int(y + fill_mask.height)]}


def _draw_balloon(image, item, style, pal, precious):
    look = voice(style, "caption")
    lines, size, x, y = _lines(item), item["size"], item["x"], item["y"]
    fill_mask, outline, bx, by = _balloon_shape(lines, size, look, style)
    if style.caption_bubble_theme == "dark":
        body = (14, 14, 18)
        line = pal["fill"] if pal else _own_color(style, "caption", style.text_color, (255, 255, 255))
        ink = line
    else:
        body = (250, 250, 250)
        line = (15, 15, 15)
        ink = pal["ink"] if pal else _own_color(style, "caption", style.text_color, (0, 0, 0))
    bubble = Image.alpha_composite(_solid(line, outline), _solid(body, fill_mask))
    center = (x + bubble.width / 2.0, y + bubble.height / 2.0)
    marks = Paint(pal["fill"] if pal else (255, 255, 255), line if style.caption_bubble_theme != "dark" else body)
    shown = decorate(bubble, EXTRAS.get(style.caption_extras), size, marks, style.seed, precious, center)
    image = paste_centered(image, shown, center[0], center[1])
    return paste_centered(image, render_block(lines, size, look, Paint(ink)), x + bx, y + by)


# ---------------------------------------------------------------- sound effects

def _integral(array):
    """Summed-area table with a zero first row and column."""
    return np.pad(array.astype(np.float64).cumsum(axis=0).cumsum(axis=1), ((1, 0), (1, 0)))


def _energy(rgb):
    """Integral image of the edge strength: low sums mean calm, empty areas."""
    lum = luminance(rgb.astype(np.float32))
    energy = np.zeros(lum.shape, dtype=np.float32)
    energy[:-1] += np.abs(np.diff(lum, axis=0))
    energy[:, :-1] += np.abs(np.diff(lum, axis=1))
    return _integral(energy)


def _calm_spot(energy, static, taken, box_w, box_h, width, height, rng, heavy=None, turn=None):
    """A place for a box: (x, y, clear, score).

    Candidates clear of the static obstacles (bubbles, characters) and not among the
    busiest third of them are preferred; rng picks a random point of the image and the
    candidate nearest to it wins, so repeated picks spread over the whole art. The
    choice depends only on the image and the box, so it stays put when styles change.
    A place that collides with `taken` (the caption, earlier effects) is never used
    while any other is left: the search widens to every clear place, then to places
    on a character, where `heavy` (heads, bubbles) counts several times more than the
    rest. clear tells whether the place returned is clear; score how much is covered if not.

    turn: an arrangement number, used instead of rng. The usable places are reduced to a
    few anchors that lie far apart, and turn picks one of them in rotation, so the next
    number always gives a visibly different place. With fewer than three such places
    clear of the characters, places on a character (never a head first) join in.
    static, taken and heavy are summed-area tables; taken and heavy may be None.
    """
    box_w, box_h = int(box_w), int(box_h)
    margin = int(0.02 * min(width, height))
    stride = max(4, min(width, height) // 40)
    xs = np.arange(margin, width - box_w - margin + 1, stride)
    ys = np.arange(margin, height - box_h - margin + 1, stride)
    if len(xs) == 0 or len(ys) == 0:
        return max(0, (width - box_w) // 2), max(0, (height - box_h) // 2), False, float("inf")
    area = float(max(1, box_w * box_h))

    def boxes(table):
        return ((table[np.ix_(ys + box_h, xs + box_w)] - table[np.ix_(ys, xs + box_w)]
                 - table[np.ix_(ys + box_h, xs)] + table[np.ix_(ys, xs)]) / area).ravel()

    cost = boxes(energy)
    blocked = boxes(static)
    penalty = cost + 1000.0 * blocked
    if heavy is not None:
        penalty = penalty + 6000.0 * boxes(heavy)
    clear = np.nonzero(blocked < 0.002)[0]
    found = len(clear) > 0

    def centers(candidates):
        return xs[candidates % len(xs)] + box_w / 2.0, ys[candidates // len(xs)] + box_h / 2.0

    def anchors(pool, limit=6):
        """Up to `limit` places of the pool that lie far apart, the calmest one first."""
        px, py = centers(pool)
        chosen = [int(np.argmin(penalty[pool]))]
        apart = np.hypot(px - px[chosen[0]], py - py[chosen[0]])
        while len(chosen) < limit:
            far = int(np.argmax(apart))
            if apart[far] < 0.14 * min(width, height):
                break  # what is left is too close to count as another place
            chosen.append(far)
            apart = np.minimum(apart, np.hypot(px - px[far], py - py[far]))
        return [(float(px[i]), float(py[i])) for i in chosen]

    if turn is None:
        target_x, target_y = rng.random() * width, rng.random() * height
    else:
        spots = anchors(clear[cost[clear] <= np.quantile(cost[clear], 0.85)]) if found else []
        if len(spots) < 3:
            least = np.argsort(penalty)[:max(1, int(penalty.size * 0.12))]
            extra = [s for s in anchors(least) if all(np.hypot(s[0] - o[0], s[1] - o[1])
                                                    >= 0.14 * min(width, height) for o in spots)]
            spots = spots + extra
        target_x, target_y = spots[turn % len(spots)]

    def nearest(candidates):
        center_x, center_y = centers(candidates)
        return candidates[np.argsort((center_x - target_x) ** 2 + (center_y - target_y) ** 2)]

    # Tiers of candidates, best first: calm and clear, any clear place, then anywhere,
    # ordered by how little is covered. The first one free of `taken` wins, so two
    # effects never share a place while there is room left anywhere.
    tiers = []
    if found:
        tiers.append(nearest(clear[cost[clear] <= np.quantile(cost[clear], 0.85 if turn is not None else 0.7)]))
        tiers.append(nearest(clear))
    if turn is not None:
        # The anchor may be a place on a character: let the nearest low-cover place win.
        least = np.argsort(penalty)[:max(1, int(penalty.size * 0.12))]
        tiers.insert(0, nearest(np.union1d(tiers[0], least) if tiers else least)[:1])
    tiers.append(np.argsort(penalty))
    score = 0.0 if found else float(penalty.min())
    pick = int(tiers[0][0])
    if taken is not None:
        busy = boxes(taken)
        for tier in tiers:
            free = tier[busy[tier] < 0.002]
            if len(free):
                pick = int(free[0])
                break
        else:
            pick = int(np.argmin(busy + penalty * 1e-6))
    return int(xs[pick % len(xs)]), int(ys[pick // len(xs)]), bool(blocked[pick] < 0.002), score


def _sfx_layer(effect, size, base_look, style, pal, rng, seed, width, height, rotation=None):
    """One sound effect as a cropped RGBA layer, with the paint used for it.

    rotation: the tilt to use instead of the random one (which is still drawn from rng,
    so everything after it comes out the same).
    """
    look = copy.copy(base_look)
    look.rotation = rng.uniform(-style.sfx_tilt, style.sfx_tilt)
    if rotation is not None:
        look.rotation = rotation
    look.arc = rng.uniform(-0.2, 0.2)
    look.opacity = style.sfx_opacity
    look.seed = seed
    look.line_spacing += 1.2 * (0.14 + (0.07 if pal and pal.get("outer") else 0.0))
    paragraphs = parse_text(effect, style.uppercase)
    while True:
        lines = layout(paragraphs, get_fonts(look, size), width * 0.7)
        block_w, block_h = block_size(lines, size, look)
        if (block_w <= width * 0.72 and block_h <= height * 0.4) or size <= 10:
            break
        size = max(10, int(size * 0.9))
    paint = _paint(style, "sfx", pal, size, look.font)
    layer = render_block(lines, size, look, paint)
    bounds = layer.getbbox()
    return (layer.crop(bounds) if bounds else None), paint, size


def _repeat(effect):
    """("FAP", 5) for "FAP x5"; (the effect, 1) otherwise."""
    repeat = REPEAT.match(effect)
    count = min(12, int(repeat.group(2))) if repeat else 1
    return (repeat.group(1) if repeat and count > 1 else effect), count


def _place_sfx(rgb, effects, static, taken, style, energy, precious=None, pins=None, first=0):
    """The scene items for the sound effects. `taken` gains the room of each one.

    first: the number of the first effect; the effects of regions are numbered apart.
    """
    height, width = rgb.shape[:2]
    static_table = _integral(static)
    heavy = _integral(precious) if precious is not None else None
    items = []
    for index, effect in enumerate(effects, first):
        # Two random streams, both independent of the look: one for the size and tilt,
        # one for the place. Changing fonts, colors or moods then moves nothing.
        rng = random.Random(style.sfx_seed * 1000003 + index)
        size = max(10, int(style.sfx_size / 100.0 * height * rng.uniform(0.85, 1.15)))
        word, count = _repeat(effect)
        pin = _pin((pins or {}).get("sfx:%d" % index))
        # The tilt a single word gets is the next number of the stream; a column of words
        # tilts each word by itself, so its own tilt is none unless set by hand.
        rotation = pin.get("rotation", rng.uniform(-style.sfx_tilt, style.sfx_tilt) if count == 1 else 0.0)
        if "size" in pin:
            size = max(10, pin["size"])
        # The place is chosen for a nominal box that depends on the text and size only.
        # Its width is estimated per character, not measured, so the font does not matter.
        units = _sfx_units(word)
        # An effect that would land on a character is tried smaller first. Like the place,
        # the size then depends on the image and the text only.
        taken_table = _integral(taken)
        tried = []
        for factor in ((1.0,) if "size" in pin or "cx" in pin else (1.0, 0.8, 0.65)):
            trial = max(10, int(size * factor))
            trial_w = int(min(width * 0.9, (units + 0.8) * trial))
            trial_h = int(min(height * 0.9, trial * (1.4 if count == 1 else 0.75 * count + 0.8)))
            if "cx" in pin:
                # Where it was put by hand, as far as its box stays inside the image.
                x = int(min(max(pin["cx"] - trial_w / 2.0, 0), max(0, width - trial_w)))
                y = int(min(max(pin["cy"] - trial_h / 2.0, 0), max(0, height - trial_h)))
                clear = True
            else:
                x, y, clear, _ = _calm_spot(energy, static_table, taken_table, trial_w, trial_h, width, height,
                                            None, heavy, turn=style.sfx_seed + index)
            tried.append((trial, trial_w, trial_h, x, y))
            if clear:
                break
        size, nominal_w, nominal_h, x, y = tried[-1] if clear else tried[min(1, len(tried) - 1)]
        # Reserve room for this effect so the next one keeps off it. The room is worked
        # out from the text and the size alone, generous enough for a wide font and for
        # marks around: were it measured from what was drawn, a change of font or marks
        # would resize it and push the later effects somewhere else.
        room_w = (units * 0.62 + 1.0) * size + 2.8 * size
        room_h = size * (1.5 if count == 1 else 0.75 * count + 0.9) + 2.8 * size
        center_x, center_y = x + nominal_w / 2.0, y + nominal_h / 2.0
        room = [max(0, int(center_x - room_w / 2.0)), max(0, int(center_y - room_h / 2.0)),
                max(0, int(center_x + room_w / 2.0)), max(0, int(center_y + room_h / 2.0))]
        _reserve(taken, room)
        items.append({"kind": "sfx", "id": "sfx:%d" % index, "text": effect, "index": index, "size": int(size),
                      "x": int(x), "y": int(y), "nominal": [int(nominal_w), int(nominal_h)], "room": room,
                      "rotation": float(rotation)})
    return items


def _draw_sfx(image, item, static, taken, style, pal, width, height):
    """Draw one sound effect. `taken` is the room of what was drawn before it."""
    base_look = voice(style, "sfx")
    index, effect, size, x, y = item["index"], item["text"], item["size"], item["x"], item["y"]
    nominal_w, nominal_h = item["nominal"]
    rng = random.Random(style.sfx_seed * 1000003 + index)
    rng.uniform(0.85, 1.15)  # the draw that sized the effect when it was placed: keep the stream in step
    seed = style.sfx_seed + index * 101
    word, count = _repeat(effect)
    if count > 1:
        # "FAP x5": the word several times in a ragged column.
        rows = []
        for row in range(count):
            piece, paint, _ = _sfx_layer(word, max(10, int(size * rng.uniform(0.7, 1.15))),
                                         base_look, style, pal, rng, seed + row, width, height)
            if piece is not None:
                rows.append((piece, int(rng.uniform(-0.3, 0.3) * size)))
        if not rows:
            return image
        reach = int(0.3 * size)
        layer = Image.new("RGBA", (max(p.width for p, _ in rows) + 2 * reach,
                                   int(sum(p.height * 0.72 for p, _ in rows) + rows[-1][0].height * 0.28) + 2),
                          (0, 0, 0, 0))
        top = 0.0
        for piece, shift in rows:
            layer.alpha_composite(piece, (max(0, (layer.width - piece.width) // 2 + shift), int(top)))
            top += piece.height * 0.72
        if item.get("rotation"):
            layer = layer.rotate(item["rotation"], resample=Image.BICUBIC, expand=True)  # the whole column
        bounds = layer.getbbox()
        if bounds is None:
            return image
        layer = layer.crop(bounds)
    else:
        layer, paint, size = _sfx_layer(effect, size, base_look, style, pal, rng, seed, width, height,
                                        item.get("rotation"))
        if layer is None:
            return image
    if layer.width > width * 0.9 or layer.height > height * 0.9:
        layer.thumbnail((int(width * 0.9), int(height * 0.9)), Image.LANCZOS)
    cx = min(max(x + nominal_w / 2.0, layer.width / 2.0), width - layer.width / 2.0)
    cy = min(max(y + nominal_h / 2.0, layer.height / 2.0), height - layer.height / 2.0)
    # An effect made of symbols alone gets no marks around it: hearts around hearts.
    plain = [ch for ch in word if not ch.isspace() and ch != "*"]
    kind = None if plain and all(ch in SYMBOLS for ch in plain) else EXTRAS.get(style.sfx_extras)
    # Marks keep off the characters, the bubbles and the room of earlier effects.
    layer = decorate(layer, kind, size, paint, seed, static | taken, (cx, cy))
    return paste_centered(image, layer, cx, cy)
