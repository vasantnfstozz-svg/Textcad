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
7. **Run** `python -m pytest tests -q` — all green.
8. Restart studio, smoke-test via API if the op has UI implications.
