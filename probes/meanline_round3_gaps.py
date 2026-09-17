"""Round three, the cheap questions: attack round two's own rule, and look for
a published number with no area behind it.

1. How near the knife edge does round two's `b2 > L` refusal cut? A duty
   refused at b2/L = 1.0001 is a wheel that is 0.01% wrong, not 39%.
2. Is the INLET ANNULUS the design publishes ever of zero area? `r1s` is
   sqrt(area/pi + r1h**2), so a duty whose continuity area vanishes beside the
   hub gives r1s == r1h and an eye with nothing in it — and `_check_wheel`
   only asks whether r1s is inside the RIM.
3. What blade counts the dials reach (the eye blockage is Z * thickness).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import math      # noqa: E402
import meanline as M   # noqa: E402

FLOW = [1e-4, 1e-3, 0.005, 0.02, 0.05, 0.2, 0.5, 2.0, 5.0, 20.0, 50.0]
PR = [1.01, 1.05, 1.2, 1.5, 2.0, 3.0, 4.5, 7.0]
RPM = [200, 500, 1200, 3000, 8000, 20000, 45000, 100000, 200000, 400000]
BS = [-60.0, -30.0, 0.0, 25.0, 35.0, 45.0, 60.0, 70.0]

near_edge = []
zero_eye = []
zs = set()
ok = refused = 0
for f in FLOW:
    for p in PR:
        for n in RPM:
            for b in BS:
                duty = M.Duty(mass_flow=f, pressure_ratio=p, rpm=n,
                              backsweep_deg=b)
                try:
                    M._check(duty)
                except ValueError:
                    continue
                # re-derive the design WITHOUT the wheel gate, to see what the
                # gate is refusing
                import copy
                d = None
                try:
                    d = M.design(duty)
                    ok += 1
                    zs.add(d.blade_count)
                except ValueError as e:
                    refused += 1
                    msg = str(e)
                    if "deep" in msg:
                        # pull the two numbers back out of the sentence
                        import re
                        nums = re.findall(r"([\d,]+\.\d\d) mm", msg)
                        if len(nums) >= 2:
                            b2 = float(nums[0].replace(",", ""))
                            L = float(nums[1].replace(",", ""))
                            near_edge.append((b2 / L, f, p, n, b, b2, L))
                    continue
                if d is not None:
                    gap = d.inducer_shroud_radius - d.inducer_hub_radius
                    area = math.pi * (d.inducer_shroud_radius ** 2
                                      - d.inducer_hub_radius ** 2)
                    zero_eye.append((area, gap, f, p, n, b, d))
                del copy

print(f"designs accepted {ok}, refused {refused}")
print(f"blade counts reachable: {sorted(zs)}")
print()
near_edge.sort()
print(f"duties refused by the b2 > L rule: {len(near_edge)}")
for r in near_edge[:6]:
    print(f"  b2/L {r[0]:8.4f}  {r[1]:g} kg/s PR{r[2]:g} {r[3]:g} rpm "
          f"bs{r[4]:g}   b2 {r[5]:.2f} vs L {r[6]:.2f}  -> the wheel would be "
          f"{100*(r[0]-1):.2f}% short of its published width")
print()
zero_eye.sort()
print("the 8 smallest inlet annuli the gate lets through:")
for r in zero_eye[:8]:
    d = r[6]
    print(f"  annulus {r[0]:12.4f} mm2  (r1s-r1h {r[1]:8.4f} mm)  "
          f"{r[2]:g} kg/s PR{r[3]:g} {r[4]:g} rpm bs{r[5]:g} | r2 "
          f"{d.tip_radius:9.2f}  r1h {d.inducer_hub_radius:8.2f} r1s "
          f"{d.inducer_shroud_radius:8.2f}  Z {d.blade_count}")
print()
n0 = sum(1 for r in zero_eye if r[0] <= 0.0)
print(f"designs whose published inlet annulus has ZERO area: {n0}")
print(f"designs whose annulus is under 1 mm2: "
      f"{sum(1 for r in zero_eye if r[0] < 1.0)}")
