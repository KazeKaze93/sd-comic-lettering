"""A1111 / Forge / reForge script.

The panel sits under the result gallery. Text can be applied to the images of the last
generation without generating again, or automatically to every new image.
"""
import io
import json
import os
import sys

import gradio as gr

from modules import scripts

_BASE = scripts.basedir()
if _BASE not in sys.path:
    sys.path.append(_BASE)

from comic_lettering import PLACEMENTS, Style, font_names, letter, list_fonts  # noqa: E402
from comic_lettering.render import (BUBBLE_SHAPES, BUBBLE_THEMES, EXTRAS, MOODS,  # noqa: E402
                                    PALETTES, TAILS)

SETTINGS_FILE = os.path.join(_BASE, "user_settings.json")
SAME_FONT = "same as bubbles"
SFX_FONT = "Bangers"
FIELDS = ["Bubbles", "Caption", "SFX"]
# Marks that are drawn as shapes; the buttons insert them, since a keyboard cannot.
SYMBOLS = [(u"\u2665", "heart"), (u"\u2605", "star"), (u"\u2726", "sparkle"), (u"\u266a", "note"),
           (u"\U0001F4A2", "anger"), (u"\U0001F4A7", "drop")]

# Everything except the texts and the two action checkboxes is remembered between sessions.
DEFAULTS = {
    "placement": "auto", "font": "", "spill": True, "uppercase": True, "erase": True,
    "bubble_size": 9.0, "bubble_min_size": 1.5, "free_size": 5.5, "text_color": "auto",
    "stroke_color": "auto", "stroke_width": 0.12, "shadow": 0.5, "jitter": 0.3, "arc": 0.0,
    "rotation": 0.0, "soften": 0.4, "grain": 0.0, "opacity": 1.0, "margin": 0.08,
    "white_threshold": 120, "seed": 0,
    "sfx_font": "", "sfx_size": 7.0, "sfx_color": "auto", "sfx_tilt": 15.0, "sfx_opacity": 0.95,
    "sfx_seed": 0,
    "caption_font": SAME_FONT, "bubble_colors": "auto", "caption_colors": "auto",
    "sfx_colors": "auto", "bubble_mood": "calm", "caption_mood": "calm", "sfx_mood": "shout",
    "caption_extras": "none", "sfx_extras": "none", "caption_bubble": "none",
    "caption_bubble_theme": "light", "caption_tail": "none", "size_jitter": 0.0,
    "line_tilt": 0.0, "line_shift": 0.0, "rough": 0.0, "line_spacing": 1.08,
}
# Order of the remembered values in the argument list, after enabled, text, caption,
# numbers and the SFX text.
ORDER = ["placement", "font", "spill", "uppercase", "erase", "bubble_size", "bubble_min_size",
         "free_size", "text_color", "stroke_color", "stroke_width", "shadow", "jitter", "arc",
         "rotation", "soften", "grain", "opacity", "margin", "white_threshold", "seed",
         "sfx_font", "sfx_size", "sfx_color", "sfx_tilt", "sfx_opacity", "sfx_seed",
         "caption_font", "bubble_colors", "caption_colors", "sfx_colors", "bubble_mood",
         "caption_mood", "sfx_mood", "caption_extras", "sfx_extras", "caption_bubble",
         "caption_bubble_theme", "caption_tail", "size_jitter", "line_tilt", "line_shift",
         "rough", "line_spacing"]
# Lists a saved value must belong to; anything else falls back to the default.
CHOICES = {
    "placement": PLACEMENTS, "bubble_colors": list(PALETTES), "caption_colors": list(PALETTES),
    "sfx_colors": list(PALETTES), "bubble_mood": list(MOODS), "caption_mood": list(MOODS),
    "sfx_mood": list(MOODS), "caption_extras": list(EXTRAS), "sfx_extras": list(EXTRAS),
    "caption_bubble": BUBBLE_SHAPES, "caption_bubble_theme": BUBBLE_THEMES,
    "caption_tail": list(TAILS),
}

# Per tab: the images of the last generation before any lettering, and what is needed to save.
STORE = {}
_last_saved = {}


