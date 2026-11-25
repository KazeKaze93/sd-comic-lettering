"""Entry point: put the user's text into detected bubbles, or straight onto the art."""
import colorsys
import copy
import math
import random
import re
from typing import Dict, Tuple

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from .detect import detect_bubbles, edge_energy, erase_letters, luminance
from .people import person_mask
from .render import (EXTRAS, MOODS, PALETTES, Paint, Style, _solid, block_size, bubble_shape,
                     decorate, get_fonts, layout, layout_shaped, line_heights, parse_color,
                     parse_text, paste_centered, render_block, shape_score, stem_ratio)

PLACEMENTS = ["auto", "top", "bottom", "center", "top-left", "top-right", "bottom-left",
              "bottom-right"]
SHAPE_WEIGHT = 0.6   # how much font size a better line shape is worth
SHAPE_REACH = 0.8    # look for a better shape down to this share of the largest size
SAMPLE_TEXT = u"Hello! Привет! 123"
REPEAT = re.compile(u"^(.*?\\S)\\s*[xX×]\\s*(\\d{1,2})$")  # "FAP x5"


def letter(image, text="", caption="", spill=True, placement="auto", style=None, erase=True,
           white_threshold=120, rtl=False, numbers=False, sfx=""):
    # type: (Image.Image, str, str, bool, str, Style, bool, int, bool, bool, str) -> Tuple[Image.Image, Dict]
    """Letter an image.

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
    style = style or Style()
    info = {"bubbles_found": 0, "bubbles_filled": 0, "free_text": False, "font_sizes": []}
    lines = [line.strip() for line in (text or "").replace("\r", "").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    caption = (caption or "").replace("\r", "").strip()
    effects = [line.strip() for line in (sfx or "").replace("\r", "").split("\n") if line.strip()]
    if not lines and not caption and not numbers and not effects:
        return image, info
    rgb = np.array(image.convert("RGB"))
    height = rgb.shape[0]
    bubbles = detect_bubbles(rgb, white_threshold, rtl=rtl)  # also so nothing lands on them
    info["bubbles_found"] = len(bubbles)
    strict = bool(spill)
    if numbers:
        lines = [str(i + 1) for i in range(len(bubbles))]
        caption = ""
        erase = False
        strict = False
    accent = None
    if "from the art" in (style.bubble_colors, style.caption_colors, style.sfx_colors):
        accent = accent_palette(rgb)
    bubble_look = voice(style, "bubble")

    def fit(index, line):
        return _fit_bubble(height, bubbles[index], line, bubble_look, strict)

    plans, rest = _assign(lines, len(bubbles), fit)
    if erase:
        for index, _ in plans:
            erase_letters(rgb, bubbles[index])
    out = Image.fromarray(rgb)
    for index, (laid_out, size, cx, cy) in plans:
        ink = _bubble_ink(style, bubbles[index], palette(style, "bubble", accent))
        out = paste_centered(out, render_block(laid_out, size, bubble_look, Paint(ink)), cx, cy)
        info["font_sizes"].append(size)
        info["bubbles_filled"] += 1
    free = (rest if spill and not numbers else []) + ([caption] if caption else [])
    effects = [] if numbers else effects
    # Static obstacles: the bubbles found in the art and, when known, the characters.
    static = np.zeros(rgb.shape[:2], dtype=bool)
    for bubble in bubbles:
        h, w = bubble.filled.shape
        static[bubble.y0:bubble.y0 + h, bubble.x0:bubble.x0 + w] |= bubble.filled
    automatic = effects or (free and placement == "auto")
    people = None
    if automatic:
        people = person_mask(rgb)
        info["characters"] = people is not None
        if people is not None:
            static |= people
    energy = _energy(rgb) if (effects or (free and style.caption_bubble != "none")) else None
    caption_box = None
    if free:
        out, size, caption_box = _letter_free(out, rgb, "\n".join(free), placement, style, static,
                                              palette(style, "caption", accent), energy, people)
        info["free_text"] = True
        info["font_sizes"].append(size)
    if effects:
        taken = np.zeros(rgb.shape[:2], dtype=bool)  # the caption and the effects placed so far
        if caption_box is not None:
            x0, y0, x1, y1 = caption_box
            taken[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
        out = _letter_sfx(out, rgb, effects, static, taken, style, palette(style, "sfx", accent), energy)
        info["sfx"] = len(effects)
    return out.convert("RGB"), info


# ---------------------------------------------------------------- looks and colors

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
    return accent if spec == "accent" else spec


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
        return parse_color(style.text_color, plain)
    return pal["ink"] if light else pal["fill"]


def _paint(style, which, pal, size, font=None):
    """Colors and outline widths for a caption or a sound effect."""
    stroke_px = int(round(size * max(0.0, style.stroke_width if which == "caption" else 0.14)))
    shadow = style.shadow if which == "caption" else 0.0
    if pal is None:
        fill = parse_color(style.text_color if which == "caption" else style.sfx_color, (255, 255, 255))
        stroke = (0, 0, 0) if _brightness(fill) > 128 else (255, 255, 255)
        if which == "caption":
            stroke = parse_color(style.stroke_color, stroke)
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
    the line then tries the next bubble. An empty line uses up one bubble.
    Returns ([(bubble index, layout)], leftover lines).
    """
    taken = [False] * count
    plans = []
    rest = []
    for line in lines:
        placed = False
        for index in range(count):
            if taken[index]:
                continue
            taken[index] = True
            if not line:
                placed = True
                break
            result = fit(index, line)
            if result is not None:
                plans.append((index, result))
                placed = True
                break
        if not placed and line:
            rest.append(line)
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
    paragraphs = parse_text(text, style.uppercase)
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


