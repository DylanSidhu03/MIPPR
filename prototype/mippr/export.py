"""Turn measurements into the output files defined in docs/OUTPUT_CSV.md.

Two files: particles.csv (one row per particle) and summary.csv (one row
per sample, calculated only from particles.csv). Columns that a release
doesn't fill yet are left empty, so files from different versions combine.
"""
import statistics
from collections import Counter

from .classify import COLOR_CLASSES, COLOR_RULES_VERSION, MORPHOLOGY_CLASSES, morphology_rules

NOTE = "Visual classification only. Whether a particle is plastic, and its polymer type, were not tested."

# Flag thresholds (docs/OUTPUT_CSV.md section 7).
SIEVE_MM = 0.5
NEAR_CUTOFF = 0.10  # +-10% around the sieve size
LOW_CONTRAST = 100.0  # provisional; on the sample the pale A4 fragment is 92, all others >= 141
MERGED_SOLIDITY = 0.75  # provisional
MERGED_AREA_X_MEDIAN = 3.0  # provisional; area this many times the image's median area
MERGED_MIN_PARTICLES = 3  # the area rule needs a median to compare against

SIZE_BINS = [(0.0, 0.5, "<0.5"), (0.5, 1.0, "0.5-1"), (1.0, 2.0, "1-2"), (2.0, 5.0, "2-5"), (5.0, float("inf"), ">5")]
MORPHOLOGY = MORPHOLOGY_CLASSES
COLORS = COLOR_CLASSES
FLAGS = ["flag_edge", "flag_merged", "flag_low_confidence", "flag_scale",
         "flag_near_cutoff", "flag_min_width", "flag_low_contrast", "flag_line", "flag_multi_blob",
         "flag_width_unresolved", "flag_bundle"]
METADATA = ("date", "operator", "lab", "setup", "site")

COLUMNS = [
    # Identifiers and sample details
    "sample_id", "picture_label", "image_id", "particle_id", "particle_ref", *METADATA,
    # Location
    "centroid_x_px", "centroid_y_px", "bbox_x_px", "bbox_y_px", "bbox_w_px", "bbox_h_px",
    "centroid_x_mm", "centroid_y_mm",
    # Size (mm)
    "length_mm", "width_mm", "area_mm2", "perimeter_mm", "ced_mm", "fiber_length_mm", "size_length_source",
    "size_class",
    "convex_area_mm2", "convex_perimeter_mm",
    # Shape
    "aspect_ratio", "circularity", "solidity",
    # ImageJ-compatible
    "perimeter_imagej_mm", "circularity_imagej",
    # Color
    "color_L", "color_a", "color_b", "color_L_sd", "color_a_sd", "color_b_sd", "color_hex",
    "opacity", "color_secondary", "color_secondary_fraction", "color_label", "color_confidence",
    # Morphology
    "morphology_label", "morphology_source", "morphology_confidence", "morphology_runner_up",
    "morphology_runner_up_confidence",
    # Quality flags
    *FLAGS, "review_reason",
    # Review
    "review_status", "color_label_original", "morphology_label_original", "outline_edited", "tar_like",
    "reviewed_by", "reviewer_role", "reviewed_at",
    # Lab results
    "polymer_confirmed", "polymer_method",
    # Provenance
    "background_type", "mm_per_px", "scale_source",
    "app_version", "color_rules_version", "model_version", "processed_at",
]

SUMMARY_COLUMNS = [
    "sample_id", "n_images", "n_particles",
    *[f"count_{m}" for m in MORPHOLOGY],
    *[f"count_color_{c}" for c in COLORS],
    *[f"count_size_{b[2]}" for b in SIZE_BINS],
    "length_mm_median", "length_mm_min", "length_mm_max",
    "n_reviewed", "n_corrected", "pct_human_confirmed",
    *[f"n_{f}" for f in FLAGS],
    "app_version", "color_rules_version", "model_version",
]


def size_class(length_mm):
    for lo, hi, name in SIZE_BINS:
        if lo <= length_mm < hi:
            return name
    return ""


