"""Section 8 FIX probe: what lib3mf hands back, so the `is_valid` fast path
can be turned on without breaking the multi-body / open / inverted cases."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import struct, io, tempfile, os
from build123d import Mesher, Solid

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

def look(name, tris):
    tmp = tempfile.NamedTemporaryFile(suffix=".stl", delete=False)
    tmp.write(to_bin(tris)); tmp.close()
    shapes = Mesher().read(tmp.name)
    print(f"\n{name}: {len(shapes)} shape(s)")
    for i,s in enumerate(shapes):
        try: valid = s.is_valid
        except Exception as e: valid = f"raised {e}"
        try: nsol = len(s.solids())
        except Exception as e: nsol = f"raised {e}"
        print(f"   [{i}] {type(s).__name__} volume={s.volume:.2f} "
              f"shells={len(s.shells())} solids={nsol} is_valid={valid}")
    os.unlink(tmp.name)

look("single cube", box(0,0,0,10,10,10))
look("two DISJOINT cubes", box(0,0,0,10,10,10) + box(30,0,0,40,10,10))
look("hollow cube (sealed void)", box(0,0,0,10,10,10) + box(3,3,3,7,7,7, inward=True))
look("inverted cube", box(0,0,0,10,10,10, inward=True))
look("open box (2 triangles missing)", box(0,0,0,10,10,10)[:-2])
look("cube with a void AND a second body",
     box(0,0,0,10,10,10) + box(3,3,3,7,7,7, inward=True) + box(30,0,0,40,10,10))
