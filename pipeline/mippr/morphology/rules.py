"""Part 5, morphology: the v2 rules for the classes measurements can decide.

Fiber (length:width >= 3, or too thin to measure a width), pellet (round, solid,
about as wide as long) and film (mostly see-through). Everything else is fragment
with confidence 0.5, meaning "the rules can't tell": rubbery fragment and foam
need the image model (model.py, v3). Thresholds are provisional, to be tuned on
the lab's labels (part 7).
"""
import math

MORPHOLOGY_CLASSES = ["fragment", "rubbery_fragment", "fiber", "film", "foam", "pellet", "other"]
FIBER_ASPECT = 3.0  # decided: length:width >= 3:1
PELLET_CIRCULARITY, PELLET_SOLIDITY, PELLET_ASPECT = 0.85, 0.95, 1.3
FILM_OPACITY = 0.5


def _conf(value, threshold, higher_is_more, scale):
    """Confidence that a value is on the class's side of a threshold: 0.5 at the threshold."""
    if value is None or math.isnan(value):
        return 0.0
    z = (value - threshold) / scale if higher_is_more else (threshold - value) / scale
    return 1 / (1 + math.exp(-4 * max(-50.0, min(50.0, z))))  # clamped: extreme shapes mustn't overflow


def morphology_rules(aspect, circularity, solidity, opacity_value, width_unresolved=False):
    """(label, confidence, runner_up, runner_up_confidence) from the v2 rules.

    Fiber: length:width >= 3 (or too thin to measure a width). Pellet: round, solid
    and about as wide as long. Film: mostly see-through and not a fiber. Everything
    else is fragment with confidence 0.5, meaning "the rules can't tell" (rubbery
    fragment and foam need the v3 image model).
    """
    scores = {}
    scores["fiber"] = 0.99 if width_unresolved else _conf(aspect, FIBER_ASPECT, True, 1.0)
    pellet = min(_conf(circularity, PELLET_CIRCULARITY, True, 0.05),
                 _conf(solidity, PELLET_SOLIDITY, True, 0.03),
                 _conf(aspect, PELLET_ASPECT, False, 0.15))
    scores["pellet"] = pellet
    if opacity_value is not None:
        scores["film"] = min(_conf(opacity_value, FILM_OPACITY, False, 0.15), 1 - scores["fiber"])
    best = max(scores, key=scores.get)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    if scores[best] >= 0.5:
        runner = ranked[1] if len(ranked) > 1 else ("fragment", 0.5)
        if runner[1] < 0.5:
            runner = ("fragment", 1 - scores[best])
        return best, float(scores[best]), runner[0], float(runner[1])
    return "fragment", 0.5, ranked[0][0], float(ranked[0][1])
