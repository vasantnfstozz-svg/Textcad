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
    """The 7-blade curved impeller as an editable feature tree.

    THE SHAFT BORE IS DRILLED LAST, after the blades are fused on. A bore
    drilled into the hub FIRST is filled straight back in by any blade that
    reaches inside it, and nothing notices — the wheel is still one watertight
    solid, still 7-fold symmetric, still the right tip radius, so the spec
    passes (measured 2026-09-17 on the compressor sample edited down to a
    small wheel: 67.210 mm3 of blade in a 2 mm bore, `spec_problems=[]`;
    probes/compressor_bore_order_probe.py). This sample's own blades clear its
    bore by 3 mm, so the ordering costs it nothing — volume, face count and
    bounding box are identical either way — but the tree a user edits has to
    teach the shape that survives being edited.
    """
    doc = Document(name="impeller-7")
    doc.add("hub_body", "revolve_profile",
            {"points": [[0, 0], [22, 0], [22, 3], [10, 28], [0, 28]]})
    doc.add("blade", "curved_blade",
            {"inner_radius": 9, "outer_radius": 40, "inlet_angle_deg": 30,
             "exit_angle_deg": 55, "height": 26, "thickness": 2.5})
    doc.add("blades_raw", "polar_pattern", {"count": 7}, inputs=["blade"])
    doc.add("shroud_cutter", "revolve_profile",
            {"points": [[8, 26], [40, 10], [48, 10], [48, 60], [8, 60]]})
    doc.add("blades", "cut", inputs=["blades_raw", "shroud_cutter"])
    doc.add("wheel", "fuse", inputs=["hub_body", "blades"])
    doc.add("impeller", "with_center_hole", {"radius": 6}, inputs=["wheel"])
    doc.spec = {"symmetry": 7, "n_solids": 1, "tip_radius": 40.0, "tol": 0.5}
    return doc


def sample_compressor() -> Document:
    """Physics-designed compressor: meanline calc -> feature tree. Heavier to
    rebuild (13 curved blades) — expect a minute or two per rebuild.

    WHERE THAT MINUTE GOES, measured 2026-09-17 and not guessed
    (probes/compressor_rebuild_profile.py, a cProfile of one cold rebuild):
    **94% of it is OpenCASCADE's boolean engine** — 31.5 s of a 33.6 s rebuild
    inside `OCP.BRepAlgoAPI.Build`, over 19 boolean calls. Three of them are
    the whole story:

        the spec's 13-fold symmetry PROOF   16.2 s   (inspector._rotation_
                                                      residual: one cut of the
                                                      69-face solid against
                                                      its 27.7-degree copy)
        polar_pattern's 13-blade fuse        8.0 s   (pattern._fuse_all)
        fuse hub + blades                    6.1 s   (document._fuse)
        cut the shroud                       1.4 s

    Nothing above the kernel is slow: the eight features' own Python is under
    100 ms, `inspector.health` 0.3 s for all ten calls, the deep validity pass
    87 ms, and the meanline calculation itself 0.1 ms. The wall clock swings
    3x with what else the box is doing (29.5 s idle, 91.6 s with four other
    OpenCASCADE jobs running), which is where "a minute or two" comes from.

    So this is the kernel doing necessary work, and the tree is not the place
    to fix it. Two things were measured and NOT taken: cutting the shroud on
    ONE blade before the pattern instead of on all thirteen afterwards saves
    about 3 s but moves the volume in the 9th figure (428259.878 -> 428259.876,
    probes/compressor_order_probe.py), and no spec may be dropped to save the
    proof. The one proven lever is outside this file:
    `pattern._fuse_all`'s pairwise tree costs 9.90 s on these 13 blades where
    ONE multi-argument `Shape.fuse(*rest)` costs 3.72 s — 2.7x, with the volume
    identical to the last digit, 91 faces both ways, 13 solids both ways and
    health [] (probes/compressor_fuse_lever_probe.py).
    """
    d = meanline.design(meanline.Duty(mass_flow=0.5, pressure_ratio=3.0,
                                      rpm=45000))
    t, L = d.backplate_thk, d.axial_length
    r_in = round(0.75 * d.inducer_hub_radius, 2)
    thk = round(max(0.02 * d.tip_radius, 1.5), 2)
    big = t + L + 50.0
    root = meanline.shroud_root_radius(r_in)   # never negative; see there
    doc = Document(name=f"compressor-PR3-{d.blade_count}blades")
    doc.add("hub_body", "revolve_profile",
            {"points": [[0, 0], [d.tip_radius, 0], [d.tip_radius, t],
                        [d.inducer_hub_radius, t + L], [0, t + L]]})
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
    doc.add("wheel", "fuse", inputs=["hub_body", "blades"])
    # THE BORE IS DRILLED LAST. Drilled into the hub first, as this tree did
    # until 2026-09-17, the blades fused on afterwards fill it back in on any
    # wheel small enough for them to reach — measured on this same tree at the
    # micro-turbo duty: 67.210 mm3 of blade inside a 2 mm bore, `ok=True`,
    # `spec_problems=[]`, one watertight solid, health [], 13-fold symmetric.
    # Nothing in the tree or the spec can see it, because the bore's wall is
    # still there (`cylinder_radii={2.0: 1, ...}`), just filled in behind.
    # Drilling last, the same duty measures 0.000 mm3 in the bore, and on THIS
    # duty the wheel is identical to the last digit: volume 428259.878, 69
    # faces, one solid, bbox 187.6 x 187.6 x 35.64, max_radius 93.8 — and the
    # rebuild is no slower (probes/compressor_bore_order_probe.py).
    doc.add("impeller", "with_center_hole", {"radius": d.bore_radius},
            inputs=["wheel"])
    doc.spec = {"symmetry": d.blade_count, "n_solids": 1,
                "tip_radius": d.tip_radius, "tol": 1.0}
    return doc


SAMPLES = {"flange": sample_flange, "impeller": sample_impeller,
           "compressor": sample_compressor}
