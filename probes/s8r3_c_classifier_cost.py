"""Round three C: cost of deciding 'wholly inside' by classifying EVERY vertex
and face centre of a shell - Load once, Perform many - on a realistic void
(an 18k-triangle sphere inside a box)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import os, tempfile, time, numpy as np, meshrepair as M
from build123d import Mesher, Sphere, Box, export_stl, Solid, Align
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.TopAbs import TopAbs_State
from OCP.gp import gp_Pnt
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_ShapeEnum
from OCP.BRep import BRep_Tool
from OCP.TopoDS import TopoDS
D = tempfile.mkdtemp()
pb, ps = os.path.join(D, "box.stl"), os.path.join(D, "sph.stl")
export_stl(Box(60, 60, 60, align=Align.MIN), pb)
export_stl(Sphere(20).moved(__import__("build123d").Location((30, 30, 30))), ps, tolerance=0.003, angular_tolerance=0.05)
vb, fb = M.parse_binary_stl(open(pb, "rb").read()); vs, fs = M.parse_binary_stl(open(ps, "rb").read())
print("sphere shell:", len(fs), "triangles,", len(vs), "vertices")
both = M.to_binary_stl(np.concatenate([vb, vs]), np.concatenate([fb, fs[:, ::-1] + len(vb)]))
p = os.path.join(D, "hollow.stl"); open(p, "wb").write(both)
shp = Mesher().read(p)[0]
shells = shp.shells()
outer = max(shells, key=lambda s: abs(Solid(BRepBuilderAPI_MakeSolid(s.wrapped).Solid()).volume))
inner = [s for s in shells if s is not outer][0]
osol = Solid(BRepBuilderAPI_MakeSolid(outer.wrapped).Solid())
if osol.volume < 0: osol = Solid(osol.wrapped.Reversed())

# 1. vertex coordinates straight from TopExp (no ShapeList)
t = time.time()
pts, ex, seen = [], TopExp_Explorer(inner.wrapped, TopAbs_ShapeEnum.TopAbs_VERTEX), set()
while ex.More():
    v = TopoDS.Vertex_s(ex.Current()); k = v.HashCode(1 << 30) if hasattr(v, "HashCode") else id(v)
    pnt = BRep_Tool.Pnt_s(v); pts.append((pnt.X(), pnt.Y(), pnt.Z())); ex.Next()
print(f"TopExp vertices: {len(pts)} (with repeats) in {time.time()-t:.2f}s")
t = time.time(); vv = inner.vertices(); print(f"build123d .vertices(): {len(vv)} in {time.time()-t:.2f}s")

# 2. Load-once / Perform-many classifier over all vertices
cls = BRepClass3d_SolidClassifier(osol.wrapped)
t = time.time(); n_in = 0
for x, y, z in pts:
    cls.Perform(gp_Pnt(x, y, z), 1e-7)
    n_in += cls.State() == TopAbs_State.TopAbs_IN
dt = time.time() - t
print(f"classifier: {len(pts)} points in {dt:.2f}s ({dt/len(pts)*1e6:.0f} us/pt), IN={n_in}")

# 3. per-call construction (what _shell_inside does today), 200 points
t = time.time()
for x, y, z in pts[:200]:
    BRepClass3d_SolidClassifier(osol.wrapped, gp_Pnt(x, y, z), 1e-7).State()
print(f"construct-per-call: 200 points in {time.time()-t:.2f}s")

# 4. face centres via triangulation nodes (mean of the 3 vertices per face)
t = time.time(); cents = []
ex = TopExp_Explorer(inner.wrapped, TopAbs_ShapeEnum.TopAbs_FACE)
while ex.More():
    f = ex.Current(); vx = TopExp_Explorer(f, TopAbs_ShapeEnum.TopAbs_VERTEX); acc = np.zeros(3); k = 0
    while vx.More():
        pn = BRep_Tool.Pnt_s(TopoDS.Vertex_s(vx.Current())); acc += (pn.X(), pn.Y(), pn.Z()); k += 1; vx.Next()
    cents.append(acc / k); ex.Next()
print(f"face centres: {len(cents)} in {time.time()-t:.2f}s")
