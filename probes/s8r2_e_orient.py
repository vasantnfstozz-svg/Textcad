"""Round two E: can blocks FORCE shell orientation, so nesting depth decides
what is a void and the file's winding decides nothing?"""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import struct, io, os, tempfile
from build123d import Mesher, Solid
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
from OCP.TopoDS import TopoDS
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
def shells_of(tris):
    tmp = tempfile.NamedTemporaryFile(suffix=".stl", delete=False); tmp.write(to_bin(tris)); tmp.close()
    s = Mesher().read(tmp.name)[0].shells(); os.unlink(tmp.name); return s

# the INVERTED hollow file: outer wound inward, cavity wound outward
sh = shells_of([(a,c,b) for a,b,c in box(0,0,0,10,10,10) + box(3,3,3,7,7,7, inward=True)])
vols = [Solid(BRepBuilderAPI_MakeSolid(s.wrapped).Solid()).volume for s in sh]
print("inverted hollow: raw shell solid volumes", [round(v,1) for v in vols])
outer = sh[vols.index(max(vols, key=abs))]; void = sh[1 - sh.index(outer)]

def oriented(shell, outward: bool):
    sol = Solid(BRepBuilderAPI_MakeSolid(shell.wrapped).Solid())
    if (sol.volume > 0) != outward:
        return TopoDS.Shell_s(shell.wrapped.Reversed())
    return shell.wrapped
o_out = oriented(outer, True); v_in = oriented(void, False); v_out = oriented(void, True)
print("  outer forced outward ->", round(Solid(BRepBuilderAPI_MakeSolid(o_out).Solid()).volume,1))
for label, vsh in (("void INWARD", v_in), ("void OUTWARD", v_out)):
    mk = BRepBuilderAPI_MakeSolid(o_out); mk.Add(vsh); s = Solid(mk.Solid())
    print(f"  MakeSolid(outer).Add({label}) -> volume {s.volume:.1f} valid {s.is_valid}  (want 936)")

# exact containment: a vertex of the void against the outer's OUTWARD solid
osol = Solid(BRepBuilderAPI_MakeSolid(o_out).Solid())
vx = void.vertices()[0].to_tuple()
st = BRepClass3d_SolidClassifier(osol.wrapped, gp_Pnt(*vx), 1e-7).State()
print("  void vertex", tuple(round(c,1) for c in vx), "in outer:", st == TopAbs_State.TopAbs_IN)
vx2 = outer.vertices()[0].to_tuple()
vsol = Solid(BRepBuilderAPI_MakeSolid(v_out).Solid())
st2 = BRepClass3d_SolidClassifier(vsol.wrapped, gp_Pnt(*vx2), 1e-7).State()
print("  outer vertex in void:", st2 == TopAbs_State.TopAbs_IN)
# and against an INWARD-wound solid: does the classifier flip?
isol = Solid(BRepBuilderAPI_MakeSolid(outer.wrapped).Solid())   # raw = inward here
st3 = BRepClass3d_SolidClassifier(isol.wrapped, gp_Pnt(*vx), 1e-7).State()
print("  void vertex vs INWARD outer solid:", st3, "(a trap if not IN)")
