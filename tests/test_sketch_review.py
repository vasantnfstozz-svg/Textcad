"""Sketcher code review (REVIEW-QUEUE section 1, 2026-09-09).

The findings this file locks in, each measured before it was fixed
(probes/sketcher_review_probe.py):

F1/F2  the sketcher works out which shapes are holes, but the entities
       reached the kernel in DRAWING order and `_compose` is sequential:
       a hole drawn before its outer, or an island drawn last, composed
       into the wrong solid with status "ok" and no warning.
F4     `_path_face` had no validation, so a crossing or degenerate path
       handed raw OpenCASCADE text to the user.
F8     a bore's parameter seam was advertised as a model "corner" and its
       antipode as a "midpoint" - snap targets that are not features.
F7     the tree re-derived corner-vs-arc instead of asking the backend.
"""
import math

import build123d as b3d
import pytest

import sketch as sk
import sketch_corner as sc
import sketch_snap as snap

RING = math.pi * (30**2 - 10**2)
RING_AND_ISLAND = math.pi * (30**2 - 20**2 + 10**2)


def circle(r, mode="add", x=0, y=0):
    return {"kind": "circle", "mode": mode, "x": x, "y": y, "r": r}


# ---------------------------------------------------------------- F1 / F2
def test_hole_drawn_before_its_outer_still_makes_a_washer():
    """F1: the user draws the bore first, then the rim. Measured before the
    fix: 2827.43 mm2 (a solid disc) instead of 2513.27."""
    ents = [circle(10, "subtract"), circle(30)]
    assert sk.make_sketch("XY", 0, ents).area == pytest.approx(RING, abs=1.0)


def test_island_drawn_last_survives_its_hole():
    """F2: r10, r30, r20 in drawing order. Measured before the fix:
    1570.80 mm2 (the island was cut away) instead of 1884.96."""
    ents = [circle(10), circle(30), circle(20, "subtract")]
    area = sk.make_sketch("XY", 0, ents).area
    assert area == pytest.approx(RING_AND_ISLAND, abs=1.0)


def test_a_hole_in_an_island_nests_three_deep():
    """outer 30, hole 20, island 10, bore 4 - shuffled into the worst order
    the sketcher can produce."""
    ents = [circle(4, "subtract"), circle(10), circle(30), circle(20, "subtract")]
    want = math.pi * (30**2 - 20**2 + 10**2 - 4**2)
    assert sk.make_sketch("XY", 0, ents).area == pytest.approx(want, abs=1.0)


def test_reordering_never_changes_a_correctly_ordered_sketch():
    """Outers-first input must behave exactly as before - the fix may not
    disturb the sketches already in the library."""
    ents = [circle(30), circle(10, "subtract")]
    assert sk.make_sketch("XY", 0, ents).area == pytest.approx(RING, abs=1.0)


def test_an_overlapping_bite_is_not_treated_as_a_hole():
    """A subtract that STRADDLES the rim is not nested; it must keep its
    place in the sequence and still take its bite."""
    ents = [circle(30), circle(10, "subtract", x=30)]
    area = sk.make_sketch("XY", 0, ents).area
    assert area < math.pi * 30**2 - 100          # a real bite was taken
    assert area > math.pi * 30**2 - math.pi * 100


def test_two_separate_profiles_each_keep_their_own_hole():
    ents = [circle(5, "subtract", x=-40), circle(20, x=-40),
            circle(5, "subtract", x=40), circle(20, x=40)]
    want = 2 * math.pi * (20**2 - 5**2)
    assert sk.make_sketch("XY", 0, ents).area == pytest.approx(want, abs=1.0)


def test_first_entity_subtracting_from_nothing_still_says_so():
    """A lone subtract has nothing to cut: the sentence must survive. Its
    wording changed with the third review (2026-09-09) — a subtraction CAN now
    come first (it removes nothing), so the mistake being named is a sketch of
    nothing but cuts, not the position of the first entity."""
    with pytest.raises(ValueError, match="every entity is a cut"):
        sk.make_sketch("XY", 0, [circle(10, "subtract")])


# -------------------------------------------------------------------- F4
BOWTIE = {"kind": "path", "mode": "add", "start": [0, 0], "segments": [
    {"type": "line", "to": [20, 20]},
    {"type": "line", "to": [20, 0]},
    {"type": "line", "to": [0, 20]}]}
SAME_CELL = {"kind": "path", "mode": "add", "start": [0, 0], "segments": [
    {"type": "line", "to": [0, 0]}]}
TWO_POINTS = {"kind": "path", "mode": "add", "start": [0, 0], "segments": [
    {"type": "line", "to": [10, 0]}]}
