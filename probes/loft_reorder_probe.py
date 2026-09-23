"""PROBE - review of Loft (ec45cf1), 2026-09-23: what the plan's REORDER
builds. The order guard refuses a U-bend (up, across, back down: A, B, C) and
the plan then puts the sections "in the order they lie along the loft",
sorted by their station along the MEAN normal - for a U-bend that is A, C, B.
Is that loft sound, and does the op let it through?

Run: python probes/memcap.py --gb 4 --timeout 600 -- python probes/loft_reorder_probe.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build123d as b3d            # noqa: E402
from OCP.BOPAlgo import BOPAlgo_CheckerSI   # noqa: E402
from OCP.TopTools import TopTools_ListOfShape  # noqa: E402

import inspector                   # noqa: E402
import toolplan                    # noqa: E402
from document import Document      # noqa: E402


def self_hits(solid) -> bool:
    chk = BOPAlgo_CheckerSI()
    lst = TopTools_ListOfShape()
    lst.Append(solid.wrapped)
    chk.SetArguments(lst)
    chk.SetRunParallel(False)
    chk.Perform()
    return chk.HasErrors()


def ubend(sq=4):
    d = Document(name="ubend")
    d.add("A", "sketch", {"plane": "XY", "entities": [{"kind": "rectangle", "w": sq, "h": sq}]})
    d.add("p", "offset_plane", {"offset": 10}, inputs=[]) if False else None
    d.add("B", "sketch", {"plane": "YZ", "offset": 10, "entities": [
        {"kind": "rectangle", "w": sq, "h": sq, "x": 0, "y": 10}]})
    d.add("C", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": sq, "h": sq, "x": 20, "y": 0}]})
    d.rebuild()
    return d


d = ubend()
for f in ("A", "B", "C"):
    part = d._parts[f]
    print(f, "centre", [round(v, 2) for v in part.faces()[0].center()],
          "normal", [round(v, 2) for v in part.faces()[0].normal_at(part.faces()[0].center())])
plan = toolplan.plan(d, {"tool": "loft", "sketch_ids": ["A", "B", "C"]})
print("plan ok", plan.get("ok"), "order", plan.get("order"), "reordered", plan.get("reordered"))
print("note:", plan.get("note"))
order = plan.get("order") or ["A", "B", "C"]
d.add("L", "loft", {}, inputs=order)
d.rebuild()
f = d.get("L")
print("feature", f.status, f.problems[:1])
body = d._parts.get("L")
if body is not None:
    print(f"volume {body.volume:.2f} valid {body.is_valid} health {inspector.health(body)[:1]} "
          f"self-intersects {self_hits(body)}")
    ruled = b3d.loft([d._parts[i] for i in order], ruled=True)
    print(f"ruled volume of the same order {ruled.volume:.2f} self-intersects {self_hits(ruled)}")
