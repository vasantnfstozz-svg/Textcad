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

def test_two_holes_headline_is_surface_to_surface():
    """User report (2026-08-31): "its measuring from center to cernter, i do
    not want like this, it should measure from the surface to surface". The
    headline (and the drawn line) is the wall-to-wall gap; the machinist's
    hole-spacing number stays one row below."""
    doc = two_hole_doc()
    cyls = find_all_faces(doc, lambda f: "CYLINDER" in str(f.geom_type))
    assert len(cyls) >= 2
    r = measure.measure(doc, sel(doc, "face", cyls[0]),
                        sel(doc, "face", cyls[1]))
    assert r.get("error") is None, r
    assert r["kind"] == "clearance"
    # 50 centre-to-centre minus both r=6 walls
    assert r["value"] == pytest.approx(38.0, abs=1e-3)
    rows = dict(r["rows"])
    assert float(rows["centre-to-centre"].split()[0]) == pytest.approx(50.0)
    assert rows["Δy"].startswith("0.00"), rows
    # the LINE runs wall to wall, not centre to centre
    assert abs(r["from"][0]) == pytest.approx(19.0, abs=1e-3)
    assert abs(r["to"][0]) == pytest.approx(19.0, abs=1e-3)


def test_probe_between_two_pillars_slides_in_parallel():
    """User report (2026-08-31): with two curved surfaces "one end is struck,
    it should move parlley". The drag station is the point projected on the
    source axis; the line runs axis-to-axis at that station trimmed by both
    radii — so probing at two heights gives the same surface gap with BOTH
    ends translated together, and never falls into the clamp."""
    doc = two_hole_doc()
    cyls = find_all_faces(doc, lambda f: "CYLINDER" in str(f.geom_type))
    a, b = sel(doc, "face", cyls[0]), sel(doc, "face", cyls[1])
    lo = measure.probe(doc, a, b, [-25 + 6, 0, 2], on="a")
    hi = measure.probe(doc, a, b, [-25 + 6, 0, 8], on="a")
    for r in (lo, hi):
        assert r.get("error") is None, r
        assert r["mode"] == "across", r
        assert r["value"] == pytest.approx(38.0, abs=1e-6)
        # both ends sit ON the walls, on the line between the axes
        assert r["from"][0] == pytest.approx(-19.0, abs=1e-6)
        assert r["to"][0] == pytest.approx(19.0, abs=1e-6)
        assert r["from"][1] == pytest.approx(0.0, abs=1e-6)
    # ...and the whole line moved in PARALLEL with the drag height
    assert lo["from"][2] == pytest.approx(2.0, abs=1e-6)
    assert lo["to"][2] == pytest.approx(2.0, abs=1e-6)
    assert hi["from"][2] == pytest.approx(8.0, abs=1e-6)
    assert hi["to"][2] == pytest.approx(8.0, abs=1e-6)


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


def test_a_step_says_it_is_not_a_clearance():
    """From any one view the two faces that FACE each other are never both
    visible, so the natural two clicks land on faces pointing the SAME way —
    the far side of a feature, not the gap in front of it. The user measured
    and then moved exactly that pair and reported "it was not moving", so the
    readout has to name the difference instead of just saying "step"."""
    doc = pocket_doc()
    floor = find_face(doc, lambda f: abs(normal(f)[2] - 1) < 1e-9
                      and abs(f.center().Z - 7) < 1e-6)
    r = measure.measure(doc, sel(doc, "face", top_face(doc)),
                        sel(doc, "face", floor))
    assert r["kind"] == "step"
    rows = dict(r["rows"])
    assert "clearance" in rows.get("note", ""), rows
    assert "facing" in rows.get("note", ""), rows


# ------------------------------------------- face-boundary diameters ---------

def washer_doc():
    """A ⌀80 disc with a ⌀24 centre hole: its top face IS "outer 80, inner 24"
    to anyone clicking it (user request 2026-08-31)."""
    doc = Document(name="t-washer")
    doc.add("plate", "disc", {"radius": 40, "thickness": 8})
    doc.add("bore", "with_center_hole", {"radius": 12}, inputs=["plate"])
    assert doc.rebuild(), doc.tree()
    return doc