def _letter_free(image, rgb, text, placement, style, static, pal, energy, people=None):
    if style.caption_bubble != "none":
        return _letter_drawn_bubble(image, rgb, text, placement, style, static, pal, energy)
    height, width = rgb.shape[:2]
    look = voice(style, "caption")
    # Outlines make the lines taller: leave room for them.
    look.line_spacing += 1.2 * (max(0.0, style.stroke_width) + (0.07 if pal and pal.get("outer") else 0.0))
    paragraphs = parse_text(text, style.uppercase)
    size = max(8, int(style.free_size / 100.0 * height))
    corner = "-" in placement
    reach = 0.46 if corner else 0.88
    while True:
        lines = layout(paragraphs, get_fonts(look, size), width * reach)
        block_w, block_h = block_size(lines, size, look)
        if (block_h <= height * 0.36 and block_w <= width * (reach + 0.04)) or size <= 8:
            break
        size = max(8, min(size - 1, int(size * 0.92)))
    edge = int(0.04 * height)
    if placement == "auto":
        # The calmer of top and bottom; a band over a bubble or a character loses, and
        # one over a head loses badly: a caption across the legs is fine, across the
        # face it is not.
        left = int(max(0, width / 2.0 - block_w / 2.0))
        right = int(min(width, width / 2.0 + block_w / 2.0))
        heads = None
        if people is not None and people.any():
            rows_with_people = np.nonzero(people.any(axis=1))[0]
            first, last = int(rows_with_people[0]), int(rows_with_people[-1])
            heads = people.copy()
            heads[first + int(0.25 * (last - first + 1)):] = False

        def cost(rows):
            covered = static[rows[0]:rows[1], left:right]
            total = edge_energy(rgb, *rows) + 1000.0 * (float(covered.mean()) if covered.size else 1.0)
            if heads is not None:
                total += 3000.0 * float(heads[rows[0]:rows[1], left:right].mean())
            return total

        top = cost((edge, min(height, edge + block_h)))
        bottom = cost((max(0, height - edge - block_h), height - edge))
        placement = "top" if top < bottom else "bottom"
    cx, cy = _anchor(placement, block_w, block_h, width, height)
    paint = _paint(style, "caption", pal, size, look.font)
    layer = render_block(lines, size, look, paint)
    layer = decorate(layer, EXTRAS.get(style.caption_extras), size, paint, style.seed)
    box = (int(cx - block_w / 2.0 - size), int(cy - block_h / 2.0 - size * 0.5),
           int(cx + block_w / 2.0 + size), int(cy + block_h / 2.0 + size * 0.5))
    return paste_centered(image, layer, cx, cy), size, box


