"""Round two A: the P0 through the INVERSION door - a hollow part whose whole
file is wound inside-out (a known exporter bug; test_inverted_winding_is_repaired
covers the plain case). Outer shell reads as a 'void', inner as a 'body'."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import struct, io, os, tempfile, blocks, inspector
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
hollow = box(0,0,0,10,10,10) + box(3,3,3,7,7,7, inward=True)
inv = [(a,c,b) for a,b,c in hollow]
for name, tris in (("hollow-ok.stl", hollow), ("hollow-INVERTED.stl", inv),
                   ("hollow-inverted+other.stl", inv + box(30,0,0,40,10,10))):
    p = os.path.join(D, name); open(p,"wb").write(to_bin(tris))
    part = blocks.import_stl(p)
    print(f"{name}: volume={part.volume:.1f} bodies={len(part.solids())} "
          f"health={inspector.health(part, check_valid=False)} valid={part.is_valid}")
