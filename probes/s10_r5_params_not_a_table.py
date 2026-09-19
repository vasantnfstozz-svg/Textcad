r"""Round FIVE, part 2: the reads of `f.params` that still assume a table.

Round four closed `param_refs` ("`f.params` may be anything a foreign file
held") and `_params_dict` / `_param_items` before it.  This probe asks the
same question of EVERY entry point a design file reaches, for EVERY op, with
`params` holding a list -- the exact shape those two fixes were written for.

A row marked RAISED is a call that does not answer in a sentence: for
`rebuild` that is the whole design failing to open, because `_signature` runs
ahead of the per-feature try.

READ-ONLY with respect to designs/: every document is made in memory.

Run: C:\Python314\python.exe probes/s10_r5_params_not_a_table.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import document as D                                                # noqa: E402
from document import Document                                       # noqa: E402

BAD = [1, 2]            # what the file held where a table belongs


def one(op):
    """a document with `op` carrying BAD params, wired so the op is legal"""
    d = Document(name="t")
    d._cache = {}
    if op in D.CREATORS:
        d.add("m", op)
    elif op in D.COMBINERS:
        d.add("a", "plate", {"width": 20, "depth": 20, "thickness": 5})
        d.add("b", "plate", {"width": 10, "depth": 10, "thickness": 5})
        d.add("m", op, inputs=["a", "b"])
    else:
        d.add("body", "plate", {"width": 20, "depth": 20, "thickness": 10})
        d.add("m", op, inputs=["body"])
    d.get("m").params = list(BAD)
    return d


def call(what, fn):
    try:
        fn()
        return None
    except ValueError as e:                  # a sentence: the door answered
        return ("sentence", str(e)[:70])
    except Exception as e:                   # noqa: BLE001
        return ("RAISED", f"{type(e).__name__}: {e}")


CALLS = [
    ("rebuild", lambda d: d.rebuild()),
    ("tree", lambda d: d.tree()),
    ("to_data", lambda d: d.to_data()),
    ("parameters_json", lambda d: d.parameters_json()),
    ("resolved_json", lambda d: d.resolved_json(d.get("m"))),
    ("param_refs", lambda d: Document.param_refs(d.get("m"))),
    ("remove_plan", lambda d: d.remove_plan("m")),
    ("rename", lambda d: d.rename("m", "m2")),
    ("consumed_ids", lambda d: d.consumed_ids()),
    ("leaf_solid_ids", lambda d: d.leaf_solid_ids()),
    ("rename_parameter", lambda d: d.rename_parameter("wall", "wall2")),
    ("delta_features", lambda d: d.delta_features("m")),
]

ops = sorted(set(D.CREATORS) | set(D.MODIFIERS) | set(D.COMBINERS) | {"move"})
raised = []
for op in ops:
    for label, fn in CALLS:
        d = one(op)
        if label == "rename_parameter":
            d.parameters["wall"] = {"expr": "5"}
        r = call(label, lambda: fn(d))
        if r and r[0] == "RAISED":
            raised.append((op, label, r[1]))

print(f"{len(ops)} ops x {len(CALLS)} calls = {len(ops) * len(CALLS)} rows\n")
print(f"RAISED (an answer in Python, not a sentence): {len(raised)}")
seen = {}
for op, label, msg in raised:
    seen.setdefault((label, msg), []).append(op)
for (label, msg), who in sorted(seen.items()):
    print(f"\n  {label}()  ->  {msg}")
    print(f"     ops: {', '.join(who)}")

# ---------------------------------------------------------------------------
print("\n" + "=" * 72)
print("Does the DESIGN OPEN?  Document.from_data on the same shape")
print("=" * 72)
for op in ("import_stl", "import_step", "mirror", "extrude"):
    data = {"name": "t", "spec": {},
            "features": [{"id": "m", "op": op, "params": BAD, "inputs": []}]}
    try:
        doc = Document.from_data(data)
        doc._cache = {}
        ok = doc.rebuild()
        print(f"  {op:12s} opens, rebuild ok={ok}, row: "
              f"{(doc.get('m').problems or ['(none)'])[0][:70]}")
    except Exception as e:                                          # noqa: BLE001
        print(f"  {op:12s} *** {type(e).__name__}: {e}")

# ...and the same through the real file door, including a sound feature beside
# it -- the point of round four's F4 is that a design whose OTHER features are
# fine must still open.
print("\nA sound design with ONE damaged import feature in it:")
data = {"name": "t", "spec": {}, "features": [
    {"id": "body", "op": "plate",
     "params": {"width": 20, "depth": 20, "thickness": 5}, "inputs": []},
    {"id": "imp", "op": "import_step", "params": BAD, "inputs": []},
]}
try:
    doc = Document.from_data(data)
    doc._cache = {}
    doc.rebuild()
    print("  opens; rows:")
    for f in doc.features:
        print(f"    {f.id:6s} {f.status:7s} {(f.problems or [''])[0][:60]}")
except Exception as e:                                              # noqa: BLE001
    print(f"  *** the whole design failed to open: {type(e).__name__}: {e}")