COLLINEAR = {"kind": "path", "mode": "add", "start": [0, 0], "segments": [
    {"type": "line", "to": [10, 0]}, {"type": "line", "to": [20, 0]}]}


@pytest.mark.parametrize("ent,word", [
    (BOWTIE, "crosses itself"),
    (SAME_CELL, "same point"),
    (TWO_POINTS, "at least 3"),
    (COLLINEAR, "encloses no area"),
])
def test_a_degenerate_path_says_what_is_wrong(ent, word):
    """F4: measured before the fix - Standard_TypeMismatch('TopoDS::Face'),
    StdFail_NotDone('BRep_API: command not done') and build123d's "Face can
    only be created with closed wires" reached the tree verbatim."""
    with pytest.raises(ValueError, match=word):
        sk.make_sketch("XY", 0, [ent])


def test_a_good_path_still_builds():
    ent = {"kind": "path", "mode": "add", "start": [0, 0], "segments": [
        {"type": "line", "to": [20, 0]},
        {"type": "arc", "via": [25, 5], "to": [20, 10]},
        {"type": "line", "to": [0, 10]}]}
    assert sk.make_sketch("XY", 0, [ent]).area > 190


def test_no_opencascade_text_ever_reaches_the_user():
    """Rule 5: an OCCT error must never be the message. Whatever a path
    does, the exception is a ValueError with a readable sentence."""
    for ent in (BOWTIE, SAME_CELL, TWO_POINTS, COLLINEAR):
        try:
            sk.make_sketch("XY", 0, [ent])
        except ValueError as e:
            assert "TopoDS" not in str(e) and "BRep_API" not in str(e)
        except Exception as e:                               # noqa: BLE001
            pytest.fail(f"{type(e).__name__} escaped: {e}")


# -------------------------------------------------------------------- F8
def test_a_bore_offers_its_centre_not_a_fake_corner():
    """F8: measured before the fix - corner at (5, 0) and midpoint at
    (-5, 0), the parameter seam of the bore circle and its antipode."""
    solid = b3d.Box(40, 40, 10) - b3d.Cylinder(radius=5, height=20)
    res = snap.snap_geometry({"b": solid}, "XY", 5.0)
    rim = [p for p in res["points"]
           if abs(math.hypot(p["x"], p["y"]) - 5) < 1e-2]
    assert not [p for p in rim if p["kind"] in ("corner", "midpoint")]
    centres = [(p["kind"], round(p["x"], 6), round(p["y"], 6))
               for p in res["points"]]
    assert ("center", 0.0, 0.0) in centres


def test_a_box_still_offers_its_real_corners():
    """The fix may not cost a straight edge its endpoints."""
    res = snap.snap_geometry({"b": b3d.Box(40, 40, 10)}, "XY", 5.0)
    corners = {(round(p["x"], 3), round(p["y"], 3))
               for p in res["points"] if p["kind"] == "corner"}
    assert {(-20.0, -20.0), (20.0, -20.0), (20.0, 20.0), (-20.0, 20.0)} <= corners


def test_an_arc_edge_keeps_its_two_real_endpoints():
    """A rounded corner is a real arc: its ends ARE corners of the outline."""
    solid = b3d.fillet(b3d.Box(40, 40, 10).edges().filter_by(b3d.Axis.Z), 6)
    res = snap.snap_geometry({"b": solid}, "XY", 5.0)
    corners = [p for p in res["points"] if p["kind"] == "corner"]
    assert len(corners) == 8             # 4 arcs x 2 ends, shared with the lines


# -------------------------------------------------------------------- F7
def test_path_arcs_labels_a_closed_paths_wrap_around_neighbour():
    """F7: on a CLOSED path whose first and last segments are both arcs,
    the tree called both of them 'corner' - promising "the round stays
    tangent to its edges" - because it read segment 0's predecessor as the
    auto-close line. Its real neighbour is the last arc, so both are free
    arcs and a radius edit just re-bulges them. This is the backend's own
    answer, which the tree must use instead of re-deriving it."""
    ent = {"kind": "path", "start": [0, 0], "segments": [
        {"type": "arc", "via": [-3, 12], "to": [0, 24]},
        {"type": "line", "to": [30, 24]},
        {"type": "line", "to": [30, 0]},
        {"type": "arc", "via": [15, -3], "to": [0, 0]}]}
    kinds = {a["segment"]: a["kind"] for a in sc.path_arcs(ent)}
    assert kinds == {0: "arc", 3: "arc"}


