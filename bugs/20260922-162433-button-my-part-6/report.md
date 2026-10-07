# Bug report: my-part-6

Filed from the app at 2026-09-22 16:24:33, tab running ui v232.

## What the user said

> when i select offset plane, and i draw some shapes, and i am trying to extrude the shapes , its not working

## The design

8 features, 1 bodies on screen, healthy; opened from nothing (a new design); 25 undo steps.

## The last things this tab did (oldest first; a read that succeeded is not kept)

- `POST /api/feature/strike` -> 200 in 41 ms  `{"feature_id":"sketch2"}`
- `POST /api/feature/strike` -> 200 in 36 ms  `{"feature_id":"sketch2","restore":true}`
- `POST /api/tool/plan` -> 200 in 95 ms  `{"tool":"loft","sketch_id":"sketch1","sketch_ids":["sketch1"]}`
- `POST /api/tool/plan` -> 200 in 175 ms  `{"tool":"loft","sketch_id":"sketch1","sketch_ids":["sketch1","sketch2"]}`
- `POST /api/feature/add` -> 200 in 175 ms  `{"id":"loft1","op":"loft","params":{"ruled":false},"inputs":["sketch1","sketch2"]}`
- `POST /api/feature/params` -> 200 in 83 ms  `{"feature_id":"loft1","params":{"ruled":false}}`
- `POST /api/feature/strike` -> 200 in 49 ms  `{"feature_id":"loft1"}`
- `POST /api/tool/plan` -> 200 in 33 ms  `{"tool":"extrude","sketch_id":"sketch1"}`
- `POST /api/feature/add` -> 200 in 36 ms  `{"id":"extrude2","op":"extrude","params":{"amount":88.07,"both":false,"amount2":0,"taper":0,"flip":false,"through":false},"inputs":["sketch1"]}`
- `POST /api/face-feature` -> 200 in 60 ms  `{"body":"extrude2","face":2,"center":[0,0,88.07],"area":4790.93,"point":[4.6059482723255485,2.2921224599011225,88.06999969482422]}`
- `POST /api/tool/plan` -> 200 in 25 ms  `{"tool":"sketch","plane":"XZ","offset":0}`
- `POST /api/feature/add` -> 200 in 52 ms  `{"id":"plane2","op":"offset_plane","params":{"plane":"XZ","offset":261},"inputs":[]}`
- `POST /api/sketch/snap` -> 200 in 33 ms  `{"plane":"XY","offset":0,"frame":{"origin":[0,-144.8,0],"x_dir":[1,0,0],"y_dir":[0,0,1],"z_dir":[0,-1,0]}}`
- `POST /api/feature/add` -> 200 in 39 ms  `{"id":"sketch3","op":"sketch","params":{"plane":"plane2","offset":0,"entities":[{"kind":"rectangle","mode":"add","x":-12.5,"y":-5,"w":55,"h":60,"rotation":0}]},`
- `POST /api/tool/plan` -> 200 in 43 ms  `{"tool":"extrude","sketch_id":"sketch3"}`

## What the browser reported

- Struck out "extrude1" (with plane1, sketch2) — the geometry is removed, the row stays. ↩ on the row brings it back.
- Restored "plane1" (with sketch2) — the geometry is back.
- Loft: click a sketch profile in the viewport — your pick, nothing is chosen for you. Esc cancels.
- ⚠ Finish the Loft first — press OK or Cancel in its panel (flashing on the right).
- Struck out "sketch2" (with plane1) — the geometry is removed, the row stays. ↩ on the row brings it back.
- Restored "sketch2" (with plane1) — the geometry is back.
- Loft: click a sketch profile in the viewport — your pick, nothing is chosen for you. Esc cancels.
- Loft created — editable in the feature tree.
- Struck out "loft1" (with plane1, sketch2) — the geometry is removed, the row stays. ↩ on the row brings it back.
- 🐞 Saved to bugs/20260922-162226-button-my-part-6. Keep going — a later fix session reads that folder.
- Extrude created — editable in the feature tree.
- Offset plane "plane2" placed 261 mm from the XZ plane. Press Create Sketch to draw on it now, or click the plane in the viewport any time.
- Sketching on the offset plane "plane2".
- Sketch "sketch3" created. Use Create → Extrude or Revolve to turn it into a solid.
- ⚠ Extrude cannot start: sketch: plane must be "XY", "XZ" or "YZ".

## Files

- `doc.tcad.json`
- `state.json`
- `report.md`
- `screenshot.png`

## Reproduce

    python tests/journeys.py --replay bugs/20260922-162433-button-my-part-6

That opens `doc.tcad.json` in a fresh in-process server and runs the body checks; `state.json` carries the tree with every status and problem sentence as the user saw it. Open the design in Studio to look at it in 3D.
