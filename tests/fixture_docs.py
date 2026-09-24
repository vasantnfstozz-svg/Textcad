"""Small documents the code tests build on.

`flange()` is the retired File > Examples > Flange sample (samples.py, deleted
2026-09-24), frozen here because about fifteen test files used it as a quick
real part: a disc, a centre bore and a six-hole bolt circle, with a spec.
"""
from document import Document


def flange() -> Document:
    doc = Document(name="flange-100")
    doc.add("body", "disc", {"radius": 50, "thickness": 10})
    doc.add("bore", "with_center_hole", {"radius": 15}, inputs=["body"])
    doc.add("bolts", "with_bolt_circle",
            {"count": 6, "bolt_radius": 4, "pitch_circle_dia": 76},
            inputs=["bore"])
    doc.spec = {"symmetry": 6, "n_solids": 1, "holes": {4.0: 6}, "tol": 0.5}
    return doc
