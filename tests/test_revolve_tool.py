"""Revolve (LAUNCH-PLAN.md P3, specs/revolve.md): the guards that make dragging
safe, and the planner that only ever hands the UI an axis that builds.

Dragging changes the value on every mouse move, so anything the op refuses is
hit constantly. probes/revolve_axis_probe.py (2026-09-03) found every banned
failure live in the kernel:

    profile straddling the axis  -> StdFail_NotDone (an OCP exception, NOT a
                                    RuntimeError)
    axis perpendicular to plane  -> a "successful" solid of volume 0
    angle 0                      -> quietly a FULL turn;  400 -> quietly 40

Every geometric claim below is checked against the kernel: volumes against
Pappus (V = 2*pi*r_centroid*A*theta/360), sweep direction against the
centroid, the planned axis by building with it.
"""
import math

import pytest

import sketch as sk
import toolplan
from document import Document

PLANES = ["XY", "XZ", "YZ"]


def rect_sketch(plane="XZ", x=20.0, y=10.0, w=10.0, h=6.0, offset=0.0):
    return sk.make_sketch(plane=plane, offset=offset, entities=[
        {"kind": "rectangle", "w": w, "h": h, "x": x, "y": y, "mode": "add"}])


def doc_with(plane="XZ", x=20.0, y=10.0, w=10.0, h=6.0, offset=0.0, kind="rectangle", r=4.0):
    d = Document(name="rev")
    ent = ({"kind": "circle", "r": r, "x": x, "y": y} if kind == "circle"
           else {"kind": "rectangle", "w": w, "h": h, "x": x, "y": y})
    d.add("p", "sketch", {"plane": plane, "offset": offset, "entities": [ent]}, [])
    d.rebuild()
    return d


def pappus(r_bar, area, angle):
    return 2 * math.pi * abs(r_bar) * area * abs(angle) / 360.0


# ------------------------------------------------- nothing escapes raw -------

@pytest.mark.parametrize("plane", PLANES)
@pytest.mark.parametrize("axis", ["X", "Y", "Z", "u", "v"])
@pytest.mark.parametrize("x", [20.0, 0.0])
def test_every_axis_and_profile_combination_fails_friendly_or_builds(plane, axis, x):
    """30 combinations: a healthy solid or a ValueError a user could act on.
    A raw kernel exception here is what this file exists to prevent."""
    try:
        solid = sk.revolve_sketch(rect_sketch(plane, x=x), axis=axis, angle=270)
    except ValueError as e:
        assert str(e).startswith("revolve:"), "a refusal names the op"
        assert len(str(e)) > 40, "a refusal says what to change"
        return
    assert solid is not None and solid.volume > 0


def test_a_straddling_profile_says_which_way_it_crosses():
    with pytest.raises(ValueError, match="crosses the v axis .*-5 to 5"):
        sk.revolve_sketch(rect_sketch("XZ", x=0), axis="v", angle=360)


def test_a_circle_straddling_the_axis_is_caught_by_its_reach_not_its_seam():
    """A circle has ONE vertex; measuring vertices missed a circle centred at
    x=2 with r=4 that reaches -2. The span is measured on the kernel's box."""
    s = sk.make_sketch(plane="XZ", entities=[{"kind": "circle", "r": 4, "x": 2, "y": 0}])
    lo, hi = sk.revolve_axis_span(s, sk.revolve_axis(s, "v"))
    # the radial sign is the helper's own; what matters: the reach is the full
    # diameter and it crosses the axis
    assert hi - lo == pytest.approx(8, abs=1e-3) and lo < -1.9 and hi > 1.9
    with pytest.raises(ValueError, match="crosses"):
        sk.revolve_sketch(s, axis="v", angle=360)


def test_an_axis_outside_the_plane_says_so():
    """XZ's normal is -Y: spinning about Y sweeps nothing (volume 0 today)."""
    with pytest.raises(ValueError, match="does not contain the Y axis"):
        sk.revolve_sketch(rect_sketch("XZ"), axis="Y", angle=90)


