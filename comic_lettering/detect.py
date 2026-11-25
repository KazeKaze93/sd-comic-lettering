"""Speech bubble detection: light, outlined, reasonably solid regions."""
from typing import List, Tuple

import numpy as np
from scipy import ndimage as ndi
from scipy.spatial import ConvexHull

try:
    from scipy.spatial import QhullError
except ImportError:  # scipy < 1.8
    from scipy.spatial.qhull import QhullError


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


def detect_bubbles(rgb, white_threshold=120, min_area=0.003, max_area=0.6,
                   min_outline=0.8, rtl=False):
    # type: (np.ndarray, int, float, float, float, bool) -> List[Bubble]
    """Find speech bubbles in an RGB uint8 array.

    A bubble is a flat, unsaturated fill enclosed by a dark outline, with a smooth,
    nearly convex shape. Its brightness does not matter beyond white_threshold: models
    with a muted palette draw gray bubbles, sometimes darker than the wall behind.
    """
    found = []
    for item in scan(rgb, white_threshold, min_area, max_area):
        if is_bubble(item, min_outline):
            found.append(item["bubble"])
    return _reading_order(found, rtl)


def is_bubble(item, min_outline=0.8):
    """Thresholds measured on real generations: they tell a bubble from a pale face,
    an ear, a wall patch or a picture frame, which are also light and outlined.

    Real bubbles there: flatness up to 0.8, outline 0.88 or more, solidity 0.92 or
    more. The nearest look-alikes: flatness 1.5 and up, or outline under 0.8.
    """
    return (item["flatness"] <= 1.3 and item["solidity"] >= 0.85
            and 0.45 <= item["extent"] < 0.96 and item["outline"] >= min_outline
            and item["body"] >= 0.55)


def _reading_order(bubbles, rtl):
    """Rows top to bottom; bubbles that overlap vertically share a row."""
    rows = []
    for bubble in sorted(bubbles, key=lambda b: b.cy):
        if rows:
            _, top, _, bottom = rows[-1][0].bbox()
            if top <= bubble.cy < bottom:
                rows[-1].append(bubble)
                continue
        rows.append([bubble])
    ordered = []
    for row in rows:
        ordered.extend(sorted(row, key=lambda b: -b.cx if rtl else b.cx))
    return ordered


def _solidity(mask):
    """Area of the mask divided by the area of its convex hull."""
    ys, xs = np.nonzero(mask ^ ndi.binary_erosion(mask))
    try:
        hull = ConvexHull(np.stack([xs, ys], axis=1)).volume
    except (QhullError, ValueError):
        return 0.0
    return float(mask.sum()) / hull if hull > 0 else 0.0


def scan(rgb, floor=120, min_area=0.003, max_area=0.6):
    """Yield every flat, unsaturated region with the measurements used to judge it."""
    h, w = rgb.shape[:2]
    lum = luminance(rgb.astype(np.float32))
    mn = rgb.min(axis=2)
    mx = rgb.max(axis=2)
    local_range = ndi.maximum_filter(lum, size=3) - ndi.minimum_filter(lum, size=3)
    flat = (local_range <= 8.0) & ((mx.astype(np.int16) - mn) <= 32) & (lum >= floor)
    labels, count = ndi.label(flat)
    if count == 0:
        return
    areas = np.bincount(labels.ravel())
    total = h * w
    for idx, sl in enumerate(ndi.find_objects(labels), start=1):
        area = int(areas[idx])
        if area < total * min_area * 0.6 or area > total * max_area:
            continue
        ring_w = max(3, int(0.015 * np.sqrt(area)))
        pad = ring_w + 5
        y0 = max(0, sl[0].start - pad)
        y1 = min(h, sl[0].stop + pad)
        x0 = max(0, sl[1].start - pad)
        x1 = min(w, sl[1].stop + pad)
        comp = labels[y0:y1, x0:x1] == idx
        filled = ndi.binary_fill_holes(comp)
        filled_area = int(filled.sum())
        if filled_area < total * min_area:
            continue
        pixels = rgb[y0:y1, x0:x1][comp]
        color = tuple(int(v) for v in np.median(pixels, axis=0))
        fill_lum = color[0] * 0.299 + color[1] * 0.587 + color[2] * 0.114
        ys, xs = np.nonzero(filled)
        box = (ys.max() - ys.min() + 1) * (xs.max() - xs.min() + 1)
        # Outline: the share of the perimeter that has a dark line right next to it.
        # Measured along the edge, not by ring area, so a thin line counts in full.
        # Where the region runs into the image border there is no line: that part
        # counts as open.
        reach = ring_w + 3
        band = ndi.binary_dilation(filled, iterations=reach) & ~filled
        dark = band & (lum[y0:y1, x0:x1] < min(110.0, fill_lum - 40.0))
        edge = ndi.binary_dilation(filled) & ~filled
        covered = int((ndi.binary_dilation(dark, iterations=reach) & edge).sum())
        on_border = 0
        if y0 == 0:
            on_border += int(filled[0].sum())
        if y1 == h:
            on_border += int(filled[-1].sum())
        if x0 == 0:
            on_border += int(filled[:, 0].sum())
        if x1 == w:
            on_border += int(filled[:, -1].sum())
        perimeter = int(edge.sum()) + on_border
        outline = covered / float(perimeter) if perimeter else 0.0
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
        yield {
            "bubble": Bubble(y0, x0, comp, filled, body, color),
            "flatness": float(pixels.mean(axis=1).std()),
            "solidity": _solidity(filled),
            "extent": filled_area / float(box),
            "outline": outline,
            "body": float(body.sum()) / filled_area,
        }


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
