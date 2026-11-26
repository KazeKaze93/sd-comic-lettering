"""ComfyUI node: place it between VAE Decode and Save Image."""
import json

import numpy as np
import torch
from PIL import Image

from .comic_lettering import (BUBBLE_SHAPES, BUBBLE_THEMES, EXTRAS, MOODS, PALETTES, PLACEMENTS,
                              TAILS, Style, arrange, draw, font_names, web)

SAME_FONT = "same as bubbles"
# Inputs that are arguments of letter() rather than Style options.
DIRECT = ("image", "bubbles", "caption", "sfx", "show_numbers", "spill_to_caption", "placement",
          "erase_ai_text", "white_threshold", "layout")


def node_tab(unique_id):
    """The name under which the editor finds the image a node last worked on."""
    return "node:%s" % unique_id


def read_layout(layout):
    """What the editor placed and drew by hand, from the node's hidden field: (pins, regions)."""
    try:
        data = json.loads(layout) if layout else {}
    except (TypeError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    pins = data.get("pins") if isinstance(data.get("pins"), dict) else {}
    regions = data.get("regions") if isinstance(data.get("regions"), list) else []
    return pins, regions


def sfx_fonts():
    """Font names with the default effects font first."""
    names = font_names()
    if "Bangers" in names:
        names.remove("Bangers")
        names.insert(0, "Bangers")
    return names


class ComicLettering(object):
    @classmethod
    def INPUT_TYPES(cls):
        def num(default, lo, hi, step):
            return ("FLOAT", {"default": default, "min": lo, "max": hi, "step": step})

        def text(default="auto"):
            return ("STRING", {"default": default})

        fonts = font_names()
        return {"required": {
            "image": ("IMAGE",),
            "bubbles": ("STRING", {"multiline": True, "default": ""}),
            "caption": ("STRING", {"multiline": True, "default": ""}),
            "sfx": ("STRING", {"multiline": True, "default": ""}),
            "show_numbers": ("BOOLEAN", {"default": False}),
            "spill_to_caption": ("BOOLEAN", {"default": True}),
            "font": (fonts,),
            "bubble_colors": (list(PALETTES),),
            "bubble_mood": (list(MOODS),),
            "caption_font": ([SAME_FONT] + fonts,),
            "caption_colors": (list(PALETTES),),
            "caption_mood": (list(MOODS),),
            "caption_extras": (list(EXTRAS),),
            "placement": (PLACEMENTS,),
            "caption_bubble": (BUBBLE_SHAPES,),
            "caption_bubble_theme": (BUBBLE_THEMES,),
            "caption_tail": (list(TAILS),),
            "sfx_font": (sfx_fonts(),),
            "sfx_colors": (list(PALETTES),),
            "sfx_mood": (["shout"] + [name for name in MOODS if name != "shout"],),
            "sfx_extras": (list(EXTRAS),),
            "uppercase": ("BOOLEAN", {"default": True}),
            "erase_ai_text": ("BOOLEAN", {"default": True}),
            "bubble_size": num(9.0, 1.0, 30.0, 0.5),
            "bubble_min_size": num(1.5, 0.5, 10.0, 0.1),
            "margin": num(0.08, 0.0, 0.3, 0.01),
            "free_size": num(5.5, 1.0, 30.0, 0.5),
            "stroke_width": num(0.12, 0.0, 0.5, 0.01),
            "shadow": num(0.5, 0.0, 1.0, 0.05),
            "sfx_size": num(7.0, 1.0, 30.0, 0.5),
            "sfx_tilt": num(15.0, 0.0, 45.0, 1.0),
            "sfx_opacity": num(0.95, 0.1, 1.0, 0.05),
            "text_color": text(),
            "stroke_color": text(),
            "sfx_color": text(),
            "jitter": num(0.3, 0.0, 1.0, 0.05),
            "size_jitter": num(0.0, 0.0, 1.0, 0.05),
            "rough": num(0.0, 0.0, 1.0, 0.05),
            "line_tilt": num(0.0, 0.0, 15.0, 0.5),
            "line_shift": num(0.0, 0.0, 1.0, 0.05),
            "line_spacing": num(1.08, 0.7, 1.6, 0.02),
            "arc": num(0.0, -1.0, 1.0, 0.05),
            "rotation": num(0.0, -45.0, 45.0, 0.5),
            "opacity": num(1.0, 0.1, 1.0, 0.05),
            "soften": num(0.4, 0.0, 3.0, 0.1),
            "grain": num(0.0, 0.0, 1.0, 0.05),
            "white_threshold": ("INT", {"default": 120, "min": 40, "max": 255}),
            "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF}),
            "sfx_seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF}),
        }, "optional": {
            # Written by the editor (the Open editor button): what was placed and drawn by hand.
            "layout": ("STRING", {"default": "", "multiline": False}),
        }, "hidden": {"unique_id": "UNIQUE_ID"}}

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "run"
    CATEGORY = "image/postprocessing"

    def run(self, image, bubbles, caption, sfx, show_numbers, spill_to_caption, placement,
            erase_ai_text, white_threshold, layout="", unique_id=None, **options):
        pins, regions = read_layout(layout)
        if unique_id is not None and len(image):
            # The editor letters the image this node last saw, as it came in.
            tab = node_tab(unique_id)
            web.begin_generation(tab)
            first = (image[0][..., :3].cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
            web.LAST_CLEAN[tab].append(Image.fromarray(first))
        if (not bubbles.strip() and not caption.strip() and not sfx.strip() and not show_numbers
                and not any(isinstance(region, dict) and region.get("text") for region in regions)):
            return (image,)
        style = Style()
        for key, value in options.items():
            if hasattr(style, key):
                setattr(style, key, value)
        if style.caption_font == SAME_FONT:
            style.caption_font = ""
        frames = []
        for frame in image:
            array = (frame[..., :3].cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
            picture = Image.fromarray(array)
            scene = arrange(picture, bubbles, caption=caption, spill=spill_to_caption, placement=placement,
                            style=style, erase=erase_ai_text, white_threshold=white_threshold,
                            numbers=show_numbers, sfx=sfx, pins=pins, regions=regions)
            result = draw(picture, scene)
            frames.append(torch.from_numpy(np.asarray(result).astype(np.float32) / 255.0))
        return (torch.stack(frames),)


NODE_CLASS_MAPPINGS = {"ComicLettering": ComicLettering}
NODE_DISPLAY_NAME_MAPPINGS = {"ComicLettering": "Comic Lettering"}
