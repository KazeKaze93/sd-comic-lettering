"""ComfyUI entry point. A1111 / Forge / reForge load scripts/ instead and never import this."""
import os

from .comfy_nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS
from .comic_lettering import web

# The page script that puts the Open editor button on the node. The editor's own files are
# served by a route (see web.register_aiohttp), not from this folder.
WEB_DIRECTORY = "./comfy_web"


def save_like_comfy(image, parameters, tab):
    """Save the editor's image into ComfyUI's output folder, named and numbered the way its
    Save Image node does. Returns the file's path."""
    import folder_paths
    from PIL.PngImagePlugin import PngInfo

    folder, name, counter, _, _ = folder_paths.get_save_image_path("ComfyUI_lettered", folder_paths.get_output_directory(),
                                                                   image.width, image.height)
    info = None
    if parameters:
        info = PngInfo()
        info.add_text("parameters", parameters)
    path = os.path.join(folder, "%s_%05d_.png" % (name, counter))
    image.save(path, pnginfo=info, compress_level=4)
    return path


try:
    from server import PromptServer
except ImportError:  # imported outside ComfyUI (tests): the node works, the editor has no server
    PromptServer = None
if PromptServer is not None and getattr(PromptServer, "instance", None) is not None:
    web.register_aiohttp(PromptServer.instance.routes, save_like_comfy)

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
