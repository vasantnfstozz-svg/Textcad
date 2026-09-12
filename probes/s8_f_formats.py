"""Section 8 probe F: format detection, malformed input, STEP path."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import struct, io, os, tempfile, blocks

D = tempfile.mkdtemp()
def w(name, data):
    p = os.path.join(D, name); open(p,"wb").write(data); return p

def try_stl(name, data, scale=1.0):
    p = w(name, data)
    try:
        part = blocks.import_stl(p, scale)
        print(f"  {name}: OK volume={part.volume:.2f} bodies={len(part.solids())} "
              f"bbox={[round(c,2) for c in part.bounding_box().size]}")
    except Exception as e:
        print(f"  {name}: {type(e).__name__}: {str(e)[:130]}")

def box_tris(x0,y0,z0,x1,y1,z1):
    P=[(x0,y0,z0),(x1,y0,z0),(x1,y1,z0),(x0,y1,z0),
       (x0,y0,z1),(x1,y0,z1),(x1,y1,z1),(x0,y1,z1)]
    F=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
       (1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    return [(P[a],P[b],P[c]) for a,b,c in F]

def to_bin(tris, header=b"\0"*80):
    out = io.BytesIO(); out.write(header[:80].ljust(80,b"\0"))
    out.write(struct.pack("<I", len(tris)))
    for a,b,c in tris:
        out.write(struct.pack("<3f",0,0,0))
        for v in (a,b,c): out.write(struct.pack("<3f",*v))
        out.write(struct.pack("<H",0))
    return out.getvalue()

def to_ascii(tris, eol=b"\n"):
    L=[b"solid part"]
    for a,b,c in tris:
        L.append(b"  facet normal 0 0 0"); L.append(b"    outer loop")
        for v in (a,b,c):
            L.append(b"      vertex %f %f %f" % v)
        L.append(b"    endloop"); L.append(b"  endfacet")
    L.append(b"endsolid part")
    return eol.join(L) + eol

T = box_tris(0,0,0,10,10,10)
print("FORMAT DETECTION")
try_stl("plain-binary.stl", to_bin(T))
try_stl("binary-header-says-solid.stl", to_bin(T, b"solid exported by SomeCAD"))
try_stl("ascii-unix.stl", to_ascii(T))
try_stl("ascii-crlf.stl", to_ascii(T, b"\r\n"))
try_stl("truncated-binary.stl", to_bin(T)[:200])
try_stl("empty-ascii.stl", b"solid empty\nendsolid empty\n")
try_stl("not-an-stl.stl", b"\x89PNG\r\n\x1a\n" + b"\0"*200)
try_stl("one-triangle.stl", to_bin(T[:1]))
try_stl("scaled-2x.stl", to_bin(box_tris(50,50,0,60,60,10)), scale=2.0)
try_stl("zero-scale.stl", to_bin(T), scale=0.0)

print("\nSTEP")
from build123d import Box, export_step, Compound, Pos
sp = os.path.join(D, "two.step")
export_step(Compound(children=[Box(10,10,10), Pos(30,0,0)*Box(4,4,4)]), sp)
try:
    part = blocks.import_step(sp)
    print(f"  two-solid step: volume={part.volume:.1f} bodies={len(part.solids())}")
except Exception as e:
    print("  two-solid step:", type(e).__name__, e)
for name, data in [("nota.step", b"hello world"),
                   ("wrongext.stp", to_bin(T))]:
    p = w(name, data)
    try:
        blocks.import_step(p); print(f"  {name}: OK (!)")
    except Exception as e:
        print(f"  {name}: {type(e).__name__}: {str(e)[:110]}")
p = w("renamed.txt", to_bin(T))
try:
    blocks.import_step(p); print("  renamed.txt: OK (!)")
except Exception as e:
    print(f"  renamed.txt: {type(e).__name__}: {str(e)[:110]}")
