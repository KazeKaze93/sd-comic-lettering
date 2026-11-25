"""Entry point: put the user's text into detected bubbles, or straight onto the art."""
import copy
import math
import random
import re
from typing import Dict, Tuple

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from .detect import detect_bubbles, edge_energy, erase_letters, luminance
from .render import (Style, block_size, get_fonts, layout, layout_shaped, line_heights,
                     parse_color, parse_text, paste_centered, render_block, shape_score)

PLACEMENTS = ["auto", "top", "bottom", "center"]
SHAPE_WEIGHT = 0.6   # how much font size a better line shape is worth
SHAPE_REACH = 0.8    # look for a better shape down to this share of the largest size
SAMPLE_TEXT = u"Hello! \u041f\u0440\u0438\u0432\u0435\u0442! 123"


def letter(image, text="", caption="", spill=True, placement="auto", style=None, erase=True,
           white_threshold=120, rtl=False, numbers=False, sfx=""):
    # type: (Image.Image, str, str, bool, str, Style, bool, int, bool, bool, str) -> Tuple[Image.Image, Dict]
    """Letter an image.

    text: one line per bubble, in reading order (top to bottom, left to right). An
    empty line leaves its bubble alone.
    caption: free text drawn straight onto the art, outside the bubbles.
    spill: a line goes into a bubble only if it fits at a readable size
    (style.bubble_min_size); a bubble too small for it is passed over, and lines left
    without a bubble are added to the caption. Off: always write into the bubbles,
    however small, and drop the lines left over.
    numbers: draw each bubble's number instead of any text, to see the order.
    sfx: sound effects, one per line ("SLAP", "THUD"). Each is drawn big and tilted in
    a calm, empty part of the art, clear of the bubbles, the caption and each other.
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
    bubbles = detect_bubbles(rgb, white_threshold, rtl=rtl) if (lines or numbers or effects) else []
    info["bubbles_found"] = len(bubbles)
    strict = bool(spill)
    if numbers:
        lines = [str(i + 1) for i in range(len(bubbles))]
        caption = ""
        erase = False
        strict = False

    def fit(index, line):
        return _fit_bubble(height, bubbles[index], line, style, strict)

    plans, rest = _assign(lines, len(bubbles), fit)
    if erase:
        for index, _ in plans:
            erase_letters(rgb, bubbles[index])
    out = Image.fromarray(rgb)
    for index, (laid_out, size, cx, cy) in plans:
        bubble = bubbles[index]
        light = (bubble.color[0] * 0.299 + bubble.color[1] * 0.587 + bubble.color[2] * 0.114) > 128
        fill = parse_color(style.text_color, (0, 0, 0) if light else (255, 255, 255))
        out = paste_centered(out, render_block(laid_out, size, style, fill), cx, cy)
        info["font_sizes"].append(size)
        info["bubbles_filled"] += 1
    free = (rest if spill and not numbers else []) + ([caption] if caption else [])
    caption_box = None
    occupied = np.zeros(rgb.shape[:2], dtype=bool)
    for bubble in bubbles:
        h, w = bubble.filled.shape
        occupied[bubble.y0:bubble.y0 + h, bubble.x0:bubble.x0 + w] |= bubble.filled
    if free:
        out, size, caption_box = _letter_free(out, rgb, "\n".join(free), placement, style, occupied)
        info["free_text"] = True
        info["font_sizes"].append(size)
    if effects and not numbers:
        if caption_box is not None:
            x0, y0, x1, y1 = caption_box
            occupied[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = True
        out = _letter_sfx(out, rgb, effects, occupied, style)
        info["sfx"] = len(effects)
    return out.convert("RGB"), info


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
    bubble = render_block(lines, font_size, style, (0, 0, 0))
    image = paste_centered(image, bubble, width * 0.25, height / 2.0)
    stroke = int(round(font_size * max(0.0, style.stroke_width)))
    free = render_block(lines, font_size, style, (255, 255, 255), (0, 0, 0), stroke, style.shadow)
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


def _letter_free(image, rgb, text, placement, style, occupied):
    height, width = rgb.shape[:2]
    paragraphs = parse_text(text, style.uppercase)
    size = max(8, int(style.free_size / 100.0 * height))
    while True:
        lines = layout(paragraphs, get_fonts(style, size), width * 0.88)
        block_w, block_h = block_size(lines, size, style)
        if (block_h <= height * 0.36 and block_w <= width * 0.92) or size <= 8:
            break
        size = max(8, min(size - 1, int(size * 0.92)))
    edge = int(0.04 * height)
    top_cy = edge + block_h / 2.0
    bottom_cy = height - edge - block_h / 2.0
    if placement == "auto":
        # The calmer of top and bottom; a band that would cover a bubble loses.
        left = int(max(0, width / 2.0 - block_w / 2.0))
        right = int(min(width, width / 2.0 + block_w / 2.0))
        top_rows = (edge, min(height, edge + block_h))
        bottom_rows = (max(0, height - edge - block_h), height - edge)
        top = edge_energy(rgb, *top_rows) + 1000.0 * occupied[top_rows[0]:top_rows[1], left:right].any()
        bottom = (edge_energy(rgb, *bottom_rows)
                  + 1000.0 * occupied[bottom_rows[0]:bottom_rows[1], left:right].any())
        placement = "top" if top < bottom else "bottom"
    cy = {"top": top_cy, "bottom": bottom_cy}.get(placement, height / 2.0)
    fill = parse_color(style.text_color, (255, 255, 255))
    fill_light = (fill[0] * 0.299 + fill[1] * 0.587 + fill[2] * 0.114) > 128
    stroke = parse_color(style.stroke_color, (0, 0, 0) if fill_light else (255, 255, 255))
    stroke_px = int(round(size * max(0.0, style.stroke_width)))
    layer = render_block(lines, size, style, fill, stroke, stroke_px, style.shadow)
    box = (int(width / 2.0 - block_w / 2.0 - size), int(cy - block_h / 2.0 - size * 0.5),
           int(width / 2.0 + block_w / 2.0 + size), int(cy + block_h / 2.0 + size * 0.5))
    return paste_centered(image, layer, width / 2.0, cy), size, box


def _integral(array):
    """Summed-area table with a zero first row and column."""
    return np.pad(array.astype(np.float64).cumsum(axis=0).cumsum(axis=1), ((1, 0), (1, 0)))


def _calm_spot(energy, taken, box_w, box_h, width, height, rng):
    """Top-left corner for a box: a free place among the calmest ones, picked at random."""
    margin = int(0.02 * min(width, height))
    stride = max(4, min(width, height) // 40)
    xs = np.arange(margin, width - box_w - margin + 1, stride)
    ys = np.arange(margin, height - box_h - margin + 1, stride)
    if len(xs) == 0 or len(ys) == 0:
        return max(0, (width - box_w) // 2), max(0, (height - box_h) // 2)

    def boxes(table):
        return (table[np.ix_(ys + box_h, xs + box_w)] - table[np.ix_(ys, xs + box_w)]
                - table[np.ix_(ys + box_h, xs)] + table[np.ix_(ys, xs)])

    busy = boxes(taken)
    cost = boxes(energy) / float(box_w * box_h)
    free = busy < 0.5
    if free.any():
        cost = np.where(free, cost, np.inf)
        pool = max(1, int(free.sum() * 0.08))
    else:  # no free place left: overlap as little as possible
        cost = cost + busy
        pool = 1
    pick = int(np.argsort(cost, axis=None)[rng.randrange(pool)])
    return int(xs[pick % len(xs)]), int(ys[pick // len(xs)])


def _letter_sfx(image, rgb, effects, occupied, style):
    height, width = rgb.shape[:2]
    rng = random.Random(style.sfx_seed)
    lum = luminance(rgb.astype(np.float32))
    energy = np.zeros((height, width), dtype=np.float32)
    energy[:-1] += np.abs(np.diff(lum, axis=0))
    energy[:, :-1] += np.abs(np.diff(lum, axis=1))
    energy = _integral(energy)
    fill = parse_color(style.sfx_color, (255, 255, 255))
    fill_light = (fill[0] * 0.299 + fill[1] * 0.587 + fill[2] * 0.114) > 128
    stroke = (0, 0, 0) if fill_light else (255, 255, 255)
    for index, effect in enumerate(effects):
        look = copy.copy(style)
        look.font = style.sfx_font or style.font
        look.rotation = rng.uniform(-style.sfx_tilt, style.sfx_tilt)
        look.arc = rng.uniform(-0.2, 0.2)
        look.jitter = max(style.jitter, 0.45)
        look.opacity = style.sfx_opacity
        look.seed = style.sfx_seed + index
        size = max(10, int(style.sfx_size / 100.0 * height * rng.uniform(0.85, 1.15)))
        paragraphs = parse_text(effect, style.uppercase)
        while True:
            lines = layout(paragraphs, get_fonts(look, size), width * 0.7)
            block_w, block_h = block_size(lines, size, look)
            if (block_w <= width * 0.72 and block_h <= height * 0.4) or size <= 10:
                break
            size = max(10, int(size * 0.9))
        layer = render_block(lines, size, look, fill, stroke, int(round(size * 0.14)), 0.0)
        bounds = layer.getbbox()
        if bounds is None:
            continue
        layer = layer.crop(bounds)
        x, y = _calm_spot(energy, _integral(occupied), layer.width, layer.height, width, height, rng)
        image = paste_centered(image, layer, x + layer.width / 2.0, y + layer.height / 2.0)
        occupied[max(0, y):y + layer.height, max(0, x):x + layer.width] = True
    return image
