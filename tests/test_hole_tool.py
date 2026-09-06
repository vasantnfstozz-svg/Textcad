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


def test_a_small_hole_in_a_BIG_part_is_cut_not_refused():
    """"nothing was cut" used to be measured against a millionth of the WHOLE
    part, so a real ⌀1 hole in a 200 x 100 x 50 block "found no material"
    (probes/hole_review_probe.py §2). A cutter that truly misses leaves the
    volume unchanged to the last bit — the floor is absolute."""
    big = b3d.Box(200, 100, 50)
    for dia, dep in ((1.0, 1.0), (0.5, 0.5)):
        out = healthy(sk.hole(big, face="top", at=[10, 10], diameter=dia, depth=dep))
        assert big.volume - out.volume == pytest.approx(PI * (dia / 2) ** 2 * dep, rel=1e-6)


def test_a_through_hole_may_have_a_seat_and_the_reach_is_the_shared_one():
    """A through hole has no depth for the seat to sit inside, so the two
    "shallower than the hole" comparisons do not apply to it — they used to run
    against the bounding-box span and could print "less than 112.4 mm". The
    reach itself is sketch.THROUGH_MM, the one every through cut uses."""
    b = box()
    out = healthy(sk.hole(b, **TOP, at=[5, 5], diameter=6, depth=1, through=True,
                          kind="counterbore", cbore_diameter=10, cbore_depth=2))
    assert b.volume - out.volume == pytest.approx(PI * 9 * 20 + PI * (25 - 9) * 2, rel=1e-6)
    assert sk.THROUGH_MM == 2000.0            # the same reach extrude_sketch uses


def test_at_None_is_the_ops_own_default_not_the_face_centre():
    """`at=None` reaches the op from an AI-authored `"at": null` and from the
    tool's own params before a plan has landed. It must mean the documented
    default (0, 0) — the value the PLAN also falls back to — and never the face
    centre, or the marker and the cut disagree again on an off-origin body."""
    body = b3d.Pos(20, 10, 0) * b3d.Box(60, 40, 12)        # face centre at (20, 10)
    for at in (None, [0, 0], sk.HOLE_AT):
        out = healthy(sk.hole(body, face="top", at=at, diameter=6, depth=4))
        assert gone(body, out)[1][:2] == pytest.approx([0, 0], abs=1e-4), at
    with pytest.raises(ValueError, match="`at` must be"):   # junk still speaks
        sk.hole(body, face="top", at="middle", diameter=6, depth=4)


def test_through_reaches_past_a_body_deeper_than_the_constant():
    """THROUGH_MM is the shared reach, not a ceiling: a body deeper than 2 m
    measured from the face must still be drilled THROUGH, not quietly left with
    a blind hole (the bounding-box span the op used before had no ceiling)."""
    tall = b3d.Box(50, 50, 2400)
    assert sk.through_reach(tall) > sk.THROUGH_MM
    out = healthy(sk.hole(tall, face="top", at=[0, 0], diameter=6, depth=1, through=True))
    assert tall.volume - out.volume == pytest.approx(PI * 9 * 2400, rel=1e-6)
    assert sk.through_reach(b3d.Box(10, 10, 10)) == sk.THROUGH_MM   # small bodies: the constant


def test_the_seat_numbers_are_judged_before_the_face_is_resolved():
    """A half-typed seat ⌀ is a certain refusal; resolving a face on a big body
    costs ~400 ms. The seat sentence must come back even when the face itself
    could never be found."""
    with pytest.raises(ValueError, match="counterbore diameter"):
        sk.hole(box(), face="nowhere", at=[0, 0], diameter=6, depth=8,
                kind="counterbore", cbore_diameter=5, cbore_depth=2)


def test_a_kernel_error_while_BUILDING_the_cutter_is_still_a_sentence(monkeypatch):
    """rule 5 by construction, not by luck: the cutter was built one line ABOVE
    the try that guards the cut, so a kernel exception raised there would have
    reached the user as document.py's repr(e) — the class name and all."""
    def boom(*a, **k):
        raise Exception("Standard_ConstructionError: BRepPrim_Cylinder")
    monkeypatch.setattr(sk, "hole_cutter", boom)
    with pytest.raises(ValueError) as ei:
        sk.hole(box(), **TOP, at=[5, 5], diameter=6, depth=8)
    msg = str(ei.value)
    assert msg.startswith("hole: the kernel could not cut"), msg
    assert "Standard_" not in msg and "BRepPrim" not in msg


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
    assert p["face_center"] == pytest.approx([0, 0, 6], abs=1e-6)
    assert p["face"] is None                    # a PICK: the geometry, not a name
    # the material under the point costs a kernel boolean — only when asked
    assert p["limits"] == {}
    m = ok(toolplan.plan(plate_doc(), {"tool": "hole", "body_id": "b", **TOP_PLATE,
                                       "face_point": [5, 5, 6], "measure_material": True}))
    assert m["limits"]["material"] == pytest.approx(12, abs=1e-6)


def test_the_plan_carries_no_field_nobody_reads():
    """R1 the other way round: every key the browser is handed must be one it
    uses. `diameter`, `normal`, `into_sign` and `limits.through_span` were
    echoes nothing read — dead wiring the next reader would build on."""
    p = ok(toolplan.plan(plate_doc(), {"tool": "hole", "body_id": "b", **TOP_PLATE,
                                       "face_point": [5, 5, 6]}))
    for dead in ("diameter", "normal", "into_sign"):
        assert dead not in p, dead
    assert "through_span" not in p["limits"]