@pytest.mark.parametrize("angle", [0, 0.0, 361, -400, 720])
def test_a_useless_angle_is_refused_before_the_kernel_wraps_it(angle):
    with pytest.raises(ValueError, match="angle"):
        sk.revolve_sketch(rect_sketch("XZ"), axis="v", angle=angle)


def test_a_bad_axis_name_is_a_sentence():
    with pytest.raises(ValueError, match='"u" or "v"'):
        sk.revolve_sketch(rect_sketch("XZ"), axis="W", angle=90)


# ----------------------------------------------------- the kernel agrees -----

@pytest.mark.parametrize("plane", PLANES)
@pytest.mark.parametrize("angle", [90, 180, 360, -90])
def test_a_rectangle_revolved_about_v_matches_pappus(plane, angle):
    # rectangle 10 x 6 centred at (20, 10) in the plane: about v (the plane's
    # y through the origin) the centroid is 20 from the axis
    solid = sk.revolve_sketch(rect_sketch(plane), axis="v", angle=angle)
    assert solid.volume == pytest.approx(pappus(20, 60, angle), rel=1e-6)


@pytest.mark.parametrize("plane", PLANES)
def test_a_rectangle_revolved_about_u_matches_pappus(plane):
    # about u (the plane's x) the centroid is 10 from the axis
    solid = sk.revolve_sketch(rect_sketch(plane), axis="u", angle=360)
    assert solid.volume == pytest.approx(pappus(10, 60, 360), rel=1e-6)


def test_a_circle_makes_a_torus_of_the_pappus_volume():
    s = sk.make_sketch(plane="XZ", entities=[{"kind": "circle", "r": 4, "x": 15, "y": 0}])
    solid = sk.revolve_sketch(s, axis="v", angle=360)
    assert solid.volume == pytest.approx(pappus(15, math.pi * 16, 360), rel=1e-6)


def test_an_l_profile_matches_pappus_with_its_composite_centroid():
    # L = a 10x2 foot at x 10..20 (centroid 15) plus a 2x8 leg at x 10..12 (centroid 11)
    s = sk.make_sketch(plane="XZ", entities=[
        {"kind": "rectangle", "w": 10, "h": 2, "x": 15, "y": 1, "mode": "add"},
        {"kind": "rectangle", "w": 2, "h": 8, "x": 11, "y": 6, "mode": "add"}])
    solid = sk.revolve_sketch(s, axis="v", angle=360)
    a1, a2 = 20.0, 16.0
    r_bar = (15 * a1 + 11 * a2) / (a1 + a2)
    assert solid.volume == pytest.approx(pappus(r_bar, a1 + a2, 360), rel=1e-6)


def test_the_sign_of_the_angle_is_the_direction_of_the_sweep():
    """A positive arc is right-handed about the axis (probed): a profile at +x
    on XZ swept +90 about Z lands at +y, -90 at -y."""
    s = rect_sketch("XZ")
    assert sk.revolve_sketch(s, axis="v", angle=90).center().Y > 5
    assert sk.revolve_sketch(s, axis="v", angle=-90).center().Y < -5


def test_u_and_v_ride_an_offset_plane_and_a_world_axis_outside_it_is_refused():
    """The tool's axes go through the SKETCH origin: on XZ offset 7 (y = -7)
    "v" is the line x=0 in that plane, so the volume is the plain lathe volume.
    The world Z axis is 7 mm OUTSIDE that plane: the kernel builds a valid solid
    of the wrong shape from it (review 2026-09-03: lathe volume, displaced
    centroid) — refused with a sentence, never built."""
    s = rect_sketch("XZ", offset=7)
    assert sk.revolve_sketch(s, axis="v", angle=360).volume == pytest.approx(pappus(20, 60, 360), rel=1e-6)
    with pytest.raises(ValueError, match="does not contain the Z axis"):
        sk.revolve_sketch(s, axis="Z", angle=360)
    d = Document(name="skew")
    d.add("p", "sketch", {"plane": "XZ", "offset": 7, "entities": [
        {"kind": "rectangle", "w": 10, "h": 6, "x": 20, "y": 10}]}, [])
    d.add("r", "revolve", {"axis": "Z", "angle": 90}, ["p"])
    d.rebuild()
    assert d.get("r").status == "failed" and "does not contain" in " ".join(d.get("r").problems)


