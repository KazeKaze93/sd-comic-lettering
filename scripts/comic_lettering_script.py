"""A1111 / Forge / reForge script.

The panel sits under the result gallery. Text can be applied to the images of the last
generation without generating again, or automatically to every new image.
"""
import base64
import io
import json
import os
import sys

import gradio as gr

from modules import scripts

_BASE = scripts.basedir()
if _BASE not in sys.path:
    sys.path.append(_BASE)

from comic_lettering import PLACEMENTS, Style, font_names, font_sample, letter  # noqa: E402

SETTINGS_FILE = os.path.join(_BASE, "user_settings.json")

# Everything except the texts and the two action checkboxes is remembered between sessions.
DEFAULTS = {
    "placement": "auto", "font": "", "spill": True, "uppercase": True, "erase": True,
    "bubble_size": 9.0, "bubble_min_size": 1.5, "free_size": 5.5, "text_color": "auto",
    "stroke_color": "auto", "stroke_width": 0.12, "shadow": 0.5, "jitter": 0.3, "arc": 0.0,
    "rotation": 0.0, "soften": 0.4, "grain": 0.0, "opacity": 1.0, "margin": 0.08,
    "white_threshold": 120, "seed": 0,
}
# Order of the remembered values in the argument list, after enabled, text, caption, numbers.
ORDER = ["placement", "font", "spill", "uppercase", "erase", "bubble_size", "bubble_min_size",
         "free_size", "text_color", "stroke_color", "stroke_width", "shadow", "jitter", "arc",
         "rotation", "soften", "grain", "opacity", "margin", "white_threshold", "seed"]

# Per tab: the images of the last generation before any lettering, and what is needed to save.
STORE = {}
_last_saved = {}


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
    fonts = font_names()
    if values["font"] not in fonts:
        values["font"] = fonts[0]
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


def read_values(values):
    s = dict(DEFAULTS)
    s.update(dict(zip(ORDER, values)))
    s["seed"] = int(s["seed"] or 0)
    s["white_threshold"] = int(s["white_threshold"])
    if not s["font"]:
        s["font"] = font_names()[0]
    return s


def make_style(s):
    return Style(font=s["font"], uppercase=s["uppercase"], text_color=s["text_color"],
                 stroke_color=s["stroke_color"], stroke_width=s["stroke_width"],
                 shadow=s["shadow"], rotation=s["rotation"], jitter=s["jitter"], arc=s["arc"],
                 soften=s["soften"], grain=s["grain"], opacity=s["opacity"],
                 free_size=s["free_size"], bubble_size=s["bubble_size"],
                 bubble_min_size=s["bubble_min_size"], margin=s["margin"], seed=s["seed"])


def run_letter(image, text, caption, numbers, s):
    return letter(image, text, caption=caption, spill=s["spill"], placement=s["placement"],
                  style=make_style(s), erase=s["erase"], white_threshold=s["white_threshold"],
                  numbers=numbers)


