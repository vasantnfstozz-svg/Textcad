"""Hole (LAUNCH-PLAN.md P4, specs/hole.md): Fusion's Hole as ONE op that eats
its body, and the planner that hands the tool its point, its axis into the
material and the marker's frame.

probes/hole_probe.py (2026-09-06) found in the kernel:

    build123d's Hole objects           -> double-length builder-mode tools (not used)
    a hand-built cutter                -> exact volumes, healthy, on every corpus face
    a hole centred in an existing hole -> removes nothing, and "succeeds"
    a hole tangent to the face's edge  -> an OPEN SHELL the kernel calls valid
    Face.is_inside / Edge ∩ Solid      -> "on the face" and "how thick underneath"

Every geometric claim below is checked against the kernel: volumes against
formulas, positions against the centroid of the material that went away.
"""
import json
import math

import build123d as b3d
import pytest

import inspector
import sketch as sk
import toolplan
from document import Document, op_params
from tests.gauntlet import BODIES, planar_faces

PI = math.pi


def box(w=50.0, d=50.0, t=20.0):
    return b3d.Box(w, d, t)                 # centred on the origin: top face at z = t/2


TOP = dict(face_center=[0.0, 0.0, 10.0], face_normal=[0.0, 0.0, 1.0])


def gone(before, after):
    """the material a hole took away: its volume and its centroid"""
    removed = before - after
    c = removed.center()
    return before.volume - after.volume, [round(c.X, 4), round(c.Y, 4), round(c.Z, 4)]


def healthy(part):
    assert inspector.health(part) == []
    return part


# ------------------------------------------------------------------ the op ---

def test_a_blind_hole_removes_exactly_a_cylinder_where_it_was_clicked():
    b = box()
    out = healthy(sk.hole(b, **TOP, at=[5, 5], diameter=6, depth=8))
    dv, c = gone(b, out)
    assert dv == pytest.approx(PI * 9 * 8, rel=1e-6)
    assert c == pytest.approx([5, 5, 10 - 4], abs=1e-4)   # 8 deep from the top: centroid 4 below it


def test_through_ignores_the_depth_and_runs_out_the_far_side():
    b = box()
    out = healthy(sk.hole(b, **TOP, at=[5, 5], diameter=6, depth=1, through=True))
    dv, c = gone(b, out)
    assert dv == pytest.approx(PI * 9 * 20, rel=1e-6)
    assert c == pytest.approx([5, 5, 0], abs=1e-4)


def test_a_counterbore_adds_a_wider_seat_at_the_face():
    b = box()
    out = healthy(sk.hole(b, **TOP, at=[0, 0], diameter=6, depth=8, kind="counterbore",
                          cbore_diameter=10, cbore_depth=2))
    dv, _ = gone(b, out)
    assert dv == pytest.approx(PI * 9 * 8 + PI * (25 - 9) * 2, rel=1e-6)


def test_a_countersink_adds_a_cone_at_the_face():
    b = box()
    out = healthy(sk.hole(b, **TOP, at=[0, 0], diameter=6, depth=8, kind="countersink",
                          csink_diameter=12, csink_angle=90))
    h = (6 - 3) / math.tan(math.radians(45))               # 3 mm of cone
    frustum = PI * h / 3 * (36 + 18 + 9)
    dv, _ = gone(b, out)
    assert dv == pytest.approx(PI * 9 * 8 + frustum - PI * 9 * h, rel=1e-6)


def test_a_named_face_and_a_picked_face_are_the_same_hole():
    a = sk.hole(box(), **TOP, at=[5, 5], diameter=6, depth=8)
    n = sk.hole(box(), face="top", at=[5, 5], diameter=6, depth=8)
    assert a.volume == pytest.approx(n.volume, rel=1e-9)
    assert gone(box(), a)[1] == pytest.approx(gone(box(), n)[1], abs=1e-6)


def test_on_the_bottom_face_the_hole_goes_up_and_reads_the_same_x_y():
    """`at` on the bottom face is the sketch's x / y there (probe §6), and the
    hole runs INTO the material — upward."""
    b = box()
    out = healthy(sk.hole(b, face="bottom", at=[5, 7], diameter=6, depth=8))
    dv, c = gone(b, out)
    assert dv == pytest.approx(PI * 9 * 8, rel=1e-6)
    assert c == pytest.approx([5, 7, -10 + 4], abs=1e-4)


def test_a_tilted_face_drills_along_its_own_normal():
    w = BODIES["wedge"]()
    _idx, face, c, n = next(t for t in planar_faces(w) if abs(t[3][0] - 0.7071) < 1e-3)
    loc = sk.face_profile_plane(face).to_local_coords(b3d.Vector(*c))
    out = healthy(sk.hole(w, face_center=c, face_normal=n, at=[loc.X, loc.Y],
                          diameter=4, depth=5))
    dv, cc = gone(w, out)
    assert dv == pytest.approx(PI * 4 * 5, rel=1e-6)
    assert cc == pytest.approx([c[i] - n[i] * 2.5 for i in range(3)], abs=1e-4)


