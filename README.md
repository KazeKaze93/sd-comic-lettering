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
2. Type the text and press **Apply to image**. The images of the last generation are lettered again from their clean copies, so nothing is generated twice. Change the text, the font or any option and press Apply again.
3. Press **Save result** to write the lettered images to the output folder with a `-lettered` suffix. The gallery's own save button works too.

Tick **Apply to every new image** to letter images during generation instead. Changing the font re-applies the text at once and updates the sample strip under the font list. The font and the options under `Style` are remembered in `user_settings.json`.

### ComfyUI

Add the `Comic Lettering` node (category `image/postprocessing`) between `VAE Decode` and `Save Image`.

### CLI

`python -m comic_lettering in.png out.png --text "Hello" --caption "Later..."` from the repo folder.

### Text

Two fields:

- **Bubbles**: one line per bubble, in reading order (top to bottom, left to right). An empty line skips a bubble. Line breaks inside a bubble are placed automatically.
- **Caption**: text drawn straight onto the art, outside the bubbles.

`*word*` makes a word bigger. A word may break after a hyphen (`H-m-m`) when that lets the text be bigger.

**Show bubble numbers** draws each bubble's number instead of the text, to see which bubbles were found and in what order.

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

## Fonts

Drop `.ttf` / `.otf` files into `fonts/` and restart. Font files are git-ignored.

## Limits

- A bubble is detected as a flat white or gray fill (any brightness above `white_threshold`), enclosed by a dark outline, with a smooth, nearly convex shape. Spiky or cloud-shaped bubbles, bubbles without an outline, bubbles with a gradient fill and rectangular caption boxes are not found.
- Anything else that looks the same gets lettered too, such as a blank sheet of paper on a wall. Use `Show bubble numbers` to see what was found and an empty line to skip it.
- A narrow bubble cannot hold a long word at a readable size. Such text goes to the caption.
- No face detection: the caption can land on a character. Pick the placement by hand in that case.
- No emoji fallback font.
