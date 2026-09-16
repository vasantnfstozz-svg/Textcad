# kernel-stalled: my-part-9, seed 96223, step 19

'j7_shell' (shell): shell: walls of 2.5 mm was stopped after 15 minutes and nothing was changed. Hollowing a body with hundreds of faces can take that long. Try a thinner wall, or shell the body before the features that added those faces.

## The step that broke it

`POST /api/feature/add`

```json
{
 "id": "j7_shell",
 "op": "shell",
 "params": {
  "thickness": 2.5,
  "open_face": "top"
 },
 "inputs": [
  "j1_chamfer"
 ]
}
```

## Reproduce

`before.tcad.json` is the design this finding was measured against; `after.tcad.json` (if present) is what it became.

    python tests/journeys.py --replay bugs/20260916-011919-my-part-9-s96223-step19

That opens `before.tcad.json` in a fresh in-process server, sends the step above and runs the same checks. The whole journey is in `journey.json` (`steps`), in order.

## Notes (not bugs)

- step 19 (add shell) took 900098 ms


## Triage 2026-09-16 (fixing chat)

NOT fixed. Measured with `probes/shell_thin_wall_probe.py` at a 90 s budget:
1.5 and 1.7 are refused as invalid in 12-30 s; 1.6, 1.8, 1.85, 1.9, 2.0, 2.1,
2.5 and 5 all stall; 3.0 is refused after 45 s. The body's thinnest web is
3.856 mm and its deepest material 15.6 mm, so this is not a wall the offset
does not fit — every one of these shells has a cavity to make — and the stall
band is not monotonic. LAUNCH-PLAN.md section 10 carries it as P2; this folder
stays as the repro. The body is at `probes/_thin_mypart9.brep`.