def flags(m, median_area_mm2=None, scale_flag=False, multi_blob=False):
    """True/false quality flags for one measured particle. Empty where not available yet."""
    length, width = m["feret_max_um"] / 1000, m["feret_min_um"] / 1000
    unresolved = bool(m.get("width_unresolved"))
    big = (median_area_mm2 is not None
           and m["area_um2"] / 1e6 > MERGED_AREA_X_MEDIAN * median_area_mm2)
    return {
        "flag_edge": bool(m.get("_touches_edge")),
        "flag_merged": bool(m["solidity"] < MERGED_SOLIDITY or big),
        "flag_low_confidence": "",  # needs colour rules (v2) or the morphology model (v3)
        "flag_scale": bool(scale_flag),  # markers missing, or the user corrected the scale
        "flag_near_cutoff": bool(SIEVE_MM * (1 - NEAR_CUTOFF) <= length <= SIEVE_MM * (1 + NEAR_CUTOFF)),
        # A fiber too thin to measure is narrower than the sieve, but its width isn't known.
        "flag_min_width": bool(width < SIEVE_MM) and not unresolved,
        "flag_low_contrast": bool(m.get("_contrast", float("inf")) < LOW_CONTRAST),
        "flag_line": bool(m.get("_touches_line")),
        "flag_multi_blob": bool(multi_blob),
        "flag_width_unresolved": unresolved,
        "flag_bundle": "",  # set by a reviewer; later by the model (v3)
    }


CURVED_RATIO = 1.1  # centre-line length / straight length above which a particle counts as bent


def morphology(m):
    """(label, source, confidence, runner_up, runner_up_confidence) from the v2 rules.

    The fiber rule uses the straight (Feret) length:width, or the along-the-fiber one
    for a particle that bends, so a curved fiber still counts.
    """
    ar = m["aspect_ratio"]
    # The centre-line length:width only takes over for a particle that bends (its length
    # along the centre line is clearly longer than straight across). For straight
    # particles Feret is already right, and the centre line over-reads chunky,
    # elongated fragments (found on the lab's EX_01 photos, November 11, 2026).
    if (m.get("fiber_uniform") and m.get("fiber_width_um")
            and m["fiber_length_um"] >= CURVED_RATIO * m["feret_max_um"]):
        ar = max(ar, m["fiber_length_um"] / m["fiber_width_um"])
    label, conf, runner, runner_conf = morphology_rules(ar, m["circularity"], m["solidity"], m.get("opacity"),
                                                        bool(m.get("width_unresolved")))
    return label, "rule", conf, runner, runner_conf


def _hex(m):
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(m[f"{c}_mean"]))) for c in "RGB"))


def particle_ids(measurements):
    """{measurement index: particle_id}. The box label (B4); B4-1, B4-2 ... when a box holds several blobs,
    numbered top to bottom, then left to right."""
    by_box = {}
    for i, m in enumerate(measurements):
        by_box.setdefault(m.get("box") or "", []).append(i)
    ids = {}
    for box, idx in by_box.items():
        idx.sort(key=lambda i: (round(measurements[i]["y_um"]), measurements[i]["x_um"]))
        for n, i in enumerate(idx, 1):
            if not box:
                ids[i] = str(n)
            else:
                ids[i] = box if len(idx) == 1 else f"{box}-{n}"
    return ids, {b for b, idx in by_box.items() if b and len(idx) > 1}


