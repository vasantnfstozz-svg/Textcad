"""S5: snapping a sketch to an existing body's geometry.

Reported: "when I want to start a sketch at those boxes edges, we need
something for selecting to those edges, like how we do for the origin."

sketch_snap finds body geometry COINCIDENT with the sketch plane and returns it
in the plane's own 2D coordinates: corners, edge midpoints, circle centres, and
points where an edge pierces the plane.
"""
import pytest
from build123d import Location

import blocks
import sketch as sk
import sketch_snap as snap


def kinds_at(res, x, y, tol=1e-2):
    return {p["kind"] for p in res["points"]
            if abs(p["x"] - x) < tol and abs(p["y"] - y) < tol}


def xy_set(res, kind=None):
    return {(round(p["x"], 3), round(p["y"], 3)) for p in res["points"]
            if kind is None or p["kind"] == kind}


# blocks.plate is CENTRED on the origin in x/y and spans +/- t/2 in z
PLATE = lambda w=60, d=40, t=20: blocks.plate(w, d, t)


def test_box_sitting_on_the_plane_offers_its_corners():
    """A plate spanning z -10..+10: its bottom face is at z=-10, so sketching
    on XY (z=0) must snap to where the VERTICAL edges pierce the plane — the
    four corners of the box in plan view."""
    res = snap.snap_geometry({"b": PLATE()}, "XY", 0)
    corners = xy_set(res, "crossing")
    assert corners == {(30.0, 20.0), (30.0, -20.0), (-30.0, 20.0),
                       (-30.0, -20.0)}, corners


def test_edges_lying_in_the_plane_give_corners_midpoints_and_polylines():
    """Sketch on XY at z = -10 == the plate's bottom face: those 4 edges lie IN
    the plane, so they are drawable reference geometry AND snap targets."""
    res = snap.snap_geometry({"b": PLATE()}, "XY", -10)
    assert kinds_at(res, 30, 20) == {"corner"}
    # midpoints of the four bottom edges
    assert (0.0, 20.0) in xy_set(res, "midpoint")
    assert (30.0, 0.0) in xy_set(res, "midpoint")
    # the in-plane edges come back as polylines to draw
    assert len(res["edges"]) == 4, res["edges"]
    for e in res["edges"]:
        assert e["body"] == "b" and len(e["pts"]) >= 2


def test_hole_centre_is_snappable():
    """The most useful snap on a real part: the centre of a bore. The circular
    edge lies in the face's plane, so its arc centre comes back as `center`."""
    part = blocks.with_center_hole(blocks.disc(30, 10), 8)
    res = snap.snap_geometry({"d": part}, "XY", 5)      # the top face
    assert "center" in kinds_at(res, 0, 0), res["points"][:6]
    # and the outer rim's centre lands on the same point (deduped, corner/center
    # rank keeps the more meaningful label)
    assert len([p for p in res["points"]
                if abs(p["x"]) < 1e-6 and abs(p["y"]) < 1e-6]) == 1


def test_nothing_returned_when_the_plane_misses_the_body():
    res = snap.snap_geometry({"b": PLATE()}, "XY", 500)
    assert res["points"] == [] and res["edges"] == []


def test_points_are_in_PLANE_LOCAL_coordinates_not_world():
    """XZ's local y axis is world +Z (probed in sketch.py's PLANE_FRAMES) — a
    world-coordinate leak here would put every snap in the wrong place."""
    part = blocks.plate(60, 40, 20)                     # z from -10 to +10
    res = snap.snap_geometry({"b": part}, "XZ", 0)      # plane y=0, local y = world z
    ys = {round(p["y"], 3) for p in res["points"]}
    assert 10.0 in ys and -10.0 in ys, ys              # top/bottom in local y
    xs = {round(p["x"], 3) for p in res["points"]}
    assert 30.0 in xs and -30.0 in xs, xs


