"""Sweep (Tier 2, specs/sweep.md): the guards that make dragging safe, and the
planner that only ever opens on a sweep that builds.

Every number here came off the kernel first (probes/sweep_api_probe*.py):

    path leaving IN the profile's plane  -> a "valid" solid of volume 0.0
    bend tighter than the profile        -> volume A·L, is_valid True, health []
                                            (the inside folded over itself)
    corner leg shorter than the mitre    -> invalid, open shell
    TRANSFORMED at a sharp corner        -> HALF the volume, status ok
    a path 20 mm off the profile's plane -> a solid 50 mm high nobody asked for
    Wire.trim(0, f)                      -> exactly f of the LENGTH

Every geometric claim below is checked against the kernel: a perpendicular
sweep of one face along a planar path is area × length (Pappus), to 1e-6.
"""
import json
import math

import build123d as b3d
import pytest

import sketch as sk
import toolplan
from document import Document

R = 3.0
A = math.pi * R * R
KERNEL_WORDS = ("StdFail", "Standard_", "BRep", "TopoDS", "OCP", "NoneType", "Traceback")


def circle(plane="XY", x=0.0, y=0.0, r=R):
    return sk.make_sketch(plane=plane, entities=[
        {"kind": "circle", "r": r, "x": x, "y": y, "mode": "add"}])


def path_sketch(segments, plane="XZ", start=(0, 0), offset=0.0):
    return sk.make_sketch(plane=plane, offset=offset, entities=[
        {"kind": "path", "closed": False, "start": list(start), "segments": segments}])


def line(to):
    return {"type": "line", "to": list(to)}


def arc(via, to):
    return {"type": "arc", "via": list(via), "to": list(to)}


def bend(r=10.0, up=20.0, out=20.0):
    """up, a quarter-circle bend of radius r towards +x, then out — the classic
    pipe elbow; its length is up + r·π/2 + out."""
    return [line((0, up)),
            arc((r * (1 - math.cos(math.pi / 4)), up + r * math.sin(math.pi / 4)), (r, up + r)),
            line((r + out, up + r))]


BEND_LEN = 20 + 10 * math.pi / 2 + 20


def sweep(profile, path, **kw):
    return sk.sweep_sketch(profile, path="rail", _path_sketch=path, **kw)


def refusal(fn):
    with pytest.raises(ValueError) as e:
        fn()
    msg = str(e.value)
    assert msg.startswith("sweep"), msg
    assert len(msg) > 40, "a refusal says what to change: " + msg
    assert not any(w in msg for w in KERNEL_WORDS), msg
    return msg


# ------------------------------------------------- what builds is A·L -------

def test_full_sweep_along_a_bent_path_is_area_times_length():
    out = sweep(circle(), path_sketch(bend()), full=True)
    assert out.volume == pytest.approx(A * BEND_LEN, rel=1e-6)
    assert not __import__("inspector").health(out)


@pytest.mark.parametrize("d", [5.0, 20.0, 25.0, 40.0, BEND_LEN])
def test_a_partial_sweep_is_area_times_the_distance(d):
    out = sweep(circle(), path_sketch(bend()), distance=d)
    assert out.volume == pytest.approx(A * d, rel=1e-6)


def test_a_sharp_corner_is_mitred_not_halved():
    """TRANSFORMED swept only the first leg (565 of 1131 mm3, status ok)."""
    out = sweep(circle(), path_sketch([line((0, 20)), line((20, 20))]), full=True)
    assert out.volume == pytest.approx(A * 40, rel=1e-6)


def test_a_closed_loop_path_makes_a_frame():
    loop = [line((0, 30)), line((40, 30)), line((40, 0)), line((0, 0))]
    out = sweep(circle(), path_sketch(loop), full=True)
    assert out.volume == pytest.approx(A * 140, rel=1e-6)
    assert len(out.solids()) == 1


