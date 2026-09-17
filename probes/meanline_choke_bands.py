"""Round four: how far past the choking limit do the grid's wheels sit?

`probes/meanline_eye_choke.py` shows the fixed tenth passes 3,178 of 6,273
designs whose measured inlet passage cannot pass their own mass flow. That
count alone does not say where a REFUSAL should sit: five of the eight wheels
the tests bless as sound are also past the limit (1.05x to 1.59x), so a rule
at the limit itself would refuse the module's own corpus.

This prints the distribution, so the line can be put where the corpus is not.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline                                                  # noqa: E402
from meanline_eye_choke import (FLOWS, PRS, RPMS, SWEEPS,        # noqa: E402
                                choke_flux, open_area_mm2)

SOUND = [
    ("the shipped sample", dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000)),
    ("the MCP test duty", dict(mass_flow=1.0, pressure_ratio=3.0, rpm=40000)),
    ("a small turbo", dict(mass_flow=0.1, pressure_ratio=2.0, rpm=120000)),
    ("a micro turbo", dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000)),
    ("a big turbo", dict(mass_flow=2.0, pressure_ratio=4.0, rpm=25000)),
    ("an industrial stage", dict(mass_flow=5.0, pressure_ratio=2.5, rpm=15000)),
    ("a big industrial", dict(mass_flow=20.0, pressure_ratio=3.5, rpm=8000)),
    ("the largest measured", dict(mass_flow=50.0, pressure_ratio=2.0,
                                  rpm=3000)),
]

BANDS = [0.5, 0.8, 1.0, 1.2, 1.6, 2.0, 3.0, 5.0, 10.0, 1e9]


def band_of(ratio):
    for b in BANDS:
        if ratio < b:
            return b
    return BANDS[-1]


def main():
    counts = {b: 0 for b in BANDS}
    tenth_refuses = {b: 0 for b in BANDS}
    for mf in FLOWS:
        for pr in PRS:
            for rpm in RPMS:
                for bs in SWEEPS:
                    duty = meanline.Duty(mass_flow=mf, pressure_ratio=pr,
                                         rpm=rpm, backsweep_deg=bs)
                    try:
                        d = meanline.design(duty)
                    except ValueError:
                        continue
                    a_open, a_all = open_area_mm2(d)
                    if a_all <= 0:
                        continue
                    ratio = (mf / (choke_flux(duty) * a_open)
                             if a_open > 0 else 1e9)
                    b = band_of(ratio)
                    counts[b] += 1
                    if a_open / a_all < meanline._EYE_OPEN_FRACTION:
                        tenth_refuses[b] += 1
    lo = 0.0
    print("choke ratio (duty / what the passage can pass)")
    print("   band          designs   of those, the tenth already refuses")
    for b in BANDS:
        label = f"{lo:>5.1f} - {b:<6.1f}" if b < 1e8 else f"{lo:>5.1f} +     "
        print(f"  {label}   {counts[b]:6d}   {tenth_refuses[b]:6d}")
        lo = b
    print("\nthe sound corpus:")
    for name, kw in SOUND:
        duty = meanline.Duty(**kw)
        d = meanline.design(duty)
        a_open, a_all = open_area_mm2(d)
        print(f"  {name:<22} open {100 * a_open / a_all:6.2f}%  "
              f"choke ratio {mf if False else 0:.0f}"
              f"{duty.mass_flow / (choke_flux(duty) * a_open):6.2f}x")


if __name__ == "__main__":
    main()
