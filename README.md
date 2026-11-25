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

- **ComfyUI**: add the `Comic Lettering` node (category `image/postprocessing`) between `VAE Decode` and `Save Image`.
- **reForge**: open the `Comic Lettering` accordion in txt2img or img2img, tick `Enable`, type the text. Every generated image is lettered before it is saved.
- **CLI**, for quick tests: `python -m comic_lettering in.png out.png --text "Hello"` from the repo folder.

### Text syntax

- A **blank line** starts the next bubble, in reading order (top to bottom, left to right).
- A block that is just `-` skips its bubble.
- A block starting with `2:` goes into bubble number 2, whatever its position in the text.
- The text `#` alone draws each bubble's number, to see the order before writing.
- A word may break after a hyphen (`H-m-m`) when that lets the text be bigger.
- `*word*` makes a word bigger.
- More text blocks than bubbles: the rest becomes free text (mode `auto`) or is dropped (mode `bubble`).
- Mode `auto` writes into a bubble only if the text fits at a readable size (`bubble_min_size`). A bubble too small for it is passed over, and the text becomes free text. Mode `bubble` always writes into the bubbles, however small.

### Options

| Option | What it does |
|---|---|
| `mode` | `auto`: bubbles first, free text as fallback. `bubble`: bubbles only. `free`: skip detection. |
| `placement` | Free text position: `top`, `bottom`, `center`, or `auto` (the calmer of top and bottom). |
| `font` | Fonts from `fonts/` first, then comic-looking system fonts. |
| `uppercase` | Comic-style capitals. |
| `bubble_size` | Bubble text: largest font size tried, % of image height. The biggest size that fits is used. |
| `bubble_min_size` | Mode `auto`: smallest font size still considered readable, % of image height. |
| `free_size` | Free text: font size, % of image height. |
| `text_color`, `stroke_color` | `auto` or `#RRGGBB`. |
| `stroke_width`, `shadow` | Outline and drop shadow. Free text only. |
| `jitter` | Per-letter wobble of baseline and angle, so the text does not look typeset. |
| `arc`, `rotation` | Bend and tilt of the whole block. |
| `soften`, `grain`, `opacity` | Blur, uneven ink and transparency, to blend the letters with the art. |
| `margin` | Gap between the text and the bubble edge. |
| `erase_ai_text` | Erase the model's letters before writing. |
| `white_threshold` | Darkest bubble fill that still counts (default 180). Lower it for darker gray bubbles, raise it if light clothing gets lettered. |
| `seed` | Seed of the jitter. |

## Fonts

Drop `.ttf` / `.otf` files into `fonts/` and restart. Font files are git-ignored.

## Limits

- Only light bubbles are detected: a flat white to light gray fill, a dark outline around most of the edge, and a smooth, nearly convex shape. Spiky or cloud-shaped bubbles and bubbles without an outline are not found.
- A narrow bubble cannot hold a long word at a readable size. In mode `auto` such text becomes free text.
- No face detection: free text can land on a character. Pick the placement by hand in that case.
- No emoji fallback font.