@pytest.mark.parametrize("plane,path_plane", [("XY", "XZ"), ("XY", "YZ"), ("XZ", "XY"),
                                              ("YZ", "XY"), ("XZ", "YZ"), ("YZ", "XZ")])
def test_every_perpendicular_plane_pair_builds(plane, path_plane):
    """The path plane's frame decides which in-plane axis is 'up'; the guard
    reads the kernel's tangent, not a plane name, so every pair works or says
    why (a path plane whose axes both lie in the profile plane cannot leave)."""
    prof = circle(plane)
    try:
        out = sweep(prof, path_sketch([line((0, 20)), line((20, 20))], plane=path_plane),
                    full=True)
    except ValueError as e:
        assert "along the profile" in str(e) or "off the profile's plane" in str(e), str(e)
        return
    assert out.volume == pytest.approx(A * 40, rel=1e-6)


def test_a_path_drawn_towards_the_profile_is_read_from_its_touching_end():
    """The far end touches the profile's plane: the path is reversed and the
    op says so, instead of sweeping from a start 20 mm in the air."""
    sk.drain_notes()
    out = sweep(circle(), path_sketch([line((20, 20)), line((0, 20)), line((0, 0))],
                                      start=(20, 40)), full=True)
    # 20 + 20 + 20 of path; the solid runs from the profile upward: up to
    # z 20, across to x 20, up to z 40 (the last leg is vertical, so the cap
    # is flat at 40 and the radius shows in x only)
    assert out.volume == pytest.approx(A * 60, rel=1e-6)
    bb = out.bounding_box()
    assert bb.min.Z == pytest.approx(0, abs=1e-6) and bb.max.Z == pytest.approx(40, abs=1e-6)
    assert bb.max.X == pytest.approx(23, abs=1e-6)
    assert any("far end" in n for n in sk.drain_notes())


def test_a_slanted_start_builds_thinner_and_says_so():
    """45°: exactly A·L·cos45 — the section is carried as it lies."""
    sk.drain_notes()
    out = sweep(circle(), path_sketch([line((20, 20))]), full=True)
    assert out.volume == pytest.approx(A * math.hypot(20, 20) * math.cos(math.pi / 4), rel=1e-6)
    assert any("45°" in n for n in sk.drain_notes())


def test_a_straight_path_starting_off_centre_sweeps_the_profile_where_it_is():
    # (the note that stood here said "the sweep runs from the centre", which
    # is only true of a STRAIGHT path: the kernel turns the profile about the
    # path's start - see test_sweep_review.py - so a straight path is the one
    # case where the start makes no difference, and it says nothing now)
    sk.drain_notes()
    out = sweep(circle(), path_sketch([line((10, 20))], start=(10, 0)), full=True)
    bb = out.bounding_box()
    assert bb.min.X == pytest.approx(-R, abs=1e-6) and bb.max.X == pytest.approx(R, abs=1e-6)
    assert out.volume == pytest.approx(A * 20, rel=1e-6)
    assert not any("from the profile's centre" in n for n in sk.drain_notes())


def test_two_profiles_sweep_into_two_bodies():
    prof = sk.make_sketch(plane="XY", entities=[
        {"kind": "circle", "r": 2, "x": -6, "y": 0, "mode": "add"},
        {"kind": "circle", "r": 2, "x": 6, "y": 0, "mode": "add"}])
    out = sweep(prof, path_sketch([line((0, 20))]), full=True)
    assert len(out.solids()) == 2
    assert out.volume == pytest.approx(2 * math.pi * 4 * 20, rel=1e-6)


# ------------------------------------------------- what is refused ----------

def test_a_path_in_the_profiles_plane_is_refused_not_a_zero_volume_success():
    msg = refusal(lambda: sweep(circle(), path_sketch([line((20, 0))], plane="XY"), full=True))
    assert "along the profile" in msg and "perpendicular" in msg


def test_a_path_off_the_profiles_plane_at_both_ends_is_refused():
    msg = refusal(lambda: sweep(circle(), path_sketch([line((0, 40)), line((20, 40))],
                                                      start=(0, 20)), full=True))
    assert "off the profile's plane" in msg and "20" in msg


