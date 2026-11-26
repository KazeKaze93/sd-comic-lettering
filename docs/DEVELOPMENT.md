# Development

- [Setting up](#setting-up)
- [Building the editor](#building-the-editor)
- [Running without a host](#running-without-a-host)
- [Conventions](#conventions)
- [Recipes](#recipes)
- [Checking a change](#checking-a-change)
- [Installing from a clean clone](#installing-from-a-clean-clone)

## Setting up

Clone the repository into the host you work with:

```
<webui>/extensions/sd-comic-lettering        AUTOMATIC1111 / Forge / reForge
<ComfyUI>/custom_nodes/sd-comic-lettering    ComfyUI
```

To work on both hosts from one checkout, clone into one and link the folder into the other (a junction on Windows, a symlink elsewhere):

```powershell
New-Item -ItemType Junction -Path "<ComfyUI>\custom_nodes\sd-comic-lettering" -Target "<webui>\extensions\sd-comic-lettering"
```

The Python side has no build step and no dependencies beyond what the hosts ship. Read [ARCHITECTURE.md](ARCHITECTURE.md) first: it says which file belongs to which layer.

## Building the editor

The editor needs a current Node LTS (20.19 or newer), only to build.

```
cd ui
npm install
npm run build
```

`npm run build` type-checks (`tsc -b`) and writes `ui/dist`. **Commit `ui/dist` together with the sources**: users install with `git clone` and have no Node.

`npm run build:watch` rebuilds on every save. After a build, refresh the host page; the server puts a fresh `?v=` on every asset, so a plain refresh is enough in most browsers. When in doubt, hard-refresh (Ctrl+F5).

`npm run dev` starts Vite's dev server, but the page needs the `/comic_lettering/*` routes, so it is only useful behind a proxy to a running host. Building is simpler.

## Running without a host

**The core** runs anywhere:

```
python -m comic_lettering in.png out.png --text "Hi!" --caption "Later..."
```

**The editor** needs only the routes. A stand-in server is a few lines with FastAPI (any A1111-family venv has it):

```python
import os, sys
sys.path.insert(0, REPO)
import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from comic_lettering import web

app = FastAPI()
web.register(app)                      # no saver: Save writes into saved/

@app.get("/file={path:path}")          # what the A1111 family serves ui/dist through
async def files(path: str):
    prefix = "extensions/%s/" % web.EXTENSION
    return FileResponse(os.path.join(REPO, path[len(prefix):]))

uvicorn.run(app, port=8198)
```

Open `http://127.0.0.1:8198/comic_lettering/ui` and use `Own image`. Opened directly, with no host page around it, the editor hides what only a host gives meaning to: the list of sources, the `Auto` chip, `To gallery`, `Close` and the `Automatic mode` section.

Point `web.SETTINGS_FILE` somewhere else first if you do not want the stand-in to write your real `user_settings.json`.

## Conventions

| Where | Rule |
|---|---|
| Python | Runs on Python 3.9: `Dict` / `List` / `Optional` from `typing`, no `X \| Y`, no `match`. Type comments (`# type: (...) -> ...`) in the core. |
| `comic_lettering/` | Imports no host module at import time. `core.py` does not import `web.py`. |
| `javascript/comic_lettering.js` | ES5 style, like the host's scripts: `var`, `function`, string concatenation. No arrow functions, no template literals. |
| `comfy_web/`, `ui/` | Modern JavaScript and TypeScript. |
| `ui/` | Colors through the `cl-*` Tailwind tokens (`ui/tailwind.config.js`), never raw hex in components. Controls from `components/controls.tsx` before writing a new one. No new runtime dependency without a reason: there are three. |
| Store | Actions are read with `useStore.getState()`; an effect that calls them has `[]` as its dependencies. |
| Text in the UI | Plain words for what a control does. No jargon: "Marks around", not "Decorations preset". |
| Comments | Say why, not what. |
| Sizes | Relative to the image in `Style`; pixels only inside a scene. |

## Recipes

### Add a mark

1. `render.py`: write the shape as polygons on a unit square (see `_more_shapes()`; a dict entry cuts out of what is already drawn) and add it to `SHAPES`.
2. `render.py`: map a character to it in `SYMBOLS`.
3. `web.py`: add the character to `SYMBOLS`, the list of characters drawn as shapes.
4. `web.py`: add it to `MARK_GROUPS` under the group it belongs to. A mark that is missing there is named on the server's error stream and does not appear on the bars of the text fields.
5. Optional: add an entry to `EXTRAS` to offer it as marks around a text.

No change in the editor is needed: it draws the buttons from the `marks` of `/options`, with the mask the renderer makes of the shape.

### Add a color preset

Add a dict to `render.PALETTES`: `fill`, `stroke`, `ink`, and optionally `fill2` (gradient), `outer` (second outline), `glow`. It appears in all three `Colors` lists and in the ComfyUI node.

### Add a mood

Add a dict of the six mood options to `render.MOODS`.

### Add an option to the look

1. `render.py`: add it to `Style.__init__` with its default.
2. Use it where the text is drawn.
3. `web.py`: add it to `DEFAULTS` (and to `CHOICES` if it is a list).
4. `comfy_nodes.py`: add it to `INPUT_TYPES`. Anything not in `DIRECT` is copied onto the `Style` by name.
5. `ui/src/components/SidePanel.tsx`: add it to the section of the text it belongs to. A list goes into the section's look; a slider into the spec array behind its `More…` (`BUBBLES`, `CAPTION`, `EFFECTS`), or into `ALL_TEXT` when every kind of text shares it. A slider spec has a short `label` and a `hint` that says it in full.
6. `__main__.py`: nothing, `--opt name=value` already reaches it.

Adding an input changes the node's widget order: add new inputs **at the end** of `required`, or saved workflows shift their values.

### Add a bubble template

`ui/src/geometry.ts`: add the name to `BubbleShape` in `types.ts` and to `BUBBLE_SHAPES`, and give `radius()` or `bubbleShapes()` its outline. The server needs nothing: it only sees polygons.

### Change what counts as a bubble

`detect.is_bubble()`. Every threshold there was measured on real generations and the comments say against what. Check a change on images that have bubbles **and** on images with look-alikes (faces, paper, window panes): a looser test finds more of both.

## Checking a change

There is no test suite. A change is checked by what it produces.

**Core changes that should not change the picture** (refactors, speed): letter the same images before and after and compare the pixels.

```python
import numpy as np
before = np.asarray(letter_on_main(image))      # run from a checkout of main
after = np.asarray(letter(image, ...)[0])
print((before != after).any(axis=2).sum(), "pixels differ")
```

**Core changes that should change it**: look at the result, at more than one image size, with and without a character mask.

**Editor changes**: build, hard-refresh, and try the change in a host. Stale bundles are the usual cause of "it did not work".

**Both hosts**: a change in `web.py`, `core.py` or `ui/` reaches both. Check the node too: its output must equal what the editor showed.

**Before a commit**: `npm run build` exits with 0, `ui/dist` is rebuilt and staged, `git status --short` shows only what was meant.

## Installing from a clean clone

What a user gets is what `git clone` gives. To check that nothing depends on files that exist only on a developer's machine:

```
git clone https://github.com/KazeKaze93/sd-comic-lettering.git
```

1. **Core**: `python -m comic_lettering in.png out.png --text Hi` from the clone, with only `numpy`, `scipy` and `Pillow` available.
2. **ComfyUI**: start ComfyUI with the clone in `custom_nodes`; `GET /object_info/ComicLettering` lists the node, `GET /comic_lettering/ui` answers 200, and every asset address in that page answers 200.
3. **A1111 family**: with the clone in `extensions`, the tool icon appears under `Generate` and `GET /comic_lettering/options` answers 200.

Files that must be in the clone for this to work: `ui/dist/` (the built editor) and `fonts/bundled/` (the default fonts). Files that must not be: `user_settings.json`, anything in `fonts/` outside `bundled/`.
