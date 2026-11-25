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

The `Comic Lettering` panel sits under the result gallery, in txt2img and img2img. It starts collapsed.

1. Generate an image.
2. Type the text and press **Apply**. The images of the last generation are lettered again from their clean copies, so nothing is generated twice. Change the text and press Apply again; changing any list re-applies at once.
3. Save the result with the gallery's own buttons, or right-click the image.

| Button | What it does |
|---|---|
| `Apply` | Letters the images of the last generation. |
| `Remove text` | Shows those images as they were generated, without any lettering. |
| `Move SFX` | Puts the sound effects somewhere else. |
| `Reset options` | Puts every list and slider back to its default. |
| `Clear bubbles` / `caption` / `sfx` | Empties that text field. |
| `♥` `★` `✦` `♪` `💢` `💧` | Adds that mark to the field chosen under `Insert a symbol into`. |

Tick **Every new image** to letter images during generation instead. The lists and the options under `Fine tuning` are remembered in `user_settings.json`; the texts and the two checkboxes are not.

### Keeping off the characters

Text that is placed automatically (the sound effects, the caption and the drawn bubble with `auto` placement) avoids the characters when two things are present on the machine: the `ultralytics` package and a person segmentation model named `person_yolov8*-seg.pt`. ADetailer installs the package. The model is looked for in `models/adetailer`, `models/ultralytics/segm`, a StabilityMatrix `Models/Ultralytics/segm` folder and a sibling ComfyUI install; the `SDCL_PERSON_MODEL` environment variable can point at any other file. Nothing is downloaded. Without them the status line says so, and placement goes by calm areas alone, which often means on the character.

### ComfyUI

Add the `Comic Lettering` node (category `image/postprocessing`) between `VAE Decode` and `Save Image`.

### CLI

`python -m comic_lettering in.png out.png --text "Hello" --caption "Later..."` from the repo folder.

### Text

Three fields:

- **Bubbles**: one line per bubble, in reading order (top to bottom, left to right). An empty line skips a bubble. Line breaks inside a bubble are placed automatically, at the largest font size that fits, and so that the lines form a diamond: short at the top and bottom, long in the middle.
- **Caption**: text drawn straight onto the art, outside the bubbles, or inside a bubble drawn for it. With `auto` placement it takes the calmer of top and bottom, keeps off the bubbles and avoids covering a head.
- **SFX**: sound effects, one per line (`SLAP`, `THUD`). Each one is drawn big, tilted and outlined, in its own font, in a calm and empty part of the art, clear of the bubbles, the characters, the caption and the other effects. `FAP x5` stacks the word five times in a ragged column. **Move SFX** puts them somewhere else. Changing the look of an effect does not move it.

In any field:

- `*word*` makes a word bigger.
- `♥` (or `<3`), `★`, `✦`, `♪`, `💢`, `💧` are drawn as shapes: heart, star, sparkle, note, anger mark, drop.
- A word may break after a hyphen (`H-m-m`) when that lets the text be bigger.

**Bubble numbers** draws each bubble's number instead of the text, to see which bubbles were found and in what order.

A line goes into a bubble only if it fits at a readable size (`bubble_min_size`). A bubble too small for it is passed over, and lines left without a bubble are added to the caption. Untick `Text that does not fit a bubble goes to the caption` to always write into the bubbles, however small, and drop the lines left over.

### Look

Each kind of text (bubbles, caption, SFX) has its own row of lists. Changing any list re-applies the text at once.

| List | What it does |
|---|---|
| Font | Every entry of the list is drawn in its own font. The caption can use the bubble font or its own. |
| Colors | `auto` is white with a dark outline (black text inside a light bubble), or the colors typed under `Fine tuning`. `pink`, `gold`, `candy`, `ice`, `blood`, `neon green`, `black on white` are presets with a second outline, a gradient or a glow where it fits. `from the art` takes the strongest color of the image. |
| Mood | How unruly the letters are. `calm`: straight. `playful`: letters of different sizes, lines tilted. `shout`: more of both. `shaky`: trembling letters. `rough`: ragged, angular edges. `custom`: the sliders under `Fine tuning`. |
| Extras | Small marks scattered around a caption or an effect: hearts, sparkles, stars, notes, sweat drops, anger marks, motion lines. |

