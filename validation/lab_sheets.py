"""Read the lab's ParticleCount spreadsheets and map their labels to the app's classes.

Columns used (names matched loosely, as they vary between files): SampleID, ParticleID,
ParticleShape, ParticleColor, ParticleLength and ParticleWidth (µm). Works on .xlsx
(every sheet with a SampleID column) and .csv. See docs/LAB_DATA.md.
"""
import csv
import re
from pathlib import Path

# The lab's names -> the app's classes (docs/CLASSIFICATION_SPEC.md). None: no class to compare with.
SHAPES = {"fragment": "fragment", "rubbery fragment": "rubbery_fragment", "fiber": "fiber", "fibre": "fiber",
          "line": "fiber", "line bundle": "fiber", "fiber bundle": "fiber", "sphere": "pellet", "pellet": "pellet",
          "bead": "pellet", "film": "film", "foam": "foam"}
COLORS = {"multicolor (2+ colors)": "multicolor", "multicolor": "multicolor", "multicolour": "multicolor",
          "gray": "grey", "unknown": None}

_KEYS = {"sampleid": "sample_id", "particleid": "particle_id", "particleshape": "shape", "particlecolor": "color",
         "particlecolour": "color", "particlelength": "length_um", "particlelengthum": "length_um",
         "particlewidth": "width_um", "particlewidthum": "width_um", "notes": "notes"}


def _norm(h):
    return re.sub(r"[^a-z0-9]", "", str(h).lower()) if h is not None else ""


def lab_shape(name):
    return SHAPES.get(str(name or "").strip().lower())


def lab_color(name):
    s = str(name or "").strip().lower()
    return COLORS.get(s, s) or None


def _tables(path):
    if str(path).lower().endswith(".csv"):
        with open(path, newline="") as fh:
            return [[tuple(r) for r in csv.reader(fh)]]
    import openpyxl
    return [list(ws.iter_rows(values_only=True))
            for ws in openpyxl.load_workbook(path, read_only=True, data_only=True).worksheets]


def _number(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def read_lab_records(paths):
    """{(sample_id, particle_id): record} from one or more ParticleCount files.

    A record has the lab's own `shape` and `color` text, the app classes they map to
    (`shape_class`, `color_class`, None when there is no matching class), and
    `length_mm`, `width_mm` (None when missing, e.g. "Particle Missing").
    Particle IDs are normalised: W5 -> W05, F3 -> F03.
    """
    out = {}
    for path in [paths] if isinstance(paths, (str, Path)) else paths:
        for table in _tables(path):
            rows = [r for r in table if any(c not in (None, "") for c in r)]
            if not rows or "sampleid" not in [_norm(h) for h in rows[0]]:
                continue
            idx = {_KEYS[_norm(h)]: i for i, h in enumerate(rows[0]) if _norm(h) in _KEYS}
            for r in rows[1:]:
                d = {k: (r[i] if i < len(r) else None) for k, i in idx.items()}
                sample, pid = str(d.get("sample_id") or "").strip(), normalise_id(d.get("particle_id"))
                if not sample or not pid:
                    continue
                L, W = _number(d.get("length_um")), _number(d.get("width_um"))
                out[(sample, pid)] = {
                    "shape": str(d.get("shape") or "").strip(), "color": str(d.get("color") or "").strip(),
                    "shape_class": lab_shape(d.get("shape")), "color_class": lab_color(d.get("color")),
                    "length_mm": L / 1000 if L else None, "width_mm": W / 1000 if W else None,
                    "notes": str(d.get("notes") or "").strip(), "source": Path(path).name}
    return out


def normalise_id(pid):
    """W5 -> W05, f3 -> F03, P01 stays; anything else is returned stripped."""
    s = str(pid or "").strip()
    m = re.fullmatch(r"([A-Za-z]+)0*(\d+)", s)
    return f"{m.group(1).upper()}{int(m.group(2)):02d}" if m else s
