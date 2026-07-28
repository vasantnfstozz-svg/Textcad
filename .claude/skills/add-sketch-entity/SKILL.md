---
name: add-sketch-entity
description: Checklist for adding a NEW 2D sketch entity kind (shape or drawing tool) to TextCAD's sketcher — backend geometry, canvas tool, rendering, hit-testing, AI author. Use for new sketch shapes like text, points, construction lines, fillets-in-sketch.
---

# Adding a new 2D sketch entity — the full checklist

1. **Probe** the build123d 2D API in scratch (algebra-mode object or
   BuildSketch/BuildLine recipe; confirm `.area > 0` and it composes with +/-).
2. **sketch.py** — add the kind to `_entity()` (or a helper like `_path_face`).
   JSON-safe params only; clear ValueError messages (they feed the repair loop).
3. **static/js/sketcher.js**:
   - `DEFAULT_FIELDS` entry (sensible defaults).
   - palette button in static/index.html (`data-shape="<kind>"`).
   - placement: 2-click via `twoClickEntity()` or a custom flow (see the
     polygon/path tools for multi-click patterns).
   - `entitySVG()` rendering (remember: SVG y is flipped, world +y is up;
     use `vector-effect="non-scaling-stroke"` for zoom-stable lines).
   - `hitTest()` case (rotation-aware local frame if the entity rotates).
   - `updateHint()` instruction text for the tool.
4. **author.py** — extend the SKETCH WORKFLOW entity list in AUTHOR_PROMPT.
5. **Tests** — `tests/test_e2_sketch.py`: entity builds (area > 0), invalid
   params raise, works in a Document sketch -> extrude.
6. `python -m pytest tests -q` green; bump `main.js?v=N`; Ctrl+F5.