def clean_values(values):
    """Make every value usable: known fonts, known list entries, the right number types."""
    fonts = font_names()
    if values.get("font") not in fonts:
        values["font"] = fonts[0]
    if values.get("sfx_font") not in fonts:
        values["sfx_font"] = SFX_FONT if SFX_FONT in fonts else fonts[0]
    if values.get("caption_font") not in fonts:
        values["caption_font"] = SAME_FONT
    for key, allowed in CHOICES.items():
        if values.get(key) not in allowed:
            values[key] = DEFAULTS[key]
    for key in ("seed", "sfx_seed", "white_threshold"):
        values[key] = int(values.get(key) or 0)
    return values


def load_settings():
    values = dict(DEFAULTS)
    try:
        with io.open(SETTINGS_FILE, encoding="utf-8") as handle:
            saved = json.load(handle)
        for key in DEFAULTS:
            if key not in saved:
                continue
            if isinstance(saved[key], type(DEFAULTS[key])):
                values[key] = saved[key]
            elif isinstance(DEFAULTS[key], float) and isinstance(saved[key], int):
                values[key] = float(saved[key])
    except (IOError, OSError, ValueError):
        pass
    return clean_values(values)


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


def read_values(values):
    s = dict(DEFAULTS)
    s.update(dict(zip(ORDER, values)))
    return clean_values(s)


def make_style(s):
    style = Style()
    for key, value in s.items():
        if key in ("placement", "spill", "erase", "white_threshold"):
            continue  # arguments of letter(), not style options
        if not hasattr(style, key):
            continue
        setattr(style, key, value)
    if s["caption_font"] == SAME_FONT:
        style.caption_font = ""
    return style


def run_letter(image, text, caption, numbers, s, sfx=""):
    return letter(image, text, caption=caption, spill=s["spill"], placement=s["placement"],
                  style=make_style(s), erase=s["erase"], white_threshold=s["white_threshold"],
                  numbers=numbers, sfx=sfx)


def fonts_css():
    """CSS that draws every entry of the font lists in its own font.

    Fonts inside the web UI folder are fetched through the host's file route; system
    fonts are picked up by name from the browser's machine.
    """
    try:
        from urllib.parse import quote
    except ImportError:  # Python 2 never runs this; keeps linters quiet on old hosts
        from urllib import quote
    app_dir = os.path.abspath(os.getcwd())
    rules = []
    for index, (name, path) in enumerate(list_fonts().items()):
        family = "sdcl-font-%d" % index
        full = os.path.abspath(path)
        if full.lower().startswith(app_dir.lower() + os.sep):
            relative = os.path.relpath(full, app_dir).replace(os.sep, "/")
            source = "url('file=%s?%d')" % (quote(relative), int(os.path.getmtime(full)))
        else:
            source = "local('%s')" % name.replace("'", "")
        value = name.replace("\\", "\\\\").replace('"', '\\"')
        rules.append("@font-face{font-family:'%s';src:%s;font-display:swap}" % (family, source))
        rules.append('li.item[data-value="%s"]{font-family:\'%s\',sans-serif;font-size:17px;'
                     'line-height:1.5}' % (value, family))
    return "<style>%s</style>" % "".join(rules)


def insert_symbol(where, mark, bubbles, caption, sfx):
    """Append a mark to the chosen field."""
    values = [bubbles or "", caption or "", sfx or ""]
    index = FIELDS.index(where) if where in FIELDS else 2
    current = values[index]
    values[index] = current + ("" if not current or current.endswith((" ", "\n")) else " ") + mark
    return values


def describe(info):
    """One line on what was done with an image."""
    message = "Bubbles found: %d, filled: %d%s%s." % (
        info.get("bubbles_found", 0), info.get("bubbles_filled", 0),
        ", plus a caption" if info.get("free_text") else "",
        ", SFX: %d" % info["sfx"] if info.get("sfx") else "")
    if info.get("characters") is False:
        message += (" Character detection is off (no ultralytics or no person_yolov8*-seg.pt found),"
                    " so text may land on a character.")
    return message


def note(message):
    return "<p style='margin:0.3em 0;opacity:0.8'>%s</p>" % message


