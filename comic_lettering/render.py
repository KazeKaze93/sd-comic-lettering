"""Text layout and stylized rendering to an RGBA layer."""
import math
import random
from typing import List, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter
from scipy import ndimage as ndi

from functools import lru_cache

from .fonts import load_font

EMPHASIS_SCALE = 1.3

# Characters drawn as shapes, because comic fonts do not have them.
SYMBOLS = {
    u"♥": "heart", u"❤": "heart", u"♡": "heart",
    u"★": "star", u"☆": "star",
    u"✦": "spark", u"✨": "spark",
    u"♪": "note", u"♫": "note",
    u"\U0001F4A2": "anger",
    u"\U0001F4A6": "drop", u"\U0001F4A7": "drop",
}
SYMBOL_WIDTH = 0.95  # of the font size

# What can be scattered around a caption or a sound effect.
EXTRAS = {"none": None, "hearts": "heart", "sparkles": "spark", "stars": "star",
          "notes": "note", "sweat": "drop", "anger": "anger", "motion lines": "motion"}

# Mood presets: how unruly the letters and the lines are. "custom" uses the sliders.
MOODS = {
    "calm": dict(jitter=0.08, size_jitter=0.0, line_tilt=0.0, line_shift=0.0, line_spacing=1.08, rough=0.0),
    "playful": dict(jitter=0.35, size_jitter=0.2, line_tilt=3.0, line_shift=0.15, line_spacing=1.12, rough=0.0),
    "shout": dict(jitter=0.5, size_jitter=0.45, line_tilt=5.0, line_shift=0.25, line_spacing=1.05, rough=0.15),
    "shaky": dict(jitter=2.2, size_jitter=0.4, line_tilt=3.0, line_shift=0.15, line_spacing=1.1, rough=0.5),
    "rough": dict(jitter=0.3, size_jitter=0.1, line_tilt=1.0, line_shift=0.05, line_spacing=1.05, rough=1.3),
    "custom": None,
}

# Color presets. fill2 makes a top-to-bottom gradient, outer is a second outline,
# ink is the color used for plain text inside a light bubble.
PALETTES = {
    "auto": None,
    "black on white": dict(fill=(24, 24, 24), stroke=(255, 255, 255), ink=(24, 24, 24)),
    "pink": dict(fill=(255, 143, 199), stroke=(255, 255, 255), outer=(60, 16, 40), ink=(214, 36, 127)),
    "neon green": dict(fill=(140, 255, 90), stroke=(6, 32, 10), glow=(57, 255, 20), ink=(12, 122, 18)),
    "gold": dict(fill=(255, 224, 110), fill2=(255, 150, 40), stroke=(58, 33, 0), ink=(150, 90, 0)),
    "candy": dict(fill=(255, 122, 217), fill2=(164, 139, 255), stroke=(27, 11, 46), ink=(150, 60, 190)),
    "blood": dict(fill=(235, 40, 45), stroke=(20, 0, 0), ink=(190, 20, 25)),
    "ice": dict(fill=(200, 244, 255), fill2=(90, 170, 255), stroke=(6, 32, 58), ink=(30, 100, 190)),
    "from the art": "accent",
    "custom": "custom",
}

BUBBLE_SHAPES = ["none", "oval", "box", "cloud", "burst"]
BUBBLE_THEMES = ["light", "dark"]
TAILS = {"none": None, "down-left": (-0.6, 1.0), "down": (0.0, 1.0), "down-right": (0.6, 1.0),
         "left": (-1.0, 0.25), "right": (1.0, 0.25), "up-left": (-0.6, -1.0), "up": (0.0, -1.0),
         "up-right": (0.6, -1.0)}