def test_an_annular_face_reports_outer_and_inner_diameter():
    doc = washer_doc()
    top = find_face(doc, lambda f: abs(normal(f)[2] - 1) < 1e-9)
    r = measure.measure(doc, sel(doc, "face", top))
    assert r["kind"] == "area"
    rows = dict(r["rows"])
    assert rows["outer ⌀"] == "80.00 mm", rows
    assert rows["inner ⌀"] == "24.00 mm", rows


def test_a_pocket_mouth_face_reports_its_hole_diameter():
    """The pocket_doc top face has ONE full circle boundary (the ⌀18 mouth) —
    and its corner-free rectangle outline contributes nothing round."""
    doc = pocket_doc()
    r = measure.measure(doc, sel(doc, "face", top_face(doc)))
    rows = dict(r["rows"])
    assert rows["⌀"] == "18.00 mm", rows


def test_corner_fillet_arcs_are_not_reported_as_diameters():
    """A rounded-corner boss face has four r=3 ARCS. Someone asking "what is
    this bore" does not mean the corner radius, so partial circles must stay
    out of the ⌀ rows."""
    doc = Document(name="t-fillets")
    doc.add("b", "plate", {"width": 60, "depth": 40, "thickness": 10})
    doc.add("f", "fillet", {"radius": 3, "edges": "vertical"}, inputs=["b"])
    ok = doc.rebuild()
    if not ok:
        import pytest as _pt
        _pt.skip("fillet op unavailable on vertical edges in this build")
    top = find_face(doc, lambda f: abs(normal(f)[2] - 1) < 1e-9)
    r = measure.measure(doc, sel(doc, "face", top))
    rows = dict(r["rows"])
    assert "⌀" not in rows and "outer ⌀" not in rows, rows


# ---------------------------------------------------- the draggable probe ----

def boss_doc():
    """80x60x12 plate with a r=5 cylindrical boss at the origin: the distance
    from the boss to a wall VARIES around the cylinder, which is exactly what
    the draggable probe exists to explore (user request 2026-08-31)."""
    doc = Document(name="t-probe")
    doc.add("b", "plate", {"width": 80, "depth": 60, "thickness": 12})
    doc.add("sk", "sketch_on_face", {"face": "top", "offset": 0,
            "entities": [{"kind": "circle", "mode": "add",
                          "x": 0, "y": 0, "r": 5}]}, inputs=["b"])
    doc.add("boss", "extrude", {"amount": 6}, inputs=["sk"])
    doc.add("j", "fuse", {}, inputs=["b", "boss"])
    assert doc.rebuild(), doc.tree()
    return doc


def test_probe_reports_the_local_distance_not_the_witness_pair():
    """Two spots on the boss give two different distances to the same wall:
    the near point reads 35, a quarter turn away reads 40. The fixed witness
    pair could only ever say 35."""
    doc = boss_doc()
    faces = doc.result().faces()
    cyl = next(i for i, f in enumerate(faces)
               if "CYLINDER" in str(f.geom_type))
    wall = next(i for i, f in enumerate(faces)
                if abs(f.normal_at(f.center()).X + 1) < 1e-9
                and abs(f.center().X + 40) < 1e-6)
    a = sel(doc, "face", cyl)
    b = sel(doc, "face", wall)

    # CALIPER model (round 10): the boss axis runs parallel to the wall, so
    # the probe is the flat+round caliper — value = d0 − sqrt(r²−t²) on the
    # wall's PLANE, both dots at the same lateral offset. Facing (t=0): 35.
    # A quarter turn (t=r) clamps at the flank: d0 = 40.
    near = measure.probe(doc, a, b, [-5, 0, 9], on="a")
    side = measure.probe(doc, a, b, [0, 5, 9], on="a")
    assert near.get("error") is None, near
    assert side.get("error") is None, side
    assert near["value"] == pytest.approx(35.0, abs=1e-3)
    assert side["value"] == pytest.approx(40.0, abs=1e-3)
    # the flat dot is the perpendicular foot on the wall plane
    assert near["to"][0] == pytest.approx(-40.0, abs=1e-6)
    assert near["from"] == pytest.approx([-5, 0, 9])
    # flank clamp: BOTH dots hold at the pillar's extreme point
    assert side["from"][1] == pytest.approx(5.0, abs=1e-3)
    assert side["to"][1] == pytest.approx(5.0, abs=1e-3)