@pytest.mark.parametrize("r", [1.0, 2.0, 2.5, 3.0])
def test_a_bend_tighter_than_the_profile_is_refused_before_the_kernel(r):
    """The kernel calls the folded solid VALID with exactly A·L of volume."""
    msg = refusal(lambda: sweep(circle(), path_sketch(bend(r=r)), full=True))
    assert "tighter than the profile" in msg and f"{r:.3g}" in msg


def test_a_wide_enough_bend_builds():
    out = sweep(circle(), path_sketch(bend(r=3.5)), full=True)
    assert out.volume == pytest.approx(A * (20 + 3.5 * math.pi / 2 + 20), rel=1e-6)


@pytest.mark.parametrize("leg", [1.0, 2.0, 2.9])
def test_a_corner_leg_shorter_than_the_mitre_is_refused(leg):
    """Measured: legs of 1, 2, 3 mm with a 3 mm profile come back INVALID."""
    msg = refusal(lambda: sweep(circle(), path_sketch(
        [line((0, leg)), line((leg, leg)), line((leg, 2 * leg))]), full=True))
    assert "corner" in msg and "folds" in msg


def test_a_hairpin_is_refused():
    msg = refusal(lambda: sweep(circle(), path_sketch([line((0, 20)), line((0, 0.5))]), full=True))
    assert "back on itself" in msg


def test_distance_zero_and_beyond_the_end_are_sentences():
    assert "distance is 0" in refusal(lambda: sweep(circle(), path_sketch(bend()), distance=0))
    msg = refusal(lambda: sweep(circle(), path_sketch(bend()), distance=999))
    assert "longer than the path" in msg and "full" in msg


def test_a_profile_with_no_face_is_refused():
    msg = refusal(lambda: sweep(path_sketch([line((0, 20))], plane="XY"),
                                path_sketch([line((0, 20))]), full=True))
    assert "closed shape" in msg


def test_a_path_sketch_with_no_open_path_is_refused():
    msg = refusal(lambda: sweep(circle(), circle("XZ"), full=True))
    assert "no open path" in msg and "Path tool" in msg


def test_legacy_path_points_still_sweep_the_whole_polyline():
    out = sk.sweep_sketch(circle(), path_points=[[0, 0, 0], [0, 0, 20], [20, 0, 20]])
    assert out.volume == pytest.approx(A * 40, rel=1e-6)


def test_sweep_face_sweeps_a_flat_face_of_a_body():
    box = b3d.Box(10, 10, 5)
    top = max(box.faces(), key=lambda f: f.center().Z)
    out = sk.sweep_face(box, list(top.center()), [0, 0, 1], path="rail",
                        _path_sketch=path_sketch([line((0, 22.5)), line((20, 22.5))],
                                                 start=(0, 2.5)), full=True)
    assert out.volume == pytest.approx(100 * 40, rel=1e-6)


# ------------------------------------------------- the path sketch ----------

def test_a_path_sketch_is_a_sketch_of_edges_with_its_wire():
    ps = path_sketch(bend())
    assert sk.is_sketch(ps) and not ps.faces() and ps.area == 0
    wires = sk.sketch_paths(ps)
    assert len(wires) == 1 and wires[0].length == pytest.approx(BEND_LEN, rel=1e-9)
    assert sk.is_path_sketch([{"kind": "path", "closed": False}])
    assert not sk.is_path_sketch([{"kind": "path"}]) and not sk.is_path_sketch([])


def test_an_open_path_beside_a_closed_shape_rides_along():
    s = sk.make_sketch(plane="XY", entities=[
        {"kind": "circle", "r": 3, "mode": "add"},
        {"kind": "path", "closed": False, "start": [10, 0], "segments": [line((30, 0))]}])
    assert len(s.faces()) == 1 and s.area == pytest.approx(A, rel=1e-6)
    assert len(sk.sketch_paths(s)) == 1
    assert sk.extrude_sketch(s, 5).volume == pytest.approx(A * 5, rel=1e-6)


