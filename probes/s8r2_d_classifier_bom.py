"""Round two D: (1) an EXACT point-in-solid test for void ownership, so bbox
nesting is not the rule; (2) a UTF-8 BOM in front of an ASCII STL; (3) the
viewport mesh of a solid that carries a void."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import struct, io, os, tempfile, blocks, studio
from build123d import Solid, Vertex
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.TopAbs import TopAbs_State
from OCP.gp import gp_Pnt
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

print("1. BRepClass3d_SolidClassifier")
cube = Solid.make_box(10, 10, 10)
for pt in ((5,5,5), (15,5,5), (0,5,5)):
    cl = BRepClass3d_SolidClassifier(cube.wrapped, gp_Pnt(*pt), 1e-6)
    print(f"   point {pt}: state={cl.State()} (IN={TopAbs_State.TopAbs_IN})")
# a vertex OF a void shell classified against the OUTER body's solid
verts = list(cube.vertices())
print("   Vertex -> coords:", tuple(round(c,3) for c in verts[0].to_tuple()))

print("\n2. ASCII STL with a UTF-8 BOM")
ascii_ = ("solid t\n" + "".join("facet normal 0 0 0\n outer loop\n" + "".join(
    f"  vertex {v[0]} {v[1]} {v[2]}\n" for v in tri) + " endloop\nendfacet\n"
    for tri in box(0,0,0,10,10,10)) + "endsolid t\n").encode()
D = tempfile.mkdtemp()
for name, data in (("plain.stl", ascii_), ("bom.stl", b"\xef\xbb\xbf" + ascii_)):
    p = os.path.join(D, name); open(p,"wb").write(data)
    try:
        part = blocks.import_stl(p); print(f"   {name}: OK volume={part.volume:.1f}")
    except Exception as e:
        print(f"   {name}: {str(e)[:140]}")

print("\n3. viewport mesh of a hollow solid")
p = os.path.join(D, "hollow.stl")
open(p,"wb").write(to_bin(box(0,0,0,10,10,10) + box(3,3,3,7,7,7, inward=True)))
part = blocks.import_stl(p)
m = studio._tagged_mesh(part, body_id="h")
pos, idx = m["positions"], m["indices"]
s6 = 0.0
for t in range(0, len(idx), 3):
    (ax,ay,az),(bx,by,bz),(cx,cy,cz) = (pos[3*idx[t+k]:3*idx[t+k]+3] for k in range(3))
    s6 += ax*(by*cz-bz*cy) - ay*(bx*cz-bz*cx) + az*(bx*cy-by*cx)
print(f"   solid volume {part.volume:.1f}; viewport mesh signed volume {s6/6:.1f}; "
      f"faces {len(m['faces'])}")
