"""probes/compressor_fuse_lever_probe.py -- the one lever the profile names,
measured, so the next wave does not have to guess.

probes/compressor_rebuild_profile.py measured the compressor sample's rebuild
at 33.6 s, of which 31.5 s (94%) is `OCP.BRepAlgoAPI.Build` over 19 boolean
calls. The three fat ones:

    inspector._rotation_residual   16.2 s   (the spec's 13-fold symmetry proof)
    pattern._fuse_all               8.0 s   (13 blades, pairwise tree)
    document._fuse                  6.1 s   (hub + blades)

Both fuses are in files this wave may not touch, so measure whether the lever
is even real before writing it into the report: does ONE multi-argument fuse
beat the pairwise tree on the 13 DISJOINT blades of this very sample?

Also: is the blade fuse necessary at all? The 13 blades do not touch each
other -- they only touch the hub -- so the union is a Compound either way.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import blocks  # noqa: E402
import inspector  # noqa: E402
import meanline  # noqa: E402
import pattern  # noqa: E402
from build123d import Pos  # noqa: E402

d = meanline.design(meanline.Duty(mass_flow=0.5, pressure_ratio=3.0,
                                  rpm=45000))
t, L = d.backplate_thk, d.axial_length
r_in = round(0.75 * d.inducer_hub_radius, 2)
thk = round(max(0.02 * d.tip_radius, 1.5), 2)

t0 = time.perf_counter()
one = Pos(0, 0, t) * blocks.curved_blade(
    inner_radius=r_in, outer_radius=d.tip_radius,
    inlet_angle_deg=d.beta1_deg, exit_angle_deg=d.beta2_deg,
    height=L, thickness=thk)
print(f"one blade built in {time.perf_counter() - t0:.2f} s, "
      f"{len(one.faces())} faces, volume {one.volume}")

copies = [one.rotate(__import__("build123d").Axis.Z, a)
          for a in pattern.polar_angles(d.blade_count, 360.0)]
parts = [one] + copies
print(f"{len(parts)} blades")

t0 = time.perf_counter()
tree = pattern._fuse_all(list(parts))
dt_tree = time.perf_counter() - t0
print(f"  pattern._fuse_all (pairwise tree): {dt_tree:6.2f} s  "
      f"volume={tree.volume!r} faces={len(tree.faces())} "
      f"solids={len(tree.solids())}")

t0 = time.perf_counter()
try:
    multi = parts[0].fuse(*parts[1:])
    dt_multi = time.perf_counter() - t0
    print(f"  Shape.fuse(*rest) (one OCCT call): {dt_multi:6.2f} s  "
          f"volume={multi.volume!r} faces={len(multi.faces())} "
          f"solids={len(multi.solids())}")
    print(f"  health(tree)  = {inspector.health(tree, check_valid=False)}")
    print(f"  health(multi) = {inspector.health(multi, check_valid=False)}")
    print(f"  volume delta  = {abs(tree.volume - multi.volume):.9f} mm3")
    print(f"  speedup       = {dt_tree / dt_multi:.1f}x")
except Exception as e:
    print(f"  Shape.fuse(*rest) FAILED: {type(e).__name__}: {e}")
