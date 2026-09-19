"""Round FOUR: the census round three ran walked PARAMETERS. This one walks
the SHAPE OF A FEATURE and of the document around it.

A file written by another build (or by a hand, or by an older TextCAD) opens
through `Document.from_data` -> `Document.add(strict=False)`, which looks at
almost nothing. Round three closed `params` that is not a dict. Everything
else a feature carries is measured here:

    id · op · inputs · suppressed · the feature itself · the features list

For each one, three questions, in the order the user meets them:

    OPEN      does `Document.from_data` raise?  (the design cannot be opened)
    REBUILD   does `Document.rebuild()` raise?  (it promises it never does)
    /api/doc  do `parameters_json`, `resolved_json`, `tree`, `to_data` raise?

Run: C:\\Python314\\python.exe probes/s10_r4_feature_shape.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from document import Document                                      # noqa: E402

PLATE = {"width": 20, "depth": 20, "thickness": 5}


def data(*feats, **extra):
    return {"name": "n", "features": list(feats), **extra}


def feat(fid="a", op="plate", params=None, inputs=None, **extra):
    out = {"id": fid, "op": op, "params": PLATE if params is None else params,
           "inputs": [] if inputs is None else inputs}
    out.update(extra)
    return out


def why(e):
    return f"{type(e).__name__}: {e}"


PYTHON_WORDS = (
    "TypeError", "AttributeError", "KeyError", "IndexError", "ZeroDivisionError",
    "is not iterable", "unhashable", "object has no attribute",
    "not enough values to unpack", "has no len()", "not subscriptable",
    "sequence item", "must be str",
)


def run(label, payload):
    row = {"case": label, "open": "-", "rebuild": "-", "doc": "-"}
    try:
        d = Document.from_data(payload)
    except Exception as e:                                        # noqa: BLE001
        row["open"] = why(e)
        print(f"{label:<44} OPEN     {row['open']}")
        return row
    try:
        d.rebuild()
    except Exception as e:                                        # noqa: BLE001
        row["rebuild"] = why(e)
    try:
        d.parameters_json()
        for f in d.features:
            d.resolved_json(f)
        d.tree()
        d.to_data()
        d.leaf_solid_ids()
        d.consumed_ids()
        d.result_bodies()
    except Exception as e:                                        # noqa: BLE001
        row["doc"] = why(e)
    states = [(f.id, f.status, (f.problems or [None])[0]) for f in d.features]
    print(f"{label:<44} rebuild={row['rebuild']}  doc={row['doc']}")
    for s in states:
        print(f"{'':<44}   {s}")
    return row


print("=" * 78)
print("the SHAPE of a feature")
print("=" * 78)
rows = []

# --- id ---------------------------------------------------------------------
for bad in (5, None, True, ["a"], {"a": 1}, 2.5):
    rows.append(run(f"id = {bad!r}", data(feat(fid=bad))))
rows.append(run("id missing", data({"op": "plate", "params": PLATE, "inputs": []})))
rows.append(run("two features, the SAME id",
                data(feat("a"), feat("a", "sphere", {"radius": 5}))))

# --- op ---------------------------------------------------------------------
for bad in (5, None, ["plate"], {"plate": 1}):
    rows.append(run(f"op = {bad!r}", data(feat(op=bad))))
rows.append(run("op missing", data({"id": "a", "params": PLATE, "inputs": []})))

# --- inputs -----------------------------------------------------------------
for bad in ("s1", 5, {"s1": 1}, True, [["s1"]], [None]):
    rows.append(run(f"inputs = {bad!r}",
                    data(feat("s1"), feat("b", "fillet", {"radius": 1}, bad))))
rows.append(run("inputs = an id that is not in the file",
                data(feat("b", "fillet", {"radius": 1}, ["ghost"]))))
rows.append(run("inputs = ITSELF (a 1-cycle)",
                data(feat("b", "fillet", {"radius": 1}, ["b"]))))
rows.append(run("inputs = a feature BELOW it (forward ref)",
                data(feat("b", "fillet", {"radius": 1}, ["c"]),
                     feat("c"))))
rows.append(run("an int id, referenced as an int input",
                data(feat(5), feat("b", "fillet", {"radius": 1}, [5]))))

# --- suppressed -------------------------------------------------------------
for bad in ("yes", 1, None, [], {"a": 1}):
    rows.append(run(f"suppressed = {bad!r}", data(feat(suppressed=bad))))

# --- the feature / the list -------------------------------------------------
rows.append(run("a feature that is a LIST", data([1, 2])))
rows.append(run("a feature that is a STRING", data("plate")))
rows.append(run("features = a dict", {"name": "n", "features": {"a": 1}}))
rows.append(run("features missing", {"name": "n"}))
rows.append(run("name missing", {"features": [feat()]}))
rows.append(run("parameters = a list", data(feat(), parameters=[1, 2])))
rows.append(run("spec = a list", data(feat(), spec=[1, 2])))

print("\n" + "=" * 78)
print("SUMMARY — rows where Python's own words reached a user-facing path")
print("=" * 78)
n = 0
for r in rows:
    hits = [k for k in ("open", "rebuild", "doc")
            if r[k] != "-" and any(w in r[k] for w in PYTHON_WORDS)]
    if hits:
        n += 1
        print(f"  {r['case']:<44} {', '.join(f'{h}={r[h]}' for h in hits)}")
print(f"\n{n} of {len(rows)} shapes answer in Python")
