"""Section 8 probe H: an assembly that contains the SAME body twice at the
same place -> every triangle is a duplicate -> drop_duplicate_walls empties it."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import struct, io, os, tempfile, numpy as np, blocks, meshrepair as M

def to_bin(tris):
    out = io.BytesIO(); out.write(b"\0"*80); out.write(struct.pack("<I", len(tris)))
    for a,b,c in tris:
        out.write(struct.pack("<3f",0,0,0))
        for v in (a,b,c): out.write(struct.pack("<3f",*v))
        out.write(struct.pack("<H",0))
    return out.getvalue()
def box(x0,y0,z0,x1,y1,z1):
    P=[(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),
       (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
    F=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
       (1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    return [(P[a],P[b],P[c]) for a,b,c in F]
D=tempfile.mkdtemp()
def go(name, tris):
    p=os.path.join(D,name); open(p,"wb").write(to_bin(tris))
    v,f = M.parse_binary_stl(to_bin(tris))
    print(f"\n{name}: tris={len(f)} edge_counts={M.edge_counts(f)} "
          f"dupes={int(M.duplicate_triangles(f).sum())}")
    try:
        part = blocks.import_stl(p)
        print(f"   OK volume={part.volume:.1f} bodies={len(part.solids())} "
              f"report={blocks.import_stl_report(p)}")
    except Exception as e:
        print(f"   {type(e).__name__}: {str(e)[:140]}")

# the same 10mm cube twice at the SAME place (a duplicated assembly component)
go("duplicate-body.stl", box(0,0,0,10,10,10) + box(0,0,0,10,10,10))
# one duplicated body + one good body elsewhere
go("dup-plus-good.stl", box(0,0,0,10,10,10)*2 + box(30,0,0,40,10,10))
