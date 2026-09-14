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
