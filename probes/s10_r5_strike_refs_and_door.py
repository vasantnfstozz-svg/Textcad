r"""Round FIVE, part 4: the suppressed switch against a REF target, the
rollback bar across a refusal, and the door round four tightened.

  A  A ref is as much a dependency as an input -- that is the sentence round
     four's `_signature` fix is built on.  `unstrike` walks UPSTREAM through
     `f.inputs` only ("restoring an extrude whose sketch is still struck would
     bring it back broken, so the sketch comes back with it"), and a sweep's
     path is not an input.

  B  The rollback bar and a refused feature: does a refusal leave the document
     in a state the next action reads wrongly?

  C  The open door: shapes a design can legitimately have, that must still
     open.

READ-ONLY with respect to designs/.

Run: C:\Python314\python.exe probes/s10_r5_strike_refs_and_door.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from document import Document                                       # noqa: E402

CIRCLE = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]


def _rail(mm):
    return [{"kind": "path", "closed": False, "start": [0, 0],
             "segments": [{"kind": "line", "to": [0, mm]}]}]


def swept(name="t"):
    d = Document(name=name)
    d._cache = {}
    d.add("prof", "sketch", {"entities": CIRCLE, "plane": "XY", "offset": 0.0})
    d.add("rail", "sketch", {"entities": _rail(20), "plane": "XZ", "offset": 0.0})
    d.add("sw", "sweep", {"path": "rail", "full": True}, inputs=["prof"])
    return d


def line(t):
    print("\n" + "=" * 72 + f"\n{t}\n" + "=" * 72)


line("A. the suppressed switch and a REF target")

print("\n-- A1. strike the PATH: does the sweep go with it? --")
d = swept()
d.rebuild()
print(f"   sweep before: {d.get('sw').volume}")
plan = d.strike("rail")
print(f"   strike('rail') -> deleted {plan['deleted']}")
d.rebuild()
print(f"   sweep now: {d.get('sw').status} suppressed={d.get('sw').suppressed}")
d.unstrike("rail")
d.rebuild()
print(f"   unstrike('rail') -> sweep {d.get('sw').status} {d.get('sw').volume}")

print("\n-- A2. the path switched off BY HAND, then the sweep struck and"
      " restored --")
d = swept()
d.rebuild()
d.set_suppressed("rail", True)       # /api/feature/suppress, the AI, the MCP
d.rebuild()
print(f"   path off by hand -> sweep {d.get('sw').status}: "
      f"{(d.get('sw').problems or [''])[0][:60]}")
d.strike("sw")
print(f"   strike('sw') -> struck {d._struck_by.get('sw')}")
res = d.unstrike("sw")
print(f"   unstrike('sw') -> restored {res['restored']}")
d.rebuild()
print(f"   sweep {d.get('sw').status}: {(d.get('sw').problems or [''])[0][:70]}")
print("   ^ an extrude whose SKETCH is struck comes back with the sketch;"
      " a sweep whose PATH is struck does not.")

print("\n-- A3. the same shape with an INPUT, for the comparison --")
d2 = Document(name="cmp")
d2._cache = {}
d2.add("prof", "sketch", {"entities": CIRCLE, "plane": "XY", "offset": 0.0})
d2.add("ex", "extrude", {"amount": 10}, inputs=["prof"])
d2.rebuild()
d2.set_suppressed("prof", True)
d2.strike("ex")
res = d2.unstrike("ex")
print(f"   unstrike('ex') -> restored {res['restored']}  (the sketch comes back)")

print("\n-- A4. a pattern whose SEED is switched off by hand --")
d3 = Document(name="seed")
d3._cache = {}
d3.add("body", "plate", {"width": 40, "depth": 40, "thickness": 10})
d3.add("h", "with_center_hole", {"radius": 3}, inputs=["body"])
d3.add("pat", "linear_pattern", {"count": 3, "dx": 10, "seed": "h"},
       inputs=["h"])
d3.rebuild()
print(f"   built: {d3.get('pat').status} {d3.get('pat').volume}")
d3.set_suppressed("h", True)
d3.rebuild()
print(f"   seed off by hand -> pattern {d3.get('pat').status}: "
      f"{(d3.get('pat').problems or [''])[0][:70]}")
d3.strike("pat")
r = d3.unstrike("pat")
print(f"   strike+unstrike('pat') -> restored {r['restored']}")
d3.rebuild()
print(f"   pattern {d3.get('pat').status}: "
      f"{(d3.get('pat').problems or [''])[0][:70]}")

line("B. the rollback bar across a refusal")
d = Document(name="bar")
d._cache = {}
d.add("body", "plate", {"width": 40, "depth": 40, "thickness": 10})
d.add("bad", "fillet", {"radius": None, "edges": "all"}, inputs=["body"])
d.add("after", "with_center_hole", {"radius": 3}, inputs=["bad"])
d.rebuild()
for f in d.features:
    print(f"   {f.id:6s} {f.status:7s} vol={f.volume} "
          f"{(f.problems or [''])[0][:50]}")
print(f"   result bodies: {len(d.result_bodies())}  leaves {d.leaf_solid_ids()}")
d.rollback = "bad"
d.rebuild()
print("   bar parked ON the refused feature:")
for f in d.features:
    print(f"   {f.id:6s} {f.status:7s} vol={f.volume} "
          f"{(f.problems or [''])[0][:50]}")

line("C. shapes that must still OPEN")
CASES = [
    ("no spec key", {"name": "d", "features": []}),
    ("spec is null", {"name": "d", "spec": None, "features": []}),
    ("spec is an empty table", {"name": "d", "spec": {}, "features": []}),
    ("no features at all", {"name": "d", "spec": {}, "features": []}),
    ("inputs absent", {"name": "d", "features": [
        {"id": "a", "op": "plate",
         "params": {"width": 1, "depth": 1, "thickness": 1}}]}),
    ("an unknown extra key", {"name": "d", "features": [
        {"id": "a", "op": "plate", "colour": "red",
         "params": {"width": 1, "depth": 1, "thickness": 1}}]}),
    ("a param this build dropped", {"name": "d", "features": [
        {"id": "a", "op": "plate",
         "params": {"width": 1, "depth": 1, "thickness": 1,
                    "bevel": 2}}]}),
    ("duplicate ids", {"name": "d", "features": [
        {"id": "a", "op": "plate",
         "params": {"width": 1, "depth": 1, "thickness": 1}},
        {"id": "a", "op": "plate",
         "params": {"width": 2, "depth": 2, "thickness": 2}}]}),
    ("a forward input", {"name": "d", "features": [
        {"id": "b", "op": "fillet", "params": {"radius": 1}, "inputs": ["a"]},
        {"id": "a", "op": "plate",
         "params": {"width": 9, "depth": 9, "thickness": 9}}]}),
    ("parameters name a feature", {"name": "d", "parameters": {"a": {"expr": "3"}},
                                   "features": [
        {"id": "a", "op": "plate",
         "params": {"width": 1, "depth": 1, "thickness": 1}}]}),
    ("a formula naming a feature", {"name": "d",
                                    "parameters": {"w": {"expr": "base*2"}},
                                    "features": [
        {"id": "base", "op": "plate",
         "params": {"width": 1, "depth": 1, "thickness": 1}}]}),
    ("name is a number", {"name": 7, "features": []}),
    ("an op this build lacks", {"name": "d", "features": [
        {"id": "a", "op": "sprocket", "params": {}}]}),
]
for label, data in CASES:
    try:
        doc = Document.from_data(data)
        doc._cache = {}
        doc.rebuild()
        print(f"  OPENS   {label:30s} {len(doc.features)} features")
    except Exception as e:                                          # noqa: BLE001
        print(f"  REFUSED {label:30s} {type(e).__name__}: {str(e)[:60]}")
