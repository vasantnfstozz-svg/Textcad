"""Section 8 FIX probe: build ONE solid from an outer shell + void shells."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import struct, io, tempfile, os
from build123d import Mesher, Solid
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
from OCP.BRep import BRep_Tool

def to_bin(tris):
    out = io.BytesIO(); out.write(b"\0"*80); out.write(struct.pack("<I", len(tris)))
    for a,b,c in tris:
        out.write(struct.pack("<3f",0,0,0))
        for v in (a,b,c): out.write(struct.pack("<3f",*v))
        out.write(struct.pack("<H",0))
    return out.getvalue()
def box(x0,y0,z0,x1,y1,z1, inward=False):
    P=[(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),
       (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
    F=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
       (1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    t=[(P[a],P[b],P[c]) for a,b,c in F]
    return [(a,c,b) for a,b,c in t] if inward else t

tris = box(0,0,0,10,10,10) + box(3,3,3,7,7,7, inward=True) + box(30,0,0,40,10,10)
tmp = tempfile.NamedTemporaryFile(suffix=".stl", delete=False); tmp.write(to_bin(tris)); tmp.close()
shp = Mesher().read(tmp.name)[0]; os.unlink(tmp.name)
shells = shp.shells()
print("shells:", len(shells))
info = []
for i, sh in enumerate(shells):
    closed = BRep_Tool.IsClosed_s(sh.wrapped)
    sol = Solid(BRepBuilderAPI_MakeSolid(sh.wrapped).Solid())
    bb = sh.bounding_box()
    info.append((sh, sol.volume, bb))
    print(f"  [{i}] closed={closed} solid_volume={sol.volume:+.1f} "
          f"bbox {[round(c,1) for c in bb.min]}..{[round(c,1) for c in bb.max]}")

print("\nMakeSolid.Add available:", hasattr(BRepBuilderAPI_MakeSolid(), "Add"))
outer = next(s for s,v,b in info if v > 0 and b.min.X == 0)
void  = next(s for s,v,b in info if v < 0)
mk = BRepBuilderAPI_MakeSolid(outer.wrapped)
mk.Add(void.wrapped)
sol = Solid(mk.Solid())
print("outer + void ->", round(sol.volume,2), "(want 936.0)  is_valid", sol.is_valid)
import inspector
print("   health:", inspector.health(sol, check_valid=False))
