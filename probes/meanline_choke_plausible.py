"""Round four: would a flow-based eye rule refuse ORDINARY machines?

Before any limit moves, the wheels a person would actually ask for have to be
measured against it. These are plausible duties across the whole size range,
with the choke ratio (the duty's mass flow divided by the most its measured
inlet passage could pass, at the speed of sound) beside each.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline                                                  # noqa: E402
from meanline_eye_choke import choke_flux, open_area_mm2         # noqa: E402

PLAUSIBLE = [
    ("car turbo", 0.15, 2.2, 130000, 35.0),
    ("car turbo, big", 0.35, 2.5, 90000, 35.0),
    ("truck turbo", 0.6, 3.0, 60000, 35.0),
    ("APU load compressor", 1.0, 3.5, 45000, 35.0),
    ("small gas turbine", 2.0, 4.0, 30000, 35.0),
    ("high PR stage", 1.0, 5.0, 40000, 35.0),
    ("high PR, slower", 1.0, 5.0, 20000, 35.0),
    ("process blower", 5.0, 1.5, 12000, 35.0),
    ("industrial stage", 5.0, 2.5, 15000, 35.0),
    ("big industrial", 20.0, 3.5, 8000, 35.0),
    ("largest measured", 50.0, 2.0, 3000, 35.0),
    ("micro turbo", 0.05, 1.8, 180000, 35.0),
    ("micro blower", 0.01, 1.3, 90000, 35.0),
    ("model turbine", 0.08, 2.5, 150000, 35.0),
    ("drone blower", 0.02, 1.5, 100000, 35.0),
    ("radial blades", 1.0, 3.0, 40000, 0.0),
    ("hard backsweep", 1.0, 3.0, 40000, 60.0),
    ("forward swept", 1.0, 3.0, 40000, -20.0),
    ("the shipped sample", 0.5, 3.0, 45000, 35.0),
]


if __name__ == "__main__":
    print(f"{'machine':<22} {'r2 mm':>8} {'open %':>7} {'choke':>7}  verdict")
    for name, mf, pr, rpm, bs in PLAUSIBLE:
        duty = meanline.Duty(mass_flow=mf, pressure_ratio=pr, rpm=rpm,
                             backsweep_deg=bs)
        try:
            d = meanline.design(duty)
        except ValueError as e:
            print(f"{name:<22} refused: {e}")
            continue
        a_open, a_all = open_area_mm2(d)
        ratio = mf / (choke_flux(duty) * a_open) if a_open > 0 else 1e9
        verdict = ("refused by a 2x rule" if ratio >= 2.0
                   else "past choke" if ratio > 1.0 else "flows")
        print(f"{name:<22} {d.tip_radius:8.2f} {100 * a_open / a_all:7.2f} "
              f"{ratio:7.2f}  {verdict}")
