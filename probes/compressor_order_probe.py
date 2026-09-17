"""probes/compressor_order_probe.py -- can the compressor sample's tree be
CHEAPER without changing one micron of the geometry?

The cost measured by probes/compressor_rebuild_cost.py is:
    polar_pattern 7.3 s + cut 1.3 s + fuse 5.0 s  = 13.6 s of kernel
    + 16 s for the spec's 13-fold symmetry proof.

The shroud cutter is a REVOLVE about Z, so it is axisymmetric: cutting one
blade and then rotating the copies must give the same solid as rotating first
and cutting all thirteen. If that is true the cut is paid once instead of
thirteen times. This probe builds BOTH orders and compares volume, face count,
solid count and health -- identical, or the idea is dead.

Serial. Nothing else may touch OpenCASCADE beside it.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import inspector  # noqa: E402
import meanline  # noqa: E402
from document import Document  # noqa: E402


def _params():
    d = meanline.design(meanline.Duty(mass_flow=0.5, pressure_ratio=3.0,
                                      rpm=45000))
    t, L = d.backplate_thk, d.axial_length
    r_in = round(0.75 * d.inducer_hub_radius, 2)
    thk = round(max(0.02 * d.tip_radius, 1.5), 2)
    big = t + L + 50.0
    return d, t, L, r_in, thk, big


def tree_now() -> Document:
    """Exactly what samples.sample_compressor ships today."""
    d, t, L, r_in, thk, big = _params()
    doc = Document(name="now")
    doc.add("hub_body", "revolve_profile",
            {"points": [[0, 0], [d.tip_radius, 0], [d.tip_radius, t],
                        [d.inducer_hub_radius, t + L], [0, t + L]]})
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
            {"points": [[r_in - 2, t + L], [d.inducer_shroud_radius, t + L],
                        [d.tip_radius, t + d.exit_width],
                        [d.tip_radius + 15, t + d.exit_width],
                        [d.tip_radius + 15, big], [r_in - 2, big]]})
    doc.add("blades", "cut", inputs=["blades_raw", "shroud_cutter"])
    doc.add("impeller", "fuse", inputs=["hub", "blades"])
    doc.spec = {"symmetry": d.blade_count, "n_solids": 1,
                "tip_radius": d.tip_radius, "tol": 1.0}
    return doc


def tree_cut_first() -> Document:
    """The same design with the axisymmetric shroud cut taken on ONE blade."""
    d, t, L, r_in, thk, big = _params()
    doc = Document(name="cutfirst")
    doc.add("hub_body", "revolve_profile",
            {"points": [[0, 0], [d.tip_radius, 0], [d.tip_radius, t],
                        [d.inducer_hub_radius, t + L], [0, t + L]]})
    doc.add("hub", "with_center_hole", {"radius": d.bore_radius},
            inputs=["hub_body"])
    doc.add("blade", "curved_blade",
            {"inner_radius": r_in, "outer_radius": d.tip_radius,
             "inlet_angle_deg": d.beta1_deg, "exit_angle_deg": d.beta2_deg,
             "height": L, "thickness": thk})
    doc.add("blade_up", "move", {"z": t}, inputs=["blade"])
    doc.add("shroud_cutter", "revolve_profile",
            {"points": [[r_in - 2, t + L], [d.inducer_shroud_radius, t + L],
                        [d.tip_radius, t + d.exit_width],
                        [d.tip_radius + 15, t + d.exit_width],
                        [d.tip_radius + 15, big], [r_in - 2, big]]})
    doc.add("blade_cut", "cut", inputs=["blade_up", "shroud_cutter"])
    doc.add("blades", "polar_pattern", {"count": d.blade_count},
            inputs=["blade_cut"])
    doc.add("impeller", "fuse", inputs=["hub", "blades"])
    doc.spec = {"symmetry": d.blade_count, "n_solids": 1,
                "tip_radius": d.tip_radius, "tol": 1.0}
    return doc


for label, maker in (("NOW      ", tree_now), ("CUT FIRST", tree_cut_first)):
    doc = maker()
    t0 = time.perf_counter()
    ok = doc.rebuild()
    dt = time.perf_counter() - t0
    res = doc.result()
    m = inspector.measure(res)
    print(f"{label}  rebuild {dt:7.2f} s  ok={ok}  "
          f"volume={m['volume']!r}  faces={len(res.faces())}  "
          f"solids={m['n_solids']}  manifold={m['is_manifold']}")
    print(f"           size={m['size']}  max_radius={m.get('max_radius')}")
    print(f"           health={inspector.health(res)}  "
          f"spec_problems={doc.spec_problems}")
    for f in doc.features:
        print(f"             {f.id:16s} {f.op:18s} vol={f.volume}")
