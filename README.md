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

There are two ways in, in txt2img and in img2img alike: the speech-bubble icon in the row of tools under `Generate` (beside Style Grid's icon when that extension is installed), and the `Comic Lettering` button under the result gallery. Either opens the editor over the page; `Close` or Esc brings the page back.

1. Generate an image and press `Comic Lettering`. The editor takes the image the gallery shows, as it was generated.
2. Type the text. Everything applies by itself: a list or a checkbox when it changes, a slider when it is released, a text field when you leave it (or on Ctrl+Enter).
3. `To gallery` shows the result in the gallery of the tab you came from; `Save` writes a PNG into the host's folder for saved images.

`Own image` at the top letters any image from disk instead: drop it onto the editor or click to choose it. Nothing has to be generated for that.

| Control | What it does |
|---|---|
| `From generation` / `Own image` | Which image is lettered: the one in the gallery of the tab you came from, or a file of yours. |
| `Frames and areas` | Untick it to see the image as it will be saved, without any of this. Outlines over the image: every bubble found, numbered in reading order (dashed if left empty), and everything that was drawn. The caption, its drawn bubble and the sound effects can be moved by their frames, see below. |
| `Original` | Shows the image without the lettering. The texts stay in their fields. |
| `Save` | Writes the lettered PNG into the host's folder for saved images; the status line names the file. |
| `To gallery` | Puts the lettered image into that gallery and closes the editor. |
| `Clear` next to a field | Empties that field. |
| `Numbers` next to Bubbles | Draws each bubble's number instead of the text, to see what was found and in what order. |
| `Move` next to Sound effects | Arranges the sound effects differently. |
| The mark buttons | Insert a mark at the cursor of the text field you used last. `All 37 marks` shows the rest: hearts (full, hollow, two, broken), a kiss, stars and sparkles, a burst, anger, a bolt, a flame, a drop, splashes, steam, a puff, blush lines, a wave, a spiral, zzz, notes, a flower, moon, sun, ♂ ♀, a cross, a ring, arrows and card suits. They are drawn as shapes in the text's colors, so they work with every font. |
| `Look` | Chooses whose lists are shown: bubbles, caption or sound effects. |
| `Fine tuning` | Sizes, outlines, the custom mood and the bubble detector, grouped by kind of text. `Reset the look` puts everything back; `Keep the fonts` leaves the three fonts alone. |
| `Letter every new image while it is generated` | Letters images during generation, with the three texts and the look as they are in the editor. |

**Placing by hand.** Drag the frame of the caption, of its drawn bubble or of a sound effect to move it. Click a frame to pick it: the corner square resizes it, the round knob on a stem above it, marked with a turning arrow, turns it (not the drawn bubble). The arrow keys nudge the picked item, by ten pixels with Shift. What was placed by hand stays where it is when the texts or the look change, and the things placed automatically keep off it. `Place automatically` under a picked frame (or Delete) hands that item back to the script; `Place all automatically` at the top does it for all of them. Texts inside the bubbles found in the art are always fitted by the script.

**Areas drawn by hand.** Under `Areas drawn by hand` there are four tools, shown as icons: the arrow (no drawing: drag areas, captions and effects), the outline (draw a closed outline; it is filled), the brush (paint; the slider sets its width and a ring shows it on the image) and the eraser (rubs out whatever it passes over, in every area). Draw on the image. Each area gets a card in the panel:

| Area | What happens in it |
|---|---|
| `Text` | Its text is fitted into the area like into a bubble: as large as the shape allows. `On the art` draws it with the caption's outline; `Light bubble` and `Dark bubble` paint the area as a bubble first, so any shape you draw becomes a bubble. |
| `Effect` | Its text is one sound effect, sized to the area and put in its middle. |
| `Keep out` | Nothing that the script places (caption, drawn bubble, sound effects) lands there. |

Paint that touches the picked area adds to it; paint anywhere else starts a new area, so two bubbles are two areas with a text each. `New area` starts one even on top of the picked one. An area painted with a single brush stroke starts with `Write along the brush stroke` on (painting more onto it turns that off, since it is then a shape to fill): the text runs along the stroke and bends with it, in the direction you drew it, with letters about as tall as the brush is wide. Paint one stroke along a contour to set a word on it. Untick it to fit the text into the painted shape instead. The card of a `Text` or `Effect` area also has `Size` (how large the text is against what the area gives it; above 100% it may reach out of the area) and `Tilt` (in degrees, counter-clockwise; an effect is tilted at random until you set it). `Turn the text round` runs it along the stroke the other way. `Undo` on a card takes back the last thing drawn there. Everything the script places keeps off every area. Areas and things placed by hand belong to the image they were made on: they stay when the editor is closed and opened again on the same image, and go with the next generation. An area's tint shows while it is being worked on: once it has its text and the field is closed, the tint goes, and pointing at the area with the arrow brings it back (the eraser shows every area). With the arrow, a click on an area brings up the field for its text right beside it, and a drag moves the area with everything in it. While anything is dragged, the piece of the picture that holds it moves along at once; the exact picture follows when the server has drawn it.

The status line under the image says how many bubbles were found and filled. The look is remembered in `user_settings.json`. The texts are remembered only while `Letter every new image` is on, since the host then needs them.

The editor is a React page in `ui/`; its build in `ui/dist` is part of the repo, so Node is not needed to use the extension. To change the page: `npm install` and `npm run build` in `ui/`.

### Keeping off the characters

Text that is placed automatically (the sound effects, the caption and the drawn bubble with `auto` placement) avoids the characters when two things are present on the machine: the `ultralytics` package and a person segmentation model named `person_yolov8*-seg.pt`. ADetailer installs the package. The model is looked for in `models/adetailer`, `models/ultralytics/segm`, a StabilityMatrix `Models/Ultralytics/segm` folder and a sibling ComfyUI install; the `SDCL_PERSON_MODEL` environment variable can point at any other file. Nothing is downloaded. Without them the status line says so, and placement goes by calm areas alone, which often means on the character.

### ComfyUI

Add the `Comic Lettering` node (category `image/postprocessing`) between `VAE Decode` and `Save Image`.

### CLI

`python -m comic_lettering in.png out.png --text "Hello" --caption "Later..."` from the repo folder.

### From code

`letter()` is two steps that can be used apart:

```python
from comic_lettering import arrange, draw

scene = arrange(image, "Hi
Yo", caption="Last day of summer.", sfx="SPLASH")
result = draw(image, scene)
```

`arrange()` decides what goes where and draws nothing; its `pins` argument fixes the place, size or tilt of single items (`{"caption": {"cx": 300, "cy": 500}, "sfx:0": {"size": 120, "rotation": -20}}`). Its `regions` argument takes areas drawn by hand: polygons or brush strokes with a text to fit into them, or to keep everything out of. The scene it returns is a dict of plain values, so it survives a trip through JSON: `scene["items"]` lists the texts in the bubbles found in the art (`bubble`), the caption (`caption`) or the bubble drawn for it (`balloon`), and the sound effects (`sfx`), each with its text, its font size and its place in pixels. `draw()` draws a scene onto the image it was made for.

### Text

Three fields:

- **Bubbles**: one line per bubble, in reading order (top to bottom, left to right). An empty line skips a bubble. Line breaks inside a bubble are placed automatically, at the largest font size that fits, and so that the lines form a diamond: short at the top and bottom, long in the middle.
- **Caption**: text drawn straight onto the art, outside the bubbles, or inside a bubble drawn for it. With `auto` placement it tries a band at the top or the bottom, then a narrower block in a corner, then the same a little smaller, and takes the first that is clear of bubbles and characters; if none is, the one that covers the least, a head counting most.
- **Sound effects**: one per line (`SLAP`, `THUD`). Each one is drawn big, tilted and outlined, in its own font, in a calm and empty part of the art, clear of the bubbles, the characters, the caption and the other effects. `FAP x5` stacks the word five times in a ragged column. **Move** sends each of them to another place. An effect that would land on a character is drawn smaller first, down to 65%; in a crowded image it can still end up on a character, never on a head first. Changing the look of an effect does not move it.

In any field:

- `*word*` makes a word bigger. In a bubble too tight for the bigger word the text is written without the emphasis instead of being moved to the caption. If it still does not fit, its longest words are broken with a hyphen (`UNBE-` / `LIEVABLE`).
- Marks are drawn as shapes, since comic fonts do not have them: `♥` (or `<3`) `♡` `💕` `💔` `💋` `★` `☆` `✦` `✨` `💥` `💢` `⚡` `🔥` `💧` `💦` `♨` `💨` `〃` `〰` `🌀` `💤` `♪` `♫` `✿` `🌙` `☀` `♂` `♀` `✖` `○` `→` `←` `↑` `↓` `♦` `♠` `♣`. The editor has a button for each. `♡`, `☆`, `✨`, `♫` and `💦` used to be drawn like their plain versions and now have shapes of their own.
- A word may break after a hyphen (`H-m-m`) when that lets the text be bigger.

A line goes into a bubble only if it fits at a readable size (`bubble_min_size`) in at most eight lines. A bubble too small for it is passed over, and lines left without a bubble are added to the caption; a line that fits no bubble uses up none, so the next line still gets the first free one. Untick `Text too long for a bubble goes to the caption` under `Fine tuning` to always write into the bubbles, however small, and drop the lines left over.

### Look

Each kind of text (bubbles, caption, sound effects) has its own lists; `Look of` chooses which are shown.

| List | What it does |
|---|---|
| Font | Every entry of the list is drawn in its own font. The caption can use the bubble font or its own. |
| Colors | `auto` is white with a dark outline (black text inside a light bubble), or the colors typed under `Fine tuning`. `pink`, `gold`, `candy`, `ice`, `blood`, `neon green`, `black on white` are presets with a second outline, a gradient or a glow where it fits. `from the art` takes the strongest color of the image. |
| Mood | How unruly the letters are. `calm`: straight. `playful`: letters of different sizes, lines tilted. `shout`: more of both. `shaky`: trembling letters. `rough`: ragged, angular edges. `custom`: the sliders under `Fine tuning`. |
| Marks around | Small marks scattered around a caption or an effect: hearts, sparkles, stars, notes, sweat drops, anger marks, motion lines. |

The caption has one more row. `Bubble color` and `Tail` appear only when a bubble shape is chosen:

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
| `text_color`, `stroke_color`, `sfx_color` | `auto` or `#RRGGBB`. Used when the Colors list of that kind of text is `custom`; `text_color` also colors the bubble text when the bubbles' Colors is `custom`. |
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

- A bubble is detected as a flat white, gray or lightly tinted (cream, beige) fill (any brightness above `white_threshold`) enclosed by a dark outline, or a flat near-black fill enclosed by a bright outline, with a smooth, nearly convex shape. Spiky or cloud-shaped bubbles, bubbles without an outline, translucent or gradient bubbles and rectangular caption boxes are not found. Dark bubbles are calibrated on a single example: expect misses.
- Anything else that looks the same gets lettered too, such as a blank sheet of paper on a wall. Use `Bubble numbers` to see what was found and an empty line to skip it.
- A narrow bubble cannot hold a long word at a readable size. Such text goes to the caption.
- When a character fills most of the frame there may be no free place: a drawn bubble is then tried tall and narrow and shrunk, down to half, and put where it covers the least, keeping off heads and bubbles first. The head is taken to be the top quarter of a character, so this fails for a character lying down or upside down.
- Marks around a text are left out where they would land on a character or be cut by the image edge. An effect made of symbols alone gets no marks. A caption with a fixed placement (`top`, a corner) avoids nothing; a bubble drawn for it there is made smaller (down to 0.6 of the size) until it is clear of bubbles and characters, or drawn at 0.72 of the size if it lands on them anyway.
- The place of a sound effect is chosen for an estimated box, so a very wide font can make two effects touch.
- No emoji fallback font.
