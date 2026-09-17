"""probes/meanline_gate_boundary_probe.py -- REVIEW round: what does the new
size gate REFUSE, and is any of it a real machine?

No kernel. `_check_wheel` is patched out so the raw answer is visible, then
each gate is evaluated by hand and the firing one named. Sweeps the band a
person would actually ask for (low-pressure blowers, big slow industrial
stages, tiny high-speed wheels) plus the deliberate nonsense.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline  # noqa: E402

_real = meanline._check_wheel
meanline._check_wheel = lambda d, duty=None: None


def raw(flow, pr, rpm, beta=35.0):
    return meanline.design(meanline.Duty(mass_flow=flow, pressure_ratio=pr,
                                         rpm=rpm, backsweep_deg=beta))


def verdict(d):
    if d.tip_radius > meanline._R2_MAX_MM:
        return "REFUSED r2>max"
    if d.tip_radius < meanline._R2_MIN_MM:
        return "REFUSED r2<min"
    if d.exit_width >= d.tip_radius:
        return "REFUSED b2>=r2"
    if d.inducer_shroud_radius >= d.tip_radius:
        return "REFUSED eye>=r2"
    return "passes"


ROWS = [
    # ---- low pressure ratio: blowers and boost stages people really build
    ("blower PR1.05 0.5kg 45k",   0.5,  1.05,  45000),
    ("blower PR1.1  0.5kg 45k",   0.5,  1.10,  45000),
    ("blower PR1.2  0.5kg 45k",   0.5,  1.20,  45000),
    ("blower PR1.3  0.5kg 45k",   0.5,  1.30,  45000),
    ("blower PR1.5  0.5kg 45k",   0.5,  1.50,  45000),
    ("PR1.2 0.05kg 45k",         0.05,  1.20,  45000),
    ("PR1.2 0.5kg 10k",           0.5,  1.20,  10000),
    ("PR1.2 0.5kg  5k",           0.5,  1.20,   5000),
    ("PR1.1 0.1kg 20k",           0.1,  1.10,  20000),
    ("PR1.15 2kg 12k",            2.0,  1.15,  12000),
    # ---- big slow industrial: does anything real sit past r2 = 2000 mm?
    ("industrial 50kg 3000rpm",  50.0,  2.00,   3000),
    ("industrial 50kg 2000rpm",  50.0,  2.00,   2000),
    ("industrial 50kg 1500rpm",  50.0,  2.00,   1500),
    ("industrial 100kg 1500rpm",100.0,  2.00,   1500),
    ("industrial 20kg 1000rpm",  20.0,  2.00,   1000),
    ("industrial 5kg  900rpm",    5.0,  2.50,    900),
    ("PR8 1kg 3000rpm",           1.0,  8.00,   3000),
    # ---- tiny fast: does anything real sit below r2 = 1 mm?
    ("micro 0.01kg 300k",        0.01,  1.50, 300000),
    ("micro 0.005kg 600k",      0.005,  1.30, 600000),
    ("micro 0.001kg 1e6",       0.001,  1.20,1000000),
    ("micro 0.001kg 3e6",       0.001,  1.20,3000000),
    ("dental 1e-4 kg 5e5",      1e-4,   1.50, 500000),
    # ---- the corpus the gate claims (sanity: all must pass)
    ("SOUND shipped",             0.5,  3.00,  45000),
    ("SOUND mcp",                 1.0,  3.00,  40000),
    ("SOUND small turbo",         0.1,  2.00, 120000),
    ("SOUND micro turbo",        0.05,  1.80, 180000),
    ("SOUND big turbo",           2.0,  4.00,  25000),
    ("SOUND industrial",          5.0,  2.50,  15000),
    ("SOUND big industrial",     20.0,  3.50,   8000),
    ("SOUND largest",            50.0,  2.00,   3000),
]

hdr = (f"{'duty':26s} {'r2 mm':>11s} {'b2 mm':>10s} {'eye':>10s} "
       f"{'b2/r2':>7s} {'eye/r2':>7s} {'U2':>8s} {'kW':>10s}  verdict")
print(hdr)
print("-" * len(hdr))
for name, w, pr, rpm in ROWS:
    try:
        d = raw(w, pr, rpm)
    except Exception as e:
        print(f"{name:26s} equations refused: {e}")
        continue
    print(f"{name:26s} {d.tip_radius:11.2f} {d.exit_width:10.2f} "
          f"{d.inducer_shroud_radius:10.2f} "
          f"{d.exit_width/d.tip_radius:7.3f} "
          f"{d.inducer_shroud_radius/d.tip_radius:7.3f} "
          f"{d.tip_speed:8.1f} {d.power_kw:10.2f}  {verdict(d)}")

meanline._check_wheel = _real
