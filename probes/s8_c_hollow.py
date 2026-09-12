"""Section 8 probe C: a HOLLOW stl (outer shell + inner void) through import_stl.
The dead `shp.is_valid()` fast path in _stl_bytes_to_solids is the suspect."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import struct, io, os, tempfile, blocks, inspector, meshrepair as M
from build123d import Solid, Mesher

def soup_to_stl(tris):
    out = io.BytesIO(); out.write(b"\0"*80); out.write(struct.pack("<I", len(tris)))
    for a,b,c in tris:
        out.write(struct.pack("<3f",0,0,0))
        for v in (a,b,c): out.write(struct.pack("<3f",*v))
        out.write(struct.pack("<H",0))
    return out.getvalue()

def box(ox,oy,oz,s, inward=False):
    P=[(ox,oy,oz),(ox+s,oy,oz),(ox+s,oy+s,oz),(ox,oy+s,oz),
       (ox,oy,oz+s),(ox+s,oy,oz+s),(ox+s,oy+s,oz+s),(ox,oy+s,oz+s)]
    F=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
       (1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    t=[(P[a],P[b],P[c]) for a,b,c in F]
    return [(a,c,b) for a,b,c in t] if inward else t

# 10mm cube with a 4mm cubic void in the middle -> true volume 1000-64 = 936
tris = box(0,0,0,10) + box(3,3,3,4, inward=True)
data = soup_to_stl(tris)
v,f = M.parse_binary_stl(data)
print("mesh: tris", len(f), "edge_counts", M.edge_counts(f), "is_clean", M.is_clean(f),
      "signed_volume", M.signed_volume(v,f), "(true 936)")

d = tempfile.mkdtemp(); p = os.path.join(d, "hollow.stl")
open(p,"wb").write(data)

# what lib3mf hands back, before our code touches it
tmp = tempfile.NamedTemporaryFile(suffix=".stl", delete=False); tmp.write(data); tmp.close()
shapes = Mesher().read(tmp.name)
for i, s in enumerate(shapes):
    print(f"  lib3mf shape {i}: {type(s).__name__} volume={s.volume:.3f} "
          f"shells={len(s.shells())} is_valid={s.is_valid}")
os.unlink(tmp.name)

solids, opens = blocks._stl_bytes_to_solids(data)
print("_stl_bytes_to_solids ->", len(solids), "solids, open:", opens,
      "volumes:", [round(s.volume,3) for s in solids])

part = blocks.import_stl(p)
print("import_stl -> volume", round(part.volume,3), " bodies", len(part.solids()),
      " health", inspector.health(part, check_valid=False))
print("REPORT:", blocks.import_stl_report(p))
