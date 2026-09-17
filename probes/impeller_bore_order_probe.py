"""impeller.py has meanline's round-one P0 one edit away.

`_hub` drills the shaft bore with `blocks.with_center_hole` and `build` fuses
the blades on afterwards. The shipped defaults clear the bore (the blade starts
at `hub_top_radius` 9.0 against a 6.0 bore), so nothing is wrong TODAY — but
the spec it verifies against (symmetry, n_solids, require_manifold) is exactly
the set round one measured a plugged wheel passing.

    python probes/impeller_bore_order_probe.py         (as shipped)
    python probes/impeller_bore_order_probe.py old     (blade cut OFF)

Prints, for the shipped defaults and for a nose narrower than the bore:
the volume, the face count, the symmetry order, and the mm3 of wheel standing
inside its own shaft bore.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build123d as b3d   # noqa: E402
import impeller           # noqa: E402
import inspector          # noqa: E402

if len(sys.argv) > 1 and sys.argv[1] == "old":
    # the blade exactly as it stood before the fix: no bore cut
    from build123d import (BuildSketch, BuildLine, Polyline, make_face,
                           extrude, Plane, Axis)

    def _old_blade(p):
        with BuildSketch(Plane.XZ) as sk:
            with BuildLine():
                Polyline((p.hub_top_radius, 0.0), (p.tip_radius, 0.0),
                         (p.tip_radius, p.blade_height_tip),
                         (p.hub_top_radius, p.blade_height_hub), close=True)
            make_face()
        return extrude(sk.sketch, amount=p.blade_thickness).rotate(
            Axis.Z, p.backsweep_deg)

    impeller._one_blade = _old_blade
    print("=== the blade WITHOUT the bore cut (before the fix) ===")
else:
    print("=== the blade WITH the bore cut (as shipped) ===")

CASES = {
    "shipped": impeller.ImpellerParams(),
    # one edit: the hub nose is narrower than the bore, so the blade root
    # stands inside it
    "narrow nose": impeller.ImpellerParams(hub_top_radius=3.0,
                                           blade_height_hub=18.0),
    # the other edit: the same wheel with a bigger shaft
    "wide bore": impeller.ImpellerParams(bore_radius=12.0),
}

for name, p in CASES.items():
    rep = impeller.build(p)
    part = rep.part
    print(f"{name}: ok={rep.ok} problems={rep.all_problems()}")
    if part is None:
        continue
    m = inspector.measure(part)
    plug = part & b3d.Cylinder(radius=p.bore_radius,
                               height=8.0 * p.hub_height)
    vol = float(plug.volume) if plug is not None else 0.0
    print(f"   volume {m['volume']!r}  faces {m['n_faces']}  "
          f"solids {m['n_solids']}  manifold {m['is_manifold']}  "
          f"symmetry {inspector.rotational_symmetry_order(part, max_n=14)}")
    print(f"   material inside the {2*p.bore_radius:.1f} mm bore: "
          f"{vol:,.3f} mm3")
