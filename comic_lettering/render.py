"""Text layout and stylized rendering to an RGBA layer."""
import math
import random
from typing import List, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter
from scipy import ndimage as ndi

from .fonts import load_font

EMPHASIS_SCALE = 1.3


class Style(object):
    """Lettering options shared by both hosts. Sizes are relative, so they scale with the image."""

    def __init__(self, font="Comic Sans MS Bold", uppercase=True, text_color="auto",
                 stroke_color="auto", stroke_width=0.12, shadow=0.5, line_spacing=1.08,
                 rotation=0.0, jitter=0.3, arc=0.0, soften=0.4, grain=0.0, opacity=1.0,
                 free_size=5.5, bubble_size=9.0, bubble_min_size=1.5, margin=0.08, seed=0):
        self.font = font
        self.uppercase = uppercase
        self.text_color = text_color      # "auto" or "#RRGGBB"
        self.stroke_color = stroke_color  # "auto" or "#RRGGBB"; free text only
        self.stroke_width = stroke_width  # fraction of the font size; free text only
        self.shadow = shadow              # 0..1 strength; free text only
        self.line_spacing = line_spacing
        self.rotation = rotation          # degrees, whole block
        self.jitter = jitter              # 0..1 per-letter wobble (baseline and angle)
        self.arc = arc                    # -1..1 bend of the block
        self.soften = soften              # blur radius in px, blends letters with the art
        self.grain = grain                # 0..1 uneven ink
        self.opacity = opacity
        self.free_size = free_size        # free text: font size, % of image height
        self.bubble_size = bubble_size    # bubble text: max font size, % of image height
        self.bubble_min_size = bubble_min_size  # mode auto: smallest readable size, % of height
        self.margin = margin              # bubble: gap to the edge, fraction of bubble size
        self.seed = seed


def parse_color(value, default):
    # type: (str, Tuple[int, int, int]) -> Tuple[int, int, int]
    text = (value or "").strip().lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    if len(text) == 6:
        try:
            return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))
        except ValueError:
            pass
    return default


def parse_text(text, uppercase):
    """Split into paragraphs of (word, emphasized, glued). *word* marks emphasis."""
    if uppercase:
        text = text.upper()
    paragraphs = [[]]
    word = ""
    word_emph = False
    emph = False
    glue = False  # the next piece continues a hyphenated word: no space before it
    for ch in text.replace("\r", ""):
        if ch == "*":
            emph = not emph
        elif ch == "\n" or ch.isspace():
            if word:
                paragraphs[-1].append((word, word_emph, glue))
                word = ""
            glue = False
            if ch == "\n":
                paragraphs.append([])
        else:
            if not word:
                word_emph = emph
            word += ch
            if ch == "-" and word.strip("-"):
                # "H-m-m" -> "H-", "m-", "m": a line may break after a hyphen.
                paragraphs[-1].append((word, word_emph, glue))
                word = ""
                glue = True
    if word:
        paragraphs[-1].append((word, word_emph, glue))
    return [p for p in paragraphs if p] or [[]]


def get_fonts(style, size):
    return load_font(style.font, size), load_font(style.font, int(round(size * EMPHASIS_SCALE)))


def layout(paragraphs, fonts, max_width):
    """Greedy word wrap. Returns [(words, width)], words = [(text, emphasized, width, glued)]."""
    base, big = fonts
    space = base.getlength(" ")
    lines = []
    for para in paragraphs:
        current = []
        width = 0.0
        for word, emph, glue in para:
            word_w = (big if emph else base).getlength(word)
            gap = 0.0 if glue else space
            if current and width + gap + word_w > max_width:
                lines.append((current, width))
                current = []
                width = 0.0
            width = word_w if not current else width + gap + word_w
            current.append((word, emph, word_w, glue))
        lines.append((current, width))
    return lines


def line_heights(lines, size, style):
    """Height of every line; a line with an emphasized word is taller."""
    heights = []
    for words, _ in lines:
        scale = EMPHASIS_SCALE if any(emph for _, emph, _, _ in words) else 1.0
        heights.append(int(math.ceil(size * scale * style.line_spacing)))
    return heights


def block_size(lines, size, style):
    width = max([w for _, w in lines] or [0.0])
    return width, sum(line_heights(lines, size, style))


def _solid(color, mask):
    layer = Image.new("RGBA", mask.size, tuple(color) + (0,))
    layer.putalpha(mask)
    return layer


