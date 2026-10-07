# Bug report: my-part-6

Filed from the app at 2026-09-22 16:22:26, tab running ui v232.

## What the user said

> for this design i changed plane from first sketch to upper one, then i made a another sketch in different height, then i used loft to connect both sketch it came perfectly, but when i deleted loft in the feature tree, other sketch is also getting deletdd, the behaviour is not predictable, other sketch or extrude also getting deleted when i am doing some changews int the tree,

## The design

5 features, 0 bodies on screen, healthy; opened from nothing (a new design); 25 undo steps.

## The last things this tab did (oldest first; a read that succeeded is not kept)

- `POST /api/feature/add` -> 200 in 24 ms  `{"id":"sketch2","op":"sketch","params":{"plane":"plane1","offset":0,"entities":[{"kind":"rectangle","mode":"add","x":30,"y":-25,"w":60,"h":50,"rotation":0}]},"i`
- `POST /api/feature/strike` -> 200 in 53 ms  `{"feature_id":"extrude1"}`
- `POST /api/feature/strike` -> 200 in 23 ms  `{"feature_id":"plane1","restore":true}`
- `POST /api/tool/plan` -> 200 in 56 ms  `{"tool":"loft","sketch_id":"sketch2","sketch_ids":["sketch2"]}`
- `POST /api/tool/plan` -> 200 in 137 ms  `{"tool":"loft","sketch_id":"sketch2","sketch_ids":["sketch2","sketch1"]}`
- `POST /api/feature/add` -> 200 in 99 ms  `{"id":"loft1","op":"loft","params":{"ruled":false},"inputs":["sketch2","sketch1"]}`
- `POST /api/feature/params` -> 200 in 28 ms  `{"feature_id":"loft1","params":{"ruled":false}}`
- `POST /api/feature/remove` -> 200 in 38 ms  `{"feature_id":"loft1","mode":"strict"}`
- `POST /api/feature/strike` -> 200 in 41 ms  `{"feature_id":"sketch2"}`
- `POST /api/feature/strike` -> 200 in 36 ms  `{"feature_id":"sketch2","restore":true}`
- `POST /api/tool/plan` -> 200 in 95 ms  `{"tool":"loft","sketch_id":"sketch1","sketch_ids":["sketch1"]}`
- `POST /api/tool/plan` -> 200 in 175 ms  `{"tool":"loft","sketch_id":"sketch1","sketch_ids":["sketch1","sketch2"]}`
- `POST /api/feature/add` -> 200 in 175 ms  `{"id":"loft1","op":"loft","params":{"ruled":false},"inputs":["sketch1","sketch2"]}`
- `POST /api/feature/params` -> 200 in 83 ms  `{"feature_id":"loft1","params":{"ruled":false}}`
- `POST /api/feature/strike` -> 200 in 49 ms  `{"feature_id":"loft1"}`

## What the browser reported

- 🗑 Deleted 'plate1_at', and 7 dependent features that cannot be kept without it (plane1, sketch2, loft1, plane2, sketch3, revolve1 and 1 more). 8 features removed, 3 left. Undo (Ctrl+Z) puts it back.
- Struck out "plate1" — the geometry is removed, the row stays. ↩ on the row brings it back.
- Restored "extrude1" — the geometry is back.
- Offset plane "plane1" placed 113.4 mm from the XY plane. Press Create Sketch to draw on it now, or click the plane in the viewport any time.
- Sketching on the offset plane "plane1".
- Sketch "sketch2" created. Use Create → Extrude or Revolve to turn it into a solid.
- Struck out "extrude1" (with plane1, sketch2) — the geometry is removed, the row stays. ↩ on the row brings it back.
- Restored "plane1" (with sketch2) — the geometry is back.
- Loft: click a sketch profile in the viewport — your pick, nothing is chosen for you. Esc cancels.
- ⚠ Finish the Loft first — press OK or Cancel in its panel (flashing on the right).
- Struck out "sketch2" (with plane1) — the geometry is removed, the row stays. ↩ on the row brings it back.
- Restored "sketch2" (with plane1) — the geometry is back.
- Loft: click a sketch profile in the viewport — your pick, nothing is chosen for you. Esc cancels.
- Loft created — editable in the feature tree.
- Struck out "loft1" (with plane1, sketch2) — the geometry is removed, the row stays. ↩ on the row brings it back.

## Files

- `doc.tcad.json`
- `state.json`
- `report.md`
- `screenshot.png`

## Reproduce

    python tests/journeys.py --replay bugs/20260922-162226-button-my-part-6

That opens `doc.tcad.json` in a fresh in-process server and runs the body checks; `state.json` carries the tree with every status and problem sentence as the user saw it. Open the design in Studio to look at it in 3D.