def test_an_open_path_honours_its_own_x_y_rotation():
    """`_entity` rotates about the entity origin then places; the wire must too."""
    ps = sk.make_sketch(plane="XY", entities=[
        {"kind": "path", "closed": False, "x": 10, "y": 5, "rotation": 90,
         "start": [0, 0], "segments": [line((20, 0))]}])
    w = sk.sketch_paths(ps)[0]
    assert list(w.start_point()) == pytest.approx([10, 5, 0], abs=1e-9)
    assert list(w.end_point()) == pytest.approx([10, 25, 0], abs=1e-9)


def test_an_open_path_with_a_bad_segment_is_a_sentence():
    with pytest.raises(ValueError, match="same point"):
        path_sketch([line((0, 0))])
    with pytest.raises(ValueError, match="start point"):
        sk.make_sketch(plane="XZ", entities=[{"kind": "path", "closed": False,
                                              "segments": [line((0, 5))]}])


def test_compose_of_open_paths_only_says_so():
    with pytest.raises(ValueError, match="open paths"):
        sk.compose([{"kind": "path", "closed": False, "start": [0, 0], "segments": [line((0, 5))]}])


# ------------------------------------------------- through the document -----

# the plate is 12 thick and centred, so its top face is at z = 6 and the
# circle's centre at world (5, 0, 6): a path on XZ (y = 0) placed at entity
# x = 5, y = 6 starts exactly there (an XZ sketch's `offset` moves along Y —
# the first draft of this file put the path 6 mm UNDER the face, and the
# guard said so)
BENT_ENTS = [{"kind": "path", "closed": False, "x": 5, "y": 6, "start": [0, 0],
              "segments": bend()}]


def path_ents(segments, x=5.0, y=6.0):
    return [{"kind": "path", "closed": False, "x": x, "y": y, "start": [0, 0],
             "segments": segments}]


def doc():
    d = Document(name="sw")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
    d.add("p", "sketch_on_face", {"face": "top", "offset": 0, "entities": [
        {"kind": "circle", "r": 3, "x": 5, "y": 0, "mode": "add"}]}, ["b"])
    d.add("rail", "sketch", {"plane": "XZ", "offset": 0, "entities": BENT_ENTS}, [])
    d.rebuild()
    return d


def test_the_document_hands_the_path_sketch_to_the_op_and_rebuilds():
    d = doc()
    assert d.get("rail").status == "ok" and d.get("rail").volume is None
    d.add("sw1", "sweep", {"path": "rail", "full": True}, ["p"])
    d.rebuild()
    f = d.get("sw1")
    assert f.status == "ok", f.problems
    assert f.volume == pytest.approx(A * BEND_LEN, rel=1e-4)
    d.edit_many("sw1", {"full": False, "distance": 12})
    d.rebuild()
    assert d.get("sw1").volume == pytest.approx(A * 12, rel=1e-4)


def test_the_path_is_a_reference_rename_follows_and_delete_cascades():
    d = doc()
    d.add("sw1", "sweep", {"path": "rail", "full": True}, ["p"])
    d.rebuild()
    assert d.param_refs(d.get("sw1")) == ["rail"]
    d.rename("rail", "spine")
    assert d.get("sw1").params["path"] == "spine"
    d.rebuild()
    assert d.get("sw1").status == "ok"
    plan = d.remove_plan("spine")
    assert "sw1" in plan["deleted"], plan
    assert "p" not in plan["deleted"], "the profile is not the path's to take"


