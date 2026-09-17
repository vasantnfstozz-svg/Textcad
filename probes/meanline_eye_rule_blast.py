"""What the new eye-is-a-ring rule refuses, and what is left to test with.

Five tests at 967963d drive OTHER rules with micro-flow duties (1e-6 kg/s,
1e-4 kg/s at 500,000 rpm). The new rule refuses those duties, so this asks the
two questions a guard owes: is each refusal EARNED, and what duty still
exercises the rule the test was really about?
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline as M   # noqa: E402

print("=== the five duties the existing tests use ===")
OLD = [
    ("smallest wheel (bore sweep)", dict(mass_flow=1e-6, pressure_ratio=1.5,
                                         rpm=500000)),
    ("lower bound", dict(mass_flow=1e-4, pressure_ratio=1.5, rpm=500000)),
    ("clamp: 1e-6 kg/s", dict(mass_flow=1e-6, pressure_ratio=3.0, rpm=45000)),
    ("clamp: PR3 @ 1000 rpm", dict(mass_flow=0.5, pressure_ratio=3.0,
                                   rpm=1000)),
]
for name, kw in OLD:
    duty = M.Duty(**kw)
    # design WITHOUT the wheel gate, to see the numbers the gate is judging
    try:
        d = M.design(duty)
        print(f"  {name}: still designs. r2 {d.tip_radius} r1s "
              f"{d.inducer_shroud_radius} r1h {d.inducer_hub_radius} bore "
              f"{d.bore_radius} b2 {d.exit_width} ideal "
              f"{d.exit_width_ideal:.7f}")
    except ValueError as e:
        print(f"  {name}: REFUSED -> {e}")

print()
print("=== duties whose exit width still CLAMPS but whose eye is a ring ===")
FLOW = [1e-5, 1e-4, 1e-3, 0.005, 0.02, 0.05, 0.2, 0.5, 2.0]
PR = [1.05, 1.2, 1.5, 2.0, 3.0, 5.0]
RPM = [200, 500, 1000, 2000, 5000, 20000, 60000, 200000, 500000]
found = []
smallest = []
for f in FLOW:
    for p in PR:
        for n in RPM:
            try:
                d = M.design(M.Duty(mass_flow=f, pressure_ratio=p, rpm=n))
            except ValueError:
                continue
            smallest.append((d.tip_radius, f, p, n, d))
            if d.exit_width_ideal > 0 and d.exit_width > 1.01 * d.exit_width_ideal:
                found.append((d.exit_width / d.exit_width_ideal, f, p, n, d))
found.sort()
print(f"  {len(found)} clamped duties survive the new rule; widest "
      f"overstatement first:")
for r in found[-6:]:
    d = r[4]
    print(f"    x{r[0]:,.1f}  {r[1]:g} kg/s PR{r[2]:g} {r[3]:g} rpm | r2 "
          f"{d.tip_radius:9.2f} r1s {d.inducer_shroud_radius:8.2f} bore "
          f"{d.bore_radius:6.2f} ideal b2 {d.exit_width_ideal:.7f}")
print()
smallest.sort()
print("  the smallest wheels that survive EVERY rule now:")
for r in smallest[:5]:
    d = r[4]
    print(f"    r2 {r[0]:8.2f}  {r[1]:g} kg/s PR{r[2]:g} {r[3]:g} rpm | r1s "
          f"{d.inducer_shroud_radius:8.2f} bore {d.bore_radius:6.2f} "
          f"thk {max(0.02*d.tip_radius, 1.5):5.2f} b2 {d.exit_width:6.2f}")

print()
print("=== a finer hunt for the smallest surviving wheel ===")
best = None
f = 1e-5
while f <= 1.0:
    for p in (1.02, 1.05, 1.1, 1.2, 1.4, 1.7, 2.2, 3.0, 4.0):
        n = 100000.0
        while n <= 2000000.0:
            for b in (-40.0, 0.0, 25.0, 45.0, 65.0):
                try:
                    d = M.design(M.Duty(mass_flow=f, pressure_ratio=p, rpm=n,
                                        backsweep_deg=b))
                except ValueError:
                    continue
                if best is None or d.tip_radius < best[0]:
                    best = (d.tip_radius, f, p, n, b, d)
            n *= 1.5
    f *= 2.0
if best is not None:
    d = best[5]
    print(f"  r2 {best[0]:.2f} mm from {best[1]:g} kg/s PR{best[2]:g} "
          f"{best[3]:,.0f} rpm bs{best[4]:g} | r1s "
          f"{d.inducer_shroud_radius} bore {d.bore_radius} b2 {d.exit_width} "
          f"L {d.axial_length}  thickness {max(0.02*d.tip_radius, 1.5):.2f}")

print()
print("=== clamped duties by which sentence branch they exercise ===")
for want, lo, hi, rlo, rhi in (("micrometres + N times", 1e-3, 0.1, 1.01, 1000),
                               ("under a micrometre + N times", 0, 1e-3,
                                1.01, 1000),
                               ("under a micrometre + thousands", 0, 1e-3,
                                1000, 1e30)):
    hits = [r for r in found
            if lo <= r[4].exit_width_ideal < hi and rlo <= r[0] < rhi]
    print(f"  {want}: {len(hits)} duties")
    for r in sorted(hits, key=lambda r: -r[0])[:2]:
        d = r[4]
        print(f"     x{r[0]:,.1f}  {r[1]:g} kg/s PR{r[2]:g} {r[3]:g} rpm | "
              f"ideal {d.exit_width_ideal:.7f} r2 {d.tip_radius} r1s "
              f"{d.inducer_shroud_radius} bore {d.bore_radius}")
