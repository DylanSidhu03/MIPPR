"""Part 3, measurement: how much a particle's size depends on where its edge is drawn.

The outline is placed where the difference from the background falls to half the
particle's contrast (segmentation/edges.py). Here the particle is outlined again with
the edge at `fraction - spread` and `fraction + spread` (40% and 60% by default) and
its length and width measured each time. A sharp, high-contrast particle gives nearly
the same size; a faint, clear or blurred one doesn't, because its edge is ambiguous.

    size_uncertainty = (length at 40% - length at 60%) / length at 50%

Above SIZE_UNCERTAIN (export.py) the particle gets `flag_size_uncertain`. The
threshold is set by testing on labelled particles photographed on the sheets: it is
the value above which sizes turn out wrong (docs/PIPELINE.md, part 7). In use, the
check runs on every particle and flagged ones go first in the review list.
"""
import cv2
import numpy as np

from ..segmentation.edges import edge_level, fill_holes

EDGE_SPREAD = 0.1  # the edge is moved from 50% to 40% and 60% of the particle's contrast
REACH_PX = 10  # how far outside the outline the outer (40%) edge may go


def size_range(mask, diff, feret_fn, fraction=0.5, spread=EDGE_SPREAD, reach=REACH_PX):
    """Length and width (px) with the edge drawn at `fraction - spread` (outer) and `+ spread` (inner).

    The particle's contrast is the same as for its outline (edges.edge_level). Each new
    outline is every piece of {difference >= level} that touches the drawn outline, within
    `reach` px of it. The outer one always contains the drawn outline (holes filled), the
    inner one lies within it, so outer >= drawn >= inner. `feret_fn(mask)` returns (max Feret, min Feret) in px.
    Works on a crop round the particle, so it costs little on a large photo.
    Returns {"length_px_outer", "length_px_inner", "width_px_outer", "width_px_inner"}.
    """
    ys, xs = np.nonzero(mask)
    h, w = mask.shape
    pad = reach + 2
    y0, y1 = max(0, ys.min() - pad), min(h, ys.max() + pad + 1)
    x0, x1 = max(0, xs.min() - pad), min(w, xs.max() + pad + 1)
    m = mask[y0:y1, x0:x1].astype(bool)
    d = diff[y0:y1, x0:x1].astype(np.float64)
    contrast = edge_level(m, d, 1.0)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * reach + 1, 2 * reach + 1))
    near = cv2.dilate(m.astype(np.uint8), kernel).astype(bool)
    out = {}
    for name, f in (("outer", fraction - spread), ("inner", fraction + spread)):
        region = near & (d >= f * contrast)
        # every piece that touches the outline (a fiber can break where it crosses a printed line)
        n, lab = cv2.connectedComponents(region.astype(np.uint8), connectivity=8)
        touching = np.unique(lab[m & region])
        region = np.isin(lab, touching[touching > 0])
        # the outer outline always contains the drawn one, the inner one lies within it
        region = fill_holes(region | m) if name == "outer" else (region & m)
        if not region.any():
            region = m
        length, width = feret_fn(region)
        out[f"length_px_{name}"], out[f"width_px_{name}"] = length, width
    return out
