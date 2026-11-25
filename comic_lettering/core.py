"""Entry point: put the user's text into detected bubbles, or straight onto the art."""
import math
import re
from typing import Dict, Tuple

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

from .detect import detect_bubbles, edge_energy, erase_letters
from .render import (Style, block_size, get_fonts, layout, line_heights, parse_color,
                     parse_text, paste_centered, render_block)

PLACEMENTS = ["auto", "top", "bottom", "center"]
SAMPLE_TEXT = u"Hello! \u041f\u0440\u0438\u0432\u0435\u0442! 123"


def letter(image, text="", caption="", spill=True, placement="auto", style=None, erase=True,
           white_threshold=120, rtl=False, numbers=False):
    # type: (Image.Image, str, str, bool, str, Style, bool, int, bool, bool) -> Tuple[Image.Image, Dict]
    """Letter an image.

    text: one line per bubble, in reading order (top to bottom, left to right). An
    empty line leaves its bubble alone.
    caption: free text drawn straight onto the art, outside the bubbles.
    spill: a line goes into a bubble only if it fits at a readable size
    (style.bubble_min_size); a bubble too small for it is passed over, and lines left
    without a bubble are added to the caption. Off: always write into the bubbles,
    however small, and drop the lines left over.
    numbers: draw each bubble's number instead of any text, to see the order.
    """
    style = style or Style()
    info = {"bubbles_found": 0, "bubbles_filled": 0, "free_text": False, "font_sizes": []}
    lines = [line.strip() for line in (text or "").replace("\r", "").split("\n")]
    while lines and not lines[-1]:
        lines.pop()
    caption = (caption or "").replace("\r", "").strip()
    if not lines and not caption and not numbers:
        return image, info
    rgb = np.array(image.convert("RGB"))
    height = rgb.shape[0]
    bubbles = detect_bubbles(rgb, white_threshold, rtl=rtl) if (lines or numbers) else []
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
    if free:
        out, size = _letter_free(out, rgb, "\n".join(free), placement, style)
        info["free_text"] = True
        info["font_sizes"].append(size)
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
    while True:
        fonts = get_fonts(style, size)
        for fraction in (0.95, 0.82, 0.7, 0.58, 0.46):
            lines = layout(paragraphs, fonts, body_w * fraction)
            if _fits(lines, size, style, inner, cy, cx):
                return lines, size, bubble.x0 + cx, bubble.y0 + cy
        if size <= smallest:
            if strict:
                return None
            return layout(paragraphs, fonts, body_w * 0.82), size, bubble.x0 + cx, bubble.y0 + cy
        size = max(smallest, min(size - 1, int(size * 0.93)))


def _letter_free(image, rgb, text, placement, style):
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
        top = edge_energy(rgb, edge, min(height, edge + block_h))
        bottom = edge_energy(rgb, max(0, height - edge - block_h), height - edge)
        placement = "top" if top < bottom else "bottom"
    cy = {"top": top_cy, "bottom": bottom_cy}.get(placement, height / 2.0)
    fill = parse_color(style.text_color, (255, 255, 255))
    fill_light = (fill[0] * 0.299 + fill[1] * 0.587 + fill[2] * 0.114) > 128
    stroke = parse_color(style.stroke_color, (0, 0, 0) if fill_light else (255, 255, 255))
    stroke_px = int(round(size * max(0.0, style.stroke_width)))
    layer = render_block(lines, size, style, fill, stroke, stroke_px, style.shadow)
    return paste_centered(image, layer, width / 2.0, cy), size
