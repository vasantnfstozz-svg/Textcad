"""Round TWO of the review of 15eff19..9de0dc2 — the rest of the kind family.

The pattern gate (eed6a33) and its mirror-with-join follow-up (9de0dc2) taught
two ops to say "you fed me a sketch" by name. Six more were still answering
about geometry the user never asked for. MEASURED 2026-09-17, a circle sketch
fed straight to each one (probes/s10_solid_only_census.py):

    fillet:           radius 1 mm does not fit on 1 edge — ...
    chamfer:          distance 1 mm does not fit on 1 edge — ...
    shell:            walls of 1 mm do not fit this body — ...
    hole:             nothing was cut — the hole at (0, 0) finds no material
    with_center_hole: nothing was drilled — the hole falls outside this body
    with_bolt_circle: nothing was drilled — a pitch circle diameter of 14 mm
                      puts all 4 holes outside this body

Every one of them a diagnosis about a body that was never there. The same six
were then put to a RECTANGLE sketch with four real corners and a generous small
radius (probes/s10_solid_only_corners.py) — "fillet does not fit on 1 edge" is
no proof at all on a circle — and all six failed there too: they are genuinely
solid-only, which is why they are in the set and `extrude_face`, `revolve_face`
and `sketch_on_face` are NOT (they build real geometry from a sketch; see
below, measured in the same probes).

Every test here was RED before the fix.
"""
import pytest

from document import Document

CIRC = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]
RECT = [{"kind": "rectangle", "x": 0, "y": 0, "w": 40, "h": 30, "mode": "add"}]

# raw kernel text and the old geometry diagnoses: neither may reach the row
KERNEL_WORDS = ("Standard_", "StdFail", "TopoDS", "BRep_API", "NCollection",
                "does not fit", "nothing was drilled", "nothing was cut",
                "do not fit this body")

SOLID_ONLY = [
    ("fillet", {"radius": 1, "edges": "all"}),
    ("chamfer", {"length": 1, "edges": "all"}),
    ("shell", {"thickness": 1}),
    ("hole", {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
              "diameter": 3, "depth": 2}),
    ("with_center_hole", {"radius": 2}),
    ("with_bolt_circle", {"count": 4, "bolt_radius": 1,
                          "pitch_circle_dia": 14}),
]


def _on_sketch(op, params, entities=None):
    d = Document(name="k")
    d.add("s1", "sketch",
          {"entities": entities or CIRC, "plane": "XY", "offset": 0.0}, [])
    d.add("p1", op, params, ["s1"])
    d.rebuild()
    return d.get("p1")


def _on_plate(op, params):
    d = Document(name="s")
    d.add("b1", "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
    d.add("p1", op, params, ["b1"])
    d.rebuild()
    return d.get("p1")


@pytest.mark.parametrize("op,params", SOLID_ONLY)
def test_a_solid_only_op_fed_a_sketch_is_refused_by_name(op, params):
    f = _on_sketch(op, params)
    assert f.status == "failed"
    msg = " ".join(f.problems)
    assert msg == (f"{op} works on a SOLID body, and 's1' is a sketch — "
                   f"extrude or revolve it first, then {op} the body")
    assert not any(w in msg for w in KERNEL_WORDS), msg


@pytest.mark.parametrize("op,params", SOLID_ONLY)
def test_the_same_refusal_on_a_sketch_with_real_corners(op, params):
    """A circle has one edge and no corner, so "the radius does not fit" there
    proves nothing. A 40x30 rectangle has four corners and room for r1."""
    f = _on_sketch(op, params, RECT)
    assert f.status == "failed"
    assert "is a sketch" in " ".join(f.problems)


# --- the half that matters more: the gate must not fire on sound work ---------

@pytest.mark.parametrize("op,params,want", [
    ("fillet", {"radius": 1, "edges": "all"}, 1962.71),
    ("chamfer", {"length": 1, "edges": "all"}, 1915.33),
    ("shell", {"thickness": 1}, 1028.0),
    ("hole", {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
              "diameter": 3, "depth": 2}, 1985.86),
    ("with_center_hole", {"radius": 2}, 1937.17),
    ("with_bolt_circle", {"count": 4, "bolt_radius": 1,
                          "pitch_circle_dia": 14}, 1937.17),
])
def test_every_gated_op_still_builds_on_a_real_solid(op, params, want):
    """Measured off the kernel on a 20x20x5 plate, 2026-09-17."""
    f = _on_plate(op, params)
    assert f.status == "ok", f.problems
    assert f.volume == pytest.approx(want, abs=0.01)


@pytest.mark.parametrize("op,params", [
    # measured: a sketch face extrudes to a 235.62 mm3 prism
    ("extrude_face", {"face_center": [0, 0, 0], "face_normal": [0, 0, 1],
                      "amount": 3}),
    # measured: about a line in the sketch plane it revolves to 616.85 mm3
    ("revolve_face", {"face_center": [0, 0, 0], "face_normal": [0, 0, 1],
                      "axis": [[-5, -5], [5, -5]], "angle": 90}),
    # measured: answers a sketch with a sketch
    ("sketch_on_face", {"face_center": [0, 0, 0], "face_normal": [0, 0, 1],
                        "entities": CIRC}),
])
def test_the_gate_does_not_widen_to_the_face_ops(op, params):
    """These three take a sketch and build something real, so refusing them
    would take away work that is correct today. The set is what was MEASURED
    to be solid-only, never what merely sounds solid-only."""
    f = _on_sketch(op, params)
    assert f.status == "ok", f.problems