def test_the_marker_frame_is_right_handed_on_every_face():
    """three.js's Matrix4.makeBasis wants a right-handed basis. The frame took
    x/y from the face's plane and z from its OUTWARD normal, which is the
    opposite side on half of a box's faces — a mirrored marker waiting for the
    first non-symmetric handle (probes/hole_review_probe.py §4)."""
    d = Document(name="hand")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
    d.rebuild()
    for c, n in (([0, 0, 6], [0, 0, 1]), ([0, 0, -6], [0, 0, -1]),
                 ([30, 0, 0], [1, 0, 0]), ([-30, 0, 0], [-1, 0, 0]),
                 ([0, 20, 0], [0, 1, 0]), ([0, -20, 0], [0, -1, 0])):
        p = ok(toolplan.plan(d, {"tool": "hole", "body_id": "b", "face_center": c,
                                 "face_normal": n}))
        f = p["frame"]
        x, y, z = (b3d.Vector(*f[k]) for k in ("x_dir", "y_dir", "z_dir"))
        assert x.cross(y).dot(z) == pytest.approx(1.0, abs=1e-6), (c, f)
        # the drilling direction is its own field, and it still points IN
        assert b3d.Vector(*p["axis"]).dot(b3d.Vector(*n)) < 0


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
    assert p["input"] == "b" and p["at"] == [5, 5]
    assert p["origin"] == pytest.approx([5, 5, 6], abs=1e-6)


def test_a_click_while_editing_MOVES_the_hole():
    """The tool arms its face pick in edit mode too and the hint says "click a
    flat face to move the hole" — but the plan overwrote the request with the
    stored point, so the marker snapped back and nothing was said. The request
    is the answer; what it does not carry is what the feature stored."""
    d = plate_doc()
    d.add("h", "hole", {"face_center": [0, 0, 6], "face_normal": [0, 0, 1], "at": [5, 5],
                        "diameter": 6, "depth": 4}, ["b"])
    d.rebuild()
    moved = ok(toolplan.plan(d, {"tool": "hole", "feature_id": "h", "body_id": "b",
                                 **TOP_PLATE, "face_point": [-20, -10, 6]}))
    assert moved["at"] == pytest.approx([-20, -10], abs=1e-6)
    assert moved["origin"] == pytest.approx([-20, -10, 6], abs=1e-6)
    # onto ANOTHER face: the axis follows it, and the stored point is not reused
    other = ok(toolplan.plan(d, {"tool": "hole", "feature_id": "h", "body_id": "b",
                                 "face_center": [0, 0, -6], "face_normal": [0, 0, -1],
                                 "face_point": [8, 3, -6]}))
    assert other["at"] == pytest.approx([8, 3], abs=1e-6)
    assert other["axis"] == pytest.approx([0, 0, 1], abs=1e-6)


def test_the_face_comes_back_in_ONE_stored_form():
    """`face` (a name) beats `face_center` in the op, so a hole authored with
    face="top" could never be moved: the tool sent a new centre and the name
    outlived it. The plan hands back exactly one form — and a click clears the
    name it replaces."""
    d = plate_doc()
    d.add("h", "hole", {"face": "top", "at": [5, 5], "diameter": 6, "depth": 4}, ["b"])
    d.rebuild()
    p = ok(toolplan.plan(d, {"tool": "hole", "feature_id": "h"}))
    assert p["face"] == "top" and p["face_center"] is None and p["face_normal"] is None
    moved = ok(toolplan.plan(d, {"tool": "hole", "feature_id": "h", "body_id": "b",
                                 "face_center": [30, 0, 0], "face_normal": [1, 0, 0],
                                 "face_point": [30, 4, 2]}))
    assert moved["face"] is None and moved["face_center"] == pytest.approx([30, 0, 0], abs=1e-6)
    # and the op cuts where the plan says, with exactly those params
    out = sk.hole(d._parts["b"], face=moved["face"], face_center=moved["face_center"],
                  face_normal=moved["face_normal"], at=moved["at"], diameter=6, depth=4)
    _, c = gone(d._parts["b"], out)
    assert c == pytest.approx([30 - 2, 4, 2], abs=1e-4)


def test_a_feature_with_no_at_opens_where_it_actually_cuts():
    """The op's default `at` is (0, 0) — the frame's origin. The plan defaulted
    to the FACE CENTRE, so an AI-authored hole without an `at` drew its marker
    somewhere else and pressing OK (which always re-applies) MOVED the cut."""
    d = Document(name="noat")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
    d.add("m", "move", {"x": 20}, ["b"])                   # the face centre is now (20, 0, 6)
    d.add("h", "hole", {"face": "top", "diameter": 6, "depth": 4}, ["m"])
    assert d.rebuild(), [f.problems for f in d.features]
    _dv, cut = gone(d._parts["m"], d._parts["h"])          # where the op really cut
    assert cut[:2] == pytest.approx([0, 0], abs=1e-4)      # not the face centre
    p = ok(toolplan.plan(d, {"tool": "hole", "feature_id": "h"}))
    assert p["origin"][:2] == pytest.approx(cut[:2], abs=1e-4)
    assert p["at"] == pytest.approx(list(sk.HOLE_AT), abs=1e-6)


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