class Style(object):
    """Lettering options shared by both hosts. Sizes are relative, so they scale with the image."""

    def __init__(self, font="Comic Relief Bold", uppercase=True, text_color="auto",
                 stroke_color="auto", stroke_width=0.12, shadow=0.5, line_spacing=1.08,
                 rotation=0.0, jitter=0.3, arc=0.0, soften=0.4, grain=0.0, opacity=1.0,
                 free_size=5.5, bubble_size=9.0, bubble_min_size=1.5, margin=0.08, seed=0,
                 sfx_font="Bangers", sfx_size=7.0, sfx_color="auto", sfx_tilt=15.0,
                 sfx_opacity=0.95, sfx_seed=0, caption_font="", bubble_colors="auto",
                 caption_colors="auto", sfx_colors="auto", bubble_mood="calm",
                 caption_mood="calm", sfx_mood="shout", caption_extras="none",
                 sfx_extras="none", caption_bubble="none", caption_bubble_theme="light",
                 caption_tail="none", size_jitter=0.0, line_tilt=0.0, line_shift=0.0,
                 rough=0.0):
        self.font = font
        self.uppercase = uppercase
        self.text_color = text_color      # "auto" or "#RRGGBB"; used by the "custom" colors
        self.stroke_color = stroke_color  # "auto" or "#RRGGBB"; caption, "custom" colors
        self.stroke_width = stroke_width  # fraction of the font size; caption only
        self.shadow = shadow              # 0..1 strength; caption only
        self.line_spacing = line_spacing
        self.rotation = rotation          # degrees, whole block
        self.jitter = jitter              # 0..1 per-letter wobble (baseline and angle)
        self.arc = arc                    # -1..1 bend of the block
        self.soften = soften              # blur radius in px, blends letters with the art
        self.grain = grain                # 0..1 uneven ink
        self.opacity = opacity
        self.free_size = free_size        # caption: font size, % of image height
        self.bubble_size = bubble_size    # bubble text: max font size, % of image height
        self.bubble_min_size = bubble_min_size  # smallest readable size, % of height
        self.margin = margin              # bubble: gap to the edge, fraction of bubble size
        self.seed = seed
        self.sfx_font = sfx_font          # sound effects: their own font
        self.sfx_size = sfx_size          # font size, % of image height
        self.sfx_color = sfx_color        # "auto" or "#RRGGBB"; used by the "custom" colors
        self.sfx_tilt = sfx_tilt          # each effect is tilted by up to this many degrees
        self.sfx_opacity = sfx_opacity
        self.sfx_seed = sfx_seed          # changes where the effects land and how they tilt
        self.caption_font = caption_font  # "" = the bubble font
        self.bubble_colors = bubble_colors    # a PALETTES name, for each kind of text
        self.caption_colors = caption_colors
        self.sfx_colors = sfx_colors
        self.bubble_mood = bubble_mood        # a MOODS name, for each kind of text
        self.caption_mood = caption_mood
        self.sfx_mood = sfx_mood
        self.caption_extras = caption_extras  # an EXTRAS name
        self.sfx_extras = sfx_extras
        self.caption_bubble = caption_bubble  # draw a bubble behind the caption: BUBBLE_SHAPES
        self.caption_bubble_theme = caption_bubble_theme
        self.caption_tail = caption_tail      # a TAILS name
        self.size_jitter = size_jitter    # 0..1 letters of different sizes ("custom" mood)
        self.line_tilt = line_tilt        # each line tilted by up to this many degrees
        self.line_shift = line_shift      # each line pushed sideways, fraction of the font size
        self.rough = rough                # 0..1 ragged, angular letter edges


class Paint(object):
    """Colors of one piece of lettering."""

    def __init__(self, fill, stroke=None, stroke_px=0, outer=None, outer_px=0, fill2=None,
                 glow=None, shadow=0.0, bold_px=0):
        self.bold_px = bold_px    # thickens the fill itself, for thin fonts
        self.fill = fill
        self.fill2 = fill2        # bottom color of a vertical gradient
        self.stroke = stroke
        self.stroke_px = stroke_px if stroke is not None else 0
        self.outer = outer        # second outline, outside the first
        self.outer_px = outer_px if outer is not None else 0
        self.glow = glow
        self.shadow = shadow


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
    text = text.replace(u"️", "").replace("<3", u"♥")
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