def test_a_struck_or_missing_or_closed_path_is_a_sentence():
    d = doc()
    d.add("sw1", "sweep", {"path": "rail", "full": True}, ["p"])
    d.rebuild()
    # striking the PATH takes the sweep along, as a pattern goes with its
    # seed (a reference is a dependency) — and ↩ brings both back
    d.strike("rail")
    d.rebuild()
    assert d.get("sw1").suppressed
    d.unstrike("rail")
    d.rebuild()
    assert not d.get("sw1").suppressed and d.get("sw1").status == "ok"
    d.edit_many("sw1", {"path": "nope"})
    d.rebuild()
    assert "no sketch named 'nope'" in d.get("sw1").problems[0]
    d.edit_many("sw1", {"path": "b"})
    d.rebuild()
    assert "not a sketch" in d.get("sw1").problems[0]
    d.edit_many("sw1", {"path": "p"})
    d.rebuild()
    assert "no open path" in d.get("sw1").problems[0]


def test_extrude_and_revolve_of_a_path_sketch_are_refused_plainly():
    d = doc()
    d.add("e", "extrude", {"amount": 5}, ["rail"])
    d.add("r", "revolve", {"axis": "v", "angle": 90}, ["rail"])
    d.rebuild()
    for fid in ("e", "r"):
        msg = d.get(fid).problems[0]
        assert "path sketch" in msg and "Sweep" in msg, msg
        assert not any(w in msg for w in KERNEL_WORDS), msg


def test_sweep_of_a_body_is_still_refused():
    d = doc()
    d.add("sw1", "sweep", {"path": "rail", "full": True}, ["b"])
    d.rebuild()
    assert "solid body" in d.get("sw1").problems[0]


# ------------------------------------------------- the plan -----------------

def ok(plan):
    assert plan["ok"], plan
    json.dumps(plan)
    return plan


def test_plan_opens_on_the_newest_path_sketch_with_its_stations_on_the_wire():
    d = doc()
    plan = ok(toolplan.plan(d, {"tool": "sweep", "sketch_id": "p"}))
    assert plan["op"] == "sweep" and plan["path_id"] == "rail" and plan["target_body"] == "b"
    assert [p["id"] for p in plan["paths"]] == ["rail"]
    assert plan["limits"]["length"] == pytest.approx(BEND_LEN, abs=1e-3)
    assert plan["limits"]["reach"] == pytest.approx(3, abs=1e-3)
    assert plan["limits"]["min_bend"] == pytest.approx(10, abs=1e-3)
    S = plan["stations"]
    assert S[0]["s"] == 0 and S[-1]["s"] == pytest.approx(BEND_LEN, abs=1e-3)
    assert all(a["s"] < b["s"] for a, b in zip(S, S[1:]))
    # every station is a point of the kernel's wire, moved to the profile's centre
    w = sk.sketch_paths(d._parts["rail"])[0]
    centre = d._parts["p"].center()
    shift = centre - w.start_point()
    for s in S:
        assert w.distance_to(b3d.Vector(*s["p"]) - shift) < 1e-3, s
    assert plan["frame"]["origin"] == pytest.approx(list(centre), abs=1e-3)
    assert S[0]["p"] == pytest.approx(list(centre), abs=1e-3)
    # the frame is carried: at the end the tangent is +X and the profile's x
    # (which started as world +X) now points down the -Z way it was turned
    assert S[-1]["t"] == pytest.approx([1, 0, 0], abs=1e-3)
    assert abs(S[-1]["x"][0]) < 1e-3 or abs(S[-1]["y"][0]) < 1e-3
    assert plan["loops"] and len(plan["loops"][0]["outer"]) >= 24
    assert plan["notes"] == [] and plan["reversed"] is False


def test_plan_says_when_there_is_no_path_and_when_the_profile_is_one():
    d = Document(name="np")
    d.add("p", "sketch", {"plane": "XY", "entities": [{"kind": "circle", "r": 3, "mode": "add"}]}, [])
    d.rebuild()
    plan = toolplan.plan(d, {"tool": "sweep", "sketch_id": "p"})
    assert not plan["ok"] and "Path tool" in plan["error"]
    d2 = doc()
    plan = toolplan.plan(d2, {"tool": "sweep", "sketch_id": "rail"})
    assert not plan["ok"] and "path sketch" in plan["error"] and "PROFILE" in plan["error"]


