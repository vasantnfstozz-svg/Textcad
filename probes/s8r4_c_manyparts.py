"""Round four C: many small bodies inside a housing's BOX. (1) an open tray
(one shell) with 40 cubes in it -> 41 bodies; (2) a CLOSED housing (outer +
cavity shells) with 40 cubes sealed inside -> 41 bodies, depth-2 islands.
Time and correctness. Plus (E) _spread edge arithmetic."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import struct, io, os, tempfile, time, blocks, inspector
def to_bin(tris):
    out = io.BytesIO(); out.write(b"\0"*80); out.write(struct.pack("<I", len(tris)))
    for a,b,c in tris:
        out.write(struct.pack("<3f",0,0,0))
        for v in (a,b,c): out.write(struct.pack("<3f",*v))
        out.write(struct.pack("<H",0))
    return out.getvalue()
def box(x0,y0,z0,x1,y1,z1, inward=False):
    P=[(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),(x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
    F=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    t=[(P[a],P[b],P[c]) for a,b,c in F]
    return [(a,c,b) for a,b,c in t] if inward else t
D = tempfile.mkdtemp()
cubes = [box(5+ (k%8)*10, 5 + (k//8)*10, 5, 8 + (k%8)*10, 8 + (k//8)*10, 8) for k in range(40)]
parts = sum(cubes, [])
# (1) open tray: 90x60 floor 0..2 with 4 walls up to z=20 -> one shell, open top
from build123d import Box, Pos, Align, export_stl
import meshrepair as M, numpy as np
tray = Box(90, 60, 20, align=Align.MIN) - Pos(2, 2, 2) * Box(86, 56, 18, align=Align.MIN)
pt = os.path.join(D, "tray.stl"); export_stl(tray, pt)
vt, ft = M.parse_binary_stl(open(pt, "rb").read())
vc, fc = M.parse_binary_stl(to_bin(parts))
p1 = os.path.join(D, "tray+40.stl")
open(p1, "wb").write(M.to_binary_stl(np.concatenate([vt, vc]), np.concatenate([ft, fc + len(vt)])))
t = time.time(); part = blocks.import_stl(p1)
print(f"(1) open tray + 40 cubes: {time.time()-t:.1f}s -> bodies {len(part.solids())} (want 41) "
      f"volume {part.volume:.1f} (want {tray.volume + 40*27:.1f}) health {inspector.health(part, check_valid=False)}")
# (2) closed housing: 90x60x20 outer, cavity 2..88 x 2..58 x 2..18 inward, 40 cubes inside
housing = box(0,0,0,90,60,20) + box(2,2,2,88,58,18, inward=True) + parts
p2 = os.path.join(D, "housing+40.stl"); open(p2, "wb").write(to_bin(housing))
t = time.time(); part = blocks.import_stl(p2)
want = 90*60*20 - 86*56*16 + 40*27
print(f"(2) closed housing + 40 islands: {time.time()-t:.1f}s -> bodies {len(part.solids())} (want 41) "
      f"volume {part.volume:.1f} (want {want}) health {inspector.health(part, check_valid=False)}")
# (E) _spread
for n, cap in ((0, 400), (1, 400), (400, 400), (401, 400), (16103, 400)):
    idx = list(blocks._spread(n, cap))
    print(f"(E) _spread({n},{cap}): len {len(idx)}, min {min(idx) if idx else '-'}, max {max(idx) if idx else '-'}, "
          f"distinct {len(set(idx)) == len(idx)}, in range {all(1 <= i <= n for i in idx)}")