@pytest.mark.parametrize("kw, phrase", [
    (dict(diameter=0), "diameter must be positive"),
    (dict(depth=0), "depth must be positive"),
    (dict(kind="square"), "kind must be one of"),
    (dict(kind="counterbore", cbore_diameter=5, cbore_depth=2),
     "counterbore diameter (5 mm) must be larger than the hole diameter (6 mm)"),
    (dict(kind="counterbore", cbore_diameter=10, cbore_depth=0), "counterbore depth must be positive"),
    (dict(kind="counterbore", cbore_diameter=10, cbore_depth=9),
     "counterbore depth (9 mm) must be less than the hole depth (8 mm)"),
    (dict(kind="countersink", csink_diameter=5, csink_angle=90),
     "countersink diameter (5 mm) must be larger"),
    (dict(kind="countersink", csink_diameter=12, csink_angle=200), "countersink angle must be between"),
    (dict(kind="countersink", csink_diameter=30, csink_angle=90, depth=2),
     "is 12.00 mm deep and reaches past the hole's depth (2 mm)"),
    (dict(at=[40, 0]), "point (40, 0) is not on the face"),
    (dict(at="middle"), "`at` must be [x, y]"),
    # probe §3: a ⌀60 hole at (5, 5) is TANGENT to the 50 mm face's edge — the
    # kernel returns an open shell and calls it valid
    (dict(at=[5, 5], diameter=60), "leaves a broken solid"),
])
def test_refusals_are_sentences_in_the_holes_own_words(kw, phrase):
    args = dict(TOP, at=[0, 0], diameter=6, depth=8)
    args.update(kw)
    with pytest.raises(ValueError) as ei:
        sk.hole(box(), **args)
    msg = str(ei.value)
    assert msg.startswith("hole:") and phrase in msg, msg
    for leak in ("TopoDS", "NCollection", "Standard_", "BRep", "StdFail"):
        assert leak not in msg


def test_a_hole_centred_in_an_existing_hole_is_refused_before_it_cuts_nothing():
    """the annular face's centre is air (probe §3: the cutter there removes 0 mm³
    and the kernel calls it a success) — `is_inside` catches it first, with the
    sentence that names the fix; the nothing-was-cut check stays as the backstop"""
    p = BODIES["plate_with_hole"]()        # 60 x 60 x 10 with a ⌀20 bore: the top's centre is air
    with pytest.raises(ValueError, match="point \\(0, 0\\) is not on the face"):
        sk.hole(p, face="top", at=[0, 0], diameter=4, depth=5)
    out = healthy(sk.hole(p, face="top", at=[20, 0], diameter=4, depth=5))   # beside it: fine
    assert p.volume - out.volume == pytest.approx(PI * 4 * 5, rel=1e-6)


def test_a_cut_that_removes_nothing_is_refused(monkeypatch):
    """the backstop behind is_inside: should the kernel ever hand back the body
    unchanged, that is a refusal, not a silent no-op feature"""
    b = box()
    monkeypatch.setattr(sk, "hole_cutter", lambda *a, **k: b3d.Box(1, 1, 1).moved(b3d.Pos(200, 0, 0)))
    with pytest.raises(ValueError, match="nothing was cut"):
        sk.hole(b, **TOP, at=[5, 5], diameter=6, depth=8)


def test_a_curved_face_is_refused():
    c = BODIES["cylinder"]()
    side = next(f for f in c.faces() if f.geom_type == b3d.GeomType.CYLINDER)
    cc = side.center()
    with pytest.raises(ValueError, match="curved"):
        sk.hole(c, face_center=[cc.X, cc.Y, cc.Z], at=[0, 0], diameter=4, depth=5)


def test_the_hole_rides_an_upstream_change():
    """the point is stored in the face's frame and the face is re-resolved, so a
    taller plate keeps the hole 4 deep from its NEW top (the offset method)"""
    d = Document(name="ride")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
    d.add("h", "hole", {"face": "top", "at": [5, 5], "diameter": 6, "depth": 4}, ["b"])
    assert d.rebuild()
    dv0, c0 = gone(d._parts["b"], d._parts["h"])
    assert dv0 == pytest.approx(PI * 9 * 4, rel=1e-6)
    assert c0 == pytest.approx([5, 5, 6 - 2], abs=1e-4)
    d.edit("b", "thickness", 20)
    assert d.rebuild()
    dv1, c1 = gone(d._parts["b"], d._parts["h"])
    assert dv1 == pytest.approx(dv0, rel=1e-6)
    assert c1 == pytest.approx([5, 5, 10 - 2], abs=1e-4)      # 4 deep from the NEW top


def test_a_failed_hole_is_a_failed_feature_not_a_corrupt_body():
    d = Document(name="fail")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
    d.add("h", "hole", {"face": "top", "at": [50, 0], "diameter": 6, "depth": 4}, ["b"])
    assert d.rebuild() is False
    h = next(f for f in d.features if f.id == "h")
    assert h.status == "failed" and "not on the face" in h.problems[0]
    assert d._parts["b"].volume == pytest.approx(60 * 40 * 12)