def test_plan_refuses_with_the_ops_own_sentence():
    d = doc()
    d.add("flat", "sketch_on_face", {"face": "top", "offset": 0, "entities": [
        {"kind": "path", "closed": False, "start": [5, 0], "segments": [line((25, 0))]}]}, ["b"])
    d.rebuild()
    plan = toolplan.plan(d, {"tool": "sweep", "sketch_id": "p", "path_id": "flat"})
    assert not plan["ok"] and "along the profile" in plan["error"]


def test_plan_edit_mode_reads_the_stored_path_and_falls_back_when_it_is_gone():
    d = doc()
    d.add("sw1", "sweep", {"path": "rail", "distance": 12}, ["p"])
    d.rebuild()
    plan = ok(toolplan.plan(d, {"tool": "sweep", "feature_id": "sw1"}))
    assert plan["path_id"] == "rail" and plan["stored"] == {"distance": 12, "full": None}
    d.edit_many("sw1", {"path": "gone"})
    d.rebuild()                       # the row is red now; the plan still opens
    assert d.get("sw1").status == "failed"
    plan = ok(toolplan.plan(d, {"tool": "sweep", "feature_id": "sw1"}))
    assert plan["fallback"] == {"from": "gone", "why": "it is not in this design"}
    assert plan["path_id"] == "rail"


def test_plan_face_mode_sweeps_the_picked_face_and_the_op_builds_it():
    d = doc()
    # the plate's top face is 60 x 40: reach 36, so it needs legs of 36+ to
    # turn a corner — a straight L of 40 + 40 from the face's centre
    d.add("big", "sketch", {"plane": "XZ", "offset": 0,
                            "entities": path_ents([line((0, 40)), line((40, 40))], x=0)}, [])
    d.rebuild()
    top = max(d._parts["b"].faces(), key=lambda f: f.center().Z)
    plan = ok(toolplan.plan(d, {"tool": "sweep", "body_id": "b",
                                "face_center": list(top.center()), "face_normal": [0, 0, 1]}))
    assert plan["op"] == "sweep_face" and plan["mode"] == "face" and plan["target_body"] == "b"
    assert plan["path_id"] == "big"
    assert plan["limits"]["reach"] == pytest.approx(math.hypot(30, 20), abs=1e-3)
    d.add("sf", "sweep_face", {"face_center": list(top.center()), "face_normal": [0, 0, 1],
                               "path": "big", "full": True}, ["b"])
    d.rebuild()
    assert d.get("sf").status == "ok", d.get("sf").problems
    assert d.get("sf").volume == pytest.approx(60 * 40 * 80, rel=1e-4)
    # ...and the 10 mm bend of 'rail' is refused for that face
    d.edit_many("sf", {"path": "rail"})
    d.rebuild()
    assert "tighter than the profile" in d.get("sf").problems[0]


def test_plan_lists_every_path_sketch_newest_first_and_honours_the_request():
    d = doc()
    d.add("rail2", "sketch", {"plane": "XZ", "offset": 0,
                              "entities": path_ents([line((0, 30))])}, [])
    d.rebuild()
    plan = ok(toolplan.plan(d, {"tool": "sweep", "sketch_id": "p"}))
    assert [p["id"] for p in plan["paths"]] == ["rail2", "rail"] and plan["path_id"] == "rail2"
    plan = ok(toolplan.plan(d, {"tool": "sweep", "sketch_id": "p", "path_id": "rail"}))
    assert plan["path_id"] == "rail" and plan["fallback"] is None


def test_sweep_length_is_the_one_reading_of_distance_and_full():
    assert sk.sweep_length(0, True, 50) == 50
    assert sk.sweep_length(12, False, 50) == 12
    assert sk.sweep_length(50, False, 50) == 50
    with pytest.raises(ValueError, match="distance is 0"):
        sk.sweep_length(0, False, 50)
    with pytest.raises(ValueError, match="longer than the path"):
        sk.sweep_length(51, False, 50)
