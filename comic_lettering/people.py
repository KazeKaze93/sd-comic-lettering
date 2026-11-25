"""Where the characters are, so text can keep off them.

Uses a person segmentation model through ultralytics when both are available on this
machine. Nothing is downloaded: without the library or a local model file the mask is
None and placement falls back to "calm area" alone.
"""
import glob
import hashlib
import os
from collections import OrderedDict

import numpy as np
from scipy import ndimage as ndi

MODEL_ENV = "SDCL_PERSON_MODEL"
MODEL_PATTERN = "person_yolov8*-seg.pt"
# Folders, relative to the host's working directory, where such models usually live.
MODEL_DIRS = [
    "models/adetailer", "models/ultralytics/segm", "models/ultralytics",
    "models/Ultralytics/segm", "models/yolo",
    # StabilityMatrix keeps shared models two levels up, next to Packages/.
    "../../Models/Ultralytics/segm", "../../Models/AfterDetailer", "../../Models/adetailer",
    # A sibling ComfyUI install under the same Packages/ folder.
    "../ComfyUI/models/ultralytics/segm",
]

_model = None
_model_path = None
_failed = False
_cache = OrderedDict()


def find_model():
    """Path of a local person segmentation model, or None."""
    explicit = os.environ.get(MODEL_ENV)
    if explicit and os.path.isfile(explicit):
        return explicit
    for folder in MODEL_DIRS:
        matches = sorted(glob.glob(os.path.join(os.getcwd(), folder, MODEL_PATTERN)))
        if matches:
            # Prefer the smallest model: this only needs a rough silhouette.
            return min(matches, key=os.path.getsize)
    return None


def _load():
    global _model, _model_path, _failed
    if _model is not None or _failed:
        return _model
    try:
        path = find_model()
        if path is None:
            _failed = True
            return None
        from ultralytics import YOLO
        _model = YOLO(path)
        _model_path = path
    except Exception:  # no library, a broken file, an incompatible version: do without
        _failed = True
        _model = None
    return _model


def status():
    """A short description for the UI: which model is used, or why none is."""
    if _load() is not None:
        return "character detection: " + os.path.basename(_model_path)
    return "character detection: off (no ultralytics or no %s found)" % MODEL_PATTERN


def person_mask(rgb, grow=0.012):
    """Boolean mask of the characters in an RGB uint8 array, or None when unavailable.

    The mask is grown a little so text does not touch the silhouette.
    """
    key = (rgb.shape, hashlib.md5(np.ascontiguousarray(rgb[::8, ::8]).tobytes()).hexdigest())
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    model = _load()
    if model is None:
        return None
    try:
        result = model.predict(np.ascontiguousarray(rgb[..., ::-1]), conf=0.25, verbose=False)[0]
        height, width = rgb.shape[:2]
        mask = np.zeros((height, width), dtype=bool)
        if result.masks is not None:
            for raw in result.masks.data.cpu().numpy():
                zoom = (height / float(raw.shape[0]), width / float(raw.shape[1]))
                resized = ndi.zoom(raw.astype(np.float32), zoom, order=1) > 0.5
                h, w = min(height, resized.shape[0]), min(width, resized.shape[1])
                mask[:h, :w] |= resized[:h, :w]
        if mask.any() and grow > 0:
            mask = ndi.binary_dilation(mask, iterations=max(1, int(grow * max(height, width))))
    except Exception:  # a failed prediction must never break lettering
        return None
    _cache[key] = mask
    while len(_cache) > 8:
        _cache.popitem(last=False)
    return mask
