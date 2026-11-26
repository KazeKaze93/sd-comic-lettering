# The core

`comic_lettering/` is a plain Python package. It needs `numpy`, `scipy` and `Pillow`, runs on Python 3.9 and newer, and imports nothing from any host.

- [Three functions](#three-functions)
- [Arguments](#arguments)
- [Style](#style)
- [The scene](#the-scene)
- [Pins: placing by hand](#pins-placing-by-hand)
- [Regions: areas drawn by hand](#regions-areas-drawn-by-hand)
- [How bubbles are found](#how-bubbles-are-found)
- [How text is fitted into a bubble](#how-text-is-fitted-into-a-bubble)
- [How free text finds its place](#how-free-text-finds-its-place)
- [Characters](#characters)
- [Fonts](#fonts)
- [Command line](#command-line)

## Three functions

```python
from PIL import Image
from comic_lettering import Style, arrange, draw, letter

image = Image.open("page.png")

# One call:
result, info = letter(image, "Hi!\nYo.", caption="Last day of summer.", sfx="SPLASH")

# The same in two steps:
scene = arrange(image, "Hi!\nYo.", caption="Last day of summer.", sfx="SPLASH")
result = draw(image, scene)
```

| Function | Returns | Does |
|---|---|---|
| `letter(image, ...)` | `(image, info)` | `arrange()` then `draw()` |
| `arrange(image, ...)` | `scene` (dict) | Decides what goes where. Draws nothing. |
| `draw(image, scene)` | `image` | Draws a scene onto the image it was made for. |

`image` is a `PIL.Image`. The result is a new RGB image; the input is not changed. When nothing was asked for, `scene["empty"]` is true and `draw()` hands the input back untouched.

Everything exported: `letter`, `arrange`, `draw`, `Style`, `Paint`, `font_names`, `list_fonts`, `font_sample`, and the lists `PLACEMENTS`, `PALETTES`, `MOODS`, `EXTRAS`, `BUBBLE_SHAPES`, `BUBBLE_THEMES`, `TAILS`.

## Arguments

`arrange(image, text="", caption="", spill=True, placement="auto", style=None, erase=True, white_threshold=120, rtl=False, numbers=False, sfx="", pins=None, regions=None)`

`letter()` takes the same, without `pins` and `regions`.

| Argument | Meaning |
|---|---|
| `text` | One line per bubble found in the art, in reading order. An empty line leaves its bubble alone. |
| `caption` | Free text, drawn on the art or in a bubble drawn for it (`style.caption_bubble`). |
| `sfx` | Sound effects, one per line. `"WORD x5"` stacks the word five times. |
| `spill` | `True`: a line that does not fit its bubble at a readable size is added to the caption. `False`: always write into the bubbles, however small, and drop lines left over. |
| `placement` | Where the caption goes: one of `PLACEMENTS` (`auto`, `top`, `bottom`, `center`, four corners). |
| `style` | A `Style`; the default one when `None`. |
| `erase` | Erase the letters the model drew inside a bubble before writing. |
| `white_threshold` | The darkest light fill that still counts as a bubble, 0..255. |
| `rtl` | Reading order right to left (manga). Not exposed in the editor. |
| `numbers` | Draw each bubble's number instead of any text. |
| `pins` | What was placed by hand. See [Pins](#pins-placing-by-hand). |
| `regions` | Areas drawn by hand. See [Regions](#regions-areas-drawn-by-hand). |

In any text, `*word*` makes a word bigger (by `EMPHASIS_SCALE`, 1.3), and the characters in `render.SYMBOLS` are drawn as shapes.

## Style

`Style` holds every option of the look. Sizes are relative to the image, so a style gives the same picture at any resolution.

| Option | Default | Meaning |
|---|---|---|
| `font`, `caption_font`, `sfx_font` | `Comic Relief Bold`, `""`, `Bangers` | Font names from `font_names()`. An empty `caption_font` means the bubble font. |
| `bubble_colors`, `caption_colors`, `sfx_colors` | `auto` | A `PALETTES` name. |
| `bubble_mood`, `caption_mood`, `sfx_mood` | `calm`, `calm`, `shout` | A `MOODS` name. |
| `caption_extras`, `sfx_extras` | `none` | An `EXTRAS` name: marks scattered around. |
| `caption_bubble` | `none` | A `BUBBLE_SHAPES` name: draw a bubble for the caption. |
| `caption_bubble_theme`, `caption_tail` | `light`, `none` | `BUBBLE_THEMES`, `TAILS`. |
| `uppercase` | `True` | Capital letters. |
| `bubble_size` | `9.0` | Bubble text: the largest font size tried, % of image height. |
| `bubble_min_size` | `1.5` | The smallest size still readable, % of image height. |
| `margin` | `0.08` | Gap between the text and the bubble edge, fraction of the bubble. |
| `free_size` | `5.5` | Caption font size, % of image height. |
| `stroke_width`, `shadow` | `0.12`, `0.5` | Caption outline (fraction of the font size) and shadow strength. |
| `sfx_size`, `sfx_tilt`, `sfx_opacity` | `7.0`, `15.0`, `0.95` | Effect size (% of height), largest random tilt in degrees, opacity. |
| `text_color`, `stroke_color`, `sfx_color` | `auto` | `auto` or `#RRGGBB`. Used by the `custom` palette. |
| `jitter`, `size_jitter`, `rough`, `line_tilt`, `line_shift`, `line_spacing` | `0.3`, `0`, `0`, `0`, `0`, `1.08` | The `custom` mood. |
| `arc`, `rotation` | `0`, `0` | Bend (-1..1) and tilt (degrees) of a whole block. |
| `soften`, `grain`, `opacity` | `0.4`, `0`, `1.0` | Blur in pixels, uneven ink, opacity. |
| `seed`, `sfx_seed` | `0`, `0` | Seeds of the letter wobble and of the effect placement. |

**Palettes** (`render.PALETTES`) are dicts of colors: `fill`, optional `fill2` (a top-to-bottom gradient), `stroke`, optional `outer` (a second outline) and `glow`, and `ink` (the color of plain text inside a light bubble). `auto` is `None`; `from the art` is computed from the image by `accent_palette()`; `custom` reads the three color options.

**Moods** (`render.MOODS`) are dicts of the six mood options. `custom` is `None` and reads them from the style.

## The scene

A dict of plain values: it survives `json.dumps` and back.

```python
{
  "version": 1,
  "size": [896, 1152],            # the image the scene was made for
  "style": {...},                 # vars(style)
  "white_threshold": 120, "rtl": False, "erase": True,
  "people": True,                 # the character mask was part of the placement
  "empty": False,                 # True: nothing to draw
  "bubbles": [[x0, y0, x1, y1], ...],   # every bubble found, in reading order
  "regions": [...],               # the regions, cleaned
  "items": [...],                 # what is drawn, in order
  "info": {"bubbles_found": 2, "bubbles_filled": 2, "free_text": True,
           "font_sizes": [64, 50], "characters": True, "sfx": 1, "regions": 3},
}
```

`info["characters"]` is present when something was placed automatically: `True` when a character mask was used, `False` when none was available.

### Items

Every item has `kind`, `text`, `size` (font size in pixels) and `lines` (the text broken into lines and measured; `draw()` takes it as it is). Items that can be moved by hand also have an `id`.

| `kind` | What | `id` | Place |
|---|---|---|---|
| `bubble` | Text inside the n-th bubble found in the art | none | `bubble` (index into `scene["bubbles"]`), `cx`, `cy` |
| `caption` | Text straight on the art | `caption` | `cx`, `cy`, `box`, `rotation`, `reach`, `placement` |
| `balloon` | Text inside a bubble drawn for the caption | `caption` | `x`, `y`, `box`, `tall` |
| `sfx` | A sound effect | `sfx:<index>` | `x`, `y`, `nominal` (its size before tilting), `room` (the box it reserves), `rotation`, `index` |
| `region` | Text fitted into a hand-drawn area | `region:<id>` | `region` (index into `scene["regions"]`), `cx`, `cy`, `fill` |
| `path` | Text along a brush stroke | `region:<id>` | `region`, `path` (the smoothed centre line), `voice`, `fill` |

A sound effect that belongs to a region carries `"region": "<region id>"`, and its `index` starts at `1000` (`REGION_SFX`): adding or removing an ordinary effect does not change how the effects of regions are drawn.

Real examples:

```json
{"kind": "bubble", "bubble": 0, "text": "Hi", "size": 64, "cx": 240.9, "cy": 257.7, "lines": [...]}
{"kind": "caption", "id": "caption", "text": "Later", "placement": "top-left", "size": 63,
 "cx": 148.0, "cy": 85.0, "box": [-17, 14, 313, 155], "rotation": 0.0, "reach": 0.46, "lines": [...]}
{"kind": "sfx", "id": "sfx:0", "text": "THUD", "index": 0, "size": 60, "x": 216, "y": 658,
 "nominal": [168, 84], "room": [148, 571, 451, 829], "rotation": 7.7}
```

## Pins: placing by hand

`pins` is a dict from item id to what was set by hand. Whatever a pin leaves out is still decided by `arrange()`.

```python
pins = {
    "caption": {"cx": 300, "cy": 500},                 # only the place
    "sfx:0":   {"size": 120, "rotation": -20},         # only size and tilt
    "sfx:1":   {"cx": 640, "cy": 900, "size": 90, "rotation": 8},
}
scene = arrange(image, caption="Later...", sfx="THUD\nBAM", pins=pins)
```

| Key | Meaning |
|---|---|
| `cx`, `cy` | The middle of the item, in image pixels. Both or neither. |
| `size` | Font size in pixels, clamped to 8..2000. |
| `rotation` | Tilt in degrees, counter-clockwise. |
| `reach` | Caption only: how wide the block may be, as the scene reported it. Keeps the line breaks the caption had when it was pinned. |
| `tall` | Drawn bubble only: keep the tall, narrow variant. |

The id `caption` addresses the caption, or the bubble drawn for it. Things placed after a pinned item keep off it where it now stands.

The round trip the editor makes: read an item from the scene, send back a pin with the values the user changed plus `reach` or `tall` from the item.

## Regions: areas drawn by hand

`regions` is a list of at most 40 areas.

```python
regions = [{
    "id": "a",
    "kind": "text",                       # "text" | "sfx" | "keepout"
    "text": "Not one more step.",
    "fill": "light",                      # "none" | "light" | "dark"; kind "text" only
    "shapes": [{"type": "polygon", "points": [[600, 880], [860, 880], [860, 1080], [600, 1080]]}],
    "rotation": 0, "scale": 1.0,          # optional
    "follow": False, "flip": False,       # optional
}]
```

| Key | Meaning |
|---|---|
| `kind` | `text`: the text is fitted into the area as into a bubble. `sfx`: the text is one sound effect, sized to the area and put in its middle. `keepout`: nothing placed automatically may land there. |
| `fill` | `none`: the text gets the caption's outline. `light` / `dark`: the area is painted as a bubble first. |
| `shapes` | What the area is made of, in the order it was drawn. Up to 200 shapes, 4000 points each. |
| `rotation` | Tilt of the text or effect, degrees, counter-clockwise, -180..180. Without it an effect is tilted at random. |
| `scale` | How large the text is against what the area would give it, 0.2..4. Above 1 it may reach out of the area. |
| `follow` | The text runs along the region's longest brush stroke and bends with it, in the direction the stroke was drawn. Letters are about 0.6 of the brush width tall. |
| `flip` | With `follow`: along the stroke the other way round. |

**Shapes**

| `type` | Fields | Meaning |
|---|---|---|
| `polygon` | `points` (3 or more) | An outline that is closed and filled. |
| `stroke` | `points`, `width` | A brush stroke with round ends and joints. |
| `erase` | `points`, `width` | Rubs out what the shapes before it painted. |

A region is all of its shapes together, rasterised with Pillow in drawing order and rounded off with a small Gaussian blur, since a hand is not steady. A region needs at least one shape that paints. Everything placed automatically keeps off every region.

Text in a tilted area is fitted in the area's own frame: the mask is rotated (`scipy.ndimage.affine_transform`), the text is fitted upright, and the block is rotated back when drawn.

## How bubbles are found

`detect.detect_bubbles(rgb, white_threshold=120, min_area=0.0015, max_area=0.6, min_outline=0.8, rtl=False)` returns `Bubble` objects in reading order.

A bubble is a **flat fill enclosed by a contrasting outline, with a smooth, nearly convex shape**:

1. **Flat fill.** Pixels that are bright enough (`white_threshold`), nearly unsaturated or only lightly tinted (`MAX_TINT`, 48) and locally flat. A second pass looks for near-black fills (dark bubbles).
2. **Connected components** of such pixels, between `min_area` and `max_area` of the image.
3. **Shape tests** (`is_bubble`), on measurements taken by `scan()`: how flat the fill is, solidity against the convex hull, how much of its bounding box it fills, the share of its border that touches an outline of the opposite brightness (`min_outline`). The thresholds were measured on real generations and are explained in the code.
4. **Stricter tests** for the risky cases: a tinted fill (cream, beige) has to be brighter, flatter, more solid and better outlined, so a face is not taken for a bubble; a bubble below `SMALL` (0.3% of the image) has to pass a stricter test too.

Reading order is rows top to bottom; bubbles that overlap vertically share a row and go left to right within it (right to left with `rtl`).

`erase_letters(rgb, bubble)` paints over everything the fill encloses (the model's letters) with the bubble's own color, in place. The result of a detection is cached for the last six images, keyed by an MD5 of the pixels.

## How text is fitted into a bubble

For one line of text and one bubble (`_fit_bubble`, `_fit_text`):

1. Start at `bubble_size` and go down. At each size, lay the text out against the bubble's real shape: every row of the mask gives the width available at that height, minus `margin`.
2. Prefer a **diamond**: short lines at the top and bottom, long in the middle (`layout_shaped`, `diamond_profile`). A better shape is worth up to 20% of font size (`SHAPE_REACH` 0.8, `SHAPE_WEIGHT` 0.6).
3. If nothing fits above `bubble_min_size` in `MAX_LINES` (8) lines: drop the emphasis, then hyphenate the longest words (`_split_word`: near the middle, after a vowel that a consonant follows where there is one, three letters or more on each side).
4. Still nothing: with `spill`, the line goes to the caption and the bubble stays free for the next line (`_assign`).

## How free text finds its place

Three masks drive every automatic placement:

| Mask | What is in it | Weight |
|---|---|---|
| `static` | Bubbles, characters, regions | Must be avoided where possible |
| `precious` | Heads (the top quarter of each character), bubbles, regions | Avoided first when something has to be covered |
| `energy` | Edge energy of the art (`_energy`) | Lower is calmer: effects and drawn bubbles go to calm areas |

- **Caption, `auto`** (`_place_free`): a band at the top or bottom, then a narrower block in a corner, then the same a little smaller. The first that is clear wins; otherwise the one that covers the least, a head counting most.
- **Drawn bubble** (`_place_balloon`): a calm, free spot by integral images over `energy` and `static`; tried tall and narrow, then shrunk in steps down to 0.6 of its size, when nothing is free.
- **Sound effects** (`_place_sfx`, `_calm_spot`): one after another, each reserving its `room` so the next keeps off it. An effect that would land on a character is drawn smaller first, down to 65%. The place does not depend on the effect's look, so changing a font does not move it.
- **Marks around** (`decorate`): left out where they would land on a character or be cut by the image edge.

Pinned items are placed first where the pin says, and reserve their room like any other.

## Characters

`people.person_mask(rgb)` returns a boolean mask of the characters, or `None`.

It uses `ultralytics` and a model file matching `person_yolov8*-seg.pt`, **only if both are already on the machine**. Nothing is downloaded. The model is looked for, relative to the host's working directory, in:

```
models/adetailer            models/ultralytics/segm     models/ultralytics
models/Ultralytics/segm     models/yolo
../../Models/Ultralytics/segm   ../../Models/AfterDetailer   ../../Models/adetailer   (StabilityMatrix)
../ComfyUI/models/ultralytics/segm                                                   (a sibling ComfyUI)
```

The environment variable `SDCL_PERSON_MODEL` points at any other file. The smallest matching file is used: this only needs a rough silhouette. Any failure (no library, a broken file, a failed prediction) means `None`, never an error.

## Fonts

`fonts.list_fonts()` returns `{display name: path}`; `font_names()` the names in list order:

1. the user's own files in `fonts/` (`.ttf`, `.otf`, `.ttc`), git-ignored;
2. the sixteen bundled fonts in `fonts/bundled/`;
3. a few comic-looking system fonts, when installed.

The display name is read from the font's name table. `font_sample(style, text, size)` renders a preview strip.

## Command line

From the repository folder:

```
python -m comic_lettering in.png out.png --text "Hi!\nYo." --caption "Later..." --sfx "THUD\nBAM"
```

`\n` separates bubbles, caption lines and effects. Common options have flags (`--font`, `--placement`, `--no-erase`, `--no-spill`, `--numbers`, `--white-threshold`, the sizes); any other `Style` option goes through `--opt`:

```
python -m comic_lettering in.png out.png --caption "So cool" --opt caption_colors=pink --opt caption_bubble=cloud --opt caption_tail=down-left
```

The command prints the scene's `info`.
