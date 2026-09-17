"""What the kernel makes of a path that turns straight back on itself.

MEASURED 2026-09-17: BuildLine's wire() DROPPED the second segment (up 20,
back to 0.5 -> ONE edge of 20 mm) and the sweep along it was a green straight
tube — so `_path_wire` builds edge by edge and refuses when the wire keeps
fewer edges, or less length, than the user drew. This probe shows both forms."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build123d as b3d  # noqa: E402
from build123d import BuildLine, Line, Plane  # noqa: E402

import sketch as sk  # noqa: E402

with BuildLine(Plane.XZ) as bl:
    Line((0, 0), (0, 20))
    Line((0, 20), (0, 0.5))
w = bl.wire()
print("BuildLine: edges", len(w.edges()), "length", w.length, "(drawn 39.5)")
edges = [Line((0, 0, 0), (0, 0, 20)), Line((0, 0, 20), (0, 0, 0.5))]
w2 = b3d.Wire(edges)
print("Wire(edges): edges", len(w2.edges()), "length", w2.length)
for ents in ([{"type": "line", "to": [0, 20]}, {"type": "line", "to": [0, 0.5]}],
             [{"type": "line", "to": [0, 20]}, {"type": "line", "to": [0, 30]}],
             [{"type": "line", "to": [0, 20]}, {"type": "line", "to": [20, 20]}]):
    try:
        ps = sk.make_sketch(plane="XZ", entities=[{"kind": "path", "closed": False,
                                                   "start": [0, 0], "segments": ents}])
        w = sk.sketch_paths(ps)[0]
        print(ents[1]["to"], "-> built: edges", len(w.edges()), "length", round(w.length, 3))
    except ValueError as e:
        print(ents[1]["to"], "-> refused:", e)