def sample_html(s, text=""):
    """The font sample as a small inline image: fixed height, never stretched."""
    buffer = io.BytesIO()
    font_sample(make_style(s), text, size=(420, 56)).save(buffer, format="PNG")
    data = base64.b64encode(buffer.getvalue()).decode("ascii")
    return ("<img src='data:image/png;base64,%s' alt='font sample' "
            "style='height:56px;width:auto;max-width:100%%;border-radius:6px;margin-top:1.4em'>" % data)


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
            panel = gr.Accordion("Comic Lettering", open=True, render=False,
                                 elem_id="comic_lettering_" + self.tab)
            deferred = True
        except TypeError:  # host without deferred rendering: stay in the script list
            panel = gr.Accordion("Comic Lettering", open=False,
                                 elem_id="comic_lettering_" + self.tab)
            deferred = False
        with panel:
            with gr.Row():
                text = gr.Textbox(label="Bubbles", lines=2,
                                  placeholder="One line per bubble, top to bottom. "
                                              "An empty line skips a bubble. *word* = bigger.")
                caption = gr.Textbox(label="Caption", lines=2,
                                     placeholder="Text on the art, outside the bubbles.")
            with gr.Row():
                apply_button = gr.Button("Apply", variant="primary", size="sm", scale=1, min_width=80)
                save_button = gr.Button("Save", size="sm", scale=1, min_width=80)
                enabled = gr.Checkbox(label="Every new image", value=False, scale=2, min_width=140)
                numbers = gr.Checkbox(label="Bubble numbers", value=False, scale=2, min_width=140)
            with gr.Row():
                font = gr.Dropdown(label="Font", choices=fonts, value=s["font"], scale=2, min_width=160)
                placement = gr.Dropdown(label="Caption placement", choices=PLACEMENTS,
                                        value=s["placement"], scale=1, min_width=110)
                sample = gr.HTML(value=sample_html(s), elem_id="comic_lettering_sample_" + self.tab,
                                 scale=3, min_width=200)
            status = gr.HTML(value="")
            with gr.Accordion("Style", open=False):
                with gr.Row():
                    uppercase = gr.Checkbox(label="Uppercase", value=s["uppercase"])
                    erase = gr.Checkbox(label="Erase AI text in bubbles", value=s["erase"])
                    spill = gr.Checkbox(label="Text that does not fit a bubble goes to the caption", value=s["spill"])
                with gr.Row():
                    bubble_size = gr.Slider(label="Bubble: max font size, % of height", minimum=1, maximum=30, step=0.5, value=s["bubble_size"])
                    bubble_min_size = gr.Slider(label="Bubble: min readable font size, % of height", minimum=0.5, maximum=10, step=0.1, value=s["bubble_min_size"])
                    free_size = gr.Slider(label="Caption: font size, % of height", minimum=1, maximum=30, step=0.5, value=s["free_size"])
                with gr.Row():
                    text_color = gr.Textbox(label="Text color (auto or #RRGGBB)", value=s["text_color"])
                    stroke_color = gr.Textbox(label="Caption stroke color (auto or #RRGGBB)", value=s["stroke_color"])
                with gr.Row():
                    stroke_width = gr.Slider(label="Caption stroke width", minimum=0, maximum=0.5, step=0.01, value=s["stroke_width"])
                    shadow = gr.Slider(label="Caption shadow", minimum=0, maximum=1, step=0.05, value=s["shadow"])
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
        by_name = {"placement": placement, "font": font, "spill": spill, "uppercase": uppercase,
                   "erase": erase, "bubble_size": bubble_size, "bubble_min_size": bubble_min_size,
                   "free_size": free_size, "text_color": text_color, "stroke_color": stroke_color,
                   "stroke_width": stroke_width, "shadow": shadow, "jitter": jitter, "arc": arc,
                   "rotation": rotation, "soften": soften, "grain": grain, "opacity": opacity,
                   "margin": margin, "white_threshold": white_threshold, "seed": seed}
        remembered = [by_name[key] for key in ORDER]
        controls = [enabled, text, caption, numbers] + remembered
        # The values live in user_settings.json; keep the host's ui-config.json out of it.
        for component in controls + [sample, status]:
            component.do_not_save_to_config = True
        self.panel = panel
        self.rendered = not deferred
        self.parts = {"apply": apply_button, "save": save_button, "status": status,
                      "sample": sample, "font": font, "text": text, "caption": caption,
                      "numbers": numbers, "remembered": remembered}
        if not deferred:
            self.wire()
        return controls

    def after_component(self, component, **kwargs):
        if self.tab and kwargs.get("elem_id") == self.tab + "_gallery":
            self.gallery = component

    def before_component(self, component, **kwargs):
        # Render the panel between the gallery buttons and the generation info.
        if self.tab and not self.rendered and kwargs.get("elem_id") == "html_info_" + self.tab:
            self.rendered = True
            self.panel.render()
            self.wire()

    def wire(self):
        parts = self.parts
        inputs = [parts["text"], parts["caption"], parts["numbers"]] + parts["remembered"]
        outputs = [parts["status"], parts["sample"]]
        if self.gallery is not None:
            outputs = outputs + [self.gallery]
        parts["apply"].click(fn=self.apply_now, inputs=inputs, outputs=outputs)
        parts["font"].change(fn=self.apply_quiet, inputs=inputs, outputs=outputs)
        parts["save"].click(fn=self.save_now, inputs=[], outputs=[parts["status"]])
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

    def reply(self, message, s, text, caption, images=None):
        result = [message, sample_html(s, text or caption)]
        if self.gallery is not None:
            result.append(images if images is not None else gr.update())
        return result

    def apply_now(self, text, caption, numbers, *values, **options):
        """Letter the images of the last generation again, from their clean copies."""
        s = read_values(values)
        save_settings(s)
        clean = self.store().get("clean") or []
        if not clean:
            quiet = options.get("quiet")
            return self.reply("" if quiet else note("Generate an image first: there is nothing to letter yet."),
                              s, text, caption)
        if not (text or "").strip() and not (caption or "").strip() and not numbers:
            self.store()["results"] = None
            return self.reply(note("No text: showing the clean image."), s, text, caption, list(clean))
        results = []
        info = {}
        for image in clean:
            lettered, info = run_letter(image, text, caption, numbers, s)
            results.append(lettered)
        self.store()["results"] = None if numbers else results
        message = "Bubbles found: %d, filled: %d%s." % (
            info.get("bubbles_found", 0), info.get("bubbles_filled", 0),
            ", plus a caption" if info.get("free_text") else "")
        return self.reply(note(message), s, text, caption, results)

    def apply_quiet(self, *args):
        return self.apply_now(*args, quiet=True)

    def save_now(self):
        store = self.store()
        results = store.get("results")
        if not results:
            return note("Nothing to save: press Apply first.")
        try:
            from modules import images, shared
            paths = []
            for index, image in enumerate(results):
                def pick(name):
                    values = store.get(name) or []
                    return values[index] if index < len(values) else None
                path, _ = images.save_image(image, store.get("outpath"), "", seed=pick("seeds"),
                                            prompt=pick("prompts"), info=pick("infotexts"),
                                            extension=shared.opts.samples_format, suffix="-lettered")
                paths.append(path)
            return note("Saved %d file(s): %s" % (len(paths), os.path.dirname(paths[0])))
        except Exception as error:  # show the reason in the panel instead of a silent failure
            return note("Save failed: %s" % error)

    def process(self, p, *args):
        STORE[self.tab or ("img2img" if self.is_img2img else "txt2img")] = {
            "clean": [], "results": None, "outpath": getattr(p, "outpath_samples", None)}

    def postprocess_image(self, p, pp, enabled=False, text="", caption="", numbers=False, *values):
        store = self.store()
        store.setdefault("clean", []).append(pp.image.copy())
        if not enabled or (not (text or "").strip() and not (caption or "").strip()):
            return
        s = read_values(values)
        save_settings(s)
        pp.image, _ = run_letter(pp.image, text, caption, False, s)

    def postprocess(self, p, processed, *args):
        store = self.store()
        first = getattr(processed, "index_of_first_image", 0)
        store["infotexts"] = list(getattr(processed, "infotexts", []) or [])[first:]
        store["seeds"] = list(getattr(processed, "all_seeds", []) or [])
        store["prompts"] = list(getattr(processed, "all_prompts", []) or [])
