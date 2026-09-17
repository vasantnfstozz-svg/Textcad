"""Round four, attacking round three's eye rule: is a tenth the right line?

Round three set `_EYE_OPEN_FRACTION = 0.10` from NINE kernel-built wheels —
3.21 / 3.36 / 6.55 percent below it and 16.06 / 26.50 / 31.37 / 37.43 / 68.96 /
70.71 above. A nine-point corpus with a 2.5x hole in the middle cannot say
whether the line is in the right place; it can only say it is in the hole.

So this builds a MODEL of the same quantity, calibrates it against those nine
kernel measurements, and then puts thousands of duties to it. The model is not
trusted: it is only used where it agrees with the kernel.

    blocked fraction at radius r  =  Z * thickness / (2*pi*r*cos(beta(r)))
    open area = integral over the eye annulus of max(0, 1 - blocked) * 2*pi*r dr

`beta(r)` is the angle of the camber the kernel actually draws — the discrete
one `blocks.curved_blade` integrates with 16 forward-Euler steps — NOT the
design's own law. That distinction is worth 1.5x in the inducer (round four's
finding: the metal stands 15 to 28 degrees steeper than `beta1_deg` says).

    python probes/meanline_eye_model_round4.py calibrate
    python probes/meanline_eye_model_round4.py sweep
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline                                                  # noqa: E402

N = 16


def camber(d):
    """(radii, thetas) of the polyline `blocks.curved_blade` integrates."""
    ri, ro = 0.75 * d.inducer_hub_radius, d.tip_radius
    b1, b2 = d.beta1_deg, d.beta2_deg
    rs, ths, theta = [], [], 0.0
    for i in range(N + 1):
        t = i / N
        r = ri + (ro - ri) * t
        rs.append(r)
        ths.append(theta)
        if i < N:
            beta = math.radians(b1 + (b2 - b1) * t)
            theta += math.tan(beta) / r * ((ro - ri) / N)
    return rs, ths


def beta_metal(d, r, cache=None):
    """The camber's own angle from radial at radius r, centred difference."""
    rs, ths = cache if cache is not None else camber(d)
    if r <= rs[0]:
        i = 1
    elif r >= rs[-1]:
        i = len(rs) - 2
    else:
        i = max(1, min(len(rs) - 2,
                       int((r - rs[0]) / (rs[1] - rs[0]))))
    dth = ths[i + 1] - ths[i - 1]
    dr = rs[i + 1] - rs[i - 1]
    return math.degrees(math.atan2(rs[i] * dth, dr))


def beta_law(d, r):
    ri, ro = 0.75 * d.inducer_hub_radius, d.tip_radius
    return d.beta1_deg + (d.beta2_deg - d.beta1_deg) * (r - ri) / (ro - ri)


def open_fraction(d, use_metal=True, steps=400):
    """The model's answer for `eye_passage`'s open/available ratio."""
    r1s = d.inducer_shroud_radius
    inner = max(d.inducer_hub_radius, d.bore_radius)
    if r1s <= inner:
        return 0.0
    thk = max(0.02 * d.tip_radius, 1.5)
    Z = d.blade_count
    area_open, area_all = 0.0, 0.0
    dr = (r1s - inner) / steps
    cache = camber(d)
    for i in range(steps):
        r = inner + (i + 0.5) * dr
        beta = beta_metal(d, r, cache) if use_metal else beta_law(d, r)
        c = math.cos(math.radians(beta))
        blocked = 1.0 if c <= 1e-6 else Z * thk / (2.0 * math.pi * r * c)
        ring = 2.0 * math.pi * r * dr
        area_all += ring
        area_open += ring * max(0.0, 1.0 - blocked)
    return area_open / area_all if area_all > 0 else 0.0