def test_faces_on_both_sides_of_the_axis_revolve_when_none_crosses_it():
    """A mirrored pair (two circles at x = ±15): neither face crosses v, so both
    revolve into tori — the straddle test is per FACE, not the union."""
    s = sk.make_sketch(plane="XZ", entities=[
        {"kind": "circle", "r": 4, "x": 15, "y": 0, "mode": "add"},
        {"kind": "circle", "r": 4, "x": -15, "y": 0, "mode": "add"}])
    solid = sk.revolve_sketch(s, axis="v", angle=360)
    assert solid.volume == pytest.approx(2 * pappus(15, math.pi * 16, 360), rel=1e-6)
    d = Document(name="pair")
    d.add("p", "sketch", {"plane": "XZ", "offset": 0, "entities": [
        {"kind": "circle", "r": 4, "x": 15, "y": 0}, {"kind": "circle", "r": 4, "x": -15, "y": 0}]}, [])
    d.rebuild()
    p = plan(d)
    assert p["ok"] and p["axis_name"] == "v", p
    assert all(q[0] != 0 for L in p["loops"] for q in L["outer"])


def test_a_sketch_moved_out_of_its_plane_rides_and_a_mirrored_one_refuses_u_v():
    """A move along the normal carries the plane (and so u / v) with it; a
    mirror hands back a fresh Sketch with no recorded plane — u / v refuse with
    a sentence rather than guess, while a world axis in the plane still works."""
    d = Document(name="derived")
    d.add("p", "sketch", {"plane": "XZ", "offset": 0, "entities": [
        {"kind": "rectangle", "w": 10, "h": 6, "x": 20, "y": 10}]}, [])
    d.add("m", "move", {"y": 5}, ["p"])
    d.add("q", "mirror", {"plane": "YZ"}, ["p"])
    d.rebuild()
    moved = d._parts["m"]
    assert sk.sketch_plane_of(moved).origin.Y == pytest.approx(5, abs=1e-6)
    assert sk.revolve_sketch(moved, axis="v", angle=360).volume == pytest.approx(pappus(20, 60, 360), rel=1e-6)
    mirrored = d._parts["q"]
    with pytest.raises(ValueError, match="does not carry the plane"):
        sk.revolve_sketch(mirrored, axis="v", angle=360)
    assert sk.revolve_sketch(mirrored, axis="Z", angle=360).volume == pytest.approx(pappus(20, 60, 360), rel=1e-6)


def test_a_legacy_world_axis_off_the_plane_falls_back_with_a_note_and_alternatives_carry_the_swap():
    d = doc_with("XZ", offset=7)
    d.add("r", "revolve", {"axis": "Z", "angle": 90}, ["p"])     # fails now: Z is outside the plane
    d.rebuild()
    p = toolplan.plan(d, {"tool": "revolve", "feature_id": "r"})
    assert p["ok"] and p["axis_name"] == "v", p
    assert p["fallback"]["from"] == "Z" and "outside" in p["fallback"]["why"]
    # u, and (P3b) the rectangle's four sides — every one carries its handles
    assert set(p["alternatives"]) == {"u", "e1", "e2", "e3", "e4"}
    alt = p["alternatives"]["u"]
    assert alt["frame"]["z_dir"] == pytest.approx(list(sk.sketch_plane("XZ", 7).x_dir), abs=1e-6)
    assert alt["limits"]["max_angle"] == 360