def render_block(lines, size, style, fill, stroke=None, stroke_px=0, shadow=0.0):
    # type: (List, int, Style, Tuple[int, int, int], object, int, float) -> Image.Image
    """Render laid-out lines to an RGBA layer. The text block is centered in the layer."""
    base, big = get_fonts(style, size)
    rng = random.Random(style.seed)
    heights = line_heights(lines, size, style)
    block_w, block_h = block_size(lines, size, style)
    arc_amp = style.arc * size * 0.9
    pad = int(size * 0.9 + stroke_px + abs(arc_amp))
    width = int(math.ceil(block_w)) + 2 * pad
    height = block_h + 2 * pad
    fill_mask = Image.new("L", (width, height), 0)
    stroke_mask = Image.new("L", (width, height), 0) if stroke_px > 0 else None
    fill_draw = ImageDraw.Draw(fill_mask)
    stroke_draw = ImageDraw.Draw(stroke_mask) if stroke_mask is not None else None
    per_char = style.jitter > 0 or style.arc != 0
    half = (block_w / 2.0) or 1.0
    space = base.getlength(" ")
    top = pad
    for index, (words, line_w) in enumerate(lines):
        x = pad + (block_w - line_w) / 2.0
        ink = heights[index] / style.line_spacing
        baseline = top + heights[index] * 0.5 + ink * 0.35
        top += heights[index]
        for position, (word, emph, word_w, glue) in enumerate(words):
            font = big if emph else base
            if position and not glue:
                x += space
            if not per_char:
                fill_draw.text((x, baseline), word, font=font, fill=255, anchor="ls")
                if stroke_draw is not None:
                    stroke_draw.text((x, baseline), word, font=font, fill=255, anchor="ls",
                                     stroke_width=stroke_px)
            else:
                for i, ch in enumerate(word):
                    cx = x + font.getlength(word[:i])
                    cw = font.getlength(ch)
                    t = ((cx + cw / 2.0) - (pad + block_w / 2.0)) / half
                    dy = arc_amp * t * t + rng.uniform(-1, 1) * style.jitter * 0.07 * size
                    angle = -math.degrees(math.atan(2 * arc_amp * t / half))
                    angle += rng.uniform(-1, 1) * style.jitter * 7.0
                    m = int(font.size * 0.6) + stroke_px
                    tile_size = (int(math.ceil(cw)) + 2 * m, int(font.size * 1.4) + 2 * m)
                    origin = (int(round(cx)) - m, int(round(baseline + dy)) - (m + font.size))
                    for mask, sw in ((fill_mask, 0), (stroke_mask, stroke_px)):
                        if mask is None:
                            continue
                        tile = Image.new("L", tile_size, 0)
                        ImageDraw.Draw(tile).text((m, m + font.size), ch, font=font, fill=255,
                                                  anchor="ls", stroke_width=sw)
                        tile = tile.rotate(angle, resample=Image.BICUBIC)
                        mask.paste(255, origin, tile)
            x += word_w
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ink = ImageChops.lighter(fill_mask, stroke_mask) if stroke_mask is not None else fill_mask
    if shadow > 0:
        offset = max(1, int(round(size * 0.07)))
        shade = ImageChops.offset(ink, offset, offset).filter(ImageFilter.GaussianBlur(offset * 0.6))
        shade = shade.point(lambda v: int(v * min(1.0, shadow) * 0.75))
        layer = Image.alpha_composite(layer, _solid((0, 0, 0), shade))
    if stroke_mask is not None:
        layer = Image.alpha_composite(layer, _solid(stroke, stroke_mask))
    layer = Image.alpha_composite(layer, _solid(fill, fill_mask))
    if style.rotation:
        layer = layer.rotate(style.rotation, resample=Image.BICUBIC, expand=True)
    return _finish(layer, style)


def _finish(layer, style):
    """Soften, grain and opacity, done on premultiplied alpha to avoid dark fringes."""
    if style.soften <= 0 and style.grain <= 0 and style.opacity >= 1:
        return layer
    arr = np.asarray(layer).astype(np.float32) / 255.0
    alpha = arr[..., 3]
    rgb = arr[..., :3] * alpha[..., None]
    if style.soften > 0:
        alpha = ndi.gaussian_filter(alpha, style.soften)
        rgb = np.stack([ndi.gaussian_filter(rgb[..., c], style.soften) for c in range(3)], axis=-1)
    if style.grain > 0:
        noise = np.random.RandomState(style.seed % (2 ** 32)).rand(*alpha.shape).astype(np.float32)
        noise = ndi.gaussian_filter(noise, 0.8)
        noise = (noise - noise.min()) / max(1e-6, float(noise.max() - noise.min()))
        keep = 1.0 - min(1.0, style.grain) * noise
        alpha = alpha * keep
        rgb = rgb * keep[..., None]
    if style.opacity < 1:
        alpha = alpha * max(0.0, style.opacity)
        rgb = rgb * max(0.0, style.opacity)
    out = np.zeros_like(arr)
    safe = np.maximum(alpha, 1e-6)
    out[..., :3] = np.clip(rgb / safe[..., None], 0, 1)
    out[..., 3] = np.clip(alpha, 0, 1)
    return Image.fromarray((out * 255 + 0.5).astype(np.uint8), "RGBA")


def paste_centered(image, layer, cx, cy):
    """Alpha-composite an RGBA layer onto an RGB(A) image, centered at (cx, cy)."""
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay.paste(layer, (int(round(cx - layer.width / 2.0)), int(round(cy - layer.height / 2.0))))
    return Image.alpha_composite(image.convert("RGBA"), overlay)
