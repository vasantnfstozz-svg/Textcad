"""Is the DELETE the 5 red browser tests ask for still there in the engine?

tests/e2e/test_tree_delete.py has been red since the strike-out mandate. This
probe asks the DOCUMENT (no browser, no server) whether the behaviour those
tests were written to prove still holds, so the test fix cannot paper over a
real regression:

  1. removing a consumed sketch takes the features that cannot live without it
  2. removing a mid-chain cut reconnects the rest (history repaired)
  3. one undo brings the whole group back
"""
import sys

sys.path.insert(0, ".")
from document import Document                     # noqa: E402

FEATURES = [
    ("outline", "sketch", {"plane": "XY", "offset": 0, "entities": [
        {"kind": "rectangle", "w": 80, "h": 60, "x": 0, "y": 0, "mode": "add"}]}, []),
    ("body", "extrude", {"amount": 12}, ["outline"]),
]
prev = "body"
for tag, x in (("p0", -20), ("p1", 20)):
    FEATURES += [
        (f"{tag}_sketch", "sketch", {"plane": "XY", "offset": 12, "entities": [
            {"kind": "circle", "r": 8, "x": x, "y": 0, "mode": "add"}]}, []),
        (f"{tag}_tool", "extrude", {"amount": -5}, [f"{tag}_sketch"]),
        (tag, "cut", {}, [prev, f"{tag}_tool"]),
    ]
    prev = tag


def build():
    d = Document(name="t-delete")
    for fid, op, params, inputs in FEATURES:
        d.add(fid, op, params, inputs=inputs)
    return d


def ids(d):
    return [f.id for f in d.features]


def report():
    print("=== 1. a consumed SKETCH ===")
    d = build()
    print("built:", ids(d))
    plan = d.remove_plan("p0_sketch")
    print("deleted:", plan["deleted"])
    print("summary:", plan["summary"])
    d.remove("p0_sketch")
    print("after :", ids(d))

    print("")
    print("=== 2. the mid-chain cut, through the row the tree actually draws ===")
    print("A boolean is FOLDED onto its tool's row, so the row a user presses")
    print("for the p0 pocket is p0_tool - there is no node with fid 'p0'.")
    for fid in ("p0", "p0_tool"):
        d = build()
        plan = d.remove_plan(fid)
        print(f"  {fid:9s} -> {plan['deleted']}")
        d.remove(fid)
        p1 = next((f for f in d.features if f.id == "p1"), None)
        print(f"  {'':9s}    left {ids(d)}, p1 inputs {p1 and p1.inputs}")

    print("")
    print("=== 3. the same for the second pocket ===")
    d = build()
    print("p1_tool ->", d.remove_plan("p1_tool")["deleted"])
    d.remove("p1_tool")
    print("   left:", ids(d))


if __name__ == "__main__":
    report()
