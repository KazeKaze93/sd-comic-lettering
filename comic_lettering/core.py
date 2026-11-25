"""Entry point: put the user's text into detected bubbles, or straight onto the art."""
import math
import re
from typing import Dict, Tuple

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

from .detect import detect_bubbles, edge_energy, erase_letters
from .render import (Style, block_size, get_fonts, layout, line_heights, parse_color,
                     parse_text, paste_centered, render_block)

MODES = ["auto", "bubble", "free"]
PLACEMENTS = ["auto", "top", "bottom", "center"]


def letter(image, text, mode="auto", placement="auto", style=None, erase=True,
           white_threshold=225, rtl=False):
    # type: (Image.Image, str, str, str, Style, bool, int, bool) -> Tuple[Image.Image, Dict]
    """Letter an image.

    Text blocks are separated by a blank line. Each block goes into one bubble in
    reading order. Blocks left without a bubble become free text (mode "auto") or are
    dropped (mode "bubble"). Mode "free" skips detection.
    """
    style = style or Style()
    info = {"bubbles_found": 0, "bubbles_filled": 0, "free_text": False, "font_sizes": []}
    blocks = [b.strip() for b in re.split(r"\n[ \t]*\n", (text or "").replace("\r", "")) if b.strip()]
    if not blocks:
        return image, info
    rgb = np.array(image.convert("RGB"))
    bubbles = [] if mode == "free" else detect_bubbles(rgb, white_threshold, rtl=rtl)
    info["bubbles_found"] = len(bubbles)
    used = bubbles[:len(blocks)]
    if erase:
        for bubble in used:
            erase_letters(rgb, bubble)
    out = Image.fromarray(rgb)
    for bubble, block in zip(used, blocks):
        out, size = _letter_bubble(out, bubble, block, style)
        info["font_sizes"].append(size)
    info["bubbles_filled"] = len(used)
    rest = blocks[len(used):]
    if rest and mode != "bubble":
        out, size = _letter_free(out, rgb, "\n".join(rest), placement, style)
        info["free_text"] = True
        info["font_sizes"].append(size)
    return out.convert("RGB"), info


def _fits(lines, size, style, inner, cy, cx):
    heights = line_heights(lines, size, style)
    top = cy - sum(heights) / 2.0
    for index, (words, width) in enumerate(lines):
        line_top = top
        top += heights[index]
        if not words:
            continue
        ink = int(heights[index] / style.line_spacing)
        y0 = int(line_top + (heights[index] - ink) / 2.0)
        y1 = y0 + ink
        x0 = int(cx - width / 2.0)
        x1 = int(math.ceil(cx + width / 2.0))
        if y0 < 0 or x0 < 0 or y1 > inner.shape[0] or x1 > inner.shape[1]:
            return False
        if inner[y0:y1, x0:x1].mean() < 0.97:
            return False
    return True


def _letter_bubble(image, bubble, text, style):
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
    smallest = max(8, int(0.012 * image.height))
    size = max(smallest, int(style.bubble_size / 100.0 * image.height))
    chosen = None
    while chosen is None:
        fonts = get_fonts(style, size)
        for fraction in (0.95, 0.82, 0.7, 0.58, 0.46):
            lines = layout(paragraphs, fonts, body_w * fraction)
            if _fits(lines, size, style, inner, cy, cx):
                chosen = lines
                break
        if chosen is None:
            if size <= smallest:
                chosen = layout(paragraphs, fonts, body_w * 0.82)  # does not fit: best effort
                break
            size = max(smallest, min(size - 1, int(size * 0.93)))
    light = (bubble.color[0] * 0.299 + bubble.color[1] * 0.587 + bubble.color[2] * 0.114) > 128
    fill = parse_color(style.text_color, (0, 0, 0) if light else (255, 255, 255))
    layer = render_block(chosen, size, style, fill)
    return paste_centered(image, layer, bubble.x0 + cx, bubble.y0 + cy), size


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