def test_probe_on_parallel_faces_matches_the_plane_distance():
    doc = pocket_doc()
    top, bot = top_face(doc), bottom_face(doc)
    r = measure.probe(doc, sel(doc, "face", top), sel(doc, "face", bot),
                      [30, 20, 12], on="a")
    assert r.get("error") is None, r
    assert r["value"] == pytest.approx(12.0)
    assert r["to"] == pytest.approx([30, 20, 0], abs=1e-6)


def test_probe_can_ride_the_second_selection_too():
    """on='b' flips the roles: the point rides B and measures back to A."""
    doc = boss_doc()
    faces = doc.result().faces()
    cyl = next(i for i, f in enumerate(faces)
               if "CYLINDER" in str(f.geom_type))
    wall = next(i for i, f in enumerate(faces)
                if abs(f.normal_at(f.center()).X + 1) < 1e-9)
    r = measure.probe(doc, sel(doc, "face", wall), sel(doc, "face", cyl),
                      [0, 5, 9], on="b")
    assert r.get("error") is None, r
    # caliper flank clamp: the point rides the boss a quarter turn from the
    # wall, so the line holds at the flank and reads d0
    assert r["value"] == pytest.approx(40.0, abs=1e-3)


def test_probe_error_paths_never_raise():
    doc = boss_doc()
    a = sel(doc, "face", 0)
    assert "error" in measure.probe(doc, a, None, [0, 0, 0])
    assert "error" in measure.probe(doc, a, sel(doc, "face", 1), "not-a-point")
    assert "error" in measure.probe(doc, a, sel(doc, "face", 9999), [0, 0, 0])
    assert "error" in measure.probe(Document(name="t-empty"), a,
                                    sel(doc, "face", 1), [0, 0, 0])


def hole_doc():
    """80x60x12 plate (Z-centred: -6..6) with a r=5 THROUGH hole at the origin,
    so its cylinder spans the same Z as the outer walls — a ray from a wall at
    any z on the wall can actually meet it. (The boss fixture above sits ABOVE
    the walls' Z span; a ray from the wall passes underneath it — the third
    time the Z-centred plate has bitten a fixture in this file.)"""
    doc = Document(name="t-probe-hole")
    doc.add("b", "plate", {"width": 80, "depth": 60, "thickness": 12})
    doc.add("bore", "with_center_hole", {"radius": 5}, inputs=["b"])
    assert doc.rebuild(), doc.tree()
    return doc


def test_probe_measures_ACROSS_the_gap_not_to_the_nearest_spot():
    """User report (2026-08-31): dragging along a flat wall past a curved
    surface, "the line should move according to the surface" — extend to meet
    the circle, not pivot toward its nearest point. From the wall the ray runs
    along the wall's normal: at x=0 the gap is 25, at x=3 the circle has
    curved away to 26 — nearest-point would read 25.18 there and pivot."""
    doc = hole_doc()
    faces = doc.result().faces()
    wall = next(i for i, f in enumerate(faces)
                if abs(f.normal_at(f.center()).Y + 1) < 1e-9)
    cyl = next(i for i, f in enumerate(faces)
               if "CYLINDER" in str(f.geom_type))
    a, b = sel(doc, "face", wall), sel(doc, "face", cyl)

    at0 = measure.probe(doc, a, b, [0, -30, 3], on="a")
    at3 = measure.probe(doc, a, b, [3, -30, 3], on="a")
    assert at0.get("mode") == "across", at0
    assert at0["value"] == pytest.approx(25.0, abs=1e-6)
    assert at3.get("mode") == "across", at3
    assert at3["value"] == pytest.approx(26.0, abs=1e-6)
    # the line's far end rides the CIRCLE at this station, not the near pole
    assert at3["to"][0] == pytest.approx(3.0, abs=1e-6)
    assert at3["to"][1] == pytest.approx(-4.0, abs=1e-6)
    # the honest footnote: the nearest distance rides along
    assert at3["nearest"] < at3["value"]


