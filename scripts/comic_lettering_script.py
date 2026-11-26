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


def save_like_host(image, parameters, tab):
    """Save the editor's image the way the host saves a generation of that tab: into the
    same folder, with the host's file name pattern, numbering, format and subfolders, and
    with the generation parameters of the source image kept. Returns the file's path."""
    from modules import images

    opts = shared.opts
    folder = getattr(opts, "outdir_samples", "") or getattr(opts, "outdir_%s_samples" % tab, "")         or os.path.join("outputs", "%s-images" % tab)
    saved = images.save_image(image, folder, "", info=parameters, extension=getattr(opts, "samples_format", "png"),
                              suffix="-lettered")
    path = saved[0] if isinstance(saved, (tuple, list)) else saved
    return os.path.abspath(path or folder)


def register(_demo, app):
    web.register(app, save_like_host)


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
        if self.tab and kwargs.get("elem_id") == self.tab + "_gallery":
            self.gallery = component

    def before_component(self, component, **kwargs):
        # Nothing of this shows on the page: the way into the editor is the icon the page
        # script puts in the row of tools under Generate. What is made here is the hidden
        # button that carries the editor's image into the tab's gallery.
        if not self.tab or self.placed or kwargs.get("elem_id") != "html_info_" + self.tab:
            return
        self.placed = True
        with gr.Row(elem_id="comic_lettering_bar_" + self.tab, elem_classes=["sdcl-hidden"]):
            # Clicked by the page script when the editor sends its image to the gallery;
            # the session id comes through _js, the textbox only gives it a slot.
            session = gr.Textbox(visible=False)
            send_button = gr.Button("to gallery", visible=False, elem_id="comic_lettering_to_gallery_" + self.tab)
        for part in (session, send_button):
            part.do_not_save_to_config = True
        if self.gallery is not None:
            send_button.click(fn=self.to_gallery, inputs=[session], outputs=[self.gallery],
                              _js="function(){ return [window.sdclSession || '']; }", show_progress=False)

    def to_gallery(self, session_id):
        image = web.result_image(session_id)
        return [image] if image is not None else gr.update()

    def process(self, p, *args):
        web.begin_generation(self.tab or ("img2img" if self.is_img2img else "txt2img"))

    def postprocess_image(self, p, pp, *args):
        tab = self.tab or ("img2img" if self.is_img2img else "txt2img")
        web.LAST_CLEAN.setdefault(tab, []).append(pp.image.copy())
        auto = web.load_auto()
        if not auto["enabled"] or not (auto["text"].strip() or auto["caption"].strip() or auto["sfx"].strip()):
            return
        scene = web.make_scene(pp.image, auto["text"], auto["caption"], False, web.load_settings(), auto["sfx"])
        pp.image = draw(pp.image, scene)