def test_several_bodies_are_labelled_by_body():
    a = blocks.plate(20, 20, 10)
    b = blocks.plate(20, 20, 10).moved(Location((80, 0, 0)))
    res = snap.snap_geometry({"a": a, "b": b}, "XY", 0)
    assert {p["body"] for p in res["points"]
            if p["kind"] != "design_center"} == {"a", "b"}
    assert (80 + 10.0, 10.0) in xy_set(res)            # b's corner, shifted


def test_sketches_are_ignored_not_treated_as_bodies():
    profile = sk.make_sketch("XY", 0, [{"kind": "circle", "mode": "add",
                                       "r": 10}])
    res = snap.snap_geometry({"sk": profile}, "XY", 0)
    assert res["points"] == [] and res["edges"] == []


def test_curved_edge_crossing_is_accurate_not_sampled():
    """A cylinder's silhouette pierced by a plane: bisection on the edge
    parameter must land the point ON the circle, not on a chord between
    samples."""
    cyl = blocks.disc(25, 40)                          # z -20..20, r 25
    res = snap.snap_geometry({"c": cyl}, "XZ", 0)      # plane through the axis
    # the two silhouette lines of the cylinder sit at local x = +/-25
    xs = sorted({round(p["x"], 2) for p in res["points"]})
    assert xs[0] == pytest.approx(-25, abs=0.05), xs
    assert xs[-1] == pytest.approx(25, abs=0.05), xs


def test_bad_plane_name_is_a_clear_error():
    with pytest.raises(ValueError, match="XY"):
        snap.snap_geometry({}, "nope", 0)


# ---- face-sketch frames (they had NO model snapping before) ----------------

def test_face_frame_snaps_like_the_named_plane():
    """A face sketch passes its world frame instead of a plane name. The top
    face of a centred plate IS the XY plane at z=+10, so both paths must
    return the same points."""
    part = PLATE()
    out = sk.face_outline_2d(part, face="top")
    via_frame = snap.snap_geometry({"b": part}, frame=out["frame"])
    via_name = snap.snap_geometry({"b": part}, "XY", 10)
    assert xy_set(via_frame) == xy_set(via_name)
    assert (30.0, 20.0) in xy_set(via_frame, "corner")


def test_face_frame_hole_centre_is_exact():
    """The user's report: 'I could not find the center for that circle.' The
    frame path must return the bore's EXACT arc centre — the UI's polyline
    centroid was 0.32mm off on a Ø16 hole."""
    part = blocks.with_center_hole(blocks.disc(30, 10), 8)
    out = sk.face_outline_2d(part, face="top")
    res = snap.snap_geometry({"d": part}, frame=out["frame"])
    assert "center" in kinds_at(res, 0, 0, tol=1e-4), res["points"][:6]


def test_bad_frame_is_a_clear_error():
    with pytest.raises(ValueError, match="frame"):
        snap.snap_geometry({}, frame={"origin": [0, 0, 0]})   # no x_dir/z_dir


# ---- the centre of the design ("the software does not know the center") ----

def test_design_center_is_the_bbox_centre_of_whats_on_the_plane():
    """Two bodies at x=0 and x=80: the centre of the design on this plane is
    the bbox centre of everything found, (40, 0) — offered as its own snap."""
    a = blocks.plate(20, 20, 10)
    b = blocks.plate(20, 20, 10).moved(Location((80, 0, 0)))
    res = snap.snap_geometry({"a": a, "b": b}, "XY", 0)
    assert "design_center" in kinds_at(res, 40, 0), xy_set(res)


def test_design_center_defers_to_a_real_snap_point():
    """When the bbox centre lands ON real geometry (a centred disc's bore),
    the real point keeps its own kind — one point, labelled 'center'."""
    part = blocks.with_center_hole(blocks.disc(30, 10), 8)
    res = snap.snap_geometry({"d": part}, "XY", 5)
    at_origin = [p for p in res["points"]
                 if abs(p["x"]) < 1e-3 and abs(p["y"]) < 1e-3]
    assert len(at_origin) == 1 and at_origin[0]["kind"] == "center", at_origin


def test_no_design_center_when_the_plane_is_empty():
    res = snap.snap_geometry({"b": PLATE()}, "XY", 500)
    assert res["points"] == []
