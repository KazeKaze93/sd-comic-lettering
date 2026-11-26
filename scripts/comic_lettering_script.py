"""A1111 / Forge / reForge script.

The editor is a React page (ui/) shown over the host page; comic_lettering/web.py serves it.
All this script puts on the host page is the button that opens it. It also keeps the images
of the last generation as they were, and letters every new image when that is switched on.
"""
import os
import sys

import gradio as gr

from modules import script_callbacks, scripts, shared

_BASE = scripts.basedir()
if _BASE not in sys.path:
    sys.path.append(_BASE)
# The host runs this file again on "Reload UI" but keeps imported packages. Drop ours,
# so a reload also picks up changes in comic_lettering/ without restarting the process.
for _name in [n for n in sys.modules if n == "comic_lettering" or n.startswith("comic_lettering.")]:
    del sys.modules[_name]

from comic_lettering import draw, web  # noqa: E402


def save_folder():
    """Where the editor's Save button writes: the host's folder for saved images."""
    folder = getattr(shared.opts, "outdir_save", "") or os.path.join("outputs", "comic-lettering")
    return os.path.abspath(folder)


def register(_demo, app):
    web.register(app, save_folder)


script_callbacks.on_app_started(register)


class ComicLetteringScript(scripts.Script):
    gallery = None
    tab = None
    placed = False

    def title(self):
        return "Comic Lettering"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        self.tab = "img2img" if is_img2img else "txt2img"
        return []

    def after_component(self, component, **kwargs):
        if self.tab == "txt2img" and kwargs.get("elem_id") == "txt2img_gallery":
            self.gallery = component

    def before_component(self, component, **kwargs):
        # The button goes between the gallery buttons and the generation info of txt2img.
        if self.tab != "txt2img" or self.placed or kwargs.get("elem_id") != "html_info_txt2img":
            return
        self.placed = True
        with gr.Row(elem_id="comic_lettering_bar"):
            open_button = gr.Button("Comic Lettering", elem_id="comic_lettering_open", size="sm")
            # Clicked by the page script when the editor sends its image to the gallery;
            # the session id comes through _js, the textbox only gives it a slot.
            session = gr.Textbox(visible=False)
            send_button = gr.Button("to gallery", visible=False, elem_id="comic_lettering_to_gallery")
        for part in (open_button, session, send_button):
            part.do_not_save_to_config = True
        open_button.click(fn=None, inputs=[], outputs=[], _js="function(){ sdclOpen('txt2img'); return []; }")
        if self.gallery is not None:
            send_button.click(fn=self.to_gallery, inputs=[session], outputs=[self.gallery],
                              _js="function(){ return [window.sdclSession || '']; }", show_progress=False)

    def to_gallery(self, session_id):
        image = web.result_image(session_id)
        return [image] if image is not None else gr.update()

    def process(self, p, *args):
        web.LAST_CLEAN[self.tab or ("img2img" if self.is_img2img else "txt2img")] = []

    def postprocess_image(self, p, pp, *args):
        tab = self.tab or ("img2img" if self.is_img2img else "txt2img")
        web.LAST_CLEAN.setdefault(tab, []).append(pp.image.copy())
        auto = web.load_auto()
        if not auto["enabled"] or not (auto["text"].strip() or auto["caption"].strip() or auto["sfx"].strip()):
            return
        scene = web.make_scene(pp.image, auto["text"], auto["caption"], False, web.load_settings(), auto["sfx"])
        pp.image = draw(pp.image, scene)