def test_a_face_sketch_revolves_about_its_own_axis():
    d = Document(name="face")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
    d.add("s", "sketch_on_face", {"face": "top", "offset": 0, "entities": [
        {"kind": "rectangle", "w": 10, "h": 6, "x": 20, "y": 0}]}, ["b"])
    d.rebuild()
    prof = d._parts["s"]
    top = d._parts["b"].bounding_box().max.Z                    # the kernel's top face
    assert hasattr(prof, "_tc_plane"), "a face sketch remembers its plane"
    assert sk.sketch_plane_of(prof).origin.Z == pytest.approx(top)
    solid = sk.revolve_sketch(prof, axis="v", angle=360)
    assert solid.volume == pytest.approx(pappus(20, 60, 360), rel=1e-6)
    assert solid.center().Z == pytest.approx(top, abs=1e-6)    # it sits on the face


# ------------------------------------------------------------- the planner ---

def plan(d, **req):
    return toolplan.plan(d, {"tool": "revolve", "sketch_id": "p", **req})


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


@pytest.mark.parametrize("plane", PLANES)
def test_the_planner_opens_on_the_lathe_axis_when_both_work(plane):
    p = plan(doc_with(plane))
    assert p["ok"], p
    working = [a["name"] for a in p["axes"] if a["ok"]]
    assert p["axis_name"] == "v" and working[:2] == ["v", "u"]
    assert working[2:] == ["e1", "e2", "e3", "e4"]     # P3b: the outline's sides follow
    pl = sk.sketch_plane(plane, 0)
    assert p["axis"] == pytest.approx(list(pl.y_dir), abs=1e-6)


@pytest.mark.parametrize("plane", PLANES)
def test_the_swap_is_honoured_and_the_legacy_world_name_is_mapped(plane):
    d = doc_with(plane)
    assert plan(d, axis="u")["axis_name"] == "u"
    pl = sk.sketch_plane(plane, 0)
    world = toolplan._axis_name(list(pl.y_dir)).lstrip("+-")     # the world name of v
    assert plan(d, axis=world)["axis_name"] == "v"


def test_a_profile_crossing_v_gets_u_not_v():
    p = plan(doc_with("XZ", x=0, y=10))
    assert p["ok"] and p["axis_name"] == "u"
    working = [a["name"] for a in p["axes"] if a["ok"]]
    assert working[0] == "u" and "v" not in working
    v = next(a for a in p["axes"] if a["name"] == "v")
    assert not v["ok"] and "crosses v" in v["why"]      # listed, greyed, with the reason


def test_a_profile_over_the_origin_opens_on_its_own_side_since_p3b():
    """P3 refused this profile; Fusion turns it about one of its sides, and so
    does P3b. The refusal survives only for a profile with no straight edge —
    tests/test_revolve_p3b.py has the centred circle."""
    p = plan(doc_with("XZ", x=0, y=0))
    assert p["ok"] and p["axis_name"] == "e1"
    byname = {a["name"]: a for a in p["axes"]}
    assert "crosses v" in byname["v"]["why"] and "crosses u" in byname["u"]["why"]


def test_a_swap_to_an_axis_that_does_not_work_falls_back_to_one_that_does():
    p = plan(doc_with("XZ", x=0, y=10), axis="v")
    assert p["ok"] and p["axis_name"] == "u"