def test_flat_dot_stops_at_the_pillar_flanks():
    """User report (2026-09-01): "the flat side moves to over cross. it should
    move only till the pillar curve two points, becuase those are hightest
    point". Dragging the wall point past the bore's shadow clamps BOTH dots at
    the flank — the flat dot holds at the flank's offset instead of running
    on, and the value holds at d0."""
    doc = hole_doc()
    faces = doc.result().faces()
    wall = next(i for i, f in enumerate(faces)
                if abs(f.normal_at(f.center()).Y + 1) < 1e-9)
    cyl = next(i for i, f in enumerate(faces)
               if "CYLINDER" in str(f.geom_type))
    r = measure.probe(doc, sel(doc, "face", wall), sel(doc, "face", cyl),
                      [8, -30, 3], on="a")
    assert r.get("mode") == "across", r
    assert r["value"] == pytest.approx(30.0, abs=1e-6)
    # both dots held at the flank offset (t clamped from 8 to r=5)
    assert abs(r["from"][0]) == pytest.approx(5.0, abs=1e-3)
    assert abs(r["to"][0]) == pytest.approx(5.0, abs=1e-3)
    assert r["from"][1] == pytest.approx(-30.0, abs=1e-6)   # on the wall
    assert r["to"][1] == pytest.approx(0.0, abs=1e-3)       # at the flank


def test_probe_between_two_pillars_is_a_caliper():
    """User report (2026-09-01): "one point is stactic and fixed and one point
    is moving … the line or both ponts has to move parrlry in the curve side
    and the line should exted in the curve on the both side". The sideways
    drag shifts the WHOLE line laterally like a caliper: both dots slide to
    the same side around their own circles, and the value grows because both
    surfaces curve away — D − sqrt(rA²−t²) − sqrt(rB²−t²), clamped at the
    smaller flank."""
    doc = two_hole_doc()
    cyls = find_all_faces(doc, lambda f: "CYLINDER" in str(f.geom_type))
    a, b = sel(doc, "face", cyls[0]), sel(doc, "face", cyls[1])

    facing = measure.probe(doc, a, b, [-19, 0, 5], on="a")
    mid = measure.probe(doc, a, b, [-25 + 27 ** 0.5, 3, 5], on="a")
    flank = measure.probe(doc, a, b, [-25, 6, 5], on="a")
    for r in (facing, mid, flank):
        assert r.get("error") is None, r
        assert r["mode"] == "across", r

    assert facing["value"] == pytest.approx(38.0, abs=1e-6)
    assert mid["value"] == pytest.approx(50 - 2 * 27 ** 0.5, abs=1e-3)
    assert flank["value"] == pytest.approx(50.0, abs=1e-6)
    assert facing["value"] < mid["value"] < flank["value"]

    # BOTH dots moved to the same side, by the same lateral offset — parallel
    assert mid["from"][1] == pytest.approx(3.0, abs=1e-6)
    assert mid["to"][1] == pytest.approx(3.0, abs=1e-6)
    assert flank["from"][1] == pytest.approx(6.0, abs=1e-6)
    assert flank["to"][1] == pytest.approx(6.0, abs=1e-6)
    # each dot sits ON its own wall at that offset
    assert mid["from"][0] == pytest.approx(-25 + 27 ** 0.5, abs=1e-3)
    assert mid["to"][0] == pytest.approx(25 - 27 ** 0.5, abs=1e-3)
    # and the height rode along untouched
    assert mid["from"][2] == pytest.approx(5.0, abs=1e-6)
    assert mid["to"][2] == pytest.approx(5.0, abs=1e-6)


def test_caliper_clamps_at_the_smaller_flank():
    """Past the smaller circle's flank there is no wall point at that lateral
    offset on both sides — the line holds at the flank instead of inventing
    one (drag points on the far half project back to t=0..r)."""
    doc = Document(name="t-caliper-clamp")
    doc.add("b", "plate", {"width": 140, "depth": 60, "thickness": 10})
    doc.add("sk", "sketch_on_face", {"face": "top", "offset": 0,
            "entities": [{"kind": "circle", "mode": "add", "x": -30, "y": 0,
                          "r": 10},
                         {"kind": "circle", "mode": "add", "x": 30, "y": 0,
                          "r": 4}]}, inputs=["b"])
    doc.add("tool", "extrude", {"amount": -10}, inputs=["sk"])
    doc.add("holes", "cut", {}, inputs=["b", "tool"])
    assert doc.rebuild(), doc.tree()
    cyls = {}
    for i, f in enumerate(doc.result().faces()):
        if "CYLINDER" in str(f.geom_type):
            cyls[round(f.axis_of_rotation.position.X)] = i
    a = sel(doc, "face", cyls[-30])
    b = sel(doc, "face", cyls[30])
    # drag to t=8 on the r=10 circle: the r=4 circle has no wall there, so the
    # line clamps at t=4 — value D − sqrt(100−16) − 0 = 60 − sqrt(84)
    r = measure.probe(doc, a, b, [-30 + 6, 8, 2], on="a")
    assert r.get("error") is None, r
    assert r["from"][1] == pytest.approx(4.0, abs=1e-6), r
    assert r["to"][1] == pytest.approx(4.0, abs=1e-6), r
    assert r["value"] == pytest.approx(60 - 84 ** 0.5, abs=1e-3)


