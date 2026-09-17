# Text — sketch entity spec (Tier 2, LAUNCH-PLAN.md §4 / §8 step 1)

> **Status: approved by default while the user was out (2026-09-17, the
> scheduled Tier 2 build, tool 3 of 5 — memory `tier2-build-plan`).** Written
> before the code; the user's first try is the approval gate.

## What you click, what you see

In a sketch, press **Text** in the ribbon's Create group and click where the
word's centre should be. A small box appears at the click with **Text** and
**Height** fields; type the word (and a height in mm, default 10), press
Enter. The letters appear as outlines on the sketch plane, drawn from the
kernel's own glyph faces. Drawn inside a shape they count as a cut (the
even-odd rule every entity follows), so a name inside a plate's face sketch is
an engraving the moment it is extruded as Cut; outside, a raised word.
In the feature tree the sketch's card shows the word as an editable text
field, the height as a number, and x / y / angle as for every shape.

## The entity

```json
{"kind": "text", "text": "TEXTCAD", "size": 10, "font": "Arial",
 "x": 0, "y": 0, "rotation": 0, "mode": "add"}
```

* `text` — the word (a string; the tree edits it as text). Empty, or spaces
  only, is refused with a sentence.
* `size` — the letter height in mm (`ENTITY_FIELDS`: positive, like every
  dimension). Measured: letters stay VALID faces down to 0.1 mm, so there is
  no floor beyond "greater than 0".
* `font` — optional, default Arial. Measured on this box: Arial, Times New
  Roman, Courier New and Consolas are found; an unknown name falls back to
  Arial (the kernel warns on stderr, the shape builds).
* `x`, `y` — the word's CENTRE (build123d `Align.CENTER` both ways), so a text
  entity places like a circle does; `rotation` about that centre.
* **The kernel returns finished faces**: one per glyph piece (the dot of an
  `i` is its own face), holes as inner wires (`O` 1, `B` 2). So the word
  composes with + / − like any shape: `plate − "AB"` measured 764.099 =
  800 − 35.921 exactly, and extruding `"TEXTCAD"` gives 7 solids — one per
  piece, which the pieces rule already allows for an extrude.

## Drawing it (R1: the glyphs are the server's)

JS cannot shape a font, so the sketcher asks **`POST /api/sketch/outline`**
with the entity (at the origin, unrotated) and caches the loops it gets back
per (text, size, font), then places and turns them itself — the same
transform every entity gets (`entToSketch`). Until the answer lands the click
point is marked; the loops are drawn as outlines (no fill — a glyph's holes
would otherwise fill). Hit-testing and the even-odd mode rule use the word's
bounding box. The entity has no resize handles: the height is typed.

## Failures speak (rule 7) — the same sentences on the AI / MCP path

| Situation | Measured | What is said |
|---|---|---|
| Empty word, or spaces only | `ValueError: Unable to repositioned type NoneType…` from the kernel | "text entity needs a word — its `text` is empty; type the word to write, or remove the entity" / "'   ' has no printable letters — spaces and punctuation alone make no shape" |
| Height 0 or negative | (a negative size would build the positive one) | "text height must be greater than 0, got -3" |
| A font name that is not a string | — | "text font must be a name such as 'Arial', got 3" |
| The font cannot shape the string | — | "text entity: the font could not shape '…' — try plain letters and digits, or another font" |
| Unknown font name | falls back to Arial, builds | builds (the fallback is the kernel's; noted in §10 as a candidate for a sentence) |

## Acceptance

* `sketch.py`: `text` in `ENTITY_FIELDS` (the drift test), `ENTITY_STRINGS`,
  `_text_faces`, `entity_outlines`; `entity_schema()` carries `strings` and
  `server_outline`.
* `studio.py`: `/api/sketch/outline`.
* `sketcher.js`: the Text tool (one click + the dimension box with a text
  field), server-outline rendering with a cache, bbox hit-test, hint;
  `ribbon.js`: the button; `tree.js`: the string row.
* Tests: `tests/test_text_entity.py` (areas against the measured Arial
  figures, holes, engraving by composition, refusals, the document
  sketch → extrude, the outline endpoint) and 3 browser journeys
  (`tests/e2e/test_text_entity.py`: place a word and extrude it; engrave a
  word into a face and see the volume drop; edit the word in the tree).
