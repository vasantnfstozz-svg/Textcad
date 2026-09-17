"""The Sweep PLAN on a real document: sketch mode, face mode, edit mode, the
path list, the fallback, the stations against the kernel's own wire."""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build123d as b3d  # noqa: E402

import sketch as sk  # noqa: E402
import toolplan  # noqa: E402
from document import Document  # noqa: E402

BENT = [{"kind": "path", "closed": False, "x": 5, "y": 6, "start": [0, 0],
         "segments": [{"type": "line", "to": [0, 20]},
                      {"type": "arc", "via": [10 * (1 - math.cos(math.pi / 4)),
                                              20 + 10 * math.sin(math.pi / 4)],
                       "to": [10, 30]},
                      {"type": "line", "to": [30, 30]}]}]
d = Document(name="sw")
d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
d.add("p", "sketch_on_face", {"face": "top", "offset": 0,
                              "entities": [{"kind": "circle", "r": 3, "x": 5, "y": 0, "mode": "add"}]}, ["b"])
d.add("rail", "sketch", {"plane": "XZ", "offset": 0, "entities": BENT}, [])
d.rebuild()
plan = toolplan.plan(d, {"tool": "sweep", "sketch_id": "p"})
print("ok", plan.get("ok"), plan.get("error"))
if plan.get("ok"):
    print("path_id", plan["path_id"], "paths", plan["paths"], "target", plan["target_body"],
          "limits", plan["limits"], "notes", plan["notes"], "reversed", plan["reversed"])
    S = plan["stations"]
    print("stations", len(S), "first", S[0], "last s", S[-1]["s"])
    json.dumps(plan)
    # every station lies on the wire moved to the profile's centre
    part = d._parts["rail"]
    w = sk.sketch_paths(part)[0]
    prof = d._parts["p"]
    centre = prof.center()
    shift = centre - w.start_point()
    worst = 0.0
    for s in S:
        p = b3d.Vector(*s["p"]) - shift
        worst = max(worst, w.distance_to(p))
    print("worst station off the wire", round(worst, 6))
    print("frame origin == centre?", plan["frame"]["origin"], centre)
# face mode: the top face of the plate
top = max(d._parts["b"].faces(), key=lambda f: f.center().Z)
fp = toolplan.plan(d, {"tool": "sweep", "body_id": "b", "face_center": list(top.center()),
                       "face_normal": [0, 0, 1]})
print("face mode ok", fp.get("ok"), fp.get("error"), fp.get("op") if fp.get("ok") else "")
# no path sketch at all
d2 = Document(name="np")
d2.add("p", "sketch", {"plane": "XY", "entities": [{"kind": "circle", "r": 3, "mode": "add"}]}, [])
d2.rebuild()
print("no path:", toolplan.plan(d2, {"tool": "sweep", "sketch_id": "p"}).get("error"))
# the profile IS a path sketch
print("profile is a path:", toolplan.plan(d, {"tool": "sweep", "sketch_id": "rail"}).get("error"))
# edit mode + fallback for a path that is gone
d.add("sw1", "sweep", {"path": "rail", "distance": 12}, ["p"])
d.rebuild()
ep = toolplan.plan(d, {"tool": "sweep", "feature_id": "sw1"})
print("edit ok", ep.get("ok"), "stored", ep.get("stored"), "path", ep.get("path_id"))
d.edit_many("sw1", {"path": "gone"})
fb = toolplan.plan(d, {"tool": "sweep", "feature_id": "sw1"})
print("fallback", fb.get("fallback"), "->", fb.get("path_id"))
