"""Sweep probe 6: a Sketch made of loose EDGES (a path-only sketch) and a
Sketch of faces + loose edges: area, faces, edges, placement, extrude of it,
attribute survival, mesh data."""
import math, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import build123d as b3d
from build123d import BuildLine, Line, Plane, Circle, Sketch, extrude, sweep, Transition
import sketch as sk
with BuildLine(Plane.XZ) as pl:
    Line((0, 0), (0, 20)); Line((0, 20), (20, 20))
w = pl.wire()
s = Sketch(children=list(w.edges()))
s._tc_x = 7
print("edge-sketch: type", type(s).__name__, "area", s.area, "faces", len(s.faces()), "edges", len(s.edges()), "is_sketch", sk.is_sketch(s), "attr", s._tc_x)
print("  volume attr?", getattr(s, "volume", "none"))
moved = b3d.Pos(1, 0, 0) * s
print("  moved edges", len(moved.edges()), "attr after move", getattr(moved, "_tc_x", None))
# faces + loose edges
c = Plane.XY * Circle(3)
both = Sketch(children=[*c.faces(), *w.edges()])
print("face+edges: area", round(both.area, 3), "faces", len(both.faces()), "edges", len(both.edges()))
p = extrude(both, amount=5)
print("  extrude ->", type(p).__name__, "vol", round(p.volume, 3), "expected", round(math.pi * 9 * 5, 3), "solids", len(p.solids()))
q = sweep(both, path=w, transition=Transition.RIGHT)
print("  sweep of face+edges ->", round(q.volume, 3), "solids", len(q.solids()))
# can a wire be rebuilt from the edges of the edge-sketch? (order matters)
w2 = b3d.Wire(s.edges())
print("wire from edges len", w2.length, "start", w2.start_point())
# mesh data path used by studio
from studio import _sketch_mesh_data
m = _sketch_mesh_data(s)
print("mesh data:", None if m is None else {k: len(v) for k, v in m.items()})
# a 2D->3D: build a path wire in the plane from 2D points via Plane.to_location / plane * ?
pts2 = [(0, 0), (0, 20), (20, 20)]
with BuildLine(Plane.XZ) as pl2:
    for a, b_ in zip(pts2, pts2[1:]):
        Line(a, b_)
print("plane-built wire start/end", pl2.wire().start_point(), pl2.wire().end_point())
# does the sketch plane object let me map 2D -> world? Plane.from_local_coords
print("from_local", Plane.XZ.from_local_coords((5, 7, 0)))
