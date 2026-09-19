r"""Round FIVE, part 3: `_signature` promises never to raise.

`rebuild` signs EVERY feature before it builds any of them --

    for f in self.features:
        sigs[f.id] = self._signature(f, sigs)

-- ahead of the per-feature try.  Anything `_signature` raises is therefore
not a red row, it is the whole design failing to open (studio's
`_rebuild_and_mesh` has no try either).  Round four closed one such hole
(`_fail_key`'s `','.join` on a numeric input id).  This probe walks every
shape a JSON file can legally hold through the SAME function.

READ-ONLY with respect to designs/.

Run: C:\Python314\python.exe probes/s10_r5_signature_never_raises.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from document import Document                                       # noqa: E402

# Every value below is something `json.load` can hand back.
SHAPES = [
    ("params is a list",          {"op": "plate", "params": [1, 2]}),
    ("params is a string",        {"op": "plate", "params": "wide"}),
    ("params is a number",        {"op": "plate", "params": 7}),
    ("import_stl, params list",   {"op": "import_stl", "params": [1, 2]}),
    ("import_step, params list",  {"op": "import_step", "params": [1, 2]}),
    ("import_step, params str",   {"op": "import_step", "params": "x.step"}),
    ("import_step, file is null", {"op": "import_step",
                                   "params": {"file": "a\x00b"}}),
    ("import_step, file is list", {"op": "import_step",
                                   "params": {"file": [1, 2]}}),
    ("import_step, file is None", {"op": "import_step",
                                   "params": {"file": None}}),
    ("params holds NaN",          {"op": "plate",
                                   "params": {"width": float("nan"),
                                              "depth": 1, "thickness": 1}}),
    ("params deeply nested",      {"op": "plate",
                                   "params": {"width": [[[[[1]]]]],
                                              "depth": 1, "thickness": 1}}),
    ("inputs holds a number",     {"op": "fillet", "params": {"radius": 1},
                                   "inputs": [1]}),
    ("inputs holds a list",       {"op": "fillet", "params": {"radius": 1},
                                   "inputs": [["a"]]}),
    ("sweep path is a number",    {"op": "sweep", "params": {"path": 3}}),
    ("sweep path is a list",      {"op": "sweep", "params": {"path": ["a"]}}),
    ("sweep path is a dict",      {"op": "sweep", "params": {"path": {"a": 1}}}),
    ("mirror seed is a list",     {"op": "mirror", "params": {"seed": ["a"]}}),
    ("suppressed is a word",      {"op": "plate",
                                   "params": {"width": 1, "depth": 1,
                                              "thickness": 1},
                                   "suppressed": "yes"}),
]

print("shape                          _signature     rebuild")
print("-" * 72)
bad = []
for label, feat in SHAPES:
    data = {"name": "t", "spec": {}, "features": [
        {"id": "base", "op": "plate",
         "params": {"width": 20, "depth": 20, "thickness": 5}, "inputs": []},
        {"id": "m", **feat},
    ]}
    # the file has to survive json first: this is what a design file IS
    try:
        data = json.loads(json.dumps(data))
    except ValueError:
        pass
    sig_r, reb_r = "ok", "ok"
    try:
        doc = Document.from_data(data)
        doc._cache = {}
    except ValueError as e:
        print(f"{label:30s} refused at the door: {str(e)[:30]}")
        continue
    except Exception as e:                                          # noqa: BLE001
        print(f"{label:30s} DOOR RAISED {type(e).__name__}")
        bad.append((label, "from_data", f"{type(e).__name__}: {e}"))
        continue
    try:
        doc._signature(doc.get("m"), {})
    except Exception as e:                                          # noqa: BLE001
        sig_r = f"RAISED {type(e).__name__}"
        bad.append((label, "_signature", f"{type(e).__name__}: {e}"))
    try:
        doc.rebuild()
    except Exception as e:                                          # noqa: BLE001
        reb_r = f"RAISED {type(e).__name__}"
        bad.append((label, "rebuild", f"{type(e).__name__}: {e}"))
    print(f"{label:30s} {sig_r:14s} {reb_r}")

print(f"\nshapes that answer in Python instead of a row: {len(bad)}")
for label, where, msg in bad:
    print(f"  {label:30s} {where:12s} {msg}")