# The nine wheels round three BUILT (meanline.py's own comment block), with the
# percentage the kernel read for each.
KERNEL = [
    (dict(mass_flow=0.005, pressure_ratio=1.8, rpm=250000,
          backsweep_deg=60.0), 3.21),
    (dict(mass_flow=0.005, pressure_ratio=1.1, rpm=100000,
          backsweep_deg=35.0), 3.36),
    (dict(mass_flow=0.005, pressure_ratio=1.8, rpm=90000,
          backsweep_deg=-20.0), 6.55),
    (dict(mass_flow=0.02, pressure_ratio=2.5, rpm=150000,
          backsweep_deg=35.0), 16.06),
    (dict(mass_flow=0.005, pressure_ratio=4.0, rpm=90000,
          backsweep_deg=0.0), 26.50),
    (dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000,
          backsweep_deg=35.0), 31.37),
    (dict(mass_flow=0.1, pressure_ratio=4.0, rpm=250000,
          backsweep_deg=25.0), 37.43),
    (dict(mass_flow=20.0, pressure_ratio=2.5, rpm=5000,
          backsweep_deg=35.0), 68.96),
    (dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000,
          backsweep_deg=35.0), 70.71),
]


def calibrate():
    print("duty                                    kernel   model(metal)  "
          "model(law)")
    worst = 0.0
    for kw, pct in KERNEL:
        d = meanline.design(meanline.Duty(**kw))
        m = 100.0 * open_fraction(d, True)
        law = 100.0 * open_fraction(d, False)
        worst = max(worst, abs(m - pct))
        print(f"{kw['mass_flow']:>8g} kg/s PR{kw['pressure_ratio']:<4g} "
              f"{kw['rpm']:>7g} rpm {kw['backsweep_deg']:>5g} deg  "
              f"{pct:7.2f}  {m:9.2f}  {law:10.2f}")
    print(f"\nworst model-vs-kernel error: {worst:.2f} percentage points")


def sweep():
    """Where do real duties land against the tenth?"""
    flows = [0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0,
             10.0, 20.0, 50.0]
    prs = [1.1, 1.2, 1.5, 1.8, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
    rpms = [3000, 5000, 8000, 15000, 25000, 40000, 60000, 90000, 120000,
            180000, 250000]
    sweeps = [-20.0, 0.0, 25.0, 35.0, 45.0, 60.0]
    bands = {k: 0 for k in ("<5", "5-8", "8-10", "10-12", "12-16", "16-25",
                            ">25")}
    near = []
    designed = refused = 0
    for mf in flows:
        for pr in prs:
            for rpm in rpms:
                for bs in sweeps:
                    try:
                        d = meanline.design(meanline.Duty(
                            mass_flow=mf, pressure_ratio=pr, rpm=rpm,
                            backsweep_deg=bs))
                    except ValueError:
                        refused += 1
                        continue
                    designed += 1
                    f = 100.0 * open_fraction(d, True)
                    key = ("<5" if f < 5 else "5-8" if f < 8 else
                           "8-10" if f < 10 else "10-12" if f < 12 else
                           "12-16" if f < 16 else "16-25" if f < 25 else ">25")
                    bands[key] += 1
                    if 6.0 <= f <= 16.0:
                        near.append((f, mf, pr, rpm, bs, d.tip_radius,
                                     d.blade_count))
    print(f"{designed} designs, {refused} refused by the existing gates")
    for k in ("<5", "5-8", "8-10", "10-12", "12-16", "16-25", ">25"):
        print(f"  {k:>6} % open : {bands[k]:5d}")
    near.sort()
    print(f"\n{len(near)} duties land between 6 and 16 percent "
          f"(the line is 10):")
    for f, mf, pr, rpm, bs, r2, Z in near[:40]:
        print(f"  {f:6.2f}%  {mf:>8g} kg/s PR{pr:<4g} {rpm:>7g} rpm "
              f"{bs:>5g} deg   r2 {r2:8.2f}  Z {Z}")


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "calibrate"
    if what == "calibrate":
        calibrate()
    else:
        sweep()
