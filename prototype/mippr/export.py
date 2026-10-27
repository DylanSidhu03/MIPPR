"""Turn measurements into the output rows defined in docs/CLASSIFICATION_SPEC.md."""
from collections import defaultdict

NOTE = "Visual classification only. Whether a particle is plastic, and its polymer type, were not tested."

# Review thresholds (spec section 1 and 4).
SIEVE_UM = 500.0
NEAR_CUTOFF = 0.10  # +-10% around the sieve size
LOW_CONTRAST = 100.0  # provisional; on the sample the pale A4 fragment is 92, all others >= 141
MERGED_SOLIDITY = 0.75  # provisional

METADATA = ("date", "operator", "lab", "setup", "site")

COLUMNS = [
    "particle_id", "sample_id", "image_file", "well", "particle_number", "x_um", "y_um",
    *METADATA,
    "feret_max_um", "feret_min_um", "feret_angle_deg", "ced_um", "area_um2", "perimeter_um",
    "convex_area_um2", "convex_perimeter_um",
    "bbox_width_um", "bbox_height_um", "min_rect_length_um", "min_rect_width_um",
    "aspect_ratio", "circularity", "solidity",
    "perimeter_imagej_um", "circularity_imagej",
    *[f"{c}_{s}" for c in "RGBHSVLab" for s in ("mean", "sd")], "color_px",
    "color_class", "color_confidence", "morphology_class", "morphology_confidence",
    "review", "review_reason", "corrected_by",
    "polymer_confirmed", "polymer_method",
    "app_version", "model_version", "square_mm", "um_per_px", "area_px",
]


def review_reasons(m):
    reasons = []
    lo, hi = SIEVE_UM * (1 - NEAR_CUTOFF), SIEVE_UM * (1 + NEAR_CUTOFF)
    if lo <= m["feret_max_um"] <= hi:
        reasons.append("near_size_cutoff")
    if m["feret_min_um"] < SIEVE_UM:
        reasons.append("min_width_below_sieve")
    if m.get("_contrast", float("inf")) < LOW_CONTRAST:
        reasons.append("low_contrast_outline")
    if m.get("_touches_gridline"):
        reasons.append("touches_gridline")
    if m["solidity"] < MERGED_SOLIDITY:
        reasons.append("possibly_merged")
    return reasons


def build_rows(measurements, sample_id, image_file, metadata, app_version, square_mm, um_per_px):
    """Order, name and fill columns as in the spec. Unknown values are left blank."""
    per_well = defaultdict(int)
    out = []
    # Reading order (top to bottom, then right to left as the wells are lettered) for the -n suffix.
    for m in sorted(measurements, key=lambda m: (m["well"][1:].zfill(2), m["well"][0], m["y_um"], -m["x_um"])):
        per_well[m["well"]] += 1
        reasons = review_reasons(m)
        row = {c: "" for c in COLUMNS}
        row.update({k: v for k, v in m.items() if k in row})
        row.update({
            "particle_id": f"{sample_id}-{m['well']}-{per_well[m['well']]}",
            "sample_id": sample_id,
            "image_file": image_file,
            "particle_number": m["particle"],
            "review": "yes" if reasons else "no",
            "review_reason": ";".join(reasons),
            "app_version": app_version,
            "square_mm": square_mm,
            "um_per_px": um_per_px,
        })
        row.update({k: metadata.get(k, "") or "" for k in METADATA})
        out.append(row)
    return sorted(out, key=lambda r: r["particle_number"])
