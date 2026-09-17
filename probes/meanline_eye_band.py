"""Where the blocked-eye band starts, in the duties a person would type.

Companion to meanline_eye_scan.py: same arithmetic, but restricted to the
backsweep window `_check_wheel` calls usual (25..45 deg) and to speeds a real
machine runs at, so the answer is "can a plausible duty do this", not "can
some corner of the grid".
"""
import math
import meanline as M

FLOW = [0.005, 0.01, 0.02, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0, 20.0]
PR = [1.05, 1.1, 1.3, 1.8, 2.5, 4.0]
RPM = [1000, 5000, 20000, 60000, 100000, 150000, 200000]
BS = [25.0, 30.0, 35.0, 40.0, 45.0]


def eye(d):
    r1h, r1s = d.inducer_hub_radius, d.inducer_shroud_radius
    thk = max(0.02 * d.tip_radius, 1.5)
    lean = 1.0 / max(math.cos(math.radians(d.beta1_deg)), 1e-6)
    metal = d.blade_count * thk * lean
    ideal = math.pi * (r1s ** 2 - r1h ** 2)
    lo = max(r1h, d.bore_radius)
    if r1s <= lo:
        return 0.0, ideal
    n = 400
    o = 0.0
    for i in range(n):
        r = lo + (r1s - lo) * (i + 0.5) / n
        o += max(2 * math.pi * r - metal, 0.0) * (r1s - lo) / n
    return o, ideal


rows = []
for f in FLOW:
    for p in PR:
        for n in RPM:
            for b in BS:
                try:
                    d = M.design(M.Duty(mass_flow=f, pressure_ratio=p, rpm=n,
                                        backsweep_deg=b))
                except ValueError:
                    continue
                o, ideal = eye(d)
                rows.append((o / ideal if ideal > 0 else 0.0, o, ideal,
                             f, p, n, b, d))

rows.sort(key=lambda r: r[0])
tot = len(rows)
print(f"plausible duties accepted: {tot}")
print(f"  eye 0% open  : {sum(1 for r in rows if r[0] <= 0.0)}")
print(f"  eye <25% open: {sum(1 for r in rows if r[0] < 0.25)}")
print(f"  eye <50% open: {sum(1 for r in rows if r[0] < 0.50)}")
print(f"  r1s == r1h   : {sum(1 for r in rows if r[7].inducer_shroud_radius <= r[7].inducer_hub_radius)}")
print()
for r in rows[:12]:
    d = r[7]
    print(f"  open {r[0]*100:6.2f}%  {r[3]:g} kg/s PR{r[4]:g} {r[5]:g} rpm "
          f"bs{r[6]:g} | r2 {d.tip_radius:8.2f} Z {d.blade_count:2d} "
          f"b2 {d.exit_width:6.2f} L {d.axial_length:8.2f} "
          f"r1h {d.inducer_hub_radius:7.2f} r1s {d.inducer_shroud_radius:8.2f} "
          f"bore {d.bore_radius:6.2f} beta1 {d.beta1_deg:5.1f} "
          f"thk {max(0.02*d.tip_radius,1.5):5.2f}")
