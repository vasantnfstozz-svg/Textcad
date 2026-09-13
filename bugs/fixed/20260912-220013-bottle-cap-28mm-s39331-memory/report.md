# memory: bottle_cap_28mm, seed 39331, step 5 — the laptop died

Filed by hand: the runner of the day had no oracle for it and wrote "clean".

    [bottle_cap_28mm s39331 #5] add  plate  -> 200  1351644 ms

`POST /api/feature/add` `{"id": "j3_plate", "op": "plate", "params": {"width": 67.9,
"depth": 16.9, "thickness": 6.4}, "inputs": []}` on the live design after two
edits (rib_placed y=0), a base circle sketch r 8.3 and an extrude 7.2. The plate
itself built in 1 ms. The 22 minutes and 34 -> 44 GB were the spec check:
`spec.symmetry = 24` -> `inspector.is_rotationally_symmetric(result_shape, 24)`
-> `compound - rotated compound` on three overlapping bodies (cap, cylinder,
plate), and ShapeUpgrade_UnifySameDomain on the leftovers. Windows logged four
Resource-Exhaustion events (21:15-21:47, python.exe 44 GB on a 16 GB box); the
unexpected shutdown came at 22:00:13 (Kernel-Power 41 on the reboot at 22:12).

## Fixed

- `inspector.is_rotationally_symmetric`: two necessary gates before the boolean
  (rotation keeps the bounding box; every sampled vertex lands on or inside the
  shape) and the proof runs under `SkipClean` with `cut` (not `-`, which unpacks
  a compound's members). The plate case answers False in 11 ms; the same
  journey's step 5 takes 203 ms. All ten live designs with a symmetry spec keep
  their verdict (`probes/symmetry_gate_corpus.py`).
- `tests/journeys.py`: `HANG_MS` (120 s) and `MEMORY_BUG_MB` (2 GB growth in one
  request) are findings even at 200; every child runs inside a Windows Job
  object with a 6 GB ceiling (`--mem-gb`), and a child that dies AT its ceiling
  is filed as a `memory` finding instead of "the box gave up".

## Reproduce (now clean)

    python tests/journeys.py --library --designs bottle_cap_28mm --seed 39331 --steps 6 --journeys 1

Tests: tests/test_core.py (the two `gates` tests), tests/test_journeys.py (the
three machine-oracle tests). Probes: probes/memcap.py (the standalone ceiling),
probes/journey_39331_trace.py, probes/journey_39331_stack.py,
probes/symmetry_gate_probe.py, probes/symmetry_gate_corpus.py.
