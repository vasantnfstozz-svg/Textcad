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

## Re-measured at HEAD 2026-09-16 (shell-segfault worktree)

STILL NOT FIXED, and the three guards that landed since the triage above
(`cc78019`, `3bbfcca`, `b9a8f8f`) are not at fault. Measured with
`probes/shell_mypart9_stall_head_probe.py`, one child per thickness, at
`TEXTCAD_KERNEL_SECONDS=60` so a stall costs a minute instead of fifteen. The
body is 381,958 mm3, 55 faces, one lump, 118.2 x 152.1 x 45.11 mm.

| t | guards | kernel | answer |
|---|---|---|---|
| 2.5 (the filed step) | 0.34 s, allowed | 60 s | stopped after 60 seconds |
| 1.6 | 0.29 s, allowed | 60 s | stopped after 60 seconds |
| 1.5 | 0.27 s, allowed | 8.7 s | leaves a broken solid (OCCT says invalid) |
| 1.7 | 0.37 s, allowed | 27.8 s | leaves a broken solid (OCCT says invalid) |

The pre-kernel guards cost under 0.4 s and correctly allow every one of these:
a cavity genuinely exists. The alternation 1.5 refuse / 1.6 stall / 1.7 refuse
/ 2.5 stall is the finding - the stall band is not an interval in `t`, so no
bound that is monotone in `t` can fence it. The row's leading candidate (refuse
when a narrow face's offset vanishes) was measured out separately in
`probes/shell_stall_precheck_probe.py`: the filed body carries 13 faces under
2 mm across, but a plain 60 x 40 x 12 plate with the same 0.6 mm rim chamfer
shells SOUND at 2.5 mm top-open (28,764.3 -> 10,711.7 mm3, one lump, health
empty), so that rule would refuse correct work. The folder stays here.
