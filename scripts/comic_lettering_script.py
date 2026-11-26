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
# The host runs this file again on "Reload UI" but keeps imported packages. Drop ours,
# so a reload also picks up changes in comic_lettering/ without restarting the process.
for _name in [n for n in sys.modules if n == "comic_lettering" or n.startswith("comic_lettering.")]:
    del sys.modules[_name]

from comic_lettering import PLACEMENTS, Style, font_names, letter, list_fonts  # noqa: E402
from comic_lettering.render import (BUBBLE_SHAPES, BUBBLE_THEMES, EXTRAS, MOODS,  # noqa: E402
                                    PALETTES, TAILS)

SETTINGS_FILE = os.path.join(_BASE, "user_settings.json")
SAME_FONT = "same as bubbles"
SFX_FONT = "Bangers"
LOOKS = ["Bubbles", "Caption", "Sound effects"]
FONT_KEYS = ["font", "caption_font", "sfx_font"]
# Marks that are drawn as shapes; the buttons insert them, since a keyboard cannot.
SYMBOLS = [(u"\u2665", "heart"), (u"\u2605", "star"), (u"\u2726", "sparkle"), (u"\u266a", "note"),
           (u"\U0001F4A2", "anger"), (u"\U0001F4A7", "drop")]
HINT = "Generate an image, type the text, press Apply. Lists and sliders apply at once."

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


def describe(info):
    """What was done with an image: (message, is it a warning)."""
    message = "Bubbles found: %d, filled: %d%s%s." % (
        info.get("bubbles_found", 0), info.get("bubbles_filled", 0),
        ", plus a caption" if info.get("free_text") else "",
        ", sound effects: %d" % info["sfx"] if info.get("sfx") else "")
    if info.get("characters") is False:
        return (message + " Character detection is off (no ultralytics or no person_yolov8*-seg.pt"
                " found), so text may land on a character.", True)
    return message, False


def note(message, warning=False):
    """The status line: a colored dot and one sentence."""
    if not message:
        return ""
    color = "#e0a030" if warning else "#4c9be8"
    return ("<p style='margin:0.45em 0;line-height:1.35'><span style='display:inline-block;width:0.6em;"
            "height:0.6em;border-radius:50%%;background:%s;margin-right:0.5em'></span>%s</p>"
            % (color, message))


def heading(title):
    return gr.HTML("<p style='margin:0.9em 0 0.1em;font-weight:600;opacity:0.85'>%s</p>" % title)


