"""The measurement kernel (measure.py) against geometry whose answers are known
by construction.

User request (2026-08-27): "we dont have proper scale to measure distance
between two point … if i am clicking a line of circle, it should show the
diameter, and i want to see the distance between two faces".

The two facts these tests exist to defend, both probed before the code was
written (see measure.py's docstring):

  * `edge.center()` is a point ON a circle, not its centre. A r=9 hole centred
    at (15,0,12) reports (6,0,12) from center() — a silent one-radius error in
    every hole position, and one that LOOKS plausible. test_circle_centre_is_
    the_arc_centre is the regression guard.
  * outward face normals make thickness-vs-gap purely geometric, so a blind
    pocket in 12 mm stock with a 5 mm depth must report 7 mm of remaining
    floor. On a vacuum-held part that number is the difference between a good
    part and a cut-through, so it is asserted exactly.
"""
import math

import pytest

import measure
from document import Document


# --------------------------------------------------------------- fixtures ----

def pocket_doc():
    """80x60x12 block with a r=9, 5 mm deep blind pocket at x=15.

    Known by construction: block is 12 thick, pocket is ⌀18, remaining floor
    under the pocket is 12 - 5 = 7."""
    doc = Document(name="t-measure-pocket")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 80, "h": 60, "x": 0, "y": 0}]})
    doc.add("body", "extrude", {"amount": 12}, inputs=["outline"])
    doc.add("pocket_sketch", "sketch", {"plane": "XY", "offset": 12,
            "entities": [{"kind": "circle", "r": 9, "x": 15, "y": 0}]})
    doc.add("pocket_tool", "extrude", {"amount": -5}, inputs=["pocket_sketch"])
    doc.add("pocket", "cut", {}, inputs=["body", "pocket_tool"])
    assert doc.rebuild(), doc.tree()
    return doc


def slot_doc():
    """The same block with a 20-wide rectangular slot: its two walls FACE each
    other, so they are a gap, not a thickness."""
    doc = Document(name="t-measure-slot")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 80, "h": 60, "x": 0, "y": 0}]})
    doc.add("body", "extrude", {"amount": 12}, inputs=["outline"])
    doc.add("slot_sketch", "sketch", {"plane": "XY", "offset": 12,
            "entities": [{"kind": "rectangle", "w": 20, "h": 100,
                          "x": 0, "y": 0}]})
    doc.add("slot_tool", "extrude", {"amount": -4}, inputs=["slot_sketch"])
    doc.add("slot", "cut", {}, inputs=["body", "slot_tool"])
    assert doc.rebuild(), doc.tree()
    return doc