# ---------------------------------------------------------------------------
# Section 6 review (2026-09-10): three readouts that were quietly wrong.

def test_a_tilted_face_reports_its_own_size_not_its_world_box():
    """F4 (P2). `extents` came from the WORLD bounding box, whose third
    dimension is only ~0 when the face is axis aligned. On a 6 mm 45° chamfer
    that read 60.00 × 6.00; the face is 6√2 = 8.49 across, which is what the
    pick panel (studio._tagged_mesh) already reported for the SAME face."""
    doc = Document(name="t-chamfer")
    doc.add("b", "plate", {"width": 100, "depth": 60, "thickness": 20})
    doc.add("ch", "chamfer", {"length": 6, "edges": "top"}, inputs=["b"])
    assert doc.rebuild(), doc.tree()
    rid = doc._result_feature().id

    slanted = [i for i, f in enumerate(doc.result().faces())
               if 0.01 < abs(f.normal_at(f.center()).Z) < 0.99]
    assert slanted, "the chamfer made a slanted face"
    got = measure.measure(doc, {"body": rid, "kind": "face", "id": slanted[0]})
    ext = next(v for k, v in got["rows"] if k == "extents")
    width = float(ext.split("×")[1].split()[0])
    assert width == pytest.approx(6 * math.sqrt(2), abs=0.02), ext
    # and an axis-aligned face is unchanged by the new frame
    top = next(i for i, f in enumerate(doc.result().faces())
               if abs(f.normal_at(f.center()).Z - 1) < 1e-9)
    ext = next(v for k, v in
               measure.measure(doc, {"body": rid, "kind": "face",
                                     "id": top})["rows"] if k == "extents")
    assert "88.00" in ext and "48.00" in ext, ext   # all four top edges


def test_a_bore_reports_its_middle_as_its_centre():
    """F6 (P3). `axis_of_rotation.position` is an arbitrary point ALONG the
    axis: for a 5 mm pocket in a 12 mm plate OCCT returns the MOUTH (z=6),
    and the row calling that the bore's "centre" is a guess presented as a
    fact — the very trap the module docstring opens with."""
    doc = pocket_doc()
    rid = doc._result_feature().id
    fi = next(i for i, f in enumerate(doc.result().faces())
              if "CYLINDER" in str(f.geom_type) and abs(f.radius - 9) < 1e-9)
    wall = doc.result().faces()[fi]
    bb = wall.bounding_box()
    mid_z = (bb.min.Z + bb.max.Z) / 2

    got = measure.measure(doc, {"body": rid, "kind": "face", "id": fi})
    x, y, z = [float(v) for v in
               next(v for k, v in got["rows"] if k == "centre").split(",")]
    assert (x, y) == pytest.approx((15.0, 0.0), abs=0.01)
    assert z == pytest.approx(mid_z, abs=0.01), \
        f"the bore spans z {bb.min.Z}..{bb.max.Z}, so its centre is {mid_z}"
    assert got["centre"][2] == pytest.approx(mid_z, abs=0.01)


def test_an_imported_mesh_body_says_what_it_is():
    """F3 (P1). A triangle-soup body carries ONE mesh pseudo-face, id -1, so
    every click answered "face -1 is not on this body any more — click it
    again". That is untrue and it is a loop: clicking again gives -1 again.
    Measured on imports/liquid-piston-2-v1.stl (21552 faces, ids == [-1])."""
    doc = pocket_doc()
    rid = doc._result_feature().id
    got = measure.measure(doc, {"body": rid, "kind": "face", "id": -1})
    assert "click it again" not in got["error"], got["error"]
    assert "mesh" in got["error"], got["error"]
    # a genuinely stale index still says so
    stale = measure.measure(doc, {"body": rid, "kind": "face", "id": 9999})
    assert "click it again" in stale["error"], stale["error"]
