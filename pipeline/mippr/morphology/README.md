# Part 5: Morphology

Give each particle a shape class: fragment, rubbery_fragment, fiber, film, foam, pellet or other.

**Method:** rules for what measurements can decide (v2), and an **image model** for what they can't (v3). This is the only part that needs a trained model.

## In → Out

| In (from parts 2–4) | Out (to the export and review) |
|---|---|
| Shape values (aspect ratio, centre-line length:width, circularity, solidity), `opacity`, `width_unresolved` | `morphology_label`, `morphology_source` (rule / model), `morphology_confidence`, runner-up and its confidence |
| For the model: a crop of the particle with the background blanked, plus the shape values and the background type | |

## What exists

| File | Does |
|---|---|
| `rules.py` | v2 rules. **Fiber:** length:width ≥ 3, or too thin to measure; the centre-line ratio is used only for particles that bend. **Pellet:** round, solid, about as wide as long. **Film:** mostly see-through. Everything else is fragment with confidence 0.5. |
| `model.py` | **Planned (stubs):** cutting particle crops, and loading and running the v3 model (exported to ONNX for the browser) |

## To build

- [ ] **Particle crops** (`crop_particle`): fixed size, background blanked, scale recorded. They are needed for training and inference.
- [ ] **Training set** from the lab's labelled particles re-photographed on the printed sheets (part 7): about 2,500 fragments, about 1,200 rubbery fragments and about 800 fibers. There is little film and no foam yet, so new labels will be needed.
- [ ] **Train the model** (code in `training/`): fragment vs rubbery fragment vs foam, using the crop plus the shape values. Compare a classifier chain (colour feeds morphology) with one multi-task model.
- [ ] **How the model and rules combine:** the model may overrule a rule when it's confident (decided November 11). Set "confident" from validation data.
- [ ] **Tune the rule thresholds** on labelled particles photographed on the sheets. The lab records some ≥ 3:1 particles as fragments, so the fiber rule may need a thinness condition (question for the lab).
- [ ] **Example photos** for each class in the spec.

## Watch for

The model can't beat the agreement between two people labelling the same particles. Measure that agreement first (part 7).
