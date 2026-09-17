"""probes/meanline_kernel_repro.py -- THE REPRO: an impossible duty reaching OCCT.

    python probes/meanline_kernel_repro.py <case>

One duty per run, so a heavy one can be capped:
    python probes/memcap.py --gb 6 --timeout 300 -- \
        C:/Python314/python.exe probes/meanline_kernel_repro.py rpm1

Prints the design numbers, the shroud-cutter profile `build_from_design` would
hand `blocks.revolve_profile`, and then actually calls build_from_design and
reports what came back and how long it took.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline  # noqa: E402

CASES = {
    "sample":   dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000),
    "rpm1":     dict(mass_flow=0.5, pressure_ratio=3.0, rpm=1),
    "rpm1000":  dict(mass_flow=0.5, pressure_ratio=3.0, rpm=1000),
    "pr1001":   dict(mass_flow=0.5, pressure_ratio=1.001, rpm=45000),
    "pr105":    dict(mass_flow=0.5, pressure_ratio=1.05, rpm=45000),
    "tiny":     dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000),
    "hugeflow": dict(mass_flow=1e4, pressure_ratio=3.0, rpm=45000),
    # the two the inlet-eye gate would have to judge: an inducer annulus that
    # has all but closed. tinyflow's eye EQUALS its hub nose; beta74 is the
    # backsweep tests/test_mcp_server.py blesses, and its eye is 1.039 x the
    # nose. If both build sound solids, a gate on that ratio would refuse
    # geometry the kernel gets right.
    "tinyflow": dict(mass_flow=1e-6, pressure_ratio=3.0, rpm=45000),
    "beta74":   dict(mass_flow=1.0, pressure_ratio=3.0, rpm=40000,
                     backsweep_deg=74.0),
}

name = sys.argv[1] if len(sys.argv) > 1 else "sample"
duty = meanline.Duty(**CASES[name])
print(f"CASE {name}: {CASES[name]}")
try:
    d = meanline.design(duty)
except Exception as e:
    print(f"  design() refused: {type(e).__name__}: {e}")
    raise SystemExit(0)
print(d.report())

t, L = d.backplate_thk, d.axial_length
r_in = 0.75 * d.inducer_hub_radius
big = t + L + 50.0
prof = [(r_in - 2.0, t + L), (d.inducer_shroud_radius, t + L),
        (d.tip_radius, t + d.exit_width),
        (d.tip_radius + 15.0, t + d.exit_width),
        (d.tip_radius + 15.0, big), (r_in - 2.0, big)]
print(f"\n  shroud-cutter profile the OLD `r_in - 2.0` handed "
      f"revolve_profile:\n   {prof}")
print(f"  first radius: {prof[0][0]:.4f}  NEGATIVE={prof[0][0] < 0}")
print(f"  meanline.shroud_root_radius now says: "
      f"{meanline.shroud_root_radius(r_in):.4f}")

t0 = time.time()
rep = meanline.build_from_design(d)
dt = time.time() - t0
print(f"\n  build_from_design: ok={rep.ok} in {dt:.1f} s")
print(rep.summary())
