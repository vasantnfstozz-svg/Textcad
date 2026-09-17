"""Round three: does the INLET EYE the design publishes exist in the metal?

`inducer_shroud_radius_mm` goes out of the MCP door. Nothing measures it
against the built solid. The blades stand in that annulus: Z of them, each
`max(0.02*r2, 1.5)` thick, leaning at beta1. Where 2*pi*r is smaller than the
blade metal at that radius the annulus is SOLID.
"""
import math
import meanline as M

FLOW = [1e-3, 0.01, 0.05, 0.2, 0.5, 2.0, 10.0, 50.0]
PR = [1.05, 1.2, 1.5, 2.0, 3.0, 5.0]
RPM = [300, 1000, 3000, 10000, 45000, 120000, 300000, 800000]
BS = [-30.0, 0.0, 25.0, 35.0, 45.0, 60.0]


def eye(d):
    """open axial area of the inlet annulus, and the ideal one."""
    r1h, r1s = d.inducer_hub_radius, d.inducer_shroud_radius
    thk = max(0.02 * d.tip_radius, 1.5)
    Z = d.blade_count
    # circumferential metal at radius r, blades leaning at beta1 from radial
    lean = 1.0 / max(math.cos(math.radians(d.beta1_deg)), 1e-6)
    metal = Z * thk * lean
    ideal = math.pi * (r1s ** 2 - r1h ** 2)
    lo = max(r1h, d.bore_radius)
    if r1s <= lo:
        return 0.0, ideal, metal / (2 * math.pi)
    n = 400
    open_a = 0.0
    for i in range(n):
        r = lo + (r1s - lo) * (i + 0.5) / n
        dr = (r1s - lo) / n
        open_a += max(2 * math.pi * r - metal, 0.0) * dr
    return open_a, ideal, metal / (2 * math.pi)


rows = []
built = 0
for f in FLOW:
    for p in PR:
        for n in RPM:
            for b in BS:
                try:
                    d = M.design(M.Duty(mass_flow=f, pressure_ratio=p, rpm=n,
                                        backsweep_deg=b))
                except ValueError:
                    continue
                built += 1
                o, ideal, rblk = eye(d)
                frac = o / ideal if ideal > 0 else 0.0
                rows.append((frac, f, p, n, b, d.tip_radius, d.blade_count,
                             d.inducer_hub_radius, d.inducer_shroud_radius,
                             d.bore_radius, rblk, o, ideal))

rows.sort()
print(f"duties accepted by both gates: {built}")
print(f"eye COMPLETELY blocked (0 open area): "
      f"{sum(1 for r in rows if r[0] <= 0.0)}")
print(f"eye under 50% open           : {sum(1 for r in rows if r[0] < 0.5)}")
print(f"eye under 90% open           : {sum(1 for r in rows if r[0] < 0.9)}")
print()
print("worst 15 (open/ideal, duty, r2, Z, r1h, r1s, bore, r_block, open, ideal)")
for r in rows[:15]:
    print(f"  {r[0]:7.3f}  {r[1]:g} kg/s PR{r[2]:g} {r[3]:g} rpm bs{r[4]:g}"
          f" | r2 {r[5]:8.2f} Z {r[6]:2d} r1h {r[7]:7.2f} r1s {r[8]:8.2f}"
          f" bore {r[9]:5.2f} rblk {r[10]:7.2f} open {r[11]:10.2f}"
          f" ideal {r[12]:10.2f}")
print()
print("best 3 (for contrast)")
for r in rows[-3:]:
    print(f"  {r[0]:7.3f}  {r[1]:g} kg/s PR{r[2]:g} {r[3]:g} rpm bs{r[4]:g}"
          f" | r2 {r[5]:8.2f} Z {r[6]:2d} r1s {r[8]:8.2f} rblk {r[10]:7.2f}")
