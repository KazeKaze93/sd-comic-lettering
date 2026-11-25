"""ComfyUI node: place it between VAE Decode and Save Image."""
import numpy as np
import torch
from PIL import Image

from .comic_lettering import PLACEMENTS, Style, font_names, letter


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

        return {"required": {
            "image": ("IMAGE",),
            "bubbles": ("STRING", {"multiline": True, "default": ""}),
            "caption": ("STRING", {"multiline": True, "default": ""}),
            "sfx": ("STRING", {"multiline": True, "default": ""}),
            "show_numbers": ("BOOLEAN", {"default": False}),
            "spill_to_caption": ("BOOLEAN", {"default": True}),
            "placement": (PLACEMENTS,),
            "font": (font_names(),),
            "uppercase": ("BOOLEAN", {"default": True}),
            "bubble_size": num(9.0, 1.0, 30.0, 0.5),
            "bubble_min_size": num(1.5, 0.5, 10.0, 0.1),
            "free_size": num(5.5, 1.0, 30.0, 0.5),
            "text_color": ("STRING", {"default": "auto"}),
            "stroke_color": ("STRING", {"default": "auto"}),
            "stroke_width": num(0.12, 0.0, 0.5, 0.01),
            "shadow": num(0.5, 0.0, 1.0, 0.05),
            "jitter": num(0.3, 0.0, 1.0, 0.05),
            "arc": num(0.0, -1.0, 1.0, 0.05),
            "rotation": num(0.0, -45.0, 45.0, 0.5),
            "soften": num(0.4, 0.0, 3.0, 0.1),
            "grain": num(0.0, 0.0, 1.0, 0.05),
            "opacity": num(1.0, 0.1, 1.0, 0.05),
            "margin": num(0.08, 0.0, 0.3, 0.01),
            "erase_ai_text": ("BOOLEAN", {"default": True}),
            "white_threshold": ("INT", {"default": 120, "min": 40, "max": 255}),
            "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF}),
            "sfx_font": (sfx_fonts(),),
            "sfx_size": num(7.0, 1.0, 30.0, 0.5),
            "sfx_color": ("STRING", {"default": "auto"}),
            "sfx_tilt": num(15.0, 0.0, 45.0, 1.0),
            "sfx_opacity": num(0.95, 0.1, 1.0, 0.05),
            "sfx_seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF}),
        }}

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "run"
    CATEGORY = "image/postprocessing"

    def run(self, image, bubbles, caption, sfx, show_numbers, spill_to_caption, placement, font,
            uppercase, bubble_size, bubble_min_size, free_size, text_color, stroke_color,
            stroke_width, shadow, jitter, arc, rotation, soften, grain, opacity, margin,
            erase_ai_text, white_threshold, seed, sfx_font, sfx_size, sfx_color, sfx_tilt,
            sfx_opacity, sfx_seed):
        if not bubbles.strip() and not caption.strip() and not sfx.strip() and not show_numbers:
            return (image,)
        style = Style(font=font, uppercase=uppercase, text_color=text_color,
                      stroke_color=stroke_color, stroke_width=stroke_width, shadow=shadow,
                      rotation=rotation, jitter=jitter, arc=arc, soften=soften, grain=grain,
                      opacity=opacity, free_size=free_size, bubble_size=bubble_size,
                      bubble_min_size=bubble_min_size, margin=margin, seed=seed,
                      sfx_font=sfx_font, sfx_size=sfx_size, sfx_color=sfx_color,
                      sfx_tilt=sfx_tilt, sfx_opacity=sfx_opacity, sfx_seed=sfx_seed)
        frames = []
        for frame in image:
            array = (frame[..., :3].cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
            result, _ = letter(Image.fromarray(array), bubbles, caption=caption,
                               spill=spill_to_caption, placement=placement, style=style,
                               erase=erase_ai_text, white_threshold=white_threshold,
                               numbers=show_numbers, sfx=sfx)
            frames.append(torch.from_numpy(np.asarray(result).astype(np.float32) / 255.0))
        return (torch.stack(frames),)


NODE_CLASS_MAPPINGS = {"ComicLettering": ComicLettering}
NODE_DISPLAY_NAME_MAPPINGS = {"ComicLettering": "Comic Lettering"}
