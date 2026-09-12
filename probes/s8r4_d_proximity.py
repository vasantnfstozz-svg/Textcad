"""Round four D: BRepExtrema_ShapeProximity - BVH overlap test between two
shells' triangulations. If it is fast and exact, 'B wholly inside A' becomes
'no surface crossing + one point IN' and the 800-point sample goes away."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import os, tempfile, time, numpy as np, meshrepair as M, blocks
from build123d import Mesher, Sphere, Box, Pos, Align, Location, export_stl, Solid
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
from OCP.BRepExtrema import BRepExtrema_ShapeProximity
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_ShapeEnum
D = tempfile.mkdtemp()
def stl(shape, name, **kw):
    p = os.path.join(D, name); export_stl(shape, p, **kw); return M.parse_binary_stl(open(p, "rb").read())
def shells_of(parts, name):
    vs, fs, off = [], [], 0
    for v, f in parts: vs.append(v); fs.append(f + off); off += len(v)
    p = os.path.join(D, name); open(p, "wb").write(M.to_binary_stl(np.concatenate(vs), np.concatenate(fs)))
    return Mesher().read(p)[0].shells()
def has_tri(shell):
    ex = TopExp_Explorer(shell.wrapped, TopAbs_ShapeEnum.TopAbs_FACE); n = ok = 0
    while ex.More():
        n += 1; ok += BRep_Tool.Triangulation_s(__import__("OCP.TopoDS", fromlist=["TopoDS"]).TopoDS.Face_s(ex.Current()), TopLoc_Location()) is not None; ex.Next()
    return f"{ok}/{n} faces triangulated"
def prox(a, b, tol=0.0):
    t = time.time(); pr = BRepExtrema_ShapeProximity(a.wrapped, b.wrapped, tol); pr.Perform()
    n1 = pr.OverlapSubShapes1().Extent() if pr.IsDone() else -1
    return n1, time.time() - t

sph = stl(Sphere(30).moved(Location((30, 30, 30))), "s.stl", tolerance=0.003, angular_tolerance=0.05)
void = stl(Sphere(12).moved(Location((30, 30, 30))), "v.stl", tolerance=0.01, angular_tolerance=0.1)
cross = stl(Sphere(12).moved(Location((55, 30, 30))), "c.stl", tolerance=0.01, angular_tolerance=0.1)
print("container", len(sph[1]), "faces; void", len(void[1]), "; crossing body", len(cross[1]))

A, B = shells_of([sph, (void[0], void[1][:, ::-1])], "hollow.stl")[:2]
print("triangulation on lib3mf faces:", has_tri(A))
n, dt = prox(A, B); print(f"proximity(container, VOID) without meshing: overlaps={n} in {dt:.3f}s")
t = time.time(); BRepMesh_IncrementalMesh(A.wrapped, 0.1); BRepMesh_IncrementalMesh(B.wrapped, 0.1); print(f"IncrementalMesh both: {time.time()-t:.3f}s;", has_tri(A))
n, dt = prox(A, B); print(f"proximity(container, VOID) after meshing: overlaps={n} in {dt:.3f}s  (want 0)")

A2, C = shells_of([sph, cross], "cross.stl")[:2]
BRepMesh_IncrementalMesh(A2.wrapped, 0.1); BRepMesh_IncrementalMesh(C.wrapped, 0.1)
n, dt = prox(A2, C); print(f"proximity(container, CROSSING body): overlaps={n} in {dt:.3f}s  (want > 0)")

# the bracket-in-notch and pin cases from round three
frame = Box(30, 30, 30, align=Align.MIN) - Pos(10, 0, 10) * Box(10, 30, 20, align=Align.MIN)
bracket = Pos(8, 11, 12) * Box(10, 8, 8, align=Align.MIN)
F, Br = shells_of([stl(frame, "f.stl"), stl(bracket, "b.stl")], "notch.stl")[:2]
BRepMesh_IncrementalMesh(F.wrapped, 0.1); BRepMesh_IncrementalMesh(Br.wrapped, 0.1)
n, dt = prox(F, Br); print(f"proximity(frame, bracket): overlaps={n} in {dt:.3f}s  (want > 0)")
# disjoint: a cube in an open tray (touching nothing)
tray = Box(90, 60, 20, align=Align.MIN) - Pos(2, 2, 2) * Box(86, 56, 18, align=Align.MIN)
cube = Pos(20, 20, 5) * Box(3, 3, 3, align=Align.MIN)
T, Cu = shells_of([stl(tray, "t.stl"), stl(cube, "cu.stl")], "tray.stl")[:2]
BRepMesh_IncrementalMesh(T.wrapped, 0.1); BRepMesh_IncrementalMesh(Cu.wrapped, 0.1)
n, dt = prox(T, Cu); print(f"proximity(tray, cube in it): overlaps={n} in {dt:.3f}s  (want 0; one point then says OUT)")
