"""A1111 / Forge / reForge script: letters every generated image before it is saved."""
import sys

import gradio as gr

from modules import scripts

_BASE = scripts.basedir()
if _BASE not in sys.path:
    sys.path.append(_BASE)

from comic_lettering import MODES, PLACEMENTS, Style, font_names, letter  # noqa: E402


class ComicLetteringScript(scripts.Script):
    def title(self):
        return "Comic Lettering"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        fonts = font_names()
        with gr.Accordion("Comic Lettering", open=False):
            enabled = gr.Checkbox(label="Enable", value=False)
            text = gr.Textbox(label="Text", lines=4,
                              placeholder="Blank line = next bubble. *word* = emphasis. "
                                          "\"-\" = skip a bubble. \"2: text\" = bubble number 2. "
                                          "\"#\" alone = show bubble numbers.")
            with gr.Row():
                mode = gr.Dropdown(label="Mode", choices=MODES, value="auto")
                placement = gr.Dropdown(label="Free text placement", choices=PLACEMENTS, value="auto")
                font = gr.Dropdown(label="Font", choices=fonts, value=fonts[0])
            with gr.Row():
                uppercase = gr.Checkbox(label="Uppercase", value=True)
                erase = gr.Checkbox(label="Erase AI text in bubbles", value=True)
            with gr.Row():
                bubble_size = gr.Slider(label="Bubble: max font size, % of height", minimum=1, maximum=30, step=0.5, value=9)
                free_size = gr.Slider(label="Free text: font size, % of height", minimum=1, maximum=30, step=0.5, value=5.5)
            bubble_min_size = gr.Slider(label="Bubble: min readable font size, % of height (mode auto: smaller bubbles are passed over)", minimum=0.5, maximum=10, step=0.1, value=1.8)
            with gr.Row():
                text_color = gr.Textbox(label="Text color (auto or #RRGGBB)", value="auto")
                stroke_color = gr.Textbox(label="Stroke color (auto or #RRGGBB)", value="auto")
            with gr.Row():
                stroke_width = gr.Slider(label="Stroke width (free text)", minimum=0, maximum=0.5, step=0.01, value=0.12)
                shadow = gr.Slider(label="Shadow (free text)", minimum=0, maximum=1, step=0.05, value=0.5)
            with gr.Row():
                jitter = gr.Slider(label="Letter jitter", minimum=0, maximum=1, step=0.05, value=0.3)
                arc = gr.Slider(label="Arc", minimum=-1, maximum=1, step=0.05, value=0)
                rotation = gr.Slider(label="Rotation", minimum=-45, maximum=45, step=0.5, value=0)
            with gr.Row():
                soften = gr.Slider(label="Soften, px", minimum=0, maximum=3, step=0.1, value=0.4)
                grain = gr.Slider(label="Ink grain", minimum=0, maximum=1, step=0.05, value=0)
                opacity = gr.Slider(label="Opacity", minimum=0.1, maximum=1, step=0.05, value=1)
            with gr.Row():
                margin = gr.Slider(label="Bubble margin", minimum=0, maximum=0.3, step=0.01, value=0.08)
                white_threshold = gr.Slider(label="Bubble min brightness", minimum=120, maximum=255, step=1, value=180)
                seed = gr.Number(label="Jitter seed", value=0, precision=0)
        return [enabled, text, mode, placement, font, uppercase, erase, bubble_size, free_size,
                text_color, stroke_color, stroke_width, shadow, jitter, arc, rotation, soften,
                grain, opacity, margin, white_threshold, seed, bubble_min_size]

    def postprocess_image(self, p, pp, enabled, text, mode, placement, font, uppercase, erase,
                          bubble_size, free_size, text_color, stroke_color, stroke_width, shadow,
                          jitter, arc, rotation, soften, grain, opacity, margin, white_threshold,
                          seed, bubble_min_size=1.8):
        if not enabled or not (text or "").strip():
            return
        style = Style(font=font, uppercase=uppercase, text_color=text_color,
                      stroke_color=stroke_color, stroke_width=stroke_width, shadow=shadow,
                      rotation=rotation, jitter=jitter, arc=arc, soften=soften, grain=grain,
                      opacity=opacity, free_size=free_size, bubble_size=bubble_size,
                      bubble_min_size=bubble_min_size, margin=margin, seed=int(seed or 0))
        pp.image, _ = letter(pp.image, text, mode=mode, placement=placement, style=style,
                             erase=erase, white_threshold=int(white_threshold))
