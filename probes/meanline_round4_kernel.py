"""Round four: both sides of the new inlet-flow rule, put to the kernel.

A rule that refuses correct work is as bad as one that passes wrong work, so
three whole wheels are built here — the shipped sample, the most blocked wheel
the corpus calls sound, and a plausible micro blower the existing tenth passes:

  * the shipped sample        0.5   kg/s PR 3.0   45,000 rpm  — must still build
  * the micro turbo           0.05  kg/s PR 1.8  180,000 rpm  — must still build
    (the corpus's worst: its measured passage is 1.59x past choking)
  * a micro blower            0.01  kg/s PR 1.3   90,000 rpm  — must be REFUSED
    (10.66% open, so the tenth passes it; its 14 mm2 of passage can take
     0.0035 kg/s and the duty asks for 0.01)

    python probes/meanline_round4_kernel.py [sample|micro|blower]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import inspector                                                 # noqa: E402
import meanline                                                  # noqa: E402

WHEELS = {
    "sample": dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000),
    "micro": dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000),
    "blower": dict(mass_flow=0.01, pressure_ratio=1.3, rpm=90000),
}


def run(key):
    duty = meanline.Duty(**WHEELS[key])
    d = meanline.design(duty)
    print(f"{key}: r2 {d.tip_radius} mm, Z {d.blade_count}, eye "
          f"{d.inducer_shroud_radius} mm, choke flux "
          f"{d.inlet_choke_flux:.6g} kg/s/mm2")
    for note in d.notes:
        print(f"  NOTE: {note}")
    t0 = time.time()
    rep = meanline.build_from_design(d)
    print(f"  built in {time.time() - t0:.1f} s   ok={rep.ok}")
    for p in rep.all_problems():
        print(f"  PROBLEM: {p}")
    if rep.part is not None:
        m = inspector.measure(rep.part)
        open_mm2, available = meanline.eye_passage(rep.part, d)
        print(f"  volume {m['volume']:,.3f} mm3   solids {m['n_solids']}   "
              f"manifold {m.get('is_manifold')}   faces {len(rep.part.faces())}")
        print(f"  eye passage {open_mm2:,.2f} mm2 of {available:,.2f} "
              f"({100 * open_mm2 / available:.2f}%)   most it can pass "
              f"{d.inlet_choke_flux * open_mm2:.4g} kg/s against "
              f"{d.mass_flow:g} kg/s asked "
              f"({d.mass_flow / (d.inlet_choke_flux * open_mm2):.2f}x)")
        print(f"  {d.blade_count}-fold symmetric: "
              f"{inspector.is_rotationally_symmetric(rep.part, d.blade_count)}")


if __name__ == "__main__":
    for key in (sys.argv[1:] or ["sample", "micro", "blower"]):
        run(key)
        print()