def _drawn_bubble(paragraphs, look, style, size, width, height):
    """Lay the text out and draw a bubble around it, trimmed to what is drawn."""
    while True:
        fonts = get_fonts(look, size)
        candidates = [layout(paragraphs, fonts, width * share) for share in (0.24, 0.32, 0.42)]
        candidates += [shaped for shaped in (layout_shaped(paragraphs, fonts, n) for n in range(2, 7))
                       if shaped is not None and block_size(shaped, size, look)[0] <= width * 0.46]

        def unfit(candidate):
            # A good bubble is a diamond of text about 1.7 times wider than tall.
            w, h = block_size(candidate, size, look)
            return shape_score(candidate) + 0.3 * abs(math.log(max(w, 1.0) / (1.7 * max(h, 1.0))))

        lines = min(candidates, key=unfit)
        block_w, block_h = block_size(lines, size, look)
        if (block_w <= width * 0.5 and block_h <= height * 0.3) or size <= 8:
            break
        size = max(8, min(size - 1, int(size * 0.92)))
    fill_mask, outline, (bx, by) = bubble_shape(style.caption_bubble, block_w, block_h, size,
                                                style.caption_tail, style.seed)
    # The bubble is placed by what is drawn, tail and spikes included.
    bounds = outline.getbbox()
    if bounds:
        fill_mask, outline = fill_mask.crop(bounds), outline.crop(bounds)
        bx, by = bx - bounds[0], by - bounds[1]
    return lines, size, fill_mask, outline, bx, by


def _letter_drawn_bubble(image, rgb, text, placement, style, static, pal, energy):
    """The caption inside a bubble drawn for it."""
    height, width = rgb.shape[:2]
    look = voice(style, "caption")
    paragraphs = parse_text(text, style.uppercase)
    full = max(8, int(style.free_size / 100.0 * height))
    chosen = None
    if placement == "auto":
        # Shrink the bubble, down to 60%, until it fits clear of bubbles and characters.
        table = _integral(static)
        # If nothing fits, settle for a middle size: it covers less than the full one.
        for factor in (1.0, 0.85, 0.72, 0.6):
            drawn = _drawn_bubble(paragraphs, look, style, max(8, int(full * factor)), width, height)
            x, y, clear = _calm_spot(energy, table, None, drawn[2].width, drawn[2].height, width, height,
                                     random.Random(style.seed))
            if clear or factor == 0.72 or chosen is None:
                chosen = (drawn, x, y)
            if clear:
                break
        (lines, size, fill_mask, outline, bx, by), x, y = chosen
    else:
        lines, size, fill_mask, outline, bx, by = _drawn_bubble(paragraphs, look, style, full, width, height)
        cx, cy = _anchor(placement, fill_mask.width, fill_mask.height, width, height)
        x, y = int(cx - fill_mask.width / 2.0), int(cy - fill_mask.height / 2.0)
    if style.caption_bubble_theme == "dark":
        body = (14, 14, 18)
        line = pal["fill"] if pal else parse_color(style.text_color, (255, 255, 255))
        ink = line
    else:
        body = (250, 250, 250)
        line = (15, 15, 15)
        ink = pal["ink"] if pal else parse_color(style.text_color, (0, 0, 0))
    bubble = Image.alpha_composite(_solid(line, outline), _solid(body, fill_mask))
    x = max(0, min(x, width - bubble.width))
    y = max(0, min(y, height - bubble.height))
    center = (x + bubble.width / 2.0, y + bubble.height / 2.0)
    marks = Paint(pal["fill"] if pal else (255, 255, 255), line if style.caption_bubble_theme != "dark" else body)
    shown = decorate(bubble, EXTRAS.get(style.caption_extras), size, marks, style.seed)
    image = paste_centered(image, shown, center[0], center[1])
    image = paste_centered(image, render_block(lines, size, look, Paint(ink)), x + bx, y + by)
    return image, size, (x, y, x + bubble.width, y + bubble.height)


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


