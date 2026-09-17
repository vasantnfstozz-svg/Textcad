"""probes/compressor_bore_order_probe.py -- ROUND TWO: the SAMPLE's tree has
the same bore-ordering trap the meanline builder had.

`samples.sample_compressor` drills the shaft bore into `hub` and fuses the
blades on AFTERWARDS, so any blade material reaching inside the bore fills the
hole back in. Its own wheel is large enough to be clear (the blade reaches in
to 6.5578 mm against a 4.92 mm bore), but a user who edits that tree down to a
small wheel plugs the bore with no warning, and `doc.spec` -- symmetry, solid
count, tip radius -- cannot see it.

Run one case at a time; nothing else may touch OpenCASCADE beside it.

    C:/Python314/python.exe probes/compressor_bore_order_probe.py <case>

    sample-now     the shipped ordering, shipped duty     (the baseline)
    sample-last    bore drilled AFTER the fuse, same duty (must be identical)
    micro-now      the shipped ordering, micro-turbo duty (the trap)
    micro-last     bore drilled AFTER the fuse, micro     (the fix)
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import inspector   # noqa: E402
import meanline    # noqa: E402
from build123d import Cylinder  # noqa: E402
from document import Document   # noqa: E402

DUTIES = {
    "sample": dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000),
    "micro":  dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000),
}


def tree(duty_kw, bore_last: bool) -> tuple[Document, object]:
    d = meanline.design(meanline.Duty(**duty_kw))
    t, L = d.backplate_thk, d.axial_length
    r_in = round(0.75 * d.inducer_hub_radius, 2)
    thk = round(max(0.02 * d.tip_radius, 1.5), 2)
    big = t + L + 50.0
    root = meanline.shroud_root_radius(r_in)
    doc = Document(name="probe")
    doc.add("hub_body", "revolve_profile",
            {"points": [[0, 0], [d.tip_radius, 0], [d.tip_radius, t],
                        [d.inducer_hub_radius, t + L], [0, t + L]]})
    if not bore_last:
        doc.add("hub", "with_center_hole", {"radius": d.bore_radius},
                inputs=["hub_body"])
    doc.add("blade", "curved_blade",
            {"inner_radius": r_in, "outer_radius": d.tip_radius,
             "inlet_angle_deg": d.beta1_deg, "exit_angle_deg": d.beta2_deg,
             "height": L, "thickness": thk})
    doc.add("blade_up", "move", {"z": t}, inputs=["blade"])
    doc.add("blades_raw", "polar_pattern", {"count": d.blade_count},
            inputs=["blade_up"])
    doc.add("shroud_cutter", "revolve_profile",
            {"points": [[root, t + L], [d.inducer_shroud_radius, t + L],
                        [d.tip_radius, t + d.exit_width],
                        [d.tip_radius + 15, t + d.exit_width],
                        [d.tip_radius + 15, big], [root, big]]})
    doc.add("blades", "cut", inputs=["blades_raw", "shroud_cutter"])
    if bore_last:
        doc.add("wheel", "fuse", inputs=["hub_body", "blades"])
        doc.add("impeller", "with_center_hole", {"radius": d.bore_radius},
                inputs=["wheel"])
    else:
        doc.add("impeller", "fuse", inputs=["hub", "blades"])
    doc.spec = {"symmetry": d.blade_count, "n_solids": 1,
                "tip_radius": d.tip_radius, "tol": 1.0}
    return doc, d


def main():
    case = sys.argv[1] if len(sys.argv) > 1 else "sample-now"
    which, order = case.split("-")
    doc, d = tree(DUTIES[which], bore_last=(order == "last"))
    print(f"CASE {case}: {DUTIES[which]}")
    print(f"  r2 {d.tip_radius}  bore {d.bore_radius}  blade root "
          f"{round(0.75 * d.inducer_hub_radius, 2)}  Z {d.blade_count}")
    t0 = time.perf_counter()
    ok = doc.rebuild()
    dt = time.perf_counter() - t0
    res = doc.result()
    m = inspector.measure(res)
    print(f"  rebuild {dt:.1f} s  ok={ok}  spec_problems={doc.spec_problems}")
    print(f"  volume={m['volume']!r}  faces={m['n_faces']}  "
          f"solids={m['n_solids']}  manifold={m['is_manifold']}  "
          f"size={m['size']}  max_radius={m.get('max_radius')}")
    print(f"  health={inspector.health(res)}")
    print(f"  cylinder_radii={m.get('cylinder_radii')}")
    # THE QUESTION THE SPEC CANNOT ANSWER: is the shaft bore a hole?
    plug = res & Cylinder(radius=d.bore_radius, height=8.0 * d.axial_length)
    vol = float(plug.volume) if plug is not None else 0.0
    print(f"  MATERIAL INSIDE THE {d.bore_radius} mm BORE: {vol:.3f} mm3")


if __name__ == "__main__":
    main()
