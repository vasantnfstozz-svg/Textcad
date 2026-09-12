"""Round four E: the cost cliff end to end. A 32k-face housing with a faceted
cavity PLUS another body (lib3mf's Solid is invalid -> the regroup runs), the
cavity wound inward (a proper export) and outward (MeshLab re-orient)."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import os, tempfile, time, numpy as np, meshrepair as M, blocks, inspector
from build123d import Sphere, Box, Pos, Align, Location, export_stl
D = tempfile.mkdtemp()
def stl(shape, name, **kw):
    p = os.path.join(D, name); export_stl(shape, p, **kw); return M.parse_binary_stl(open(p, "rb").read())
housing = stl(Sphere(30).moved(Location((30, 30, 30))), "h.stl", tolerance=0.003, angular_tolerance=0.05)
cavity = stl(Sphere(12).moved(Location((30, 30, 30))), "c.stl", tolerance=0.01, angular_tolerance=0.1)
other = stl(Pos(80, 0, 0) * Box(10, 10, 10, align=Align.MIN), "o.stl")
print("housing", len(housing[1]), "faces; cavity", len(cavity[1]), "; other", len(other[1]))
want = M.signed_volume(*housing) - abs(M.signed_volume(*cavity)) + M.signed_volume(*other)
for name, cav in (("cavity INWARD (proper export)", (cavity[0], cavity[1][:, ::-1])),
                  ("cavity OUTWARD (MeshLab re-orient)", cavity)):
    vs, fs, off = [], [], 0
    for v, f in (housing, cav, other): vs.append(v); fs.append(f + off); off += len(v)
    p = os.path.join(D, "x.stl"); open(p, "wb").write(M.to_binary_stl(np.concatenate(vs), np.concatenate(fs)))
    blocks._read_stl_solids.cache_clear()
    t = time.time(); part = blocks.import_stl(p); dt = time.time() - t
    print(f"{name}: {dt:.1f}s -> volume {part.volume:.1f} (want {want:.1f}) bodies {len(part.solids())} "
          f"health {inspector.health(part, check_valid=False)}")
