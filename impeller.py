"""
impeller.py — Phase 4: the vertical slice. A real parametric centrifugal
impeller built through the ENTIRE robustness stack, end to end.

This is the proof that the system does something genuinely hard — the benchmark
we set out to hit. It exercises every piece at once:

  * blocks.py    — the hub is a revolve_profile; the blades are a polar_pattern,
                   so the blade count is symmetric BY CONSTRUCTION.
  * assembly.py  — hub + blades are separate, independently health-checked
                   components, fused and verified as one watertight solid.
  * inspector.py — the finished impeller is measured and confirmed: single body,
                   watertight, and N-fold symmetric == the requested blade count.
  * engine.py    — exports the validated STEP file.

Change BLADE_COUNT (or any parameter) and the whole thing re-runs and re-verifies
— including confirming the symmetry order actually equals the new blade count.
Nothing is trusted; everything is measured.
"""

from __future__ import annotations
from dataclasses import dataclass
import build123d as b3d
from build123d import (BuildSketch, BuildLine, Polyline, make_face,
                       extrude, Plane, Axis)

import blocks
import inspector
import assembly


@dataclass
class ImpellerParams:
    bore_radius: float = 6.0      # central shaft bore
    hub_base_radius: float = 22.0  # hub radius at the inlet base
    hub_top_radius: float = 9.0    # hub radius at the nose
    hub_height: float = 30.0
    tip_radius: float = 40.0       # blade outer (shroud) radius
    blade_count: int = 7
    blade_thickness: float = 3.0
    blade_height_hub: float = 22.0  # blade height where it meets the hub
    blade_height_tip: float = 10.0  # blade height at the tip (tapered down)
    backsweep_deg: float = 30.0     # blade lean angle


def _hub(p: ImpellerParams):
    """Axisymmetric hub body of revolution, with the central bore drilled."""
    profile = [
        (0.0, 0.0),
        (p.hub_base_radius, 0.0),
        (p.hub_base_radius, 6.0),
        (p.hub_top_radius, p.hub_height),
        (0.0, p.hub_height),
    ]
    return blocks.with_center_hole(blocks.revolve_profile(profile), p.bore_radius)


def _one_blade(p: ImpellerParams):
    """A single tapered blade: a trapezoid profile (tall at the hub, short at the
    tip) extruded thin, then leaned over by the backsweep angle.

    THE SHAFT BORE IS TAKEN OUT OF IT HERE, for the reason `meanline.one_blade`
    carries in full: `_hub` drills the bore with `blocks.with_center_hole` and
    `build` fuses the blades on AFTERWARDS, so any blade material reaching
    inside the bore fills the hole back in, and the spec below
    (`symmetry`, `n_solids`, `require_manifold`) still passes every line. The
    shipped defaults clear it — the blade starts at `hub_top_radius` 9.0
    against a 6.0 bore — so today the cut removes nothing and the impeller is
    identical to the last digit: 30,902.254 mm3, 39 faces, ONE solid, 7-fold,
    nothing inside the bore, both ways. (That figure was written here as
    "89,143.229 mm3, 37 faces" and the probe it cites has never printed it;
    re-measured round four, probes/impeller_round4_sever.py.) One edit is all
    it takes: a nose narrower than the bore, or a wider bore, and the wheel
    comes back "verified" with no hole in it.

    THE CUT CANNOT SEVER A BLADE. The cylinder is centred on the axis and the
    blade lies wholly outside it, so what it takes is always the inner end,
    never a middle: measured at ten bore radii from 2.0 to 41.0 (the same
    probe) the blade is ONE solid every time until the bore passes the tip and
    there is nothing left — and long before that, at 22.0, the hub itself
    comes back empty and the build says so in four sentences.
    """
    with BuildSketch(Plane.XZ) as sk:
        with BuildLine():
            Polyline(
                (p.hub_top_radius, 0.0),
                (p.tip_radius, 0.0),
                (p.tip_radius, p.blade_height_tip),
                (p.hub_top_radius, p.blade_height_hub),
                close=True,
            )
        make_face()
    blade = extrude(sk.sketch, amount=p.blade_thickness)
    leaned = blade.rotate(Axis.Z, p.backsweep_deg)
    return leaned - b3d.Cylinder(radius=p.bore_radius,
                                 height=8.0 * max(p.hub_height, 1.0))


def _blades(p: ImpellerParams):
    """All blades as an N-fold polar pattern — symmetric by construction."""
    return blocks.polar_pattern(_one_blade(p), p.blade_count)


def build(p: ImpellerParams | None = None) -> assembly.AssemblyReport:
    """Decompose -> verify each -> fuse -> verify the whole impeller."""
    p = p or ImpellerParams()
    spec = inspector.Spec(symmetry=p.blade_count, n_solids=1, require_manifold=True)
    return assembly.build_and_verify(
        [assembly.Component("hub", lambda: _hub(p)),
         assembly.Component("blades", lambda: _blades(p))],
        mode="fuse", assembly_spec=spec)


if __name__ == "__main__":
    import sys

    p = ImpellerParams()
    if len(sys.argv) > 1:            # optional: python impeller.py 11  (blade count)
        p.blade_count = int(sys.argv[1])

    print(f"Building a centrifugal impeller: {p.blade_count} blades, "
          f"tip radius {p.tip_radius}mm\n")

    report = build(p)
    print(report.summary())

    if report.ok and report.part is not None:
        measured = inspector.measure(report.part)
        sym = inspector.rotational_symmetry_order(report.part,
                                                  max_n=p.blade_count * 2)
        print("\n--- independent final verification ---")
        print(f"  single watertight solid : "
              f"{measured['n_solids']==1 and measured['is_manifold']}")
        print(f"  measured symmetry order : {sym}  "
              f"(requested {p.blade_count})  -> "
              f"{'MATCH' if sym == p.blade_count else 'MISMATCH'}")
        print(f"  volume                  : {measured['volume']} mm^3")
        print(f"  bounding box            : {measured['size']} mm")

        b3d.export_step(report.part, "impeller.step")
        print("\n  wrote impeller.step")
        try:
            from ocp_vscode import show
            show(report.part)
            print("  (sent to OCP CAD Viewer)")
        except Exception as e:
            print(f"  (viewer not shown: {e})")
    else:
        print("\nImpeller FAILED verification — see problems above.")
        sys.exit(1)
