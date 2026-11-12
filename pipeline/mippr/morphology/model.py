"""Part 5, morphology: the image model (v3). Planned; nothing here is implemented yet.

The model decides what the rules (rules.py) can't, mainly fragment vs rubbery
fragment vs foam, from a crop of the particle plus its shape values. It is trained
in Python (training/, part 10), exported to ONNX, and run in the browser with ONNX
Runtime Web (web/src/morphology/model.js). This file is the Python side, used for
batch runs and to check the browser gives the same answers.
"""
from dataclasses import dataclass

CROP_SIZE = 128  # px; to be chosen with the first training runs


@dataclass
class Prediction:
    label: str
    confidence: float
    runner_up: str
    runner_up_confidence: float
    model_version: str


def crop_particle(img, mask, size=CROP_SIZE, pad_frac=0.15):
    """Planned: a square crop of one particle with the background blanked.

    The crop is centred on the particle, padded by `pad_frac`, and resized to
    `size` x `size`; pixels outside the mask are set to a neutral value. It returns
    the crop and its mm per crop-pixel, so size isn't lost (the model also gets the
    shape values). Also used to save crops for training and storage (Drive 9b).
    """
    raise NotImplementedError("Part 5: particle crops are planned (see morphology/README.md)")


class MorphologyModel:
    """Planned: load an exported model and classify crops."""

    def __init__(self, path):
        raise NotImplementedError("Part 5: the v3 model is planned (see morphology/README.md)")

    def predict(self, crop, features, background_type):
        """Class probabilities for one particle -> Prediction.

        `features` are the shape values (aspect ratio, circularity, solidity, opacity,
        size); `background_type` is an input, not a separate model (Drive v0.6).
        """
        raise NotImplementedError


def combine(rule_label, rule_confidence, prediction, overrule_at=None):
    """Planned: the final label from the rules and the model.

    The model may overrule a rule when it is confident (decided November 11, 2026);
    `overrule_at` is set from validation data. The result records which one won
    (`morphology_source`).
    """
    raise NotImplementedError
