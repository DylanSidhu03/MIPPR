"""Part 6, review and correction: applying a reviewer's decisions to particle rows.

Rules already decided (docs/OUTPUT_CSV.md 3 and 4.9):
- reviewers change labels and outlines, never numbers;
- an edited outline is re-measured with the same code the pipeline uses, so every
  number still traces back to an outline;
- a correction keeps the prediction in `color_label_original` /
  `morphology_label_original`, set on the first correction only;
- rejected rows stay in particles.csv and are left out of summary.csv
  (export.build_summary already drops them).

Everything here is plain and deterministic, so the browser review screen
(web/src/review/) can port it line by line. Rows are dicts with the
particles.csv columns; values read back from a CSV ("True", "0.5") are accepted.
Functions never change their inputs: they return new rows.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

import cv2
import numpy as np

from .. import __version__
from ..color.rules import COLOR_CLASSES
from ..export import FLAGS, METADATA, build_rows, flags, review_reason
from ..measurement.geometry import measure
from ..morphology.rules import MORPHOLOGY_CLASSES

STATUSES = ("auto", "confirmed", "corrected", "rejected")
ACTIONS = ("confirm", "reject", "relabel", "edit_outline", "split", "merge", "tag")
ROLES = ("expert", "community")
TAGS = ("tar_like", "flag_bundle")
# A reviewer may also say a colour can't be told (OUTPUT_CSV.md 4.6, color_confidence).
REVIEW_COLORS = (*COLOR_CLASSES, "unknown")
REVIEW_MORPHOLOGIES = tuple(MORPHOLOGY_CLASSES)

# Columns a re-measurement takes from the new outline: everything measured, derived or
# predicted from it. Identifiers, sample details, provenance of the photo, review columns,
# reviewer tags and lab results stay as they were.
REMEASURED = (
    "centroid_x_px", "centroid_y_px", "bbox_x_px", "bbox_y_px", "bbox_w_px", "bbox_h_px",
    "centroid_x_mm", "centroid_y_mm",
    "length_mm", "width_mm", "area_mm2", "perimeter_mm", "ced_mm", "fiber_length_mm", "size_length_source",
    "size_class", "length_mm_outer", "length_mm_inner", "width_mm_outer", "width_mm_inner", "size_uncertainty",
    "convex_area_mm2", "convex_perimeter_mm",
    "aspect_ratio", "circularity", "solidity", "perimeter_imagej_mm", "circularity_imagej",
    "color_L", "color_a", "color_b", "color_L_sd", "color_a_sd", "color_b_sd", "color_hex",
    "opacity", "color_secondary", "color_secondary_fraction",
    "color_label", "color_confidence", "color_rules_version",
    "morphology_label", "morphology_source", "morphology_confidence", "morphology_runner_up",
    "morphology_runner_up_confidence",
    *(f for f in FLAGS if f not in ("flag_low_confidence", "flag_bundle")),
    "mm_per_px", "app_version",
)
# The prediction columns kept as they are when a reviewer has already corrected that label.
COLOR_PREDICTION = ("color_label", "color_confidence")
MORPHOLOGY_PREDICTION = ("morphology_label", "morphology_source", "morphology_confidence",
                         "morphology_runner_up", "morphology_runner_up_confidence")


@dataclass
class Decision:
    """One reviewer action on one particle."""
    particle_ref: str
    action: str  # "confirm", "reject", "relabel", "edit_outline", "split", "merge", "tag"
    reviewer: str
    role: str  # "expert" or "community"
    at: str  # ISO 8601 UTC
    color_label: str = ""
    morphology_label: str = ""
    outline: list = field(default_factory=list)  # polygon in image px, for edit_outline / split
    tags: dict = field(default_factory=dict)  # e.g. {"tar_like": True, "flag_bundle": True}


@dataclass
class MeasureContext:
    """What measure() was given for one photo, so an edited outline is measured the same way.

    The pipeline (cli.run_grid) has all of these in hand when it measures: `image` is the
    rectified grid, `background` the expected background behind each pixel (measure()'s
    `bg_img`), and the rest are measure()'s keyword arguments.
    """
    image: np.ndarray
    mm_per_px: float
    background: np.ndarray = None
    diff: np.ndarray = None
    color_img: np.ndarray = None
    line_mask: np.ndarray = None
    box_fn: object = None
    edge_fraction: float = 0.5
    edge_margin_px: int = 3

    def kwargs(self):
        return {k: getattr(self, k) for k in self.__dataclass_fields__ if k not in ("image", "mm_per_px", "background")}


def _true(v):
    return v is True or v == "True"


def _float(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def parse_time(at):
    """An ISO 8601 time as an aware UTC datetime (a time without a zone is taken as UTC)."""
    try:
        t = datetime.fromisoformat(str(at).replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"Review time {at!r} is not ISO 8601.") from None
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def _check(row, d):
    if d.action not in ACTIONS:
        raise ValueError(f"Unknown review action {d.action!r}; expected one of {', '.join(ACTIONS)}.")
    if d.particle_ref != row.get("particle_ref"):
        raise ValueError(f"Decision for {d.particle_ref!r} applied to row {row.get('particle_ref')!r}.")
    if not str(d.reviewer).strip():
        raise ValueError("A decision needs a reviewer.")
    if d.role not in ROLES:
        raise ValueError(f"Unknown reviewer role {d.role!r}; expected expert or community.")
    parse_time(d.at)
    if d.action == "relabel":
        if not d.color_label and not d.morphology_label:
            raise ValueError("relabel needs a colour or a morphology label.")
        if d.color_label and d.color_label not in REVIEW_COLORS:
            raise ValueError(f"Unknown colour class {d.color_label!r}.")
        if d.morphology_label and d.morphology_label not in REVIEW_MORPHOLOGIES:
            raise ValueError(f"Unknown morphology class {d.morphology_label!r}.")
    if d.action == "tag":
        bad = [k for k in d.tags if k not in TAGS]
        if bad or not d.tags:
            raise ValueError(f"Unknown or missing tags {bad}; expected some of {', '.join(TAGS)}.")
        if any(not isinstance(v, bool) for v in d.tags.values()):
            raise ValueError("Tag values must be True or False.")


def _status(row):
    """confirmed, or corrected when a label or the outline differs from what the pipeline produced."""
    changed = (row.get("color_label_original") not in ("", None)
               or row.get("morphology_label_original") not in ("", None) or _true(row.get("outline_edited")))
    return "corrected" if changed else "confirmed"


def _relabel(row, col, new):
    """Set a label; keep the prediction in *_original on the first correction only."""
    orig = col + "_original"
    if new == row[col]:
        return
    if row.get(orig) in ("", None):
        row[orig] = row[col]
    elif new == row[orig]:  # back to the prediction: no longer a correction
        row[orig] = ""
    row[col] = new


def apply(row, decision, context=None):
    """The row after one decision. The input row is not changed.

    - confirm: the labels are right (status confirmed, or corrected if earlier corrections stand)
    - reject: a false detection; the row stays in particles.csv, status rejected
    - relabel: new colour and/or morphology label (status corrected)
    - edit_outline: `decision.outline` is re-measured with `context` (a MeasureContext for the
      row's photo) and outline_edited is set (status corrected)
    - tag: `tar_like` / `flag_bundle` set to True or False; the status is not changed
    - split, merge: not built yet (NotImplementedError)

    Every decision records reviewed_by, reviewer_role and reviewed_at (the latest decision wins).
    """
    d = decision
    _check(row, d)
    if d.action in ("split", "merge"):
        raise NotImplementedError(
            f"{d.action} is not built yet: it turns one row into two (or two into one), which needs rules for the "
            "new particle_ids and for the row that is merged away. remeasure() already measures any mask, so it "
            "can be built on that once those rules are decided.")
    out = dict(row)
    if d.action == "edit_outline":
        if context is None:
            raise ValueError("edit_outline needs the photo's MeasureContext to re-measure the outline.")
        if d.outline is None or len(d.outline) < 3:
            raise ValueError("edit_outline needs a polygon of at least 3 points.")
        out = remeasure(out, d.outline, context.image, context.mm_per_px, context.background, **context.kwargs())
    elif d.action == "relabel":
        if d.color_label:
            _relabel(out, "color_label", d.color_label)
        if d.morphology_label:
            _relabel(out, "morphology_label", d.morphology_label)
    elif d.action == "tag":
        for k, v in d.tags.items():
            out[k] = v
        out["review_reason"] = review_reason({f: _true(out.get(f)) for f in FLAGS})
    if d.action == "reject":
        out["review_status"] = "rejected"
    elif d.action != "tag":
        out["review_status"] = _status(out)
    out.update({"reviewed_by": d.reviewer, "reviewer_role": d.role, "reviewed_at": d.at})
    return out


def outline_mask(outline, shape):
    """Boolean mask of a polygon (x, y vertices at pixel centres, as OpenCV contours are) or a mask itself."""
    a = np.asarray(outline)
    if a.ndim == 2 and a.shape == tuple(shape[:2]) and a.dtype == bool:
        return a.copy()
    pts = np.round(a.reshape(-1, 2)).astype(np.int32)
    if len(pts) < 3:
        raise ValueError("An outline needs at least 3 points.")
    m = np.zeros(shape[:2], np.uint8)
    cv2.fillPoly(m, [pts], 1)
    if not m.any():
        raise ValueError("The outline covers no pixels of the image.")
    return m.astype(bool)


def remeasure(row, outline, image, mm_per_px, background=None, *, diff=None, color_img=None, line_mask=None,
              box_fn=None, edge_fraction=0.5, edge_margin_px=3):
    """The row with every measured, derived and predicted value recomputed from an edited outline.

    `outline` is a polygon in the rectified image's px (or a boolean mask of it), `image`
    the rectified photo, `mm_per_px` the row's scale and `background` the expected background
    image (measure()'s `bg_img`); the keyword arguments are measure()'s, as in MeasureContext.
    Given the same inputs as the pipeline, the result equals the pipeline's row for that mask.

    Kept from the row: identifiers (particle_id stays the box label even if the centroid moved),
    sample details, background type, scale source, processed_at, review columns and reviewer
    tags, and any label a reviewer already corrected (with its confidence and source).
    Sets outline_edited. review_status is left for apply() to set.
    """
    mask = outline_mask(outline, image.shape)
    (m,) = measure(mask.astype(np.int32), image, mm_per_px * 1000, diff, edge_fraction,
                   edge_margin_px, box_fn=box_fn, line_mask=line_mask, color_img=color_img, bg_img=background)
    (new,) = build_rows([m], row["sample_id"], row["picture_label"], row["image_id"],
                        {k: row.get(k, "") for k in METADATA}, __version__, mm_per_px, row.get("processed_at", ""),
                        background_type=row.get("background_type", ""), scale_source=row.get("scale_source", ""),
                        scale_flag=_true(row.get("flag_scale")))
    # flag_multi_blob depends on the other particles in the box, so it comes from the row.
    new.update(flags(m, _true(row.get("flag_scale")), _true(row.get("flag_multi_blob"))))
    out = dict(row)
    out.update({k: new[k] for k in REMEASURED})
    if row.get("color_label_original") not in ("", None):
        out.update({k: row[k] for k in COLOR_PREDICTION})
    if row.get("morphology_label_original") not in ("", None):
        out.update({k: row[k] for k in MORPHOLOGY_PREDICTION})
    out["outline_edited"] = True
    out["review_reason"] = review_reason({f: _true(out.get(f)) for f in FLAGS})
    return out


def apply_all(rows, decisions, contexts=None):
    """All decisions applied in time order (ties keep their given order). Returns new rows in the same order.

    `contexts` maps image_id to that photo's MeasureContext, needed for edit_outline.
    """
    index = {}
    for i, r in enumerate(rows):
        if r["particle_ref"] in index:
            raise ValueError(f"Two rows share particle_ref {r['particle_ref']!r}.")
        index[r["particle_ref"]] = i
    out = [dict(r) for r in rows]
    for d in sorted(decisions, key=lambda d: parse_time(d.at)):
        if d.particle_ref not in index:
            raise ValueError(f"No particle {d.particle_ref!r} for this decision.")
        i = index[d.particle_ref]
        out[i] = apply(out[i], d, (contexts or {}).get(out[i]["image_id"]))
    return out


def kept(rows):
    """Rows that count in summary.csv: everything not rejected (export.build_summary does the same)."""
    return [r for r in rows if r.get("review_status") != "rejected"]


def _lowest_confidence(row):
    confs = [c for c in (_float(row.get("color_confidence")), _float(row.get("morphology_confidence")))
             if c is not None]
    return min(confs) if confs else 1.0


def review_queue(rows):
    """Rows in the order a reviewer should see them. Returns a new list; the rows are not copied.

    1. not yet reviewed and flagged (any flag in review_reason, or flag_low_confidence)
    2. not yet reviewed, not flagged
    3. already confirmed or corrected
    4. rejected
    Within the first two groups the lowest colour or morphology confidence comes first, since
    the flag_low_confidence threshold isn't decided yet; otherwise the input order is kept.
    """
    def key(r):
        status = r.get("review_status") or "auto"
        if status == "rejected":
            return (3, 0.0)
        if status != "auto":
            return (2, 0.0)
        flagged = bool(r.get("review_reason")) or _true(r.get("flag_low_confidence"))
        return (0 if flagged else 1, _lowest_confidence(r))
    return sorted(rows, key=key)
