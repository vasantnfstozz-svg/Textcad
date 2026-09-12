"""Round four B: classifier cost against a LARGE container (32k faces) - the
55 us/point figure was measured against a 12-face box. Plus bounding_box()
cost on the big solid (called n^2 times in nested())."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import os, tempfile, time, numpy as np, meshrepair as M, blocks
from build123d import Mesher, Sphere, Box, export_stl, Solid, Align, Location
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeSolid
D = tempfile.mkdtemp()
ps, pb = os.path.join(D, "sph.stl"), os.path.join(D, "cube.stl")
export_stl(Sphere(30).moved(Location((30, 30, 30))), ps, tolerance=0.003, angular_tolerance=0.05)
export_stl(Box(6, 6, 6, align=Align.MIN).moved(Location((27, 27, 27))), pb)
vs, fs = M.parse_binary_stl(open(ps, "rb").read()); vb, fb = M.parse_binary_stl(open(pb, "rb").read())
print("container sphere:", len(fs), "faces; void cube:", len(fb))
both = M.to_binary_stl(np.concatenate([vs, vb]), np.concatenate([fs, fb[:, ::-1] + len(vs)]))
p = os.path.join(D, "hollow_big.stl"); open(p, "wb").write(both)
shells = Mesher().read(p)[0].shells()
outer = max(shells, key=lambda s: abs(Solid(BRepBuilderAPI_MakeSolid(s.wrapped).Solid()).volume))
inner = [s for s in shells if s is not outer][0]
tsh, osol = blocks._outward(outer)
t = time.time(); bbx = osol.bounding_box(); print(f"bounding_box() on the 32k-face solid: {time.time()-t:.3f}s")
pts = blocks._shell_points(inner)
t = time.time(); ok = blocks._shell_inside(inner, osol, pts); dt = time.time() - t
print(f"_shell_inside: {len(pts)} points vs 32k-face container in {dt:.3f}s "
      f"({dt/len(pts)*1e6:.0f} us/pt) -> {ok}; x800 points = {dt/len(pts)*800:.1f}s")
# the whole import, end to end (clean path: this file has no defects)
t = time.time(); part = blocks.import_stl(p); print(f"import_stl end to end: {time.time()-t:.1f}s -> "
      f"volume {part.volume:.1f} bodies {len(part.solids())}")