@lru_cache(maxsize=128)
def stem_ratio(font_name):
    """Stroke thickness of a font relative to its size: about 0.05 thin, 0.15 bold."""
    font = load_font(font_name, 200)
    image = Image.new("L", (400, 400), 0)
    ImageDraw.Draw(image).text((100, 300), "I", font=font, fill=255, anchor="ls")
    rows = (np.asarray(image) > 128).sum(axis=1)
    rows = rows[rows > 0]
    if len(rows) < 8:
        return 0.12
    return float(np.median(rows[len(rows) // 4: 3 * len(rows) // 4])) / 200.0


def pieces(word):
    """Split a word into runs of plain text and single symbols: [(kind or None, text)]."""
    result = []
    run = ""
    for ch in word:
        if ch in SYMBOLS:
            if run:
                result.append((None, run))
                run = ""
            result.append((SYMBOLS[ch], ch))
        else:
            run += ch
    if run:
        result.append((None, run))
    return result


def text_width(font, word):
    """Width of a word, counting drawn symbols at their own width."""
    return sum(font.size * SYMBOL_WIDTH if kind else font.getlength(text)
               for kind, text in pieces(word))


def layout(paragraphs, fonts, max_width):
    """Greedy word wrap. Returns [(words, width)], words = [(text, emphasized, width, glued)]."""
    base, big = fonts
    space = base.getlength(" ")
    lines = []
    for para in paragraphs:
        current = []
        width = 0.0
        for word, emph, glue in para:
            word_w = text_width(big if emph else base, word)
            gap = 0.0 if glue else space
            if current and width + gap + word_w > max_width:
                lines.append((current, width))
                current = []
                width = 0.0
            width = word_w if not current else width + gap + word_w
            current.append((word, emph, word_w, glue))
        lines.append((current, width))
    return lines


def diamond_profile(count):
    """Relative line widths of a text block that follows an oval: short, long, short."""
    return [math.sqrt(max(0.0, 1.0 - ((2 * i + 1 - count) / float(count)) ** 2))
            for i in range(count)]


def layout_shaped(paragraphs, fonts, count):
    """Break a single paragraph into `count` lines whose widths follow an oval.

    Greedy wrapping fills the first lines and leaves a short last one. This picks the
    breaks that bring the line widths closest to the diamond profile instead. Returns
    lines in the same form as layout(), or None when it does not apply.
    """
    if len(paragraphs) != 1:
        return None
    base, big = fonts
    space = base.getlength(" ")
    tokens = [(word, emph, text_width(big if emph else base, word), glue)
              for word, emph, glue in paragraphs[0]]
    total_tokens = len(tokens)
    if count < 2 or count > total_tokens:
        return None
    gaps = [0.0 if glue else space for _, _, _, glue in tokens]
    reach = [0.0]
    for index, token in enumerate(tokens):
        reach.append(reach[-1] + token[2] + (gaps[index] if index else 0.0))

    def width(start, stop):
        return reach[stop] - reach[start] - (gaps[start] if start else 0.0)

    profile = diamond_profile(count)
    targets = [width(0, total_tokens) * p / sum(profile) for p in profile]
    infinity = float("inf")
    # best[line][stop]: least squared error with tokens[:stop] on the first `line` lines.
    best = [[infinity] * (total_tokens + 1) for _ in range(count + 1)]
    cut = [[0] * (total_tokens + 1) for _ in range(count + 1)]
    best[0][0] = 0.0
    for line in range(1, count + 1):
        for stop in range(line, total_tokens - (count - line) + 1):
            for start in range(line - 1, stop):
                if best[line - 1][start] == infinity:
                    continue
                cost = best[line - 1][start] + (width(start, stop) - targets[line - 1]) ** 2
                if cost < best[line][stop]:
                    best[line][stop] = cost
                    cut[line][stop] = start
    lines = []
    stop = total_tokens
    for line in range(count, 0, -1):
        start = cut[line][stop]
        lines.append((tokens[start:stop], width(start, stop)))
        stop = start
    lines.reverse()
    return lines


def shape_score(lines):
    """How far a layout is from the diamond shape; lower is better. One line scores 0."""
    widths = [w for _, w in lines]
    count = len(widths)
    if count <= 1:
        return 0.0
    widest = max(widths) or 1.0
    profile = diamond_profile(count)
    top = max(profile)
    score = sum((w / widest - p / top) ** 2 for w, p in zip(widths, profile)) / count
    if widths[-1] < 0.4 * widest:
        score += 0.5  # a lone short word on the last line
    if widths[0] < 0.3 * widest:
        score += 0.2
    return score + 0.02 * count


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


# ---------------------------------------------------------------- symbols

def _heart():
    points = []
    for step in range(60):
        t = 2 * math.pi * step / 60.0
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        points.append((0.5 + x / 34.0, 0.47 - y / 34.0))
    return [points]


def _star(spikes, inner):
    points = []
    for step in range(spikes * 2):
        radius = 0.5 if step % 2 == 0 else inner
        angle = math.pi * step / spikes - math.pi / 2
        points.append((0.5 + radius * math.cos(angle), 0.5 + radius * math.sin(angle)))
    return [points]


def _ellipse(cx, cy, rx, ry, steps=28):
    return [(cx + rx * math.cos(2 * math.pi * s / steps), cy + ry * math.sin(2 * math.pi * s / steps))
            for s in range(steps)]


def _drop():
    points = [(0.5, 0.02)]
    for step in range(25):
        angle = math.radians(-35 + 250 * step / 24.0)
        points.append((0.5 + 0.3 * math.cos(angle), 0.66 + 0.3 * math.sin(angle)))
    return [points]


def _note():
    return [_ellipse(0.36, 0.8, 0.22, 0.16), [(0.5, 0.08), (0.6, 0.08), (0.6, 0.82), (0.5, 0.82)],
            [(0.6, 0.08), (0.9, 0.3), (0.9, 0.46), (0.6, 0.26)]]


def _anger():
    polygons = []
    corner = [(0.57, 0.43), (0.57, 0.04), (0.75, 0.04), (0.75, 0.25), (0.96, 0.25), (0.96, 0.43)]
    for quarter in range(4):
        angle = math.pi / 2 * quarter
        polygons.append([(0.5 + (x - 0.5) * math.cos(angle) - (y - 0.5) * math.sin(angle),
                          0.5 + (x - 0.5) * math.sin(angle) + (y - 0.5) * math.cos(angle))
                         for x, y in corner])
    return polygons


SHAPES = {"heart": _heart(), "star": _star(5, 0.2), "spark": _star(4, 0.13), "drop": _drop(),
          "note": _note(), "anger": _anger()}


def symbol_tile(kind, px, grow=0):
    """A symbol as an 'L' mask of side px + 2 * grow, optionally grown for an outline."""
    px = max(4, int(px))
    scale = 4
    big = Image.new("L", (px * scale, px * scale), 0)
    draw = ImageDraw.Draw(big)
    for polygon in SHAPES[kind]:
        draw.polygon([(x * px * scale, y * px * scale) for x, y in polygon], fill=255)
    tile = Image.new("L", (px + 2 * grow, px + 2 * grow), 0)
    tile.paste(big.resize((px, px), Image.LANCZOS), (grow, grow))
    if grow > 0:
        tile = tile.filter(ImageFilter.MaxFilter(2 * min(grow, 15) + 1))
    return tile


# ---------------------------------------------------------------- rendering

def _solid(color, mask):
    layer = Image.new("RGBA", mask.size, tuple(color) + (0,))
    layer.putalpha(mask)
    return layer


def _gradient(top, bottom, mask):
    """A vertical gradient across the inked rows of the mask."""
    bounds = mask.getbbox()
    if bounds is None:
        return _solid(top, mask)
    rows = np.clip((np.arange(mask.height) - bounds[1]) / float(max(1, bounds[3] - bounds[1] - 1)), 0, 1)
    colors = np.array(top, dtype=np.float32)[None, :] * (1 - rows[:, None]) \
        + np.array(bottom, dtype=np.float32)[None, :] * rows[:, None]
    array = np.repeat(colors[:, None, :], mask.width, axis=1).astype(np.uint8)
    layer = Image.fromarray(array, "RGB").convert("RGBA")
    layer.putalpha(mask)
    return layer


def _roughen(masks, amount, size, seed, stem=0.15):
    """Push the letter edges around with noise: ragged where it is smooth, angular where it is blocky.

    Both the grain of the noise and its reach follow the stroke thickness of the font
    (stem, relative to the size): a thin font gets a fine, shallow tremor that shows
    on its hairlines without shredding them; a bold one gets big bites.
    """
    if amount <= 0:
        return masks
    width, height = masks[0].size
    state = np.random.RandomState(seed % (2 ** 32))
    stem = max(0.04, min(0.16, stem))
    cell = max(2, int(size * stem * 1.1))
    reach = size * min(0.07, 0.75 * stem)
    grid = (height // cell + 2, width // cell + 2)

    def field():
        coarse = state.uniform(-1, 1, grid)
        smooth = ndi.zoom(coarse, (height / float(grid[0]), width / float(grid[1])), order=1)
        blocky = np.kron(coarse, np.ones((cell, cell)))
        canvas = np.zeros((height, width), dtype=np.float32)
        sh, sw = min(height, smooth.shape[0]), min(width, smooth.shape[1])
        canvas[:sh, :sw] = 0.55 * smooth[:sh, :sw]
        canvas += 0.45 * blocky[:height, :width]
        return canvas * amount * reach

    rows, cols = np.mgrid[0:height, 0:width].astype(np.float32)
    coords = [rows + field(), cols + field()]
    return [Image.fromarray(ndi.map_coordinates(np.asarray(mask, dtype=np.float32), coords, order=1,
                                                mode="constant").clip(0, 255).astype(np.uint8), "L")
            for mask in masks]


def _draw_line(masks, grows, words, x, baseline, center_x, half, size, style, fonts, rng):
    """Draw one line of words into the masks (one mask per outline width in `grows`)."""
    base, big = fonts
    space = base.getlength(" ")
    arc_amp = style.arc * size * 0.9
    per_char = style.jitter > 0 or style.arc != 0 or style.size_jitter > 0
    for position, (word, emph, word_w, glue) in enumerate(words):
        font = big if emph else base
        if position and not glue:
            x += space
        cursor = x
        for kind, run in pieces(word):
            units = [run] if (kind or not per_char) else list(run)
            for unit in units:
                unit_font = font
                if per_char and style.size_jitter > 0:
                    unit_font = load_font(style.font, max(6, int(round(
                        font.size * (1 + rng.uniform(-1, 1) * 0.28 * style.size_jitter)))))
                unit_w = unit_font.size * SYMBOL_WIDTH if kind else unit_font.getlength(unit)
                if not per_char and not kind:
                    for mask, grow in zip(masks, grows):
                        ImageDraw.Draw(mask).text((cursor, baseline), unit, font=unit_font, fill=255,
                                                  anchor="ls", stroke_width=grow)
                    cursor += unit_w
                    continue
                t = ((cursor + unit_w / 2.0) - center_x) / half
                dy = arc_amp * t * t + rng.uniform(-1, 1) * style.jitter * 0.07 * size
                angle = -math.degrees(math.atan(2 * arc_amp * t / half))
                angle += rng.uniform(-1, 1) * style.jitter * 7.0
                for mask, grow in zip(masks, grows):
                    if kind:
                        px = int(unit_font.size * 0.82)
                        tile = symbol_tile(kind, px, grow)
                        origin = (int(round(cursor + (unit_w - px) / 2.0)) - grow,
                                  int(round(baseline + dy)) - px - grow)
                    else:
                        m = int(unit_font.size * 0.6) + grow
                        tile = Image.new("L", (int(math.ceil(unit_w)) + 2 * m,
                                               int(unit_font.size * 1.4) + 2 * m), 0)
                        ImageDraw.Draw(tile).text((m, m + unit_font.size), unit, font=unit_font,
                                                  fill=255, anchor="ls", stroke_width=grow)
                        origin = (int(round(cursor)) - m, int(round(baseline + dy)) - (m + unit_font.size))
                    if angle:
                        tile = tile.rotate(angle, resample=Image.BICUBIC)
                    mask.paste(255, origin, tile)
                cursor += unit_w
        x += word_w


def render_block(lines, size, style, paint):
    # type: (List, int, Style, Paint) -> Image.Image
    """Render laid-out lines to an RGBA layer. The text block is centered in the layer."""
    if not isinstance(paint, Paint):
        paint = Paint(paint)
    fonts = get_fonts(style, size)
    rng = random.Random(style.seed)
    heights = line_heights(lines, size, style)
    block_w, block_h = block_size(lines, size, style)
    grows = [paint.bold_px]
    if paint.stroke_px > 0:
        grows.append(paint.bold_px + paint.stroke_px)
        if paint.outer_px > 0:
            grows.append(paint.bold_px + paint.stroke_px + paint.outer_px)
    reach = grows[-1]
    sway = abs(style.line_shift) * size + math.sin(math.radians(min(45.0, abs(style.line_tilt)))) * block_w / 2.0
    pad = int(size * 1.0 + reach + abs(style.arc * size * 0.9) + sway + size * 0.3 * style.size_jitter)
    width = int(math.ceil(block_w)) + 2 * pad
    height = block_h + 2 * pad
    masks = [Image.new("L", (width, height), 0) for _ in grows]
    half = (block_w / 2.0) or 1.0
    top = pad
    for index, (words, line_w) in enumerate(lines):
        ink = heights[index] / style.line_spacing
        tilt = rng.uniform(-1, 1) * style.line_tilt if style.line_tilt else 0.0
        shift = rng.uniform(-1, 1) * style.line_shift * size if style.line_shift else 0.0
        if not tilt:
            x = pad + (block_w - line_w) / 2.0 + shift
            baseline = top + heights[index] * 0.5 + ink * 0.35
            _draw_line(masks, grows, words, x, baseline, pad + block_w / 2.0 + shift, half,
                       size, style, fonts, rng)
        else:
            # A tilted line is drawn on its own strip, turned, and laid onto the block.
            margin = int(size * 1.0 + reach)
            strip_size = (int(math.ceil(line_w)) + 2 * margin, heights[index] + 2 * margin)
            strips = [Image.new("L", strip_size, 0) for _ in grows]
            _draw_line(strips, grows, words, margin, margin + heights[index] * 0.5 + ink * 0.35,
                       margin + line_w / 2.0, half, size, style, fonts, rng)
            for mask, strip in zip(masks, strips):
                turned = strip.rotate(tilt, resample=Image.BICUBIC, expand=True)
                mask.paste(255, (int(round(pad + block_w / 2.0 + shift - turned.width / 2.0)),
                                 int(round(top + heights[index] / 2.0 - turned.height / 2.0))), turned)
        top += heights[index]
    masks = _roughen(masks, style.rough, size, style.seed, stem_ratio(style.font))
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ink_mask = masks[-1]
    if paint.glow is not None:
        halo = ink_mask.filter(ImageFilter.MaxFilter(3)).filter(ImageFilter.GaussianBlur(max(2.0, size * 0.16)))
        halo = halo.point(lambda v: min(255, int(v * 1.6)))
        layer = Image.alpha_composite(layer, _solid(paint.glow, halo))
    if paint.shadow > 0:
        offset = max(1, int(round(size * 0.07)))
        shade = ImageChops.offset(ink_mask, offset, offset).filter(ImageFilter.GaussianBlur(offset * 0.6))
        shade = shade.point(lambda v: int(v * min(1.0, paint.shadow) * 0.75))
        layer = Image.alpha_composite(layer, _solid((0, 0, 0), shade))
    if len(masks) > 2:
        layer = Image.alpha_composite(layer, _solid(paint.outer, masks[2]))
    if len(masks) > 1:
        layer = Image.alpha_composite(layer, _solid(paint.stroke, masks[1]))
    if paint.fill2 is not None:
        layer = Image.alpha_composite(layer, _gradient(paint.fill, paint.fill2, masks[0]))
    else:
        layer = Image.alpha_composite(layer, _solid(paint.fill, masks[0]))
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


def decorate(layer, kind, size, paint, seed):
    """Scatter marks (or action lines) around a rendered block.

    Returns a larger layer with the block still in its center.
    """
    if not kind:
        return layer
    rng = random.Random(seed * 7919 + 13)
    margin = int(size * 2.1)
    canvas = Image.new("RGBA", (layer.width + 2 * margin, layer.height + 2 * margin), (0, 0, 0, 0))
    bounds = layer.getbbox() or (0, 0, layer.width, layer.height)
    cx = margin + (bounds[0] + bounds[2]) / 2.0
    cy = margin + (bounds[1] + bounds[3]) / 2.0
    stroke = paint.stroke if paint.stroke is not None else (0, 0, 0)
    if kind == "motion":
        # Action lines: tapered strokes bursting out from the block, all around it.
        rx = (bounds[2] - bounds[0]) / 2.0 + size * 0.25
        ry = (bounds[3] - bounds[1]) / 2.0 + size * 0.2
        draw = ImageDraw.Draw(canvas)
        count = max(12, int((rx + ry) / (size * 0.42)))
        for index in range(count):
            angle = 2 * math.pi * index / count + rng.uniform(-0.1, 0.1)
            dx, dy = math.cos(angle), math.sin(angle)
            start = 1.0 + rng.uniform(0.0, 0.1)
            x0, y0 = cx + rx * start * dx, cy + ry * start * dy
            length = size * rng.uniform(0.7, 1.5)
            half = size * rng.uniform(0.08, 0.14)
            wedge = [(x0 - dy * half, y0 + dx * half), (x0 + dy * half, y0 - dx * half),
                     (x0 + dx * length, y0 + dy * length)]
            draw.polygon(wedge, fill=tuple(stroke) + (255,))
            inset = max(1.0, size * 0.03)
            inner = [(x0 + dx * inset - dy * (half - inset), y0 + dy * inset + dx * (half - inset)),
                     (x0 + dx * inset + dy * (half - inset), y0 + dy * inset - dx * (half - inset)),
                     (x0 + dx * (length - 3 * inset), y0 + dy * (length - 3 * inset))]
            draw.polygon(inner, fill=tuple(paint.fill) + (255,))
    else:
        # Marks sit on a frame around the block, so none of them covers the letters.
        rx = (bounds[2] - bounds[0]) / 2.0 + size * 0.7
        ry = (bounds[3] - bounds[1]) / 2.0 + size * 0.7
        count = rng.randint(5, 7)
        start = rng.uniform(0, 2 * math.pi)
        for index in range(count):
            angle = start + 2 * math.pi * index / count + rng.uniform(-0.25, 0.25)
            px = int(size * rng.uniform(0.5, 0.85))
            grow = max(2, int(px * 0.12))
            tile = Image.alpha_composite(_solid(stroke, symbol_tile(kind, px, grow)),
                                         _solid(paint.fill, _pad_tile(symbol_tile(kind, px, 0), grow)))
            tile = tile.rotate(rng.uniform(-25, 25), resample=Image.BICUBIC, expand=True)
            reach = min(rx / max(1e-6, abs(math.cos(angle))), ry / max(1e-6, abs(math.sin(angle))))
            x = int(cx + reach * math.cos(angle) - tile.width / 2.0)
            y = int(cy + reach * math.sin(angle) - tile.height / 2.0)
            x = max(0, min(x, canvas.width - tile.width))
            y = max(0, min(y, canvas.height - tile.height))
            canvas.alpha_composite(tile, (x, y))
    canvas.alpha_composite(layer, (margin, margin))
    return canvas


def _pad_tile(tile, grow):
    padded = Image.new("L", (tile.width + 2 * grow, tile.height + 2 * grow), 0)
    padded.paste(tile, (grow, grow))
    return padded


def bubble_shape(kind, text_w, text_h, size, tail, seed):
    """A drawn speech bubble around a text block.

    Returns (fill mask, outline mask, (cx, cy)): the masks share a size and (cx, cy) is
    where the center of the text goes.
    """
    rng = random.Random(seed * 31 + 5)
    if kind == "box":
        a = text_w / 2.0 + size * 0.7
        b = text_h / 2.0 + size * 0.55
    else:
        a = text_w / 2.0 * 1.42 + size * 0.45
        b = text_h / 2.0 * 1.42 + size * 0.4
    tail_len = size * 0.9 + b * 0.3
    thick = max(2, int(round(size * 0.09)))
    margin = int(tail_len + max(a, b) * 0.32 + thick + 4)
    scale = 3
    width = int(2 * a) + 2 * margin
    height = int(2 * b) + 2 * margin
    cx, cy = width / 2.0, height / 2.0
    big = Image.new("L", (width * scale, height * scale), 0)
    draw = ImageDraw.Draw(big)

    def up(points):
        return [(x * scale, y * scale) for x, y in points]

    if kind == "box":
        draw.rounded_rectangle(up([(cx - a, cy - b), (cx + a, cy + b)]), radius=size * 0.5 * scale, fill=255)
    elif kind == "cloud":
        radius = 0.36 * min(a, b)
        draw.ellipse(up([(cx - a + radius * 0.6, cy - b + radius * 0.6),
                         (cx + a - radius * 0.6, cy + b - radius * 0.6)]), fill=255)
        puffs = max(8, int(2 * math.pi * math.sqrt((a * a + b * b) / 2.0) / (radius * 1.15)))
        for index in range(puffs):
            angle = 2 * math.pi * index / puffs
            px = cx + (a - radius * 0.75) * math.cos(angle)
            py = cy + (b - radius * 0.75) * math.sin(angle)
            r = radius * rng.uniform(0.85, 1.1)
            draw.ellipse(up([(px - r, py - r), (px + r, py + r)]), fill=255)
    elif kind == "burst":
        spikes = 16
        points = []
        for index in range(spikes * 2):
            angle = math.pi * index / spikes
            reach = (1.3 + rng.uniform(-0.06, 0.1)) if index % 2 == 0 else 1.0
            points.append((cx + a * reach * math.cos(angle), cy + b * reach * math.sin(angle)))
        draw.polygon(up(points), fill=255)
    else:
        draw.ellipse(up([(cx - a, cy - b), (cx + a, cy + b)]), fill=255)
    direction = TAILS.get(tail)
    if direction is not None:
        length = math.hypot(*direction)
        dx, dy = direction[0] / length, direction[1] / length
        angle = math.atan2(dy * a, dx * b)  # where the ray leaves the ellipse
        edge = (cx + a * math.cos(angle), cy + b * math.sin(angle))
        root = (cx + a * 0.78 * math.cos(angle), cy + b * 0.78 * math.sin(angle))
        half = size * 0.42
        draw.polygon(up([(root[0] - dy * half, root[1] + dx * half),
                         (root[0] + dy * half, root[1] - dx * half),
                         (edge[0] + dx * tail_len, edge[1] + dy * tail_len)]), fill=255)
    fill_mask = big.resize((width, height), Image.LANCZOS)
    outline = fill_mask.filter(ImageFilter.MaxFilter(2 * min(thick, 15) + 1))
    return fill_mask, outline, (cx, cy)


def paste_centered(image, layer, cx, cy):
    """Alpha-composite an RGBA layer onto an RGB(A) image, centered at (cx, cy)."""
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay.paste(layer, (int(round(cx - layer.width / 2.0)), int(round(cy - layer.height / 2.0))))
    return Image.alpha_composite(image.convert("RGBA"), overlay)
