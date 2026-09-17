"""Round four, attacking round three's impeller fix.

`impeller._one_blade` now takes the shaft bore out of the blade before the
pattern, as `meanline.one_blade` does. Two questions the brief asks:

  1. is the SHIPPED impeller really identical? Round three's commit message
     says 30,902.254 mm3 / 39 faces and the docstring it wrote into
     `impeller.py` says 89,143.229 mm3 / 37 faces — they cannot both be the
     impeller, so it is measured here rather than read.
  2. can that cut SEVER a blade? A cylinder centred on the axis eats the inner
     end of a blade that starts at `hub_top_radius`; if it could ever leave
     two pieces, the wheel would come back with more solids than blades and
     the spec would have to say so.

    python probes/impeller_round4_sever.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build123d as b3d                                          # noqa: E402

import impeller                                                  # noqa: E402
import inspector                                                 # noqa: E402


def blade_solids(p):
    blade = impeller._one_blade(p)
    return (len(blade.solids()), float(blade.volume) if blade is not None
            else 0.0)


if __name__ == "__main__":
    p = impeller.ImpellerParams()
    t0 = time.time()
    rep = impeller.build(p)
    m = inspector.measure(rep.part) if rep.part is not None else {}
    print(f"shipped impeller: ok={rep.ok}  volume {m.get('volume'):,.3f} mm3  "
          f"faces {len(rep.part.faces())}  solids {m.get('n_solids')}  "
          f"symmetry {inspector.rotational_symmetry_order(rep.part, max_n=14)}"
          f"  ({time.time() - t0:.1f} s)")
    plug = rep.part & b3d.Cylinder(radius=p.bore_radius,
                                   height=4.0 * p.hub_height)
    print(f"  material inside its own {p.bore_radius} mm bore: "
          f"{0.0 if plug is None else plug.volume:,.6f} mm3")

    print("\nONE BLADE against a growing bore (hub nose 9.0, tip 40.0, "
          "thickness 3.0):")
    for bore in (2.0, 6.0, 9.0, 12.0, 20.0, 30.0, 39.0, 39.9, 40.05, 41.0):
        q = impeller.ImpellerParams(bore_radius=bore)
        try:
            n, vol = blade_solids(q)
        except Exception as e:
            print(f"  bore {bore:6.2f}: raised {type(e).__name__}: "
                  f"{str(e)[:60]}")
            continue
        print(f"  bore {bore:6.2f}: {n} solid(s), {vol:12.3f} mm3"
              f"{'   <-- SEVERED' if n > 1 else ''}"
              f"{'   <-- nothing left' if vol <= 0 else ''}")

    print("\nthe whole wheel at the bores that matter:")
    for bore in (6.0, 12.0, 22.0, 39.0):
        q = impeller.ImpellerParams(bore_radius=bore)
        try:
            r = impeller.build(q)
        except Exception as e:
            print(f"  bore {bore:6.2f}: raised {type(e).__name__}: "
                  f"{str(e)[:70]}")
            continue
        mm = inspector.measure(r.part) if r.part is not None else {}
        print(f"  bore {bore:6.2f}: ok={r.ok}  solids {mm.get('n_solids')}  "
              f"volume {mm.get('volume', 0):,.3f}")
        for problem in r.all_problems():
            print(f"      {problem[:110]}")