def test_path_arcs_still_calls_a_line_bounded_round_a_corner():
    """The other half of the promise: a round between two straight edges IS
    a corner, and stays one."""
    ent = {"kind": "path", "start": [0, 0], "segments": [
        {"type": "line", "to": [26, 0]},
        {"type": "arc", "via": [29.1, 1.2], "to": [30, 4]},
        {"type": "line", "to": [30, 24]},
        {"type": "line", "to": [0, 24]}]}
    kinds = {a["segment"]: a["kind"] for a in sc.path_arcs(ent)}
    assert kinds == {1: "corner"}


# ------------------------------------------------------- through the API
def test_a_crossing_path_never_500s_the_trim_tool():
    """F4 downstream: /api/sketch/trim/pieces builds every entity's face, so
    the bow-tie that used to hand OCCT text to the tree used to hand a 500
    to the browser — from the very tool a user reaches for to clean it up.
    It catches ValueError, which is now what it gets."""
    from fastapi.testclient import TestClient

    import studio
    client = TestClient(studio.app)
    r = client.post("/api/sketch/trim/pieces", json={"entities": [BOWTIE]})
    assert r.status_code == 200
    body = r.json()
    assert body["pieces"] == []
    assert "crosses itself" in body["error"]


def test_path_arcs_endpoint_labels_every_path_in_the_list():
    from fastapi.testclient import TestClient

    import studio
    client = TestClient(studio.app)
    closed_two_arcs = {"kind": "path", "mode": "add", "start": [0, 0],
                       "segments": [
                           {"type": "arc", "via": [-3, 12], "to": [0, 24]},
                           {"type": "line", "to": [30, 24]},
                           {"type": "line", "to": [30, 0]},
                           {"type": "arc", "via": [15, -3], "to": [0, 0]}]}
    ents = [circle(50), closed_two_arcs]
    arcs = client.post("/api/sketch/path-arcs",
                       json={"entities": ents}).json()["arcs"]
    assert set(arcs) == {"1"}                    # the circle has no arcs to row
    assert {a["segment"]: a["kind"] for a in arcs["1"]} == {0: "arc", 3: "arc"}
    assert all(a["r"] > 0 for a in arcs["1"])


def test_path_arcs_endpoint_shrugs_at_a_half_drawn_path():
    """The sketcher asks while the user is still clicking; a path with no
    segments yet must come back empty, not as an error."""
    from fastapi.testclient import TestClient

    import studio
    client = TestClient(studio.app)
    r = client.post("/api/sketch/path-arcs",
                    json={"entities": [{"kind": "path", "start": [0, 0]}]})
    assert r.status_code == 200 and r.json()["arcs"] == {}


# ------------------------------------------- the reorder across all kinds
def test_the_reorder_works_whatever_the_shapes_are():
    """A washer is the easy case. The same rule has to hold for a path
    outline with a bored hole, a polygon with a slot cut out of it, and an
    ellipse island inside a rectangular hole inside a rectangle - each
    handed over in the WORST order the sketcher can produce."""
    path = {"kind": "path", "mode": "add", "start": [0, 0], "segments": [
        {"type": "line", "to": [40, 0]},
        {"type": "line", "to": [40, 30]},
        {"type": "line", "to": [0, 30]}]}
    bore = {"kind": "circle", "mode": "subtract", "x": 20, "y": 15, "r": 6}
    want = 40 * 30 - math.pi * 36
    assert sk.make_sketch("XY", 0, [bore, path]).area == pytest.approx(want, abs=1)
    assert sk.make_sketch("XY", 0, [path, bore]).area == pytest.approx(want, abs=1)

    poly = {"kind": "polygon", "mode": "add",
            "points": [[0, 0], [50, 0], [50, 40], [0, 40]]}
    slot = {"kind": "slot", "mode": "subtract", "x": 25, "y": 20,
            "length": 20, "height": 8, "rotation": 0}
    want = 50 * 40 - (12 * 8 + math.pi * 16)
    assert sk.make_sketch("XY", 0, [slot, poly]).area == pytest.approx(want, abs=1)

    ents = [
        {"kind": "ellipse", "mode": "add", "x": 0, "y": 0, "rx": 8, "ry": 5},
        {"kind": "rectangle", "mode": "subtract", "x": 0, "y": 0,
         "w": 30, "h": 20},
        {"kind": "rectangle", "mode": "add", "x": 0, "y": 0, "w": 60, "h": 40},
    ]
    want = 60 * 40 - 30 * 20 + math.pi * 8 * 5
    assert sk.make_sketch("XY", 0, ents).area == pytest.approx(want, abs=1)
