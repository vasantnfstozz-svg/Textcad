"""Section 8 probe G: scale pivot, decimation drift, hollow via the repair
path, and the multi-body budget arithmetic."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import struct, io, os, tempfile, numpy as np, blocks, meshrepair as M, inspector

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
D = tempfile.mkdtemp()
def w(n,d):
    p=os.path.join(D,n); open(p,"wb").write(d); return p

print("1. SCALE PIVOT (an inch->mm conversion must be about the ORIGIN)")
p = w("off.stl", to_bin(box(50,50,0,60,60,10)))
a = blocks.import_stl(p); b = blocks.import_stl(p, 2.0)
print("   scale=1 bbox min", [round(c,2) for c in a.bounding_box().min],
      "max", [round(c,2) for c in a.bounding_box().max])
print("   scale=2 bbox min", [round(c,2) for c in b.bounding_box().min],
      "max", [round(c,2) for c in b.bounding_box().max],
      "  (origin-scaled would be 100,100,0 -> 120,120,20)")

print("\n2. HOLLOW PART through the REPAIR path (dirty/dense mesh)")
hollow = box(0,0,0,10,10,10) + box(3,3,3,4+3,4+3,4+3, inward=True)
pieces, rep = M.repair_stl_mesh(to_bin(hollow))
print("   repair_stl_mesh ->", len(pieces), "pieces, report", rep,
      "  (the void is its own component)")

print("\n3. DECIMATION drift on a dense sphere")
from build123d import Sphere, export_stl
sp = os.path.join(D, "ball.stl")
export_stl(Sphere(20), sp, tolerance=0.002, angular_tolerance=0.05)
v,f = M.parse_binary_stl(open(sp,"rb").read())
print("   exported", len(f), "triangles, mesh volume", round(M.signed_volume(v,f),1),
      " true", round(4/3*np.pi*20**3,1))
if len(f) > 20000:
    part = blocks.import_stl(sp); r = blocks.import_stl_report(sp)
    print("   imported volume", round(part.volume,1),
          " drift", round((part.volume-abs(M.signed_volume(v,f)))/abs(M.signed_volume(v,f))*100,2), "%")
    print("   report", r)

print("\n4. BUDGET arithmetic (repair_stl_mesh shares)")
for nbodies in (3, 12, 40):
    sizes = np.full(nbodies, 5000.0)
    shares = np.maximum(sizes/sizes.sum()*M.DEFAULT_BUDGET, M.MIN_COMPONENT_BUDGET).astype(int)
    print(f"   {nbodies} bodies x 5000 tris: share={shares[0]} each -> "
          f"output <= {shares.sum():,} (budget {M.DEFAULT_BUDGET:,}), "
          f"worst rung x{M.LADDER[-1]:g} -> {int(shares.sum()*M.LADDER[-1]):,}")