def two_hole_doc():
    """Two ⌀12 through holes, centres 50 mm apart in X and 0 in Y."""
    doc = Document(name="t-measure-holes")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 120, "h": 60, "x": 0, "y": 0}]})
    doc.add("body", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("holes_sketch", "sketch", {"plane": "XY", "offset": 10,
            "entities": [{"kind": "circle", "r": 6, "x": -25, "y": 0},
                         {"kind": "circle", "r": 6, "x": 25, "y": 0}]})
    doc.add("holes_tool", "extrude", {"amount": -10}, inputs=["holes_sketch"])
    doc.add("holes", "cut", {}, inputs=["body", "holes_tool"])
    assert doc.rebuild(), doc.tree()
    return doc


# ------------------------------------------------------------- selecting -----

def sel(doc, kind, idx):
    return {"body": doc._result_feature().id, "kind": kind, "id": idx}


def faces(doc):
    return doc.result().faces()


def edges(doc):
    return doc.result().edges()


def find_face(doc, pred):
    """Index of the first face matching pred(face) — indices are what the
    viewport sends, so tests must speak in indices too."""
    for i, f in enumerate(faces(doc)):
        try:
            if pred(f):
                return i
        except Exception:
            continue
    raise AssertionError("no face matched")


def find_all_faces(doc, pred):
    out = []
    for i, f in enumerate(faces(doc)):
        try:
            if pred(f):
                out.append(i)
        except Exception:
            continue
    return out


def normal(f):
    n = f.normal_at(f.center())
    return (n.X, n.Y, n.Z)


def top_face(doc):
    return find_face(doc, lambda f: abs(normal(f)[2] - 1) < 1e-9
                     and abs(f.center().Z - 12) < 1e-6)


def bottom_face(doc):
    return find_face(doc, lambda f: abs(normal(f)[2] + 1) < 1e-9)


# ------------------------------------------------------------- diameter ------

def test_cylinder_face_gives_diameter():
    doc = pocket_doc()
    i = find_face(doc, lambda f: "CYLINDER" in str(f.geom_type))
    r = measure.measure(doc, sel(doc, "face", i))
    assert r.get("error") is None, r
    assert r["kind"] == "diameter"
    assert r["value"] == pytest.approx(18.0)
    assert "18.00" in r["label"]


def test_circular_edge_gives_diameter():
    """Clicking the LINE of a circle — the user's exact words — gives ⌀."""
    doc = pocket_doc()
    i = next(j for j, e in enumerate(edges(doc)) if "CIRCLE" in str(e.geom_type))
    r = measure.measure(doc, sel(doc, "edge", i))
    assert r.get("error") is None, r
    assert r["kind"] == "diameter"
    assert r["value"] == pytest.approx(18.0)


def test_circle_centre_is_the_arc_centre():
    """REGRESSION: edge.center() returns a point ON the circle. For this hole
    that is (6,0,12) instead of (15,0,12) — plausible-looking and wrong by
    exactly one radius. measure.py must use arc_center."""
    doc = pocket_doc()
    i = next(j for j, e in enumerate(edges(doc)) if "CIRCLE" in str(e.geom_type))
    r = measure.measure(doc, sel(doc, "edge", i))
    cx, cy, _ = r["centre"]
    assert cx == pytest.approx(15.0, abs=1e-6), \
        f"centre X {cx} — center() instead of arc_center would give ~6.0"
    assert cy == pytest.approx(0.0, abs=1e-6)


# ------------------------------------------------------------ thickness ------

def test_block_thickness():
    doc = pocket_doc()
    r = measure.measure(doc, sel(doc, "face", top_face(doc)),
                        sel(doc, "face", bottom_face(doc)))
    assert r.get("error") is None, r
    assert r["kind"] == "thickness"
    assert r["value"] == pytest.approx(12.0)


def test_remaining_floor_under_a_blind_pocket():
    """The machining number that matters on a vacuum-held part: 12 mm stock
    minus a 5 mm pocket leaves 7 mm of floor."""
    doc = pocket_doc()
    floor = find_face(doc, lambda f: abs(normal(f)[2] - 1) < 1e-9
                      and abs(f.center().Z - 7) < 1e-6)
    r = measure.measure(doc, sel(doc, "face", floor),
                        sel(doc, "face", bottom_face(doc)))
    assert r.get("error") is None, r
    assert r["kind"] == "thickness"
    assert r["value"] == pytest.approx(7.0)
    assert dict(r["rows"])["between"] == "material"


def test_co_directional_faces_are_a_step_not_a_thickness():
    """A pocket floor and the rim above it BOTH point up, so there is no
    material between them and no gap between them either — it is a step, and
    its size is the pocket depth (12 - 7 = 5).

    Caught while driving the real UI: the first rule only checked the sign of
    n·(c2-c1) and confidently called this 5 mm of material."""
    doc = pocket_doc()
    floor = find_face(doc, lambda f: abs(normal(f)[2] - 1) < 1e-9
                      and abs(f.center().Z - 7) < 1e-6)
    r = measure.measure(doc, sel(doc, "face", top_face(doc)),
                        sel(doc, "face", floor))
    assert r.get("error") is None, r
    assert r["kind"] == "step", r
    assert r["value"] == pytest.approx(5.0)
    assert "material" not in str(r["rows"])


def test_facing_walls_are_a_gap_not_a_thickness():
    """A slot's two walls point AT each other: open space between them. Calling
    that a thickness would tell the user there is material where there is
    none."""
    doc = slot_doc()
    walls = find_all_faces(doc, lambda f: abs(abs(normal(f)[0]) - 1) < 1e-9
                           and abs(f.center().X) < 12
                           and f.center().Z > 8)
    assert len(walls) >= 2, f"expected two slot walls, got {walls}"
    r = measure.measure(doc, sel(doc, "face", walls[0]),
                        sel(doc, "face", walls[1]))
    assert r.get("error") is None, r
    assert r["kind"] == "gap", r
    assert r["value"] == pytest.approx(20.0)
    assert dict(r["rows"])["between"] == "open space"


def test_outer_walls_are_a_thickness():
    doc = slot_doc()
    outer = find_all_faces(doc, lambda f: abs(abs(normal(f)[0]) - 1) < 1e-9
                           and abs(f.center().X) > 30)
    assert len(outer) >= 2
    r = measure.measure(doc, sel(doc, "face", outer[0]),
                        sel(doc, "face", outer[1]))
    assert r["kind"] == "thickness"
    assert r["value"] == pytest.approx(80.0)


# ------------------------------------------------------- hole-to-hole --------

def test_hole_spacing_uses_centres():
    doc = two_hole_doc()
    cyls = find_all_faces(doc, lambda f: "CYLINDER" in str(f.geom_type))
    assert len(cyls) >= 2
    r = measure.measure(doc, sel(doc, "face", cyls[0]),
                        sel(doc, "face", cyls[1]))
    assert r.get("error") is None, r
    assert r["kind"] == "centres"
    assert r["value"] == pytest.approx(50.0, abs=1e-6)
    rows = dict(r["rows"])
    assert rows["Δy"].startswith("0.00"), rows
    # clearance is centre distance minus both radii: 50 - 6 - 6 = 38
    assert float(rows["clearance"].split()[0]) == pytest.approx(38.0, abs=1e-3)


# ------------------------------------------------------------- length --------

def test_line_edge_gives_length():
    doc = pocket_doc()
    i = next(j for j, e in enumerate(edges(doc))
             if "LINE" in str(e.geom_type)
             and abs(e.length - 80) < 1e-6)
    r = measure.measure(doc, sel(doc, "edge", i))
    assert r["kind"] == "length"
    assert r["value"] == pytest.approx(80.0)


# ------------------------------------------------------------- area ----------

def test_single_planar_face_reports_area_and_extents():
    doc = pocket_doc()
    r = measure.measure(doc, sel(doc, "face", top_face(doc)))
    assert r["kind"] == "area"
    # 80x60 minus the ⌀18 pocket mouth
    assert r["value"] == pytest.approx(80 * 60 - math.pi * 81, rel=1e-3)
    rows = dict(r["rows"])
    assert "80.00 × 60.00" in rows["extents"]


# ------------------------------------------------------------- angle ---------

def test_perpendicular_faces_report_the_angle():
    doc = pocket_doc()
    r = measure.measure(doc, sel(doc, "face", top_face(doc)),
                        sel(doc, "face", find_face(
                            doc, lambda f: abs(abs(normal(f)[0]) - 1) < 1e-9
                            and abs(f.center().X) > 30)))
    assert r.get("error") is None, r
    assert r["kind"] == "angle"
    assert r["value"] == pytest.approx(90.0, abs=1e-6)


# ------------------------------------------------------- failure modes -------

def test_stale_index_is_an_error_not_an_exception():
    """Face ids are array indices (studio.py enumerate) so they go stale on
    every rebuild. A stale pick must SAY so, never crash and never silently
    measure a different face."""
    doc = pocket_doc()
    r = measure.measure(doc, sel(doc, "face", 9999))
    assert "error" in r
    assert "click it again" in r["error"]


def test_same_selection_twice_is_refused():
    doc = pocket_doc()
    t = top_face(doc)
    r = measure.measure(doc, sel(doc, "face", t), sel(doc, "face", t))
    assert "error" in r
    assert "same thing" in r["error"]


def test_empty_design_is_an_error():
    r = measure.measure(Document(name="t-empty"), {"kind": "face", "id": 0})
    assert "error" in r
    assert "empty" in r["error"]


def test_bad_selection_kind_is_an_error():
    doc = pocket_doc()
    r = measure.measure(doc, {"body": None, "kind": "vertex", "id": 0})
    assert "error" in r


def test_measurement_is_deterministic():
    doc = pocket_doc()
    a, b = sel(doc, "face", top_face(doc)), sel(doc, "face", bottom_face(doc))
    first = measure.measure(doc, a, b)
    second = measure.measure(doc, a, b)
    assert first == second


def test_never_raises_on_any_face_pair_of_a_real_pocket():
    """Every pair of faces on the pocket body must produce either a
    measurement or a clean error — never an OCP exception escaping (house rule
    5: OCP errors derive from Exception, not RuntimeError)."""
    doc = pocket_doc()
    n = len(faces(doc))
    for i in range(n):
        for j in range(n):
            r = measure.measure(doc, sel(doc, "face", i), sel(doc, "face", j))
            assert isinstance(r, dict)
            if "error" not in r:
                assert r["value"] is not None
                assert r["label"]


def test_dimension_line_anchors_on_the_smaller_face():
    """The drawn line must sit on the feature the user clicked. Measuring a
    pocket floor against the whole top face anchored on the PLATE's centroid,
    leaving the line floating beside the pocket (caught in UI verification)."""
    doc = pocket_doc()
    floor = find_face(doc, lambda f: abs(normal(f)[2] - 1) < 1e-9
                      and abs(f.center().Z - 7) < 1e-6)
    r = measure.measure(doc, sel(doc, "face", top_face(doc)),
                        sel(doc, "face", floor))
    fx, fy, _ = r["from"]
    # the pocket is at x=15; the plate's top-face centroid is near x=-0.8
    assert fx == pytest.approx(15.0, abs=0.5), \
        f"line anchored at x={fx}, not on the pocket at x=15"
    assert r["from"][:2] == pytest.approx(r["to"][:2], abs=1e-6), \
        "a parallel-plane dimension must run along the normal"
