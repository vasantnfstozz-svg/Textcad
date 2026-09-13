# process-died: planetary-ring, seed 47276, step 33

The server process died with exit code 4294967295 (0xFFFFFFFF) while handling:

`POST /api/edit`

```json
{
 "feature_id": "space_sketch",
 "param": "offset",
 "value": 0
}
```

## What the child said before it went

```
C:\Users\VasanSeenivasan\AppData\Roaming\Python\Python314\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
  from starlette.testclient import TestClient as TestClient  # noqa
```

(the whole tail is in `child-output.txt`)

## Reproduce

    python tests/journeys.py --library --designs planetary-ring --seed 47276 --steps 33 --journeys 1

There is no before.tcad.json: the process was gone before it could be written. `journey.json` holds every step from the start of the design, in order; replaying them (`steps`) rebuilds the state. In the app this is what the crash supervisor (supervise.py) recovers from.