@pytest.mark.parametrize("plane", PLANES)
@pytest.mark.parametrize("kind", ["rectangle", "circle"])
@pytest.mark.parametrize("axis", ["v", "u"])
def test_the_planned_axis_actually_builds_and_matches_pappus(plane, kind, axis):
    """The plan is checked against what the kernel builds WITH it: the
    revolved volume equals Pappus from the plan's own outline (the (r, h)
    loops: r_bar = the outline's centroid radius from the ring origin)."""
    d = doc_with(plane, kind=kind)
    p = plan(d, axis=axis)
    assert p["ok"] and p["axis_name"] == axis, p
    solid = sk.revolve_sketch(d._parts["p"], axis=axis, angle=360)
    area = 60.0 if kind == "rectangle" else math.pi * 16
    r_bar = 20.0 if axis == "v" else 10.0                # the entity centre
    assert solid.volume == pytest.approx(pappus(r_bar, area, 360), rel=1e-6)
    # the plan's outline sits at that radius, all of it on the material side
    rs = [q[0] for q in p["loops"][0]["outer"]]
    assert min(rs) > 0 and abs(sum(rs) / len(rs) - r_bar) < 0.5
    assert p["limits"]["radius"] == pytest.approx(max(rs), abs=1e-3)


@pytest.mark.parametrize("plane", PLANES)
def test_the_ring_frame_is_orthonormal_right_handed_and_points_at_the_material(plane):
    p = plan(doc_with(plane))
    fr = p["frame"]
    for a, b in ((fr["x_dir"], fr["y_dir"]), (fr["y_dir"], fr["z_dir"]), (fr["x_dir"], fr["z_dir"])):
        assert dot(a, b) == pytest.approx(0, abs=1e-6)
    assert dot(cross(fr["z_dir"], fr["x_dir"]), fr["y_dir"]) == pytest.approx(1, abs=1e-6)
    assert fr["z_dir"] == p["axis"]
    # x points from the axis to the material: the sketch's centre (20, 10 in
    # the plane) lies at positive x
    pl = sk.sketch_plane(plane, 0)
    centre = list(pl.origin + pl.x_dir * 20 + pl.y_dir * 10)
    rel = [c - o for c, o in zip(centre, fr["origin"])]
    assert dot(rel, fr["x_dir"]) == pytest.approx(20, abs=1e-3)
    assert abs(dot(rel, fr["y_dir"])) < 1e-6                  # in the sketch plane


def test_the_ring_sits_on_the_axis_level_with_the_profile():
    p = plan(doc_with("XZ", x=20, y=10))                     # rect spans z 7..13
    o = p["origin"]
    assert o[0] == pytest.approx(0, abs=1e-6) and o[1] == pytest.approx(0, abs=1e-6)
    assert o[2] == pytest.approx(10, abs=1e-6)
    assert p["limits"]["axis_half"] >= p["limits"]["radius"]


def test_the_lathe_outline_is_centred_on_the_ring_and_positive_in_r():
    p = plan(doc_with("XZ", x=20, y=10))
    outer = p["loops"][0]["outer"]
    rs = [q[0] for q in outer]
    hs = [q[1] for q in outer]
    assert min(rs) == pytest.approx(15, abs=1e-3) and max(rs) == pytest.approx(25, abs=1e-3)
    assert min(hs) == pytest.approx(-3, abs=1e-3) and max(hs) == pytest.approx(3, abs=1e-3)


@pytest.mark.parametrize("face", ["top", "bottom"])
def test_a_face_sketch_plans_about_the_face_plane_axes_and_targets_its_body(face):
    """On a BOTTOM face the sketch plane's canonical z points INTO the body
    while the face's geometric normal points out: the ring must still point at
    the material and the outline stay at positive radius (review 2026-09-03:
    the span used to re-read the normal from the geometry)."""
    d = Document(name="face")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
    d.add("s", "sketch_on_face", {"face": face, "offset": 0, "entities": [
        {"kind": "rectangle", "w": 10, "h": 6, "x": 20, "y": 0}]}, ["b"])
    d.rebuild()
    p = toolplan.plan(d, {"tool": "revolve", "sketch_id": "s"})
    assert p["ok"], p
    bb = d._parts["b"].bounding_box()
    z = bb.max.Z if face == "top" else bb.min.Z
    assert p["origin"][2] == pytest.approx(z, abs=1e-6)      # on that face
    assert p["target_body"] == "b"
    rs = [q[0] for q in p["loops"][0]["outer"]]
    assert min(rs) > 0, "the outline sits on the material side of the axis"
    # the ring's x points from the axis to the material: the sketch's centre
    # is 20 mm out along the plane's x
    pl = sk.sketch_plane_of(d._parts["s"])
    centre = list(pl.origin + pl.x_dir * 20)
    rel = [c - o for c, o in zip(centre, p["frame"]["origin"])]
    assert dot(rel, p["frame"]["x_dir"]) == pytest.approx(20, abs=1e-3)
    solid = sk.revolve_sketch(d._parts["s"], axis=p["axis_name"], angle=360)
    assert solid.volume == pytest.approx(pappus(20, 60, 360), rel=1e-6)


