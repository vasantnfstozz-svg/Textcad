r"""Round FIVE, part 7: the verdict on round four's ref signature, and undo.

  1  A REF CHAIN. Round four's fix folds `sigs[ref]` into the signature. A
     path sketch drawn ON A BODY carries that body in its own signature, so
     the chain should hold two deep: edit the BODY, and the sweep that follows
     a path drawn on it must rebuild. Measured, not reasoned.

  2  `sweep_face` end to end -- REF_PARAMS lists it, but nothing had built one
     and edited its rail.

  3  UNDO / REDO across a REFUSED feature: does a refusal leave the document
     in a state the next action reads wrongly?

READ-ONLY with respect to designs/ (the API runs on in-memory documents).

Run: C:\Python314\python.exe probes/s10_r5_ref_chain_and_undo.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient                           # noqa: E402

import studio                                                       # noqa: E402
from document import Document                                       # noqa: E402

CIRC = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]


def rail(mm, z0=0.0):
    """a straight path in the XZ sketch plane, from (0, z0) to (0, z0 + mm)"""
    return [{"kind": "path", "closed": False, "start": [0, z0],
             "segments": [{"kind": "line", "to": [0, z0 + mm]}]}]


def line(t):
    print("\n" + "=" * 72 + f"\n{t}\n" + "=" * 72)


line("1. a REF CHAIN: a named PARAMETER drives the path, two features deep")
shared: dict = {}


def chained(shift):
    """`shift` -> the rail sketch's own `offset` (a formula) -> the rail's
    signature -> the sweep's `refs`. Nothing about `shift` is in the sweep's
    own parameters, so only the folded-in reference can carry it."""
    d = Document(name="chain")
    d._cache = shared                 # ONE cache, as the process really has
    d.set_parameter("shift", str(shift))
    d.add("prof", "sketch", {"entities": CIRC, "plane": "XY", "offset": 0.0}, [])
    d.add("rail", "sketch", {"entities": rail(20), "plane": "XZ",
                             "offset": "shift"}, [])
    d.add("sw", "sweep", {"path": "rail", "full": True}, ["prof"])
    return d


def where(d):
    bb = d._parts.get("sw")
    if bb is None:
        return "(not built)"
    b = bb.bounding_box()
    return f"y {round(b.min.Y, 3)}..{round(b.max.Y, 3)}"


a = chained(0)
a.rebuild()
print(f"   shift 0 -> {a.get('sw').status} vol={a.get('sw').volume} {where(a)}"
      f"  {(a.get('sw').problems or [''])[0][:45]}")
b = chained(3)
b.rebuild()
print(f"   shift 3 -> {b.get('sw').status} vol={b.get('sw').volume} {where(b)}"
      f"  {(b.get('sw').problems or [''])[0][:45]}")
print(f"   the two sweeps share one signature? "
      f"{a._sigs.get('sw') == b._sigs.get('sw')}   (must be False)")

print()
print("   ...and the same document, the PARAMETER changed")
c = chained(0)
c.rebuild()
was = where(c)
c.set_parameter("shift", "3")
c.rebuild()
print(f"   {was} -> {where(c)}   (must move by 3)")

line("2. sweep_face end to end, on the shape its own tests build")


def faced(mm):
    d = Document(name="sf")
    d._cache = shared2
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
    d.add("big", "sketch", {"plane": "XZ", "offset": 0, "entities": [
        {"kind": "path", "closed": False, "x": 0, "y": 6, "start": [0, 0],
         "segments": [{"type": "line", "to": [0, mm]},
                      {"type": "line", "to": [mm, mm]}]}]}, [])
    d.rebuild()
    top = max(d._parts["b"].faces(), key=lambda f: f.center().Z)
    d.add("sf", "sweep_face",
          {"face_center": list(top.center()), "face_normal": [0, 0, 1],
           "path": "big", "full": True}, ["b"])
    return d


shared2: dict = {}
for mm in (40, 60):
    d = faced(mm)
    d.rebuild()
    print(f"   rail legs {mm} -> {d.get('sf').status} vol={d.get('sf').volume} "
          f"{(d.get('sf').problems or [''])[0][:55]}")
p, q = faced(40), faced(60)
p.rebuild()
q.rebuild()
print(f"   the two share one signature? {p._sigs.get('sf') == q._sigs.get('sf')}"
      "   (must be False)")

print()
print("   ...and an EDIT of the rail on one document")
e = faced(40)
e.rebuild()
was = e.get("sf").volume
e.edit("big", "entities", [
    {"kind": "path", "closed": False, "x": 0, "y": 6, "start": [0, 0],
     "segments": [{"type": "line", "to": [0, 60]},
                  {"type": "line", "to": [60, 60]}]}])
e.rebuild()
print(f"   {was} -> {e.get('sf').volume}   (must grow if the rail is followed)")

line("3. undo and redo across a REFUSED feature")
studio.STATE = {"docs": {}, "active": None, "seq": 0}
cl = TestClient(studio.app)
cl.post("/api/new", json={"name": "undo-me"})
cl.post("/api/feature/add", json={
    "id": "b", "op": "plate",
    "params": {"width": 40, "depth": 40, "thickness": 10}, "inputs": []})
cl.post("/api/feature/add", json={
    "id": "r", "op": "fillet", "params": {"radius": 2, "edges": "all"},
    "inputs": ["b"]})


def state(tag):
    j = cl.get("/api/doc").json()
    rows = {f["id"]: (f["status"], f["volume"]) for f in j["features"]}
    print(f"   {tag:28s} ok={j.get('ok')} {rows}")
    return j


state("built")
# an edit the door refuses outright (the API answers, nothing changes)
r = cl.post("/api/edit",
            json={"feature_id": "r", "param": "radius", "value": "2mm"}).json()
print(f"   refused edit says: {str(r.get('error'))[:70]}")
state("after the refused edit")
# an edit that is ACCEPTED and then fails at the kernel
cl.post("/api/edit",
        json={"feature_id": "r", "param": "radius", "value": 40})
state("after a radius the kernel refuses")
cl.post("/api/undo")
state("after undo")
cl.post("/api/redo")
state("after redo")
cl.post("/api/undo")
state("after undo again")
# ...and the rollback bar over the same refusal
cl.post("/api/edit",
        json={"feature_id": "r", "param": "radius", "value": 40})
cl.post("/api/rollback", json={"feature_id": "b"})
state("bar parked above the refusal")
cl.post("/api/rollback", json={"feature_id": None})
state("bar released")
