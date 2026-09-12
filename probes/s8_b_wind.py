"""Section 8 probe B: mixed winding through the FULL import path."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import struct, io, numpy as np, meshrepair as M, blocks, inspector, tempfile, os

def soup_to_stl(tris):
    out = io.BytesIO(); out.write(b"\0"*80); out.write(struct.pack("<I", len(tris)))
    for a,b,c in tris:
        out.write(struct.pack("<3f",0,0,0))
        for v in (a,b,c): out.write(struct.pack("<3f",*v))
        out.write(struct.pack("<H",0))
    return out.getvalue()

def box(ox=0.0,oy=0.0,oz=0.0,s=5.0):
    P=[(ox,oy,oz),(ox+s,oy,oz),(ox+s,oy+s,oz),(ox,oy+s,oz),
       (ox,oy,oz+s),(ox+s,oy,oz+s),(ox+s,oy+s,oz+s),(ox,oy+s,oz+s)]
    F=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
       (1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    return [(P[a],P[b],P[c]) for a,b,c in F]

def through_import(tris, name):
    d = tempfile.mkdtemp()
    p = os.path.join(d, name)
    open(p,"wb").write(soup_to_stl(tris))
    try:
        part = blocks.import_stl(p)
        rep = blocks.import_stl_report(p)
        print(f"  {name}: volume={part.volume:.3f}  bbox={part.bounding_box().size}")
        print(f"     health={inspector.health(part, check_valid=False)}  valid={part.is_valid()}")
        print(f"     report={rep}")
    except Exception as e:
        print(f"  {name}: REFUSED -> {type(e).__name__}: {e}")

# box OFF the origin so every face contributes to the signed volume
tris = box(10,10,10)
v,f = M.parse_binary_stl(soup_to_stl(tris))
print("clean box off-origin: signed_volume", M.signed_volume(v,f), "(true 125)")

flip = list(tris)
for i in (4,):                       # flip ONE side-wall triangle
    a,b,c = flip[i]; flip[i] = (a,c,b)
v2,f2 = M.parse_binary_stl(soup_to_stl(flip))
print("one flipped tri: edge_counts", M.edge_counts(f2), "is_clean", M.is_clean(f2),
      "signed_volume", M.signed_volume(v2,f2))

print("\nFULL import path:")
through_import(tris, "clean.stl")
through_import(flip, "mixedwind.stl")
inv = [(a,c,b) for a,b,c in tris]
through_import(inv, "inverted.stl")
