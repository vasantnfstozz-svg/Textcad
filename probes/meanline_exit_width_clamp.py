"""probes/meanline_exit_width_clamp.py -- ROUND TWO: how far does the silent
`exit_width` clamp move the number the user reads?

`design()` ends with `exit_width=round(max(b2 * 1000, 1.0), 2)`. The 1.0 mm is
a machinable floor and it is right to have one -- but nothing says it fired,
so the design REPORTS a width the physics never asked for, and the MCP tool
hands that number straight to an AI as `exit_width_mm`.

This measures the true b2 beside the reported one for every duty the corpus
and the plan name, so the sentence that closes it quotes a measured number.

    C:/Python314/python.exe probes/meanline_exit_width_clamp.py

It also puts a set of HAND-BUILT bore radii to `one_blade` -- 0.5, 0.9, 0.99
and 0.999 of the rim -- to answer round two's question "can the cut now sever
a blade, or leave an empty one?" on the shapes `design()` itself never makes.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import inspector   # noqa: E402
import meanline    # noqa: E402
from build123d import Cylinder  # noqa: E402

DUTIES = [
    ("shipped sample",  dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000)),
    ("MCP test duty",   dict(mass_flow=1.0, pressure_ratio=3.0, rpm=40000)),
    ("small turbo",     dict(mass_flow=0.1, pressure_ratio=2.0, rpm=120000)),
    ("micro turbo",     dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000)),
    ("big turbo",       dict(mass_flow=2.0, pressure_ratio=4.0, rpm=25000)),
    ("industrial",      dict(mass_flow=5.0, pressure_ratio=2.5, rpm=15000)),
    ("big industrial",  dict(mass_flow=20.0, pressure_ratio=3.5, rpm=8000)),
    ("largest measured", dict(mass_flow=50.0, pressure_ratio=2.0, rpm=3000)),
    ("PR3 @ 1000 rpm",  dict(mass_flow=0.5, pressure_ratio=3.0, rpm=1000)),
    ("50 kg/s @ 1500",  dict(mass_flow=50.0, pressure_ratio=2.0, rpm=1500)),
    ("20 metre wheel",  dict(mass_flow=50.0, pressure_ratio=2.0, rpm=325.3597)),
    ("1e-6 kg/s",       dict(mass_flow=1e-6, pressure_ratio=3.0, rpm=45000)),
    ("1e-4 kg/s",       dict(mass_flow=1e-4, pressure_ratio=1.5, rpm=500000)),
]


def true_b2_mm(duty, flow_coeff=0.28):
    """The same arithmetic `design()` does, without the floor."""
    g, cp = duty.gamma, duty.cp
    beta2 = math.radians(duty.backsweep_deg)
    dh0 = cp * duty.T01 * (duty.pressure_ratio ** ((g - 1) / g) - 1.0) / duty.eta
    sigma_target = 0.85
    z = (math.sqrt(math.cos(beta2)) / (1.0 - sigma_target)) ** (1.0 / 0.7)
    Z = max(5, round(z))
    sigma = 1.0 - math.sqrt(math.cos(beta2)) / Z ** 0.7
    U2 = math.sqrt(dh0 / (sigma * (1.0 - flow_coeff * math.tan(beta2))))
    r2 = U2 / (2.0 * math.pi * duty.rpm / 60.0)
    rho01 = duty.P01 / (duty.R * duty.T01)
    rho2 = rho01 * duty.pressure_ratio ** (1.0 / g)
    return duty.mass_flow / (rho2 * flow_coeff * U2 * 2.0 * math.pi * r2) * 1000.0


print("=== the exit-width floor: what it hides ===")
print(f"{'duty':20s} {'r2 mm':>10s} {'b2 true':>12s} {'b2 said':>8s} "
      f"{'x':>8s}")
for name, kw in DUTIES:
    duty = meanline.Duty(**kw)
    try:
        d = meanline.design(duty)
    except ValueError as e:
        print(f"{name:20s} REFUSED: {str(e)[:50]}")
        continue
    t = true_b2_mm(duty)
    print(f"{name:20s} {d.tip_radius:10.2f} {t:12.6f} {d.exit_width:8.2f} "
          f"{d.exit_width / t:8.1f}" + ("   <-- CLAMPED" if t < 1.0 else ""))

# the smallest flow that does NOT clamp, for the shipped speed and ratio
lo, hi = 1e-9, 1.0
for _ in range(80):
    mid = (lo + hi) / 2
    if true_b2_mm(meanline.Duty(mass_flow=mid, pressure_ratio=3.0,
                                rpm=45000)) < 1.0:
        lo = mid
    else:
        hi = mid
print(f"\nat PR 3.0 / 45,000 rpm the floor fires below {hi:.4f} kg/s "
      f"(the shipped duty is 0.5 kg/s)")

print("\n=== can the bore cut sever or empty a blade? hand-built bores ===")
d = meanline.design(meanline.Duty(mass_flow=0.5, pressure_ratio=3.0,
                                  rpm=45000))
raw_vol = None
for frac in (0.1, 0.5, 0.9, 0.99, 0.999, 1.0, 1.01):
    d.bore_radius = round(frac * d.tip_radius, 4)
    try:
        meanline._check_wheel(d)
        gated = "allowed"
    except ValueError as e:
        gated = f"REFUSED ({str(e)[:40]}...)"
    try:
        blade = meanline.one_blade(d)
    except Exception as e:
        print(f"  bore {d.bore_radius:8.2f} ({frac:5g} r2)  {gated:10s} "
              f"CRASH {type(e).__name__}: {str(e)[:40]}")
        continue
    if raw_vol is None and frac == 0.1:
        raw_vol = None
    vol = float(blade.volume)
    nsol = len(blade.solids())
    left = blade & Cylinder(radius=d.bore_radius, height=8.0 * d.axial_length)
    inside = float(left.volume) if left is not None else 0.0
    print(f"  bore {d.bore_radius:8.2f} ({frac:5g} r2)  {gated:10s} "
          f"vol {vol:11.3f}  solids {nsol}  in-bore {inside:.6f}  "
          f"health {inspector.health(blade)}")
