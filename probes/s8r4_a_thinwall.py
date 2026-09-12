"""Round four A: a THIN-walled hollow part. If build123d pads a bounding box,
the void's box may poke past the outer's and _bbox_holds fails -> the void is
a body again -> cavity filled + phantom (the P0 through a thin-wall door)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import struct, io, os, tempfile, blocks, inspector
from build123d import Solid
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
s = Solid.make_box(10, 10, 10); bb = s.bounding_box()
print("bbox of an exact 10-box:", [round(c, 9) for c in bb.min], [round(c, 9) for c in bb.max], "(padding shows here)")
for wall in (2.0, 0.5, 0.05, 0.005):
    tris = box(0,0,0,10,10,10) + box(wall,wall,wall,10-wall,10-wall,10-wall, inward=True)
    true = 1000 - (10-2*wall)**3
    p = os.path.join(D, f"wall{wall}.stl"); open(p,"wb").write(to_bin(tris))
    part = blocks.import_stl(p)
    print(f"wall {wall} mm: volume={part.volume:.4f} (true {true:.4f}) bodies={len(part.solids())} "
          f"health={inspector.health(part, check_valid=False)}")
