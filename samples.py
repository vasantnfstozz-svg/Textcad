"""
samples.py — the built-in example designs (File tab -> Examples).

Kept separate from the web server so examples can grow without touching
studio.py. Each function returns a fresh, unbuilt Document.
"""

from __future__ import annotations

import meanline
from document import Document


def sample_flange() -> Document:
    doc = Document(name="flange-100")
    doc.add("body", "disc", {"radius": 50, "thickness": 10})
    doc.add("bore", "with_center_hole", {"radius": 15}, inputs=["body"])
    doc.add("bolts", "with_bolt_circle",
            {"count": 6, "bolt_radius": 4, "pitch_circle_dia": 76},
            inputs=["bore"])
    doc.spec = {"symmetry": 6, "n_solids": 1, "holes": {4.0: 6}, "tol": 0.5}
    return doc


def sample_impeller() -> Document:
    """The 7-blade curved impeller as an editable feature tree."""
    doc = Document(name="impeller-7")
    doc.add("hub_body", "revolve_profile",
            {"points": [[0, 0], [22, 0], [22, 3], [10, 28], [0, 28]]})
    doc.add("hub", "with_center_hole", {"radius": 6}, inputs=["hub_body"])
    doc.add("blade", "curved_blade",
            {"inner_radius": 9, "outer_radius": 40, "inlet_angle_deg": 30,
             "exit_angle_deg": 55, "height": 26, "thickness": 2.5})
    doc.add("blades_raw", "polar_pattern", {"count": 7}, inputs=["blade"])
    doc.add("shroud_cutter", "revolve_profile",
            {"points": [[8, 26], [40, 10], [48, 10], [48, 60], [8, 60]]})
    doc.add("blades", "cut", inputs=["blades_raw", "shroud_cutter"])
    doc.add("impeller", "fuse", inputs=["hub", "blades"])
    doc.spec = {"symmetry": 7, "n_solids": 1, "tip_radius": 40.0, "tol": 0.5}
    return doc


def sample_compressor() -> Document:
    """Physics-designed compressor: meanline calc -> feature tree. Heavier to
    rebuild (13 curved blades) — expect a minute or two per rebuild."""
    d = meanline.design(meanline.Duty(mass_flow=0.5, pressure_ratio=3.0,
                                      rpm=45000))
    t, L = d.backplate_thk, d.axial_length
    r_in = round(0.75 * d.inducer_hub_radius, 2)
    thk = round(max(0.02 * d.tip_radius, 1.5), 2)
    big = t + L + 50.0
    doc = Document(name=f"compressor-PR3-{d.blade_count}blades")
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


SAMPLES = {"flange": sample_flange, "impeller": sample_impeller,
           "compressor": sample_compressor}