The caption has one more row:

| List | What it does |
|---|---|
| Placement | `auto`, `top`, `bottom`, `center`, or a corner. |
| Draw a bubble | Puts the caption in a bubble drawn for it: `oval`, `box`, `cloud` or `burst`. With `auto` placement the bubble goes to a calm, free spot. |
| Theme | `light`: white bubble, dark outline. `dark`: black bubble with the outline and the text in the chosen colors. |
| Tail | Which way the tail points, or none. |

### Fine tuning

| Option | What it does |
|---|---|
| `uppercase` | Comic-style capitals. |
| `erase_ai_text` | Erase the model's letters before writing. |
| `bubble_size` | Bubble text: largest font size tried, % of image height. |
| `bubble_min_size` | Smallest bubble font size still considered readable, % of image height. |
| `margin` | Gap between the text and the bubble edge. |
| `free_size`, `stroke_width`, `shadow` | Caption: font size, outline width and drop shadow. |
| `sfx_size`, `sfx_tilt`, `sfx_opacity` | Sound effects: size, the largest random tilt, transparency. |
| `text_color`, `stroke_color`, `sfx_color` | `auto` or `#RRGGBB`. Used when the Colors list is `auto`. |
| `jitter`, `size_jitter`, `rough`, `line_tilt`, `line_shift`, `line_spacing` | The `custom` mood: letter wobble, letters of different sizes, ragged edges, tilt and sideways shift of each line, distance between lines. |
| `arc`, `rotation` | Bend and tilt of the whole block. |
| `soften`, `grain`, `opacity` | Blur, uneven ink and transparency, to blend the letters with the art. |
| `white_threshold` | Darkest light-bubble fill that still counts (default 120). Raise it if a gray object gets lettered. |
| `seed`, `sfx_seed` | Seeds of the letter wobble and of the effect placement. `Move SFX` raises the second by one. |

## Fonts

Sixteen fonts ship in `fonts/bundled/`, taken from [google/fonts](https://github.com/google/fonts). Their licenses (SIL Open Font License 1.1 or Apache 2.0) are in `fonts/bundled/licenses/`.

![Bundled fonts](docs/fonts.png)

- With Cyrillic: Amatic SC Bold, Bad Script, Balsamiq Sans Bold, Comic Relief Bold (the default), Marck Script, Neucha, Pangolin, Russo One.
- Latin only: Bangers, Chewy, Comic Neue Bold, Creepster, Gloria Hallelujah, Luckiest Guy, Patrick Hand, Permanent Marker.

Your own `.ttf` / `.otf` files go into `fonts/`: they are listed first and are git-ignored. A few comic-looking system fonts are listed last.

## Limits

- A bubble is detected as a flat white or gray fill (any brightness above `white_threshold`) enclosed by a dark outline, or a flat near-black fill enclosed by a bright outline, with a smooth, nearly convex shape. Spiky or cloud-shaped bubbles, bubbles without an outline, translucent or gradient bubbles and rectangular caption boxes are not found. Dark bubbles are calibrated on a single example: expect misses.
- Anything else that looks the same gets lettered too, such as a blank sheet of paper on a wall. Use `Bubble numbers` to see what was found and an empty line to skip it.
- A narrow bubble cannot hold a long word at a readable size. Such text goes to the caption.
- When a character fills most of the frame there may be no free place: a drawn bubble is then shrunk, down to 60%, and put where it covers the least. A caption with a fixed placement (`top`, a corner) avoids nothing.
- The place of a sound effect is chosen for an estimated box, so a very wide font can make two effects touch.
- No emoji fallback font.
