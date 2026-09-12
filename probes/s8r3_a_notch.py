"""Round three A: two bodies that OVERLAP but are not welded, and the smaller
one's bounding box lies inside the bigger one's (a bracket in a notch of a
C-shaped body). One vertex of B may be inside A's material -> is B a void?"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import os, tempfile, numpy as np, blocks, inspector, meshrepair as M
from build123d import Box, Pos, export_stl, Align
D = templib = tempfile.mkdtemp()
# A: 30-cube with a slot x 10..20 through y, open at the top (z 10..30)
A = Box(30, 30, 30, align=Align.MIN) - Pos(10, 0, 10) * Box(10, 30, 20, align=Align.MIN)
# B: 10x8x8 sitting in the slot, overlapping A's wall by 2 mm (x 8..10)
B = Pos(8, 11, 12) * Box(10, 8, 8, align=Align.MIN)
pa, pb = os.path.join(D, "A.stl"), os.path.join(D, "B.stl")
export_stl(A, pa); export_stl(B, pb)
va, fa = M.parse_binary_stl(open(pa, "rb").read()); vb, fb = M.parse_binary_stl(open(pb, "rb").read())
both = M.to_binary_stl(np.concatenate([va, vb]), np.concatenate([fa, fb + len(va)]))
p = os.path.join(D, "notch.stl"); open(p, "wb").write(both)
v, f = M.parse_binary_stl(both)
print("mesh: tris", len(f), "edge_counts", M.edge_counts(f), "dupes", int(M.duplicate_triangles(f).sum()))
print("true: A", round(A.volume, 1), " B", round(B.volume, 1), " as 2 bodies", round(A.volume + B.volume, 1))
try:
    part = blocks.import_stl(p)
    print(f"IMPORTED volume={part.volume:.1f} bodies={len(part.solids())} "
          f"health={inspector.health(part, check_valid=False)} valid={part.is_valid}")
    for s in part.solids():
        print("   body", round(s.volume, 1), "valid", s.is_valid)
except Exception as e:
    print("REFUSED ->", type(e).__name__, str(e)[:160])
