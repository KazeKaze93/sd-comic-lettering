"""Speech bubble detection: light, outlined, reasonably solid regions."""
from typing import List, Tuple

import numpy as np
from scipy import ndimage as ndi


class Bubble(object):
    """A detected bubble. Masks are crops; (y0, x0) is the crop origin in the image."""

    def __init__(self, y0, x0, comp, filled, body, color):
        self.y0 = y0
        self.x0 = x0
        self.comp = comp        # light pixels of the bubble
        self.filled = comp if filled is None else filled  # comp with holes (letters) filled
        self.body = body        # filled, with the tail removed
        self.color = color      # median bubble color (r, g, b)
        ys, xs = np.nonzero(body)
        self.cy = y0 + float(ys.mean())
        self.cx = x0 + float(xs.mean())
        self.area = int(self.filled.sum())

    def bbox(self):
        # type: () -> Tuple[int, int, int, int]
        ys, xs = np.nonzero(self.body)
        return (self.x0 + int(xs.min()), self.y0 + int(ys.min()),
                self.x0 + int(xs.max()) + 1, self.y0 + int(ys.max()) + 1)


def luminance(rgb):
    return rgb[..., 0] * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114


def detect_bubbles(rgb, white_threshold=225, min_area=0.008, max_area=0.6,
                   min_outline=0.3, rtl=False):
    # type: (np.ndarray, int, float, float, float, bool) -> List[Bubble]
    """Find speech bubbles in an RGB uint8 array.

    A bubble is a near-white connected region that, once the letters inside are
    filled in, is large enough, fairly solid, and mostly surrounded by a dark outline.
    """
    h, w = rgb.shape[:2]
    mn = rgb.min(axis=2)
    mx = rgb.max(axis=2)
    white = (mn >= white_threshold) & ((mx.astype(np.int16) - mn) <= 32)
    labels, count = ndi.label(white)
    if count == 0:
        return []
    lum = luminance(rgb.astype(np.float32))
    areas = np.bincount(labels.ravel())
    total = h * w
    found = []
    for idx, sl in enumerate(ndi.find_objects(labels), start=1):
        area = int(areas[idx])
        if area < total * min_area * 0.6 or area > total * max_area:
            continue
        ring_w = max(3, int(0.015 * np.sqrt(area)))
        pad = ring_w + 2
        y0 = max(0, sl[0].start - pad)
        y1 = min(h, sl[0].stop + pad)
        x0 = max(0, sl[1].start - pad)
        x1 = min(w, sl[1].stop + pad)
        comp = labels[y0:y1, x0:x1] == idx
        filled = ndi.binary_fill_holes(comp)
        filled_area = int(filled.sum())
        if filled_area < total * min_area:
            continue
        ys, xs = np.nonzero(filled)
        box = (ys.max() - ys.min() + 1) * (xs.max() - xs.min() + 1)
        if filled_area / float(box) < 0.45:
            continue
        ring = ndi.binary_dilation(filled, iterations=ring_w) & ~filled
        if not ring.any():
            continue
        # A real bubble has a dark outline. Without one, accept it only if it has
        # letters inside and still stands out from a darker surrounding.
        ring_lum = lum[y0:y1, x0:x1][ring]
        outlined = float((ring_lum < 110).mean()) >= min_outline
        lettered = (filled_area - int(comp.sum())) >= 0.004 * filled_area
        if not outlined and not (lettered and float((ring_lum < 150).mean()) >= min_outline):
            continue
        # Drop the tail: keep what survives an opening with a large radius.
        radius = max(2.0, 0.10 * np.sqrt(filled_area))
        dist = ndi.distance_transform_edt(np.pad(filled, 1))[1:-1, 1:-1]
        core = dist > radius
        core_labels, core_count = ndi.label(core)
        if core_count == 0:
            continue
        if core_count > 1:
            sizes = np.bincount(core_labels.ravel())
            sizes[0] = 0
            core = core_labels == int(sizes.argmax())
        body = (ndi.distance_transform_edt(~core) <= radius) & filled
        if body.sum() < 0.55 * filled_area:
            continue
        color = tuple(int(v) for v in np.median(rgb[y0:y1, x0:x1][comp], axis=0))
        found.append(Bubble(y0, x0, comp, filled, body, color))
    band = max(1.0, 0.2 * h)
    found.sort(key=lambda b: (int(b.cy // band), -b.cx if rtl else b.cx))
    return found


def erase_letters(rgb, bubble):
    """Paint over everything enclosed by the bubble (the model's letters). In place."""
    holes = bubble.filled & ~bubble.comp
    if not holes.any():
        return
    paint = ndi.binary_dilation(holes, iterations=2) & bubble.filled
    h, w = paint.shape
    region = rgb[bubble.y0:bubble.y0 + h, bubble.x0:bubble.x0 + w]
    region[paint] = bubble.color


def edge_energy(rgb, y0, y1):
    """Mean gradient magnitude of a horizontal band: low means a calm area."""
    lum = luminance(rgb[y0:y1].astype(np.float32))
    if lum.shape[0] < 2 or lum.shape[1] < 2:
        return 0.0
    return float(np.abs(np.diff(lum, axis=0)).mean() + np.abs(np.diff(lum, axis=1)).mean())