def bind(component, events, **kwargs):
    """Attach a handler to the first of the named events this Gradio version has."""
    for name in events:
        listener = getattr(component, name, None)
        if callable(listener):
            try:
                listener(**kwargs)
                return True
            except Exception:  # an event the host does not support: try the next one
                continue
    return False


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
        pid = "comic_lettering_" + self.tab
        try:
            panel = gr.Accordion("Comic Lettering", open=False, render=False, elem_id=pid)
            deferred = True
        except TypeError:  # host without deferred rendering: stay in the script list
            panel = gr.Accordion("Comic Lettering", open=False, elem_id=pid)
            deferred = False
        c = {}  # name -> component, for the remembered settings

        def pick(key, label, choices, **kwargs):
            c[key] = gr.Dropdown(label=label, choices=list(choices), value=s[key], min_width=110, **kwargs)

        def slide(key, label, low, high, step):
            c[key] = gr.Slider(label=label, minimum=low, maximum=high, step=step, value=s[key])

        with panel:
            # Status and the two actions on the image.
            with gr.Row():
                with gr.Column(scale=5, min_width=220):
                    status = gr.HTML(value=note(HINT))
                clean_button = gr.Button("Show original", size="sm", scale=1, min_width=120)
                apply_button = gr.Button("Apply", variant="primary", size="sm", scale=1, min_width=110)
            # The three texts, each with its own small actions.
            with gr.Row():
                with gr.Column(min_width=170):
                    text = gr.Textbox(label="Bubbles", lines=3, max_lines=8, elem_id=pid + "_bubbles",
                                      info="One line per bubble; an empty line skips one.")
                    with gr.Row():
                        clear_text = gr.Button("Clear", size="sm", min_width=60)
                        numbers = gr.Checkbox(label="Show numbers", value=False, min_width=120)
                with gr.Column(min_width=170):
                    caption = gr.Textbox(label="Caption", lines=3, max_lines=8, elem_id=pid + "_caption",
                                         info="Text on the art, outside the bubbles.")
                    with gr.Row():
                        clear_caption = gr.Button("Clear", size="sm", min_width=60)
                with gr.Column(min_width=170):
                    sfx = gr.Textbox(label="Sound effects", lines=3, max_lines=8, elem_id=pid + "_sfx",
                                     info="One per line: SLAP, THUD x3.")
                    with gr.Row():
                        clear_sfx = gr.Button("Clear", size="sm", min_width=60)
                        shuffle_button = gr.Button("Move", size="sm", min_width=60)
            with gr.Row():
                with gr.Column(scale=4, min_width=220):
                    gr.HTML("<p style='margin:0.5em 0;opacity:0.7'>Insert a mark at the cursor. "
                            "*word* makes a word bigger.</p>")
                symbol_buttons = [(gr.Button(symbol, size="sm", scale=1, min_width=36), symbol)
                                  for symbol, _ in SYMBOLS]
            # The look of one kind of text at a time.
            look = gr.Radio(label="Look of", choices=LOOKS, value=LOOKS[0])
            with gr.Column(visible=True) as look_bubbles:
                with gr.Row():
                    pick("font", "Font", fonts)
                    pick("bubble_colors", "Colors", PALETTES)
                    pick("bubble_mood", "Mood", MOODS)
            with gr.Column(visible=False) as look_caption:
                with gr.Row():
                    pick("caption_font", "Font", [SAME_FONT] + fonts)
                    pick("caption_colors", "Colors", PALETTES)
                    pick("caption_mood", "Mood", MOODS)
                    pick("caption_extras", "Marks around", EXTRAS)
                with gr.Row():
                    drawn = s["caption_bubble"] != "none"
                    pick("placement", "Position", PLACEMENTS)
                    pick("caption_bubble", "Put in a bubble", BUBBLE_SHAPES)
                    pick("caption_bubble_theme", "Bubble color", BUBBLE_THEMES, visible=drawn)
                    pick("caption_tail", "Tail", TAILS, visible=drawn)
            with gr.Column(visible=False) as look_sfx:
                with gr.Row():
                    pick("sfx_font", "Font", fonts)
                    pick("sfx_colors", "Colors", PALETTES)
                    pick("sfx_mood", "Mood", MOODS)
                    pick("sfx_extras", "Marks around", EXTRAS)
            gr.HTML(value=fonts_css(), visible=True, elem_id="comic_lettering_fonts_css_" + self.tab)
            # Clicked by the page script when this tab comes into view: txt2img and img2img
            # share one settings file, and each panel must show what the other one saved.
            sync_button = gr.Button("sync", visible=False, elem_id=pid + "_sync")
            enabled = gr.Checkbox(label="Letter every new image while it is generated", value=False)
            with gr.Accordion("Fine tuning", open=False):
                heading("All text")
                with gr.Row():
                    c["uppercase"] = gr.Checkbox(label="Capital letters", value=s["uppercase"])
                    slide("soften", "Soften the edges, px", 0, 3, 0.1)
                    slide("grain", "Uneven ink", 0, 1, 0.05)
                with gr.Row():
                    slide("arc", "Bend into an arc", -1, 1, 0.05)
                    slide("rotation", "Tilt, degrees", -45, 45, 0.5)
                    slide("opacity", "Opacity", 0.1, 1, 0.05)
                heading("Bubbles")
                with gr.Row():
                    c["erase"] = gr.Checkbox(label="Erase the letters the model drew", value=s["erase"])
                    c["spill"] = gr.Checkbox(label="Text too long for a bubble goes to the caption", value=s["spill"])
                with gr.Row():
                    slide("bubble_size", "Largest font, % of image height", 1, 30, 0.5)
                    slide("bubble_min_size", "Smallest readable font, %", 0.5, 10, 0.1)
                    slide("margin", "Gap to the bubble edge", 0, 0.3, 0.01)
                with gr.Row():
                    slide("white_threshold", "Darkest fill still seen as a bubble", 40, 255, 1)
                heading("Caption")
                with gr.Row():
                    slide("free_size", "Font size, % of image height", 1, 30, 0.5)
                    slide("stroke_width", "Outline width", 0, 0.5, 0.01)
                    slide("shadow", "Shadow", 0, 1, 0.05)
                with gr.Row():
                    c["text_color"] = gr.Textbox(label="Text color with Colors: auto (#RRGGBB or auto)", value=s["text_color"])
                    c["stroke_color"] = gr.Textbox(label="Outline color with Colors: auto (#RRGGBB or auto)", value=s["stroke_color"])
                heading("Sound effects")
                with gr.Row():
                    slide("sfx_size", "Font size, % of image height", 1, 30, 0.5)
                    slide("sfx_tilt", "Largest tilt, degrees", 0, 45, 1)
                    slide("sfx_opacity", "Opacity", 0.1, 1, 0.05)
                with gr.Row():
                    c["sfx_color"] = gr.Textbox(label="Color with Colors: auto (#RRGGBB or auto)", value=s["sfx_color"])
                    c["sfx_seed"] = gr.Number(label="Arrangement number (Move raises it)", value=s["sfx_seed"], precision=0)
                heading("Mood: custom")
                with gr.Row():
                    slide("jitter", "Letters wobble", 0, 1, 0.05)
                    slide("size_jitter", "Letters differ in size", 0, 1, 0.05)
                    slide("rough", "Ragged edges", 0, 1, 0.05)
                with gr.Row():
                    slide("line_tilt", "Lines tilt, degrees", 0, 15, 0.5)
                    slide("line_shift", "Lines shift sideways", 0, 1, 0.05)
                    slide("line_spacing", "Line spacing", 0.7, 1.6, 0.02)
                with gr.Row():
                    c["seed"] = gr.Number(label="Wobble pattern number", value=s["seed"], precision=0)
                with gr.Row():
                    reset_button = gr.Button("Reset the look to defaults", size="sm", min_width=160)
                    keep_fonts = gr.Checkbox(label="Keep the fonts", value=True, min_width=120)
        remembered = [c[key] for key in ORDER]
        controls = [enabled, text, caption, numbers, sfx] + remembered
        # The values live in user_settings.json; keep the host's ui-config.json out of it.
        for component in controls + [status, look, keep_fonts]:
            component.do_not_save_to_config = True
        self.panel = panel
        self.rendered = not deferred
        self.parts = {
            "apply": apply_button, "clean": clean_button, "shuffle": shuffle_button,
            "reset": reset_button, "keep_fonts": keep_fonts, "symbols": symbol_buttons, "sync": sync_button,
            "clear": [(clear_text, text), (clear_caption, caption), (clear_sfx, sfx)],
            "status": status, "text": text, "caption": caption, "sfx": sfx, "numbers": numbers,
            "remembered": remembered, "sfx_seed": c["sfx_seed"], "look": look,
            "looks": [look_bubbles, look_caption, look_sfx], "caption_bubble": c["caption_bubble"],
            "drawn": [c["caption_bubble_theme"], c["caption_tail"]], "by_key": c,
        }
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
            bind(component, ["change"], fn=self.generation_status, inputs=[],
                 outputs=[self.parts["status"]], show_progress=False)

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
        parts["clean"].click(fn=self.show_clean, inputs=[], outputs=outputs)
        parts["shuffle"].click(fn=self.move_sfx, inputs=inputs, outputs=outputs + [parts["sfx_seed"]])
        # Everything else applies by itself: lists and checkboxes when they change, sliders
        # when released, text when the field is left.
        quiet = dict(fn=self.apply_quiet, inputs=inputs, outputs=outputs)
        edited = dict(fn=self.apply_edited, inputs=inputs, outputs=outputs)
        bind(parts["numbers"], ["change"], **quiet)
        for key in ORDER:
            component = parts["by_key"][key]
            if isinstance(component, (gr.Dropdown, gr.Checkbox)):
                bind(component, ["change"], **quiet)
            elif isinstance(component, gr.Slider):
                bind(component, ["release"], **quiet)
            else:
                bind(component, ["blur", "submit"], **quiet)
        for field in (parts["text"], parts["caption"], parts["sfx"]):
            bind(field, ["blur"], **edited)
        for button, field in parts["clear"]:
            button.click(fn=lambda: "", inputs=[], outputs=[field], show_progress=False)
        panel_id = "comic_lettering_" + self.tab
        for button, symbol in parts["symbols"]:
            button.click(fn=None, inputs=[], outputs=[],
                         _js="function(){ sdclInsert('%s', '%s'); return []; }" % (panel_id, symbol))
        bind(parts["look"], ["change"], fn=self.show_look, inputs=[parts["look"]], outputs=parts["looks"],
             show_progress=False)
        bind(parts["caption_bubble"], ["change"], fn=self.show_drawn, inputs=[parts["caption_bubble"]],
             outputs=parts["drawn"], show_progress=False)
        font_lists = [parts["by_key"][key] for key in FONT_KEYS]
        parts["reset"].click(fn=self.reset_options, inputs=[parts["keep_fonts"]] + font_lists,
                             outputs=parts["remembered"])
        def saved():
            return [load_settings()[key] for key in ORDER]

        parts["sync"].click(fn=saved, inputs=[], outputs=parts["remembered"], show_progress=False)
        # ui-config and the build-time values are stale after a browser reload: refresh
        # the remembered values from the settings file on every page load.
        try:
            root = gr.context.Context.root_block
            if root is not None:
                root.load(fn=saved, inputs=None, outputs=parts["remembered"], show_progress=False)
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
        """Letter the images of the last generation again, from their clean copies.

        quiet: called by a list, a slider or a field rather than the Apply button, so
        it must do nothing when nothing changed or there is nothing to draw (a page
        load restores the lists and would otherwise replace the gallery image).
        edited: called on leaving a text field; emptying the fields then takes the
        lettering off.
        """
        s = read_values(values)
        save_settings(s)
        sfx = sfx or ""
        quiet = options.get("quiet")
        store = self.store()
        clean = store.get("clean") or []
        empty = not (text or "").strip() and not (caption or "").strip() and not sfx.strip() and not numbers
        signature = (text or "", caption or "", bool(numbers), sfx, tuple(sorted(s.items())))
        if quiet:
            if not clean or signature == store.get("applied"):
                return self.reply(gr.update())
            if empty and not (options.get("edited") and store.get("applied")):
                return self.reply(gr.update())
        if not clean:
            return self.reply(note("Generate an image first: there is nothing to letter yet."))
        store["applied"] = signature
        if empty:
            return self.reply(note("No text: showing the original image."), list(clean))
        results = []
        info = {}
        for image in clean:
            lettered, info = run_letter(image, text, caption, numbers, s, sfx)
            results.append(lettered)
        return self.reply(note(*describe(info)), results)

    def apply_quiet(self, *args):
        return self.apply_now(*args, quiet=True)

    def apply_edited(self, *args):
        return self.apply_now(*args, quiet=True, edited=True)

    def show_clean(self):
        """Show the images as they were generated; the texts stay in their fields."""
        store = self.store()
        clean = store.get("clean") or []
        if not clean:
            return self.reply(note("Nothing to show: generate an image first."))
        store["applied"] = None
        return self.reply(note("Showing the original image. Apply puts the text back."), list(clean))

    def show_look(self, which):
        return [gr.update(visible=(which == name)) for name in LOOKS]

    def show_drawn(self, shape):
        return [gr.update(visible=(shape != "none"))] * 2

    def reset_options(self, keep_fonts=False, *fonts):
        """Put every remembered option back to its default; the fonts stay if asked."""
        values = dict(DEFAULTS)
        if keep_fonts:
            values.update(dict(zip(FONT_KEYS, fonts)))
        values = clean_values(values)
        save_settings(values)
        return [values[key] for key in ORDER]

    def generation_status(self):
        return self.store().get("message") or note("Image ready: type the text and press Apply.")

    def move_sfx(self, text, caption, numbers, sfx, *values):
        """Put the sound effects somewhere else: raise the arrangement number and apply."""
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
        message, warning = describe(info)
        store["message"] = note("Lettered while generating. " + message, warning)
