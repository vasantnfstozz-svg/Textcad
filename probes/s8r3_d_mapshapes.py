"""Round three D: unique vertices / faces of a shell in C++ (TopExp.MapShapes)
and a bounded, spread sample of points to classify."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import os, tempfile, time, numpy as np, meshrepair as M
from build123d import Mesher, Sphere, Box, export_stl, Solid, Align, Location
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.TopAbs import TopAbs_State, TopAbs_ShapeEnum
from OCP.TopExp import TopExp
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.BRep import BRep_Tool
from OCP.TopoDS import TopoDS
from OCP.gp import gp_Pnt
D = tempfile.mkdtemp()
pb, ps = os.path.join(D, "box.stl"), os.path.join(D, "sph.stl")
export_stl(Box(60, 60, 60, align=Align.MIN), pb)
export_stl(Sphere(20).moved(Location((30, 30, 30))), ps, tolerance=0.003, angular_tolerance=0.05)
vb, fb = M.parse_binary_stl(open(pb, "rb").read()); vs, fs = M.parse_binary_stl(open(ps, "rb").read())
both = M.to_binary_stl(np.concatenate([vb, vs]), np.concatenate([fb, fs[:, ::-1] + len(vb)]))
p = os.path.join(D, "hollow.stl"); open(p, "wb").write(both)
shells = Mesher().read(p)[0].shells()
inner = min(shells, key=lambda s: abs(Solid(BRepBuilderAPI_MakeSolid(s.wrapped).Solid()).volume))
outer = [s for s in shells if s is not inner][0]
osol = Solid(BRepBuilderAPI_MakeSolid(outer.wrapped).Solid())
if osol.volume < 0: osol = Solid(osol.wrapped.Reversed())

t = time.time()
vm = TopTools_IndexedMapOfShape(); TopExp.MapShapes_s(inner.wrapped, TopAbs_ShapeEnum.TopAbs_VERTEX, vm)
fm = TopTools_IndexedMapOfShape(); TopExp.MapShapes_s(inner.wrapped, TopAbs_ShapeEnum.TopAbs_FACE, fm)
print(f"MapShapes: {vm.Extent()} unique vertices, {fm.Extent()} faces in {time.time()-t:.3f}s")

def spread(n, cap):
    return range(1, n + 1) if n <= cap else [1 + (k * n) // cap for k in range(cap)]

t = time.time()
pts = []
for i in spread(vm.Extent(), 400):
    pn = BRep_Tool.Pnt_s(TopoDS.Vertex_s(vm.FindKey(i))); pts.append((pn.X(), pn.Y(), pn.Z()))
for i in spread(fm.Extent(), 400):
    sub = TopTools_IndexedMapOfShape(); TopExp.MapShapes_s(fm.FindKey(i), TopAbs_ShapeEnum.TopAbs_VERTEX, sub)
    acc = np.zeros(3)
    for j in range(1, sub.Extent() + 1):
        pn = BRep_Tool.Pnt_s(TopoDS.Vertex_s(sub.FindKey(j))); acc += (pn.X(), pn.Y(), pn.Z())
    pts.append(tuple(acc / sub.Extent()))
print(f"sample of {len(pts)} points (vertices + face centres) in {time.time()-t:.3f}s")
t = time.time(); cls = BRepClass3d_SolidClassifier(osol.wrapped); n_in = 0
for x, y, z in pts:
    cls.Perform(gp_Pnt(x, y, z), 1e-7); n_in += cls.State() == TopAbs_State.TopAbs_IN
print(f"classified in {time.time()-t:.3f}s, IN={n_in}/{len(pts)}")
