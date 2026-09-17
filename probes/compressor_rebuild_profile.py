"""probes/compressor_rebuild_profile.py -- a real profile of the compressor
sample rebuild, so the 1-2 minute row is answered with names, not a guess.

    python probes/compressor_rebuild_profile.py

Profiles ONE cold `samples.sample_compressor().rebuild()` and prints the 30
costliest calls by cumulative time, then times the spec's symmetry proof's own
three stages on the finished solid.
"""
import cProfile
import pstats
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build123d as b3d  # noqa: E402
import inspector  # noqa: E402
import samples  # noqa: E402

doc = samples.sample_compressor()
pr = cProfile.Profile()
t0 = time.perf_counter()
pr.enable()
ok = doc.rebuild()
pr.disable()
wall = time.perf_counter() - t0
print(f"rebuild ok={ok} in {wall:.2f} s (profiler on: inflated)\n")
st = pstats.Stats(pr)
st.sort_stats("cumulative").print_stats(30)

res = doc.result()
n = doc.spec["symmetry"]
print(f"\n--- the spec's symmetry proof, stage by stage (n={n}) ---")
solid = inspector._as_solid(res)
t0 = time.perf_counter()
total = solid.volume
print(f"  solid.volume                 {time.perf_counter() - t0:7.3f} s "
      f"-> {total}")
t0 = time.perf_counter()
rotated = solid.rotate(b3d.Axis.Z, 360.0 / n)
print(f"  solid.rotate                 {time.perf_counter() - t0:7.3f} s")
bb = solid.bounding_box()
tol = 1e-3 * max(bb.size.X, bb.size.Y, bb.size.Z, 1.0)
t0 = time.perf_counter()
g1 = inspector._rotation_keeps_extent(solid, rotated, tol)
print(f"  _rotation_keeps_extent       {time.perf_counter() - t0:7.3f} s "
      f"-> {g1}")
t0 = time.perf_counter()
g2 = inspector._rotation_keeps_vertices(solid, rotated, tol)
print(f"  _rotation_keeps_vertices     {time.perf_counter() - t0:7.3f} s "
      f"-> {g2}")
t0 = time.perf_counter()
resid = inspector._rotation_residual(solid, rotated)
print(f"  _rotation_residual (the cut) {time.perf_counter() - t0:7.3f} s "
      f"-> {resid}")
print(f"  faces={len(res.faces())} edges={len(res.edges())} "
      f"vertices={len(res.vertices())}")
