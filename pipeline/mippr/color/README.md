# Part 4: Colour

Give each particle one of the 13 colour classes, plus its second colour and that colour's share.

**Method:** rules (thresholds on Lab colour, plus opacity). A model only if rules fall short.

Classes: clear, white, black, grey, blue, green, red, yellow, orange, brown, pink, purple, multicolor.

## In → Out

| In (from parts 1–3) | Out (to the export, review and part 5) |
|---|---|
| The white-balanced image, the outline, `opacity` | `color_label`, `color_confidence`, `color_secondary`, `color_secondary_fraction` |

## How it decides (`rules.py`)

1. Every pixel inside the outline (one edge pixel removed) is sorted into a class by lightness, chroma and hue.
2. The most common class is the label, and the next most common is the second colour (always recorded).
3. **Multicolor:** the second colour covers 20% or more and is clearly different. It must not be a shade of the first, and the two must be at least ΔE 25 apart.
4. **Clear:** mostly see-through (opacity under 0.5) and nearly colourless.
5. **Confidence:** the share of pixels that agree. Borderline particles go to review. There's no automatic "unknown"; a reviewer can set one.

## To build

- [ ] **Fit the hue and lightness ranges** to the lab's labelled particles (about 4,600 with colours; part 7). Until then they are provisional (`COLOR_RULES_VERSION = "0.1-provisional"`).
- [ ] **A reference swatch and Lab range per class**, written into the spec, once the colour reference on the sheets is settled (part 1).
- [ ] **Check clear vs white** on real photos on both backgrounds.
- [ ] **Set the `flag_low_confidence` threshold** from validation data.

## Watch for

Wrong white balance moves particles across colour classes. Fix it in part 1, not here.
