# sd-comic-lettering

Puts your own text on a generated image, with no image editor involved.

- **Bubble found**: the model's gibberish letters are erased and your text is fitted inside the bubble.
- **No bubble**: the text is drawn straight onto the art, with an outline and a shadow.

One repo works in both hosts: it is a **ComfyUI custom node** and an **A1111 / Forge / reForge extension**. The core uses only `numpy`, `scipy` and `Pillow`, which both hosts already ship.

## Install

ComfyUI:

```
cd ComfyUI/custom_nodes
git clone https://github.com/KazeKaze93/sd-comic-lettering.git
```

A1111 / Forge / reForge:

```
cd extensions
git clone https://github.com/KazeKaze93/sd-comic-lettering.git
```

Restart the host afterwards.

## Use

### A1111 / Forge / reForge

The `Comic Lettering` panel sits under the result gallery, in txt2img and img2img.

1. Generate an image.
2. Type the text and press **Apply**. The images of the last generation are lettered again from their clean copies, so nothing is generated twice. Change the text, the font or any option and press Apply again.
3. Press **Save** to write the lettered images to the output folder with a `-lettered` suffix. The gallery's own save button works too.

Tick **Every new image** to letter images during generation instead. Every entry of the font list is drawn in its own font. Changing the font re-applies the text at once. The font and the options under `Style` are remembered in `user_settings.json`.

### ComfyUI

Add the `Comic Lettering` node (category `image/postprocessing`) between `VAE Decode` and `Save Image`.

### CLI

`python -m comic_lettering in.png out.png --text "Hello" --caption "Later..."` from the repo folder.

### Text

Three fields:

- **Bubbles**: one line per bubble, in reading order (top to bottom, left to right). An empty line skips a bubble. Line breaks inside a bubble are placed automatically, at the largest font size that fits, and so that the lines form a diamond: short at the top and bottom, long in the middle.
- **Caption**: text drawn straight onto the art, outside the bubbles. With `auto` placement it takes the calmer of top and bottom and keeps off the bubbles.
- **SFX**: sound effects, one per line (`SLAP`, `THUD`). Each one is drawn big, tilted and outlined, in its own font, in a calm and empty part of the art, clear of the bubbles, the caption and the other effects. **Move SFX** puts them somewhere else; press it until they sit well.

`*word*` makes a word bigger. A word may break after a hyphen (`H-m-m`) when that lets the text be bigger.

**Bubble numbers** draws each bubble's number instead of the text, to see which bubbles were found and in what order.

A line goes into a bubble only if it fits at a readable size (`bubble_min_size`). A bubble too small for it is passed over, and lines left without a bubble are added to the caption. Untick `Text that does not fit a bubble goes to the caption` to always write into the bubbles, however small, and drop the lines left over.

### Options

| Option | What it does |
|---|---|
| `placement` | Caption position: `top`, `bottom`, `center`, or `auto` (the calmer of top and bottom). |
| `font` | Fonts from `fonts/` first, then comic-looking system fonts. |
| `uppercase` | Comic-style capitals. |
| `bubble_size` | Bubble text: largest font size tried, % of image height. The biggest size that fits is used. |
| `bubble_min_size` | Smallest bubble font size still considered readable, % of image height. |
| `free_size` | Caption: font size, % of image height. |
| `text_color`, `stroke_color` | `auto` or `#RRGGBB`. |
| `stroke_width`, `shadow` | Outline and drop shadow of the caption. |
| `jitter` | Per-letter wobble of baseline and angle, so the text does not look typeset. |
| `arc`, `rotation` | Bend and tilt of the whole block. |
| `soften`, `grain`, `opacity` | Blur, uneven ink and transparency, to blend the letters with the art. |
| `margin` | Gap between the text and the bubble edge. |
| `erase_ai_text` | Erase the model's letters before writing. |
| `white_threshold` | Darkest bubble fill that still counts (default 120). Raise it if a gray object gets lettered. |
| `seed` | Seed of the jitter. |
| `sfx_font`, `sfx_size`, `sfx_color`, `sfx_opacity` | Look of the sound effects. `auto` color is white with a dark outline. |
| `sfx_tilt` | Each effect is tilted by a random angle up to this many degrees. |
| `sfx_seed` | Where the effects land and how they tilt. `Move SFX` raises it by one. |

## Fonts

Sixteen fonts ship in `fonts/bundled/`, taken from [google/fonts](https://github.com/google/fonts). Their licenses (SIL Open Font License 1.1 or Apache 2.0) are in `fonts/bundled/licenses/`.

![Bundled fonts](docs/fonts.png)

- With Cyrillic: Amatic SC Bold, Bad Script, Balsamiq Sans Bold, Comic Relief Bold (the default), Marck Script, Neucha, Pangolin, Russo One.
- Latin only: Bangers, Chewy, Comic Neue Bold, Creepster, Gloria Hallelujah, Luckiest Guy, Patrick Hand, Permanent Marker.

Your own `.ttf` / `.otf` files go into `fonts/`: they are listed first and are git-ignored. A few comic-looking system fonts are listed last.

## Limits

- A bubble is detected as a flat white or gray fill (any brightness above `white_threshold`), enclosed by a dark outline, with a smooth, nearly convex shape. Spiky or cloud-shaped bubbles, bubbles without an outline, bubbles with a gradient fill and rectangular caption boxes are not found.
- Anything else that looks the same gets lettered too, such as a blank sheet of paper on a wall. Use `Bubble numbers` to see what was found and an empty line to skip it.
- A narrow bubble cannot hold a long word at a readable size. Such text goes to the caption.
- No face detection: the caption and the sound effects can land on a character. Flat skin counts as an empty area. Pick the caption placement by hand, and press `Move SFX` until the effects sit well.
- No emoji fallback font.
