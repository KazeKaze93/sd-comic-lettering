"""A1111 / Forge / reForge script: letters every generated image before it is saved."""
import io
import json
import os
import sys

import gradio as gr

from modules import scripts

_BASE = scripts.basedir()
if _BASE not in sys.path:
    sys.path.append(_BASE)

from comic_lettering import MODES, PLACEMENTS, Style, font_names, letter  # noqa: E402

SETTINGS_FILE = os.path.join(_BASE, "user_settings.json")

# Everything except Enable and Text is remembered between sessions.
DEFAULTS = {
    "mode": "auto", "placement": "auto", "font": "", "uppercase": True, "erase": True,
    "bubble_size": 9.0, "free_size": 5.5, "text_color": "auto", "stroke_color": "auto",
    "stroke_width": 0.12, "shadow": 0.5, "jitter": 0.3, "arc": 0.0, "rotation": 0.0,
    "soften": 0.4, "grain": 0.0, "opacity": 1.0, "margin": 0.08, "white_threshold": 120,
    "seed": 0, "bubble_min_size": 1.5,
}
# Order of the remembered values in the script's argument list, after enabled and text.
ORDER = ["mode", "placement", "font", "uppercase", "erase", "bubble_size", "free_size",
         "text_color", "stroke_color", "stroke_width", "shadow", "jitter", "arc", "rotation",
         "soften", "grain", "opacity", "margin", "white_threshold", "seed", "bubble_min_size"]

_last_saved = {}


def load_settings():
    values = dict(DEFAULTS)
    try:
        with io.open(SETTINGS_FILE, encoding="utf-8") as handle:
            saved = json.load(handle)
        for key in DEFAULTS:
            if key in saved and isinstance(saved[key], type(DEFAULTS[key])):
                values[key] = saved[key]
            elif key in saved and isinstance(DEFAULTS[key], float) and isinstance(saved[key], int):
                values[key] = float(saved[key])
    except (IOError, OSError, ValueError):
        pass
    fonts = font_names()
    if values["font"] not in fonts:
        values["font"] = fonts[0]
    if values["mode"] not in MODES:
        values["mode"] = DEFAULTS["mode"]
    if values["placement"] not in PLACEMENTS:
        values["placement"] = DEFAULTS["placement"]
    return values


def save_settings(values):
    global _last_saved
    if values == _last_saved:
        return
    try:
        with io.open(SETTINGS_FILE, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(values, indent=2, sort_keys=True))
        _last_saved = dict(values)
    except (IOError, OSError):
        pass


class ComicLetteringScript(scripts.Script):
    def title(self):
        return "Comic Lettering"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        fonts = font_names()
        s = load_settings()
        with gr.Accordion("Comic Lettering", open=False):
            enabled = gr.Checkbox(label="Enable", value=False)
            text = gr.Textbox(label="Text", lines=4,
                              placeholder="Blank line = next bubble. *word* = emphasis. "
                                          "\"-\" = skip a bubble. \"2: text\" = bubble number 2. "
                                          "\"#\" alone = show bubble numbers.")
            with gr.Row():
                mode = gr.Dropdown(label="Mode", choices=MODES, value=s["mode"])
                placement = gr.Dropdown(label="Free text placement", choices=PLACEMENTS, value=s["placement"])
                font = gr.Dropdown(label="Font", choices=fonts, value=s["font"])
            with gr.Row():
                uppercase = gr.Checkbox(label="Uppercase", value=s["uppercase"])
                erase = gr.Checkbox(label="Erase AI text in bubbles", value=s["erase"])
            with gr.Row():
                bubble_size = gr.Slider(label="Bubble: max font size, % of height", minimum=1, maximum=30, step=0.5, value=s["bubble_size"])
                free_size = gr.Slider(label="Free text: font size, % of height", minimum=1, maximum=30, step=0.5, value=s["free_size"])
            bubble_min_size = gr.Slider(label="Bubble: min readable font size, % of height (mode auto: smaller bubbles are passed over)", minimum=0.5, maximum=10, step=0.1, value=s["bubble_min_size"])
            with gr.Row():
                text_color = gr.Textbox(label="Text color (auto or #RRGGBB)", value=s["text_color"])
                stroke_color = gr.Textbox(label="Stroke color (auto or #RRGGBB)", value=s["stroke_color"])
            with gr.Row():
                stroke_width = gr.Slider(label="Stroke width (free text)", minimum=0, maximum=0.5, step=0.01, value=s["stroke_width"])
                shadow = gr.Slider(label="Shadow (free text)", minimum=0, maximum=1, step=0.05, value=s["shadow"])
            with gr.Row():
                jitter = gr.Slider(label="Letter jitter", minimum=0, maximum=1, step=0.05, value=s["jitter"])
                arc = gr.Slider(label="Arc", minimum=-1, maximum=1, step=0.05, value=s["arc"])
                rotation = gr.Slider(label="Rotation", minimum=-45, maximum=45, step=0.5, value=s["rotation"])
            with gr.Row():
                soften = gr.Slider(label="Soften, px", minimum=0, maximum=3, step=0.1, value=s["soften"])
                grain = gr.Slider(label="Ink grain", minimum=0, maximum=1, step=0.05, value=s["grain"])
                opacity = gr.Slider(label="Opacity", minimum=0.1, maximum=1, step=0.05, value=s["opacity"])
            with gr.Row():
                margin = gr.Slider(label="Bubble margin", minimum=0, maximum=0.3, step=0.01, value=s["margin"])
                white_threshold = gr.Slider(label="Bubble min brightness", minimum=40, maximum=255, step=1, value=s["white_threshold"])
                seed = gr.Number(label="Jitter seed", value=s["seed"], precision=0)
        remembered = [mode, placement, font, uppercase, erase, bubble_size, free_size, text_color,
                      stroke_color, stroke_width, shadow, jitter, arc, rotation, soften, grain,
                      opacity, margin, white_threshold, seed, bubble_min_size]
        # The values above are fixed when the UI is built. Refresh them on every page
        # load too, so a browser reload shows the last used settings, not the startup ones.
        try:
            root = gr.context.Context.root_block
            if root is not None:
                root.load(fn=lambda: [load_settings()[key] for key in ORDER], inputs=None,
                          outputs=remembered, show_progress=False)
        except Exception:  # the page-load refresh is optional; never break the UI over it
            pass
        return [enabled, text] + remembered

    def postprocess_image(self, p, pp, enabled, text, *values):
        if not enabled or not (text or "").strip():
            return
        s = dict(DEFAULTS)
        s.update(dict(zip(ORDER, values)))
        s["seed"] = int(s["seed"] or 0)
        s["white_threshold"] = int(s["white_threshold"])
        save_settings(s)
        style = Style(font=s["font"], uppercase=s["uppercase"], text_color=s["text_color"],
                      stroke_color=s["stroke_color"], stroke_width=s["stroke_width"],
                      shadow=s["shadow"], rotation=s["rotation"], jitter=s["jitter"], arc=s["arc"],
                      soften=s["soften"], grain=s["grain"], opacity=s["opacity"],
                      free_size=s["free_size"], bubble_size=s["bubble_size"],
                      bubble_min_size=s["bubble_min_size"], margin=s["margin"], seed=s["seed"])
        pp.image, _ = letter(pp.image, text, mode=s["mode"], placement=s["placement"], style=style,
                             erase=s["erase"], white_threshold=s["white_threshold"])