def test_the_catalogue_knows_every_key_and_a_strict_add_refuses_a_stranger():
    names = [n for n, _ in op_params("hole")]
    assert names == ["face_center", "face_normal", "face", "at", "diameter", "depth",
                     "through", "kind", "cbore_diameter", "cbore_depth",
                     "csink_diameter", "csink_angle"]
    d = Document(name="strict")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
    with pytest.raises(ValueError):
        d.add("h", "hole", {"face": "top", "at": [0, 0], "radius": 3}, ["b"], strict=True)


# ---------------------------------------------------------------- the plan ---

def plate_doc():
    d = Document(name="plan")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
    d.rebuild()
    return d


TOP_PLATE = dict(face_center=[0, 0, 6], face_normal=[0, 0, 1])


def ok(plan):
    assert plan["ok"], plan
    json.dumps(plan)                       # must survive the API boundary
    return plan


def test_plan_places_the_hole_where_the_face_was_clicked():
    p = ok(toolplan.plan(plate_doc(), {"tool": "hole", "body_id": "b", **TOP_PLATE,
                                       "face_point": [5, 5, 6]}))
    assert p["op"] == "hole" and p["mode"] == "face"
    assert p["input"] == "b" and p["target_body"] == "b"
    assert p["origin"] == pytest.approx([5, 5, 6], abs=1e-6)
    assert p["axis"] == pytest.approx([0, 0, -1], abs=1e-6)          # INTO the material
    assert p["at"] == pytest.approx([5, 5], abs=1e-6)
    assert p["frame"]["origin"] == p["origin"]
    assert p["frame"]["z_dir"] == pytest.approx([0, 0, 1], abs=1e-6)
    assert p["limits"]["material"] == pytest.approx(12, abs=1e-6)
    assert p["face_center"] == pytest.approx([0, 0, 6], abs=1e-6)
    assert p["diameter"] is None


def test_plan_on_the_bottom_face_points_up_and_reads_the_sketch_x_y():
    p = ok(toolplan.plan(plate_doc(), {"tool": "hole", "body_id": "b",
                                       "face_center": [0, 0, -6], "face_normal": [0, 0, -1],
                                       "face_point": [5, 7, -6]}))
    assert p["axis"] == pytest.approx([0, 0, 1], abs=1e-6)
    assert p["at"] == pytest.approx([5, 7], abs=1e-6)
    assert p["origin"] == pytest.approx([5, 7, -6], abs=1e-6)


def test_plan_without_a_click_point_takes_the_face_centre():
    p = ok(toolplan.plan(plate_doc(), {"tool": "hole", "body_id": "b", **TOP_PLATE}))
    assert p["at"] == pytest.approx([0, 0], abs=1e-6)
    assert p["origin"] == pytest.approx([0, 0, 6], abs=1e-6)


def test_plan_in_edit_mode_reads_the_stored_point_and_face():
    d = plate_doc()
    d.add("h", "hole", {"face_center": [0, 0, 6], "face_normal": [0, 0, 1], "at": [5, 5],
                        "diameter": 6, "depth": 4}, ["b"])
    d.rebuild()
    p = ok(toolplan.plan(d, {"tool": "hole", "feature_id": "h"}))
    assert p["input"] == "b" and p["at"] == [5, 5] and p["diameter"] == 6
    assert p["origin"] == pytest.approx([5, 5, 6], abs=1e-6)
    # the diameter the tool sends (a box being typed) wins over the stored one
    p = ok(toolplan.plan(d, {"tool": "hole", "feature_id": "h", "diameter": 8}))
    assert p["diameter"] == 8


def test_plan_agrees_with_the_op():
    """the plan's `at` handed to the op cuts exactly where the plan's origin says"""
    d = plate_doc()
    p = ok(toolplan.plan(d, {"tool": "hole", "body_id": "b", **TOP_PLATE,
                             "face_point": [-10, 8, 6]}))
    b = d._parts["b"]
    out = sk.hole(b, face_center=p["face_center"], face_normal=p["face_normal"],
                  at=p["at"], diameter=6, depth=4)
    _, c = gone(b, out)
    assert c[:2] == pytest.approx(p["origin"][:2], abs=1e-4)
    assert c[2] == pytest.approx(p["origin"][2] - 2, abs=1e-4)


def test_plan_refuses_with_a_sentence_never_an_exception():
    d = plate_doc()
    p = toolplan.plan(d, {"tool": "hole", "body_id": "b", **TOP_PLATE, "face_point": [40, 0, 6]})
    assert p["ok"] is False and "not on the face" in p["error"]
    p = toolplan.plan(d, {"tool": "hole", "body_id": "b"})
    assert p["ok"] is False and "needs a flat face" in p["error"]
    d.add("c", "disc", {"radius": 20, "thickness": 30}, [])
    d.rebuild()
    side = next(f for f in d._parts["c"].faces() if f.geom_type == b3d.GeomType.CYLINDER)
    cc, nn = side.center(), side.normal_at(side.center())
    p = toolplan.plan(d, {"tool": "hole", "body_id": "c", "face_center": [cc.X, cc.Y, cc.Z],
                          "face_normal": [nn.X, nn.Y, nn.Z]})
    assert p["ok"] is False and "curved" in p["error"]
