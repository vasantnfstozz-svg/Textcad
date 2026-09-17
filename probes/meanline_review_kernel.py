"""probes/meanline_review_kernel.py -- REVIEW round: put the newly ALLOWED and
the newly REFUSED duties to the kernel, one per run.

    C:/Python314/python.exe probes/meanline_review_kernel.py <case>

`microturbo` is the duty the shroud clamp UNLOCKED (it used to crash on the
negative cutter radius). `big` and `pr13` are duties the new size gate
REFUSES. The gate is patched out so the kernel gets to answer for itself;
measuring is the only way to know whether a refusal refuses correct geometry.

Measures, for the assembled part:
  ok / n_solids / watertight / volume / max_radius / Z-fold symmetry
and -- the question the arithmetic cannot answer -- how much material sits
INSIDE the shaft bore `with_center_hole` drilled, and how far in towards the
axis the traced blades actually reach.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import blocks        # noqa: E402
import meanline      # noqa: E402
import inspector     # noqa: E402
from build123d import Cylinder, Pos  # noqa: E402

CASES = {
    "microturbo": dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000),
    "smallturbo": dict(mass_flow=0.1, pressure_ratio=2.0, rpm=120000),
    "sample":     dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000),
    "big":        dict(mass_flow=50.0, pressure_ratio=2.0, rpm=1500),
    # r2 = 10,000 mm exactly: a wheel 20 metres across, bigger than any
    # rotating machine ever built, and the bound this review proposes
    "huge":       dict(mass_flow=50.0, pressure_ratio=2.0, rpm=325.3597),
    # r2 = 4221.36 mm: the row tests/test_meanline_gate.py lists as IMPOSSIBLE
    # ("1000 rpm"). Raising the bound admits it, so it has to be measured.
    "rpm1000":    dict(mass_flow=0.5, pressure_ratio=3.0, rpm=1000),
    "pr13":       dict(mass_flow=0.5, pressure_ratio=1.3, rpm=45000),
}

name = sys.argv[1] if len(sys.argv) > 1 else "microturbo"
meanline._check_wheel = lambda d, duty=None: None      # let the kernel answer
d = meanline.design(meanline.Duty(**CASES[name]))
print(f"CASE {name}: {CASES[name]}")
print(d.report())
r_in = 0.75 * d.inducer_hub_radius
thk = max(0.02 * d.tip_radius, 1.5)
print(f"\n  blade root r_in   : {r_in:.4f} mm   (thickness {thk:.3f})")
print(f"  shaft bore radius : {d.bore_radius:.4f} mm")
print(f"  hub nose r1h      : {d.inducer_hub_radius:.4f} mm")
print(f"  blades start INSIDE the bore: {r_in < d.bore_radius}")
print(f"  bore eats the whole nose   : {d.bore_radius >= d.inducer_hub_radius}")

t0 = time.time()
rep = meanline.build_from_design(d)
dt = time.time() - t0
print(f"\n  build_from_design: ok={rep.ok} in {dt:.1f} s")
print(rep.summary())
if rep.part is None:
    raise SystemExit(0)

m = inspector.measure(rep.part)
print(f"\n  volume      : {m['volume']}")
print(f"  n_solids    : {m['n_solids']}   watertight: {m.get('is_manifold')}")
print(f"  max_radius  : {m.get('max_radius')}  (design {d.tip_radius})")
print(f"  size        : {m['size']}")
print(f"  health      : {inspector.health(rep.part)}")
print(f"  {d.blade_count}-fold symmetric: "
      f"{inspector.is_rotationally_symmetric(rep.part, d.blade_count)}")

# is the shaft bore actually clear?
t, L = d.backplate_thk, d.axial_length
span = 4.0 * (t + L)


def plug_volume(part, radius):
    plug = Pos(0, 0, (t + L) / 2.0) * Cylinder(radius=radius, height=span)
    got = part & plug
    return got.volume if got is not None else 0.0


vol = plug_volume(rep.part, d.bore_radius)
print(f"\n  material inside the {d.bore_radius:.2f} mm shaft bore: "
      f"{vol:.3f} mm3   CLEAR={vol < 1e-6}")

# how far in does the traced blade actually reach? the hub has no material
# inside the bore at all (with_center_hole cut it), so anything here is blade.
one = blocks.curved_blade(inner_radius=r_in, outer_radius=d.tip_radius,
                          inlet_angle_deg=d.beta1_deg,
                          exit_angle_deg=d.beta2_deg, height=L, thickness=thk)
print("\n  ONE blade's reach towards the axis (its own volume "
      f"{one.volume:.3f} mm3):")
for frac in (1.0, 0.8, 0.6, 0.4, 0.2):
    r = r_in * frac
    print(f"    material inside r={r:8.4f} mm : "
          f"{plug_volume(Pos(0, 0, t) * one, r):10.4f} mm3")
