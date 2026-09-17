"""Sweep through the DOCUMENT: a path sketch builds, a sweep follows it (full
and partial, volumes against A·L), every refusal is a sentence, extrude of a
path sketch is refused, rename and delete follow the `path` reference."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from document import Document  # noqa: E402

BENT = [{"kind": "path", "closed": False, "x": 0, "y": 0, "start": [0, 0],
         "segments": [{"type": "line", "to": [0, 20]},
                      {"type": "arc", "via": [10 * (1 - math.cos(math.pi / 4)),
                                              20 + 10 * math.sin(math.pi / 4)],
                       "to": [10, 30]},
                      {"type": "line", "to": [30, 30]}]}]
L = 20 + 10 * math.pi / 4 + 20

d = Document(name="sw")
d.add("p", "sketch", {"plane": "XY", "offset": 0,
                      "entities": [{"kind": "circle", "r": 3, "x": 0, "y": 0, "mode": "add"}]}, [])
d.add("path", "sketch", {"plane": "XZ", "offset": 0, "entities": BENT}, [])
d.add("sw1", "sweep", {"path": "path", "full": True}, ["p"])
d.rebuild()
for f in d.features:
    print(f.id, f.op, f.status, f.problems, f.volume, f.notes)
print("expected full", round(math.pi * 9 * L, 2))
d.edit_many("sw1", {"full": False, "distance": 25})
d.rebuild()
print("partial", d.get("sw1").status, d.get("sw1").volume, "expected", round(math.pi * 9 * 25, 2))
for params in ({"path": "p"}, {"path": "nope"}, {"path": "path", "distance": 0},
               {"path": "path", "distance": 999}):
    d.edit_many("sw1", {"path": params.get("path"), "distance": params.get("distance", 0),
                        "full": False})
    d.rebuild()
    print(params, "->", d.get("sw1").problems)
d2 = Document(name="x")
d2.add("path", "sketch", {"plane": "XZ", "entities": [
    {"kind": "path", "closed": False, "start": [0, 0],
     "segments": [{"type": "line", "to": [0, 20]}]}]}, [])
d2.add("e", "extrude", {"amount": 5}, ["path"])
d2.rebuild()
print("path sketch:", d2.get("path").status, d2.get("path").problems)
print("extrude of a path sketch:", d2.get("e").problems)
d.edit_many("sw1", {"path": "path", "full": True, "distance": 0})
d.rebuild()
d.rename("path", "rail")
print("after rename, sw1.path =", d.get("sw1").params["path"], d.get("sw1").status)
print("remove plan of the path sketch:", d.remove_plan("rail"))
print("doc json path flag:", [(f.id, f.op) for f in d.features])
