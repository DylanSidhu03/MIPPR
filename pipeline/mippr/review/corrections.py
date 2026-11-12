"""Part 6, review and correction: applying a reviewer's decisions to particle rows. Planned.

Rules already decided (docs/OUTPUT_CSV.md 4.9): reviewers change labels and
outlines, never numbers; an edited outline is re-measured; corrections keep the
original label in `*_original`; rejected rows stay in particles.csv and are left
out of summary.csv.
"""
from dataclasses import dataclass, field

STATUSES = ("auto", "confirmed", "corrected", "rejected")


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


def apply(row, decision):
    """Planned: the row after one decision (status, *_original, reviewer columns, tags)."""
    raise NotImplementedError("Part 6: applying review decisions is planned (see review/README.md)")


def remeasure(row, outline, image, mm_per_px, background):
    """Planned: new size, shape and colour values from an edited outline (sets outline_edited)."""
    raise NotImplementedError


def review_queue(rows):
    """Planned: rows in the order a reviewer should see them (flagged and low confidence first)."""
    raise NotImplementedError
