---
name: add-operation
description: Checklist for adding a NEW CAD operation (block/modifier/combiner) to TextCAD so it appears everywhere at once — feature tree, ribbon UI, AI author, MCP. Use whenever adding ops like a new primitive, transform, or boolean.
---

# Adding a new CAD operation — the full checklist

An op only "exists" when ALL of these are done. Skipping one leaves it
half-invisible (works in tests, missing in UI, unknown to the AI).

1. **Probe** the underlying build123d API in a scratch script first.
2. **blocks.py** — implement as a small function:
   - creator: plain params -> Part; modifier: `(part, **params) -> Part`.
   - validate inputs with clear ValueError messages (they feed the AI repair loop).
   - add to `EXPORTS` dict.
   - add a case to the `__main__` self-test.
3. **document.py** — register in `CREATORS` (name tuple) or `MODIFIERS` or
   `COMBINERS`. That makes it legal in feature trees, the op catalog, and MCP
   automatically.
4. **Frontend** (`static/js/`):
   - `icons.js`: add to OP_ICONS + TOOL_NAMES.
   - `ribbon.js`: add to the right tab/group in TABS.
   - bump `main.js?v=N` in static/index.html.
5. **author.py** — if the op needs usage guidance (conventions, pitfalls,
   when to prefer it), add a line to AUTHOR_PROMPT rules.
6. **Tests** — add to `tests/test_e1_ops.py` (or a new file): healthy output,
   semantic check (volume/size/symmetry), invalid-args raise, works inside a
   Document tree.
7. **THE GAUNTLET (mandatory for any op that consumes a face, profile or
   body).** One example is one cell of a grid: an op is the feature TIMES
   every geometry a user can feed it. Run it over the whole corpus in
   `tests/gauntlet.py`:

       from gauntlet import BODIES, planar_faces, assert_op
       for name, make in BODIES.items():
           solid = make()
           for idx, face, center, normal in planar_faces(solid):
               for param in (...):          # the op's own parameter grid
                   assert_op(f"{name}.f{idx} p={param}",
                             lambda: my_op(solid, center, normal, param))

   `assert_op` enforces the contract: a HEALTHY solid, or a friendly
   ValueError. A raw kernel exception, or a "successful" invalid/non-manifold
   solid, is a test failure. See `tests/test_taper_gauntlet.py` for the shape
   of it — that file caught three real defects the day it was written.
   **When a real bug is found, add its geometry to `BODIES`** so the corpus
   only ever grows (it already carries the fused-taper seam body that broke
   extrude, precisely because a box never would have).
8. **Run** `python -m pytest tests -q` — all green.
9. Restart studio, smoke-test via API if the op has UI implications.
