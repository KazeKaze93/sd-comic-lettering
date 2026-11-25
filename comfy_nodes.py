"""ComfyUI node: place it between VAE Decode and Save Image."""
import numpy as np
import torch
from PIL import Image

from .comic_lettering import MODES, PLACEMENTS, Style, font_names, letter


class ComicLettering(object):
    @classmethod
    def INPUT_TYPES(cls):
        def num(default, lo, hi, step):
            return ("FLOAT", {"default": default, "min": lo, "max": hi, "step": step})

        return {"required": {
            "image": ("IMAGE",),
            "text": ("STRING", {"multiline": True, "default": ""}),
            "mode": (MODES,),
            "placement": (PLACEMENTS,),
            "font": (font_names(),),
            "uppercase": ("BOOLEAN", {"default": True}),
            "bubble_size": num(9.0, 1.0, 30.0, 0.5),
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
            "white_threshold": ("INT", {"default": 180, "min": 120, "max": 255}),
            "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF}),
        }}

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "run"
    CATEGORY = "image/postprocessing"

    def run(self, image, text, mode, placement, font, uppercase, bubble_size, free_size,
            text_color, stroke_color, stroke_width, shadow, jitter, arc, rotation, soften,
            grain, opacity, margin, erase_ai_text, white_threshold, seed):
        if not text.strip():
            return (image,)
        style = Style(font=font, uppercase=uppercase, text_color=text_color,
                      stroke_color=stroke_color, stroke_width=stroke_width, shadow=shadow,
                      rotation=rotation, jitter=jitter, arc=arc, soften=soften, grain=grain,
                      opacity=opacity, free_size=free_size, bubble_size=bubble_size,
                      margin=margin, seed=seed)
        frames = []
        for frame in image:
            array = (frame[..., :3].cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
            result, _ = letter(Image.fromarray(array), text, mode=mode, placement=placement,
                               style=style, erase=erase_ai_text, white_threshold=white_threshold)
            frames.append(torch.from_numpy(np.asarray(result).astype(np.float32) / 255.0))
        return (torch.stack(frames),)


NODE_CLASS_MAPPINGS = {"ComicLettering": ComicLettering}
NODE_DISPLAY_NAME_MAPPINGS = {"ComicLettering": "Comic Lettering"}
