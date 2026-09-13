# process-died: pump-impeller, seed 47244, step 56

The server process died with OpenCASCADE access violation (segfault) (0xC0000005) while handling:

`POST /api/edit`

```json
{
 "feature_id": "hub_seat",
 "param": "z",
 "value": 17.5
}
```

## What the child said before it went

```
C:\Users\VasanSeenivasan\AppData\Roaming\Python\Python314\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
  from starlette.testclient import TestClient as TestClient  # noqa
```

(the whole tail is in `child-output.txt`)

## Reproduce

    python tests/journeys.py --designs pump-impeller --seed 47244 --steps 56 --journeys 1

There is no before.tcad.json: the process was gone before it could be written. `journey.json` holds every step from the start of the design, in order; replaying them (`steps`) rebuilds the state. In the app this is what the crash supervisor (supervise.py) recovers from.