def build_rows(measurements, sample_id, picture_label, image_id, metadata, app_version, mm_per_px, processed_at,
               background_type="checkerboard", scale_source="checkerboard", scale_flag=False, merged_area_rule=True):
    """Per-particle rows, named, ordered and filled as in docs/OUTPUT_CSV.md.

    `merged_area_rule=False` uses solidity alone for flag_merged. On the printed grids
    particles sit one per box, so touching particles are rare and sizes on one sheet
    vary too much for the area rule; flag_multi_blob covers two blobs in a box.
    """
    areas = [m["area_um2"] / 1e6 for m in measurements]
    use_area = merged_area_rule and len(areas) >= MERGED_MIN_PARTICLES
    median_area = statistics.median(areas) if use_area else None
    ids, multi = particle_ids(measurements)
    rows = []
    for i in sorted(range(len(measurements)), key=lambda i: measurements[i]["particle"]):
        m = measurements[i]
        f = flags(m, median_area, scale_flag, m.get("box") in multi)
        px = m["_px"]
        length = m["feret_max_um"] / 1000
        morph, source, mconf, runner, rconf = morphology(m)
        fiber = morph == "fiber"
        fiber_length = m["fiber_length_um"] / 1000 if fiber else ""
        # Size class uses the length along the fiber for fibers (decided November 11, 2026).
        size_length = max(length, fiber_length) if fiber else length
        row = {c: "" for c in COLUMNS}
        row.update({
            "sample_id": sample_id, "picture_label": picture_label, "image_id": image_id,
            "particle_id": ids[i], "particle_ref": f"{picture_label}-{ids[i]}",
            **{k: metadata.get(k, "") or "" for k in METADATA},
            "centroid_x_px": round(px["cx"], 1), "centroid_y_px": round(px["cy"], 1),
            "bbox_x_px": px["x"], "bbox_y_px": px["y"], "bbox_w_px": px["w"], "bbox_h_px": px["h"],
            "centroid_x_mm": m["x_um"] / 1000, "centroid_y_mm": m["y_um"] / 1000,
            "length_mm": length, "width_mm": "" if m.get("width_unresolved") else m["feret_min_um"] / 1000,
            "area_mm2": m["area_um2"] / 1e6, "perimeter_mm": m["perimeter_um"] / 1000,
            "ced_mm": m["ced_um"] / 1000, "fiber_length_mm": fiber_length,
            "size_length_source": "fiber_length" if fiber else "max_feret", "size_class": size_class(size_length),
            "convex_area_mm2": m["convex_area_um2"] / 1e6, "convex_perimeter_mm": m["convex_perimeter_um"] / 1000,
            "aspect_ratio": m["aspect_ratio"], "circularity": m["circularity"], "solidity": m["solidity"],
            "perimeter_imagej_mm": m["perimeter_imagej_um"] / 1000, "circularity_imagej": m["circularity_imagej"],
            "color_L": m["L_mean"], "color_a": m["a_mean"], "color_b": m["b_mean"],
            "color_L_sd": m["L_sd"], "color_a_sd": m["a_sd"], "color_b_sd": m["b_sd"], "color_hex": _hex(m),
            "opacity": "" if m.get("opacity") is None else m["opacity"],
            "color_secondary": m.get("color_secondary", ""),
            "color_secondary_fraction": m.get("color_secondary_fraction", ""),
            # Provisional colour rules (classify.py): their thresholds aren't fitted to labelled particles yet.
            "color_label": m.get("color_label", ""), "color_confidence": m.get("color_confidence", ""),
            "morphology_label": morph, "morphology_source": source, "morphology_confidence": mconf,
            "morphology_runner_up": runner, "morphology_runner_up_confidence": rconf,
            **f,
            "review_reason": ";".join(k[len("flag_"):] for k, v in f.items() if v is True),
            "review_status": "auto", "outline_edited": False, "tar_like": "",
            "background_type": background_type, "mm_per_px": mm_per_px, "scale_source": scale_source,
            "app_version": app_version, "color_rules_version": COLOR_RULES_VERSION if m.get("color_label") else "",
            "processed_at": processed_at,
        })
        rows.append(row)
    return rows


def build_summary(rows):
    """One row per sample, from particle rows only. Rejected particles are left out."""
    out = []
    for sid in dict.fromkeys(r["sample_id"] for r in rows):
        mine = [r for r in rows if r["sample_id"] == sid]
        kept = [r for r in mine if r["review_status"] != "rejected"]
        s = {c: "" for c in SUMMARY_COLUMNS}
        s.update({"sample_id": sid, "n_images": len({r["image_id"] for r in mine}), "n_particles": len(kept)})
        # The label columns already hold the reviewer's correction (the prediction moves to *_original).
        for col, names, prefix in (("morphology_label", MORPHOLOGY, "count_"),
                                   ("color_label", COLORS, "count_color_")):
            labels = [r[col] for r in kept if r[col] != ""]
            if labels:  # leave counts empty until the labels exist (v2 colour, v3 morphology)
                c = Counter(labels)
                s.update({f"{prefix}{n}": c.get(n, 0) for n in names})
        sizes = Counter(r["size_class"] for r in kept)
        s.update({f"count_size_{b[2]}": sizes.get(b[2], 0) for b in SIZE_BINS})
        # The size used for classes: along the fiber for fibers, max Feret otherwise.
        lengths = [max(r["length_mm"], r["fiber_length_mm"]) if r["size_length_source"] == "fiber_length"
                   else r["length_mm"] for r in kept]
        if lengths:
            s.update({"length_mm_median": statistics.median(lengths),
                      "length_mm_min": min(lengths), "length_mm_max": max(lengths)})
        reviewed = [r for r in mine if r["review_status"] != "auto"]
        s.update({
            "n_reviewed": len(reviewed),
            "n_corrected": sum(r["review_status"] == "corrected" for r in mine),
            "pct_human_confirmed": round(100 * sum(r["review_status"] in ("confirmed", "corrected") for r in kept)
                                         / len(kept), 1) if kept else "",
        })
        s.update({f"n_{f}": sum(r[f] is True for r in kept) for f in FLAGS
                  if f not in ("flag_low_confidence", "flag_bundle")})
        for v in ("app_version", "color_rules_version", "model_version"):
            s[v] = ";".join(sorted({str(r[v]) for r in mine if r[v] != ""}))
        out.append(s)
    return out
