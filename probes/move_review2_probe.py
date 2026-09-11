"""Round TWO of the Move / Rotate review — the measurements behind
tests/test_move_review.py's "round two" section (base 4ee5670, 2026-09-11).

Round one put a guard in toolplan._place_input: a body ANOTHER feature is
built from is not a body to place. This probe measures what that guard
actually does, against the document's OWN rule for the same question
(Document.consumed_ids) and against the user's 50 saved designs.

  python probes/move_review2_probe.py
"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json  # noqa: E402

import toolplan  # noqa: E402
from document import Document  # noqa: E402

DESIGNS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "designs", "*.tcad.json")


def assembly():
    d = Document(name="a")
    d.add("cap", "plate", {"width": 40, "depth": 40, "thickness": 6}, [])
    d.add("rib", "plate", {"width": 6, "depth": 6, "thickness": 6}, [])
    d.add("rib_placed", "move", {"x": 12, "y": 0, "z": 6}, ["rib"])
    d.add("fused", "fuse", {}, ["cap", "rib_placed"])
    d.rebuild()
    return d


def face_sketch_plate():
    d = Document(name="fs")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 10}, [])
    d.rebuild()
    top = max(d._parts["b"].faces(), key=lambda f: f.center().Z)
    c, n = top.center(), top.normal_at(top.center())
    d.add("s", "sketch_on_face",
          {"face_center": [c.X, c.Y, c.Z], "face_normal": [n.X, n.Y, n.Z],
           "entities": [{"kind": "circle", "r": 6, "x": 0, "y": 0}]}, ["b"])
    d.rebuild()
    return d


print("=" * 78)
print("S1  A FACE SKETCH is not a consumer — the document says so, the guard did not")
print("=" * 78)
d = face_sketch_plate()
print(f"  leaf_solid_ids()  {d.leaf_solid_ids()}      <- the body ON SCREEN")
print(f"  consumed_ids()    {sorted(d.consumed_ids())}")
for tool in ("move", "rotate"):
    p = toolplan.plan(d, {"tool": tool, "body_id": "b"})
    print(f"  plan {tool:6s} ok={p.get('ok')}  {p.get('error', '')}")
d.add("boss", "extrude_face", {"amount": 5}, ["b", "s"])
d.rebuild()
print(f"  + a New-body boss: leaves {d.leaf_solid_ids()}")
p = toolplan.plan(d, {"tool": "move", "body_id": "b"})
print(f"  plan move   ok={p.get('ok')}  {p.get('error', '')}")

print()
print("=" * 78)
print("S2  A STRUCK row is a PASS-THROUGH — the round-one P1 is still live through it")
print("=" * 78)
d = assembly()
d.strike("rib_placed")
d.rebuild()
print(f"  leaves {d.leaf_solid_ids()}   consumed {sorted(d.consumed_ids())}"
      f"   <- 'rib' IS consumed, by 'fused', through the struck row")
print(f"  plan move on 'rib' ok={toolplan.plan(d, {'tool': 'move', 'body_id': 'rib'})['ok']}")
v0 = d.result().volume
d.add("move1", "move", {"x": 0, "y": 0, "z": 40}, ["rib"])
d.rebuild()
print("  what the refusal prevents (forced here, past the plan):")
print(f"    appending move1 -> leaves {d.leaf_solid_ids()}, every row "
      f"{sorted({f.status for f in d.features})}")
print(f"    the displayed result: {v0:.1f} mm3 -> {d.result().volume:.1f} mm3   (the COPY)")

print()
print("=" * 78)
print("S3  A REPLAN in create mode is about the feature THIS SESSION built")
print("=" * 78)
d = Document(name="c")
d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
d.rebuild()
print(f"  first plan            ok={toolplan.plan(d, {'tool': 'rotate', 'body_id': 'b'})['ok']}")
d.add("rotate1", "rotate", {"axis": "Z", "angle_deg": 30, "pivot": "center"}, ["b"])
d.rebuild()
p = toolplan.plan(d, {"tool": "rotate", "body_id": "b", "axis": "X"})
print(f"  the Axis box changed  ok={p.get('ok')}  {p.get('error', '')}")
p = toolplan.plan(d, {"tool": "rotate", "body_id": "b", "axis": "X", "own_id": "rotate1"})
print(f"  ... with own_id       ok={p.get('ok')}  (mirror.js / pattern.js already send it)")

print()
print("=" * 78)
print("S4  THE LIBRARY: bodies the user can SEE that the guard refuses to place")
print("=" * 78)
bad = 0
n = 0
for path in sorted(glob.glob(DESIGNS)):
    try:
        doc = Document.from_data(json.load(open(path, encoding="utf-8")))
        doc.rebuild()
    except Exception as e:                       # noqa: BLE001
        print(f"  skip {os.path.basename(path)}: {type(e).__name__}")
        continue
    n += 1
    for bid in doc.leaf_solid_ids():
        p = toolplan.plan(doc, {"tool": "move", "body_id": bid})
        if p.get("ok"):
            continue
        blocker = next((x for x in doc.features
                        if not x.suppressed and bid in (x.inputs or [])), None)
        bad += 1
        print(f"  {os.path.basename(path):30s} body {bid:20s} "
              f"blocked by op={blocker.op if blocker else '?'}")
print(f"  {n} designs rebuilt; {bad} VISIBLE bodies refused")