class ComicLetteringScript(scripts.Script):
    panel = None
    gallery = None
    rendered = False
    tab = None

    def title(self):
        return "Comic Lettering"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        self.tab = "img2img" if is_img2img else "txt2img"
        fonts = font_names()
        s = load_settings()
        try:
            panel = gr.Accordion("Comic Lettering", open=False, render=False,
                                 elem_id="comic_lettering_" + self.tab)
            deferred = True
        except TypeError:  # host without deferred rendering: stay in the script list
            panel = gr.Accordion("Comic Lettering", open=False,
                                 elem_id="comic_lettering_" + self.tab)
            deferred = False
        c = {}  # name -> component, for the remembered settings

        def pick(key, label, choices, **kwargs):
            c[key] = gr.Dropdown(label=label, choices=list(choices), value=s[key], min_width=120, **kwargs)

        def slide(key, label, low, high, step):
            c[key] = gr.Slider(label=label, minimum=low, maximum=high, step=step, value=s[key])

        with panel:
            with gr.Row():
                text = gr.Textbox(label="Bubbles", lines=2, max_lines=6,
                                  placeholder="One line per bubble, top to bottom. "
                                              "An empty line skips a bubble. *word* = bigger.")
                caption = gr.Textbox(label="Caption", lines=2, max_lines=6,
                                     placeholder="Text on the art, outside the bubbles.")
                sfx = gr.Textbox(label="SFX", lines=2, max_lines=6,
                                 placeholder="Sound effects, one per line: SLAP, THUD, FAP x5. "
                                             "Drawn big and tilted in an empty spot. "
                                             u"♥ ★ ♪ work as symbols.")
            with gr.Row():
                clear_buttons = [gr.Button("Clear " + name.lower(), size="sm", min_width=80) for name in FIELDS]
            with gr.Row():
                target = gr.Radio(label="Insert a symbol into", choices=FIELDS, value="SFX", scale=3,
                                  min_width=300)
                with gr.Column(scale=2, min_width=240):  # a column, so the buttons keep their height
                    with gr.Row():
                        symbol_buttons = [(gr.Button(symbol, size="sm", min_width=36), symbol)
                                          for symbol, _ in SYMBOLS]
            with gr.Row():
                apply_button = gr.Button("Apply", variant="primary", size="sm", min_width=80)
                clean_button = gr.Button("Remove text", size="sm", min_width=80)
                shuffle_button = gr.Button("Move SFX", size="sm", min_width=80)
                reset_button = gr.Button("Reset options", size="sm", min_width=80)
            with gr.Row():
                enabled = gr.Checkbox(label="Every new image", value=False, min_width=160)
                numbers = gr.Checkbox(label="Bubble numbers", value=False, min_width=160)
            status = gr.HTML(value="")
            with gr.Row():
                pick("font", "Bubbles: font", fonts)
                pick("bubble_colors", "Bubbles: colors", PALETTES)
                pick("bubble_mood", "Bubbles: mood", MOODS)
            with gr.Row():
                pick("caption_font", "Caption: font", [SAME_FONT] + fonts)
                pick("caption_colors", "Caption: colors", PALETTES)
                pick("caption_mood", "Caption: mood", MOODS)
                pick("caption_extras", "Caption: extras", EXTRAS)
            with gr.Row():
                pick("placement", "Caption: placement", PLACEMENTS)
                pick("caption_bubble", "Caption: bubble", BUBBLE_SHAPES)
                pick("caption_bubble_theme", "Drawn bubble", BUBBLE_THEMES)
                pick("caption_tail", "Bubble tail", TAILS)
            with gr.Row():
                pick("sfx_font", "SFX: font", fonts)
                pick("sfx_colors", "SFX: colors", PALETTES)
                pick("sfx_mood", "SFX: mood", MOODS)
                pick("sfx_extras", "SFX: extras", EXTRAS)
            gr.HTML(value=fonts_css(), visible=True, elem_id="comic_lettering_fonts_css_" + self.tab)
            with gr.Accordion("Fine tuning", open=False):
                with gr.Row():
                    c["uppercase"] = gr.Checkbox(label="Uppercase", value=s["uppercase"])
                    c["erase"] = gr.Checkbox(label="Erase AI text in bubbles", value=s["erase"])
                    c["spill"] = gr.Checkbox(label="Text that does not fit a bubble goes to the caption", value=s["spill"])
                with gr.Row():
                    slide("bubble_size", "Bubble: max font size, % of height", 1, 30, 0.5)
                    slide("bubble_min_size", "Bubble: min readable font size, % of height", 0.5, 10, 0.1)
                    slide("margin", "Bubble margin", 0, 0.3, 0.01)
                with gr.Row():
                    slide("free_size", "Caption: font size, % of height", 1, 30, 0.5)
                    slide("stroke_width", "Caption stroke width", 0, 0.5, 0.01)
                    slide("shadow", "Caption shadow", 0, 1, 0.05)
                with gr.Row():
                    slide("sfx_size", "SFX: size, % of height", 1, 30, 0.5)
                    slide("sfx_tilt", "SFX: max tilt, degrees", 0, 45, 1)
                    slide("sfx_opacity", "SFX opacity", 0.1, 1, 0.05)
                gr.HTML(note("Colors \"auto\" use the three fields below; \"auto\" in a field means white with a dark outline."))
                with gr.Row():
                    c["text_color"] = gr.Textbox(label="Text color (auto or #RRGGBB)", value=s["text_color"])
                    c["stroke_color"] = gr.Textbox(label="Caption stroke color (auto or #RRGGBB)", value=s["stroke_color"])
                    c["sfx_color"] = gr.Textbox(label="SFX color (auto or #RRGGBB)", value=s["sfx_color"])
                gr.HTML(note("Mood \"custom\" uses the six sliders below."))
                with gr.Row():
                    slide("jitter", "Letter jitter", 0, 1, 0.05)
                    slide("size_jitter", "Letter size variety", 0, 1, 0.05)
                    slide("rough", "Rough edges", 0, 1, 0.05)
                with gr.Row():
                    slide("line_tilt", "Line tilt, degrees", 0, 15, 0.5)
                    slide("line_shift", "Line shift", 0, 1, 0.05)
                    slide("line_spacing", "Line spacing", 0.7, 1.6, 0.02)
                with gr.Row():
                    slide("arc", "Arc", -1, 1, 0.05)
                    slide("rotation", "Rotation", -45, 45, 0.5)
                    slide("opacity", "Opacity", 0.1, 1, 0.05)
                with gr.Row():
                    slide("soften", "Soften, px", 0, 3, 0.1)
                    slide("grain", "Ink grain", 0, 1, 0.05)
                    slide("white_threshold", "Bubble min brightness", 40, 255, 1)
                with gr.Row():
                    c["seed"] = gr.Number(label="Jitter seed", value=s["seed"], precision=0)
                    c["sfx_seed"] = gr.Number(label="SFX placement (Move SFX changes it)", value=s["sfx_seed"], precision=0)
        remembered = [c[key] for key in ORDER]
        controls = [enabled, text, caption, numbers, sfx] + remembered
        # The values live in user_settings.json; keep the host's ui-config.json out of it.
        for component in controls + [status, target]:
            component.do_not_save_to_config = True
        self.panel = panel
        self.rendered = not deferred
        self.parts = {"apply": apply_button, "clean": clean_button, "shuffle": shuffle_button,
                      "reset": reset_button, "clear": clear_buttons, "symbols": symbol_buttons,
                      "target": target, "status": status, "text": text, "caption": caption, "sfx": sfx,
                      "numbers": numbers, "remembered": remembered, "sfx_seed": c["sfx_seed"],
                      "instant": [c[key] for key in ORDER if isinstance(c[key], gr.Dropdown)]}
        if not deferred:
            self.wire()
        return controls

    def after_component(self, component, **kwargs):
        if not self.tab:
            return
        if kwargs.get("elem_id") == self.tab + "_gallery":
            self.gallery = component
        elif kwargs.get("elem_id") == "generation_info_" + self.tab and self.rendered:
            # This hidden box changes after every generation: refresh the status line
            # then, so it never describes the previous image.
            try:
                component.change(fn=self.generation_status, inputs=[], outputs=[self.parts["status"]],
                                 show_progress=False)
            except Exception:  # optional; never break the UI over it
                pass

    def before_component(self, component, **kwargs):
        # Render the panel between the gallery buttons and the generation info.
        if self.tab and not self.rendered and kwargs.get("elem_id") == "html_info_" + self.tab:
            self.rendered = True
            self.panel.render()
            self.wire()

    def wire(self):
        parts = self.parts
        inputs = [parts["text"], parts["caption"], parts["numbers"], parts["sfx"]] + parts["remembered"]
        outputs = [parts["status"]]
        if self.gallery is not None:
            outputs = outputs + [self.gallery]
        parts["apply"].click(fn=self.apply_now, inputs=inputs, outputs=outputs)
        for dropdown in parts["instant"]:  # every list re-applies at once
            dropdown.change(fn=self.apply_quiet, inputs=inputs, outputs=outputs)
        parts["shuffle"].click(fn=self.move_sfx, inputs=inputs, outputs=outputs + [parts["sfx_seed"]])
        parts["clean"].click(fn=self.show_clean, inputs=[], outputs=outputs)
        parts["reset"].click(fn=self.reset_options, inputs=[], outputs=parts["remembered"])
        fields = [parts["text"], parts["caption"], parts["sfx"]]
        for button, field in zip(parts["clear"], fields):
            button.click(fn=lambda: "", inputs=[], outputs=[field], show_progress=False)
        for button, symbol in parts["symbols"]:
            button.click(fn=lambda where, a, b, c, mark=symbol: insert_symbol(where, mark, a, b, c),
                         inputs=[parts["target"]] + fields, outputs=fields, show_progress=False)
        # ui-config and the build-time values are stale after a browser reload: refresh
        # the remembered values from the settings file on every page load.
        try:
            root = gr.context.Context.root_block
            if root is not None:
                root.load(fn=lambda: [load_settings()[key] for key in ORDER], inputs=None,
                          outputs=parts["remembered"], show_progress=False)
        except Exception:  # optional; never break the UI over it
            pass

    def store(self):
        return STORE.setdefault(self.tab or ("img2img" if self.is_img2img else "txt2img"), {})

    def reply(self, message, images=None):
        result = [message]
        if self.gallery is not None:
            result.append(images if images is not None else gr.update())
        return result

    def apply_now(self, text, caption, numbers, sfx, *values, **options):
        """Letter the images of the last generation again, from their clean copies."""
        s = read_values(values)
        save_settings(s)
        sfx = sfx or ""
        quiet = options.get("quiet")
        clean = self.store().get("clean") or []
        empty = not (text or "").strip() and not (caption or "").strip() and not sfx.strip() and not numbers
        if quiet and (empty or not clean):
            # A list changed (also when the page loads and restores the settings) but
            # there is nothing to draw: leave the gallery and the status alone.
            return self.reply(gr.update())
        if not clean:
            return self.reply(note("Generate an image first: there is nothing to letter yet."))
        if empty:
            return self.reply(note("No text: showing the clean image."), list(clean))
        results = []
        info = {}
        for image in clean:
            lettered, info = run_letter(image, text, caption, numbers, s, sfx)
            results.append(lettered)
        return self.reply(note(describe(info)), results)

    def show_clean(self):
        """Take the lettering off: show the images as they were generated."""
        clean = self.store().get("clean") or []
        if not clean:
            return self.reply(note("Nothing to restore: generate an image first."))
        return self.reply(note("Text removed: showing the clean image."), list(clean))

    def reset_options(self):
        """Put every remembered option back to its default."""
        values = clean_values(dict(DEFAULTS))
        save_settings(values)
        return [values[key] for key in ORDER]

    def generation_status(self):
        return self.store().get("message", "")

    def apply_quiet(self, *args):
        return self.apply_now(*args, quiet=True)

    def move_sfx(self, text, caption, numbers, sfx, *values):
        """Put the sound effects somewhere else: bump the placement number and apply."""
        values = list(values)
        position = ORDER.index("sfx_seed")
        moved = int((values[position] if position < len(values) else 0) or 0) + 1
        if position < len(values):
            values[position] = moved
        return self.apply_now(text, caption, numbers, sfx, *values) + [moved]

    def process(self, p, *args):
        STORE[self.tab or ("img2img" if self.is_img2img else "txt2img")] = {"clean": [], "message": ""}

    def postprocess_image(self, p, pp, enabled=False, text="", caption="", numbers=False, sfx="",
                          *values):
        store = self.store()
        store.setdefault("clean", []).append(pp.image.copy())
        sfx = sfx or ""
        if not enabled or (not (text or "").strip() and not (caption or "").strip() and not sfx.strip()):
            return
        s = read_values(values)
        save_settings(s)
        pp.image, info = run_letter(pp.image, text, caption, False, s, sfx)
        store["message"] = note("Applied during generation. " + describe(info))
