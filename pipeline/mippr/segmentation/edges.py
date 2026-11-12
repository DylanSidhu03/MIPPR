"""Part 2, segmentation: the steps every outline goes through, whatever the background.

Thresholds with hysteresis, hole filling, and the half-maximum edge rule that puts
each outline where the particle's contrast falls to half. Only operations that exist
in OpenCV.js (threshold, morphology, connected components, contours).
"""
import cv2
import numpy as np


def hysteresis(diff, low, high, band):
    """Keep low-threshold regions that contain at least one high-threshold pixel.

    Printed lines and box edges blur and pick up lens colour fringing, so the
    difference image has thin lines along them (`band`). Inside the band only
    structures at least 3 px wide count, and a region needs a strong pixel outside
    the band to be kept.
    """
    weak = (diff >= low).astype(np.uint8)
    opened = cv2.morphologyEx(weak, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    weak = np.where(band, opened, weak).astype(np.uint8)
    n, labels = cv2.connectedComponents(weak, connectivity=8)
    strong = np.unique(labels[(diff >= high) & ~band])
    keep = np.zeros(n, bool)
    keep[strong] = True
    keep[0] = False
    return keep[labels]


def fill_holes(mask):
    """Fill holes so particles with see-through centres (film, foam) stay whole."""
    m = mask.astype(np.uint8)
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    filled = np.zeros_like(m)
    cv2.drawContours(filled, contours, -1, 1, thickness=cv2.FILLED)
    return filled.astype(bool)


def edge_level(region, diff, fraction=0.5, grow=2):
    """Difference value at which this particle's edge is drawn: `fraction` of its contrast.

    Contrast is the median over the particle's interior: the median copes with
    uneven particles (a pale fragment with a dark speck), and leaving out the
    outer `grow` px keeps the blurred halo from dragging it down.
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1))
    core = cv2.erode(region.astype(np.uint8), kernel).astype(bool)
    contrast = np.median(diff[core]) if core.sum() >= 5 else np.percentile(diff[region], 90)
    return fraction * float(contrast)


def refine_edges(mask, diff, fraction, grow=2):
    """Move each particle's edge to where the difference falls to `fraction` of its contrast.

    Detection uses a low threshold so faint particles are found, but that puts
    the outline on the blurred halo, about 1 px outside the edge you see. The
    half-maximum rule places the edge the same way for bright and faint
    particles and for sharp or soft photos.
    """
    n, labels = cv2.connectedComponents(mask.astype(np.uint8), connectivity=8)
    out = np.zeros(mask.shape, bool)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1))
    for lbl in range(1, n):
        region = labels == lbl
        near = cv2.dilate(region.astype(np.uint8), kernel).astype(bool)
        refined = near & (diff >= edge_level(region, diff, fraction, grow))
        # Only the outer edge may move. Inside, the difference can dip below the
        # edge level, e.g. where a mid-tone particle lies across a blurred box
        # edge, and that must not cut the particle.
        refined |= cv2.erode(region.astype(np.uint8), kernel).astype(bool)
        # Keep only the part that overlaps the detection, so a neighbour is not pulled in.
        k, parts = cv2.connectedComponents(refined.astype(np.uint8), connectivity=8)
        if k <= 1:
            continue
        overlap = np.bincount(parts[region], minlength=k)
        overlap[0] = 0
        out |= parts == int(np.argmax(overlap))
    return fill_holes(out)
