"""probes/meanline_bore_sweep.py -- ROUND TWO: does `one_blade` cut the bore
out of EVERY blade the product can build, or only the traced kind round one
measured?

    C:/Python314/python.exe probes/meanline_bore_sweep.py [quick|full]

Round one fixed the plugged bore by cutting the shaft cylinder out of the ONE
blade `build_from_design` patterns, and proved it on three duties. A bore that
is clear on three duties and plugged on a shape nobody tried is the same
defect. So this sweeps the whole shape space the duty dials can reach --
heavily backswept, forward swept, tall inducer, thick and thin blades, the
smallest and the largest wheel the gate allows -- and for each one MEASURES,
with real booleans:

  raw_in    mm3 of the UNCUT blade sitting inside the shaft bore
  cut_in    mm3 of the blade `one_blade` returns sitting inside the bore
  n_solids  of the cut blade  (a cut that SEVERS a blade is silent wrong
            geometry: the pieces still pattern into a watertight wheel)
  dvol      cut volume - raw volume where the raw blade ALREADY cleared the
            bore -- the "untouched to the last digit" claim, on more than the
            one shipped duty
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import blocks        # noqa: E402
import inspector     # noqa: E402
import meanline      # noqa: E402
from build123d import Cylinder  # noqa: E402


def cases(full: bool):
    """Duties chosen to move the blade's SHAPE, not just its size."""
    out = [
        # (name, duty kwargs)
        ("shipped sample",   dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000)),
        ("micro turbo",      dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000)),
        ("small turbo",      dict(mass_flow=0.1, pressure_ratio=2.0, rpm=120000)),
        ("blower PR1.5",     dict(mass_flow=0.5, pressure_ratio=1.5, rpm=45000)),
        ("blower PR1.3",     dict(mass_flow=0.5, pressure_ratio=1.3, rpm=45000)),
        ("big turbo",        dict(mass_flow=2.0, pressure_ratio=4.0, rpm=25000)),
        ("industrial",       dict(mass_flow=5.0, pressure_ratio=2.5, rpm=15000)),
        ("big industrial",   dict(mass_flow=20.0, pressure_ratio=3.5, rpm=8000)),
        ("largest measured", dict(mass_flow=50.0, pressure_ratio=2.0, rpm=3000)),
        # tiny flow: the eye collapses onto the hub nose, exit width clamps
        ("1e-6 kg/s",        dict(mass_flow=1e-6, pressure_ratio=3.0, rpm=45000)),
        ("1e-4 kg/s",        dict(mass_flow=1e-4, pressure_ratio=1.5, rpm=500000)),
        # the smallest wheel the gate lets through
        ("smallest wheel",   dict(mass_flow=1e-6, pressure_ratio=1.5, rpm=500000)),
    ]
    # the BACKSWEEP is the dial that changes the blade's shape most: it sets
    # both blade angles, so the camber wrap and the inner cap's overshoot move
    # with it.  tests/test_mcp_server.py blesses -60 .. 74.
    for beta in (-60.0, -30.0, 0.0, 15.0, 25.0, 45.0, 60.0, 70.0, 74.0):
        out.append((f"backsweep {beta:g} (small wheel)",
                    dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000,
                         backsweep_deg=beta)))
        out.append((f"backsweep {beta:g} (sample)",
                    dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000,
                         backsweep_deg=beta)))
    if full:
        # a tall inducer: a low pressure ratio at a low speed opens the eye
        for pr in (1.2, 1.4, 2.0, 6.0, 10.0):
            out.append((f"PR {pr:g} @ 10k rpm",
                        dict(mass_flow=0.5, pressure_ratio=pr, rpm=10000)))
        # the big end of the new bound
        out.append(("half speed 50kg/s",
                    dict(mass_flow=50.0, pressure_ratio=2.0, rpm=1500)))
        out.append(("20 metre wheel",
                    dict(mass_flow=50.0, pressure_ratio=2.0, rpm=325.3597)))
    return out


def raw_blade(d):
    return blocks.curved_blade(
        inner_radius=0.75 * d.inducer_hub_radius, outer_radius=d.tip_radius,
        inlet_angle_deg=d.beta1_deg, exit_angle_deg=d.beta2_deg,
        height=d.axial_length, thickness=max(0.02 * d.tip_radius, 1.5))


def inside(shape, d):
    if shape is None:
        return 0.0
    got = shape & Cylinder(radius=d.bore_radius, height=8.0 * d.axial_length)
    return float(got.volume) if got is not None else 0.0


def main():
    full = len(sys.argv) > 1 and sys.argv[1] == "full"
    print(f"{'case':28s} {'r2':>9s} {'bore':>7s} {'thk':>6s} "
          f"{'raw_in':>10s} {'cut_in':>9s} {'dvol':>12s} {'nsol':>4s} "
          f"{'valid':>5s} {'shut':>5s}")
    bad = []
    for name, kw in cases(full):
        try:
            d = meanline.design(meanline.Duty(**kw))
        except ValueError as e:
            print(f"{name:28s} REFUSED: {str(e)[:70]}")
            continue
        t0 = time.time()
        try:
            raw = raw_blade(d)
            cut = meanline.one_blade(d)
        except Exception as e:                       # OCP errors are Exception
            print(f"{name:28s} CRASH: {type(e).__name__}: {str(e)[:60]}")
            bad.append((name, "crash"))
            continue
        raw_in, cut_in = inside(raw, d), inside(cut, d)
        nsol = len(cut.solids())
        valid = bool(cut.is_valid)
        shut = not inspector.health(cut)
        dvol = float(cut.volume) - float(raw.volume)
        thk = max(0.02 * d.tip_radius, 1.5)
        print(f"{name:28s} {d.tip_radius:9.2f} {d.bore_radius:7.2f} "
              f"{thk:6.2f} {raw_in:10.3f} {cut_in:9.6f} {dvol:12.6f} "
              f"{nsol:4d} {str(valid):>5s} {str(shut):>5s}  "
              f"({time.time() - t0:.1f}s)")
        if cut_in > 1e-9:
            bad.append((name, f"bore plugged by {cut_in:.3f} mm3"))
        if nsol != 1:
            bad.append((name, f"blade is {nsol} solids"))
        if not valid or not shut:
            bad.append((name, "blade is not a sound closed solid"))
        if raw_in <= 1e-9 and abs(dvol) > 1e-9:
            bad.append((name, f"clear blade CHANGED by {dvol:.9f} mm3"))
        if cut.volume <= 0:
            bad.append((name, "blade is empty"))
    print("\n=== VERDICT ===")
    for name, why in bad:
        print(f"  BAD  {name}: {why}")
    if not bad:
        print("  every blade: bore clear, one sound solid, clear blades "
              "untouched")


if __name__ == "__main__":
    main()
