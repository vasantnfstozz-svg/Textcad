# hang: autonomiq-panel, seed 18884, step 2

The server process took longer than 600 s without answering (the runner killed it) while handling:

`POST /api/feature/add`

```json
{
 "id": "j2_shell",
 "op": "shell",
 "params": {
  "thickness": 2.7,
  "open_face": "none"
 },
 "inputs": [
  "j1_scale"
 ]
}
```

## What the child said before it went

```
C:\Users\VasanSeenivasan\AppData\Roaming\Python\Python314\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
  from starlette.testclient import TestClient as TestClient  # noqa
```

(the whole tail is in `child-output.txt`)

## Reproduce

    python tests/journeys.py --library --designs autonomiq-panel --seed 18884 --steps 2 --journeys 1

There is no before.tcad.json: the process was gone before it could be written. `journey.json` holds every step from the start of the design, in order; replaying them (`steps`) rebuilds the state. In the app this is what the crash supervisor (supervise.py) recovers from.

---

## Fixed 2026-09-14 — NOT a product bug: the runner's ceiling, not the kernel

The runner killed this child at 600 s while the guard's own 900 s budget was
still running, so nobody ever learned what the kernel was doing. `751db79`
lifted the ceiling to the budget plus the time a fresh worker needs to start.

Measured today: the shell is REFUSED by the kernel — "shell: walls of 2.7 mm
do not fit this body", the sentence the user should read — and takes 692 s
through the API (879 s standalone, `probes/shell_slow_panel.py`) to say so.
The body is one lump, 675 faces, 312 x 162 x 15 mm; 2 x 2.7 mm fits its 15 mm
thinnest extent comfortably, so nothing before the kernel could have known.

Under the shipped budget that is an ordinary red row, not a hang, and the
replayed journey files no finding at all:

    python tests/journeys.py --replay bugs/fixed/20260913-212515-autonomiq-panel-s18884-crash
      [autonomiq-panel s18884 #1] add  scale  -> 200   2153 ms
      [autonomiq-panel s18884 #2] add  shell  -> 200 691822 ms
    the step passes now

(That line only runs at all since 2026-09-14: a killed child writes no
`before.tcad.json`, and `--replay` used to stop there. It now opens the design
the journey opened and re-sends the recorded steps.)

The one thing to keep an eye on: 879 s sits about 21 s under the 900 s budget,
so a slower box turns this correct refusal into "was stopped after 15
minutes". `tests/test_kernel_guard.py` now asserts the budget stays above 879.