def test_an_existing_revolve_plans_from_its_feature_and_keeps_its_axis():
    d = doc_with("XZ")
    d.add("r", "revolve", {"axis": "u", "angle": 270}, ["p"])
    d.add("legacy", "revolve", {"angle": 270}, ["p"])            # no axis: the op's Z
    d.rebuild()
    p = toolplan.plan(d, {"tool": "revolve", "feature_id": "r"})
    assert p["ok"] and p["input"] == "p" and p["axis_name"] == "u" and p["fallback"] is None
    q = toolplan.plan(d, {"tool": "revolve", "feature_id": "legacy"})
    assert q["ok"] and q["axis_name"] == "v" and q["fallback"] is None   # Z IS v here (offset 0)


def test_failures_are_sentences_never_exceptions():
    d = doc_with("XZ")
    for req in ({"tool": "revolve"}, {"tool": "revolve", "sketch_id": "zz"},
                {"tool": "revolve", "feature_id": "p"}):
        r = toolplan.plan(d, req)
        assert r["ok"] is False and len(r["error"]) > 15, r


# ------------------------------------------------------------ in a document --

def test_revolve_works_as_a_feature_with_the_tools_axis_names():
    d = doc_with("XZ")
    d.add("r", "revolve", {"axis": "v", "angle": 360}, ["p"])
    assert d.rebuild()
    f = d.get("r")
    assert f.status == "ok"
    assert f.volume == pytest.approx(pappus(20, 60, 360), rel=1e-6)


def test_a_bad_revolve_in_a_tree_reports_instead_of_crashing():
    d = doc_with("XZ", x=0, y=0)
    d.add("r", "revolve", {"axis": "v", "angle": 360}, ["p"])
    d.rebuild()
    f = d.get("r")
    assert f.status == "failed"
    assert any("crosses" in pr for pr in f.problems), f.problems


def test_editing_the_angle_rebuilds_deterministically():
    d = doc_with("XZ")
    d.add("r", "revolve", {"axis": "v", "angle": 90}, ["p"])
    d.rebuild()
    v90 = d.get("r").volume
    d.edit("r", "angle", 180)
    d.rebuild()
    assert d.get("r").volume == pytest.approx(2 * v90, rel=1e-4)   # the tree rounds volumes
    d.edit("r", "angle", 90)
    d.rebuild()
    assert d.get("r").volume == pytest.approx(v90, rel=1e-9)


def test_the_http_route_plans_a_revolve_read_only():
    from fastapi.testclient import TestClient
    import studio
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(Document(name="untitled"))
    studio._rebuild_and_mesh()
    c = TestClient(studio.app)
    c.post("/api/feature/add", json={"id": "p", "op": "sketch", "inputs": [],
                                     "params": {"plane": "XZ", "offset": 0, "entities": [
                                         {"kind": "rectangle", "w": 10, "h": 6, "x": 20, "y": 10}]}})
    before = c.get("/api/doc").json()
    r = c.post("/api/tool/plan", json={"tool": "revolve", "sketch_id": "p", "axis": "u"}).json()
    assert r["ok"] and r["axis_name"] == "u", r
    after = c.get("/api/doc").json()
    assert after["rebuild_ms"] == before["rebuild_ms"], "a plan must never rebuild"