def _calm_spot(energy, static, taken, box_w, box_h, width, height, rng):
    """Top-left corner for a box, and whether it is clear of the static obstacles.

    Candidates clear of the static obstacles (bubbles, characters) are ranked by how
    calm the art is under them, and rng picks one of the calmest quarter. That choice
    depends only on the image and the box, so it stays put when styles change. If the
    pick collides with `taken` (the caption, earlier effects), the next free one in
    the ranking is used. static and taken are summed-area tables; taken may be None.
    """
    box_w, box_h = int(box_w), int(box_h)
    margin = int(0.02 * min(width, height))
    stride = max(4, min(width, height) // 40)
    xs = np.arange(margin, width - box_w - margin + 1, stride)
    ys = np.arange(margin, height - box_h - margin + 1, stride)
    if len(xs) == 0 or len(ys) == 0:
        return max(0, (width - box_w) // 2), max(0, (height - box_h) // 2), False
    area = float(max(1, box_w * box_h))

    def boxes(table):
        return (table[np.ix_(ys + box_h, xs + box_w)] - table[np.ix_(ys, xs + box_w)]
                - table[np.ix_(ys + box_h, xs)] + table[np.ix_(ys, xs)]) / area

    cost = boxes(energy)
    blocked = boxes(static)
    clear = blocked < 0.002
    found = bool(clear.any())
    if found:
        cost = np.where(clear, cost, np.inf)
        pool = max(1, int(clear.sum() * 0.25))
    else:  # nowhere is clear: cover as little as possible
        cost = cost + 1000.0 * blocked
        pool = max(1, int(cost.size * 0.03))
    order = np.argsort(cost, axis=None)
    start = rng.randrange(pool)
    pick = int(order[start])
    if taken is not None:
        busy = boxes(taken).ravel()
        ranked = np.concatenate([order[start:], order[:start]])
        usable = np.isfinite(cost.ravel()[ranked])
        free = np.nonzero((busy[ranked] < 0.002) & usable)[0]
        if len(free):
            pick = int(ranked[free[0]])
        elif usable.any():  # everything is taken: overlap the least
            pick = int(ranked[usable][np.argmin(busy[ranked][usable])])
    return int(xs[pick % len(xs)]), int(ys[pick // len(xs)]), found


def _sfx_layer(effect, size, base_look, style, pal, rng, seed, width, height):
    """One sound effect as a cropped RGBA layer, with the paint used for it."""
    look = copy.copy(base_look)
    look.rotation = rng.uniform(-style.sfx_tilt, style.sfx_tilt)
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


def _letter_sfx(image, rgb, effects, static, taken, style, pal, energy):
    height, width = rgb.shape[:2]
    base_look = voice(style, "sfx")
    static_table = _integral(static)
    for index, effect in enumerate(effects):
        # Two random streams, both independent of the look: one for the size and tilt,
        # one for the place. Changing fonts, colors or moods then moves nothing.
        rng = random.Random(style.sfx_seed * 1000003 + index)
        place = random.Random(style.sfx_seed * 7919 + index * 31 + 1)
        size = max(10, int(style.sfx_size / 100.0 * height * rng.uniform(0.85, 1.15)))
        seed = style.sfx_seed + index * 101
        repeat = REPEAT.match(effect)
        count = min(12, int(repeat.group(2))) if repeat else 1
        word = repeat.group(1) if repeat and count > 1 else effect
        # The place is chosen for a nominal box that depends on the text and size only.
        longest = max([len(part) for part in word.replace("*", "").split()] or [1]) if count > 1 else len(word)
        frame = 1.5 * size  # room for the marks, reserved even when there are none
        nominal_w = int(min(width * 0.9, longest * 0.55 * size + size + frame))
        nominal_h = int(min(height * 0.9, size * (1.3 if count == 1 else 0.75 * count + 0.6) + frame))
        x, y, _ = _calm_spot(energy, static_table, _integral(taken), nominal_w, nominal_h, width, height, place)
        taken[max(0, y):y + nominal_h, max(0, x):x + nominal_w] = True
        if count > 1:
            # "FAP x5": the word several times in a ragged column.
            rows = []
            for row in range(count):
                piece, paint, _ = _sfx_layer(word, max(10, int(size * rng.uniform(0.7, 1.15))),
                                             base_look, style, pal, rng, seed + row, width, height)
                if piece is not None:
                    rows.append((piece, int(rng.uniform(-0.3, 0.3) * size)))
            if not rows:
                continue
            reach = int(0.3 * size)
            layer = Image.new("RGBA", (max(p.width for p, _ in rows) + 2 * reach,
                                       int(sum(p.height * 0.72 for p, _ in rows) + rows[-1][0].height * 0.28) + 2),
                              (0, 0, 0, 0))
            top = 0.0
            for piece, shift in rows:
                layer.alpha_composite(piece, (max(0, (layer.width - piece.width) // 2 + shift), int(top)))
                top += piece.height * 0.72
        else:
            layer, paint, size = _sfx_layer(effect, size, base_look, style, pal, rng, seed, width, height)
            if layer is None:
                continue
        layer = decorate(layer, EXTRAS.get(style.sfx_extras), size, paint, seed)
        bounds = layer.getbbox()
        if bounds is None:
            continue
        layer = layer.crop(bounds)
        if layer.width > width * 0.9 or layer.height > height * 0.9:
            layer.thumbnail((int(width * 0.9), int(height * 0.9)), Image.LANCZOS)
        cx = min(max(x + nominal_w / 2.0, layer.width / 2.0), width - layer.width / 2.0)
        cy = min(max(y + nominal_h / 2.0, layer.height / 2.0), height - layer.height / 2.0)
        image = paste_centered(image, layer, cx, cy)
    return image
