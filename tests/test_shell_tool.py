"""Shell (LAUNCH-PLAN.md P4, specs/shell.md): Fusion's Shell as ONE op that eats
its body — walls of one thickness around a cavity, the picked faces removed —
and the planner that hands the tool its face set, its glow and its arrow.

probes/shell_probe.py (2026-09-10) found in the kernel:

    offset(openings=[faces])         -> exact volumes on every corpus body
    Kind.INTERSECTION                -> sharp corners (ARC rounds an outward shell's)
    offset() with NO opening         -> the offset SOLID, not a shell (a shrunk box)
    t = half the width, a face open  -> the body UNCHANGED, called a success
    t past the far wall              -> an OPEN SHELL, called a success
    a closed hollow at t >= half     -> RuntimeError; just under: a bare ValueError
    a curved face as the opening     -> RuntimeError

Every geometric claim below is checked against the kernel: volumes against
formulas, the arrow against the face's own normal.
"""
import json

import build123d as b3d
import pytest

import inspector
import sketch as sk
import toolplan
from document import Document, op_params


def box():
    return b3d.Box(50.0, 50.0, 30.0)       # centred on the origin: top at z = 15


TOP = {"center": [0, 0, 15], "normal": [0, 0, 1]}
PX = {"center": [25, 0, 0], "normal": [1, 0, 0]}


def healthy(part):
    assert inspector.health(part) == []
    return part


# ------------------------------------------------------------------ the op ---

def test_one_opening_leaves_walls_of_exactly_the_thickness():
    out = healthy(sk.shell(box(), 3, ["top"]))
    assert out.volume == pytest.approx(75000 - 44 * 44 * 27, rel=1e-6)
    # the outside stays where it was
    bb = out.bounding_box()
    assert [bb.min.X, bb.max.X, bb.min.Z, bb.max.Z] == pytest.approx([-25, 25, -15, 15], abs=1e-6)


def test_a_pick_names_the_same_face_as_its_name():
    assert sk.shell(box(), 3, [TOP]).volume == pytest.approx(sk.shell(box(), 3, ["top"]).volume)


def test_two_openings_and_a_side_opening():
    assert sk.shell(box(), 3, ["top", "+x"]).volume == pytest.approx(19164, rel=1e-6)
    assert sk.shell(box(), 3, ["+x"]).volume == pytest.approx(75000 - 47 * 44 * 24, rel=1e-6)
    assert sk.shell(box(), 3, ["top", "bottom"]).volume == pytest.approx(16920, rel=1e-6)


def test_two_picks_of_one_face_count_once():
    assert sk.shell(box(), 3, [TOP, "top"]).volume == pytest.approx(22728, rel=1e-6)


def test_no_opening_is_a_closed_hollow_not_a_shrunk_box():
    out = healthy(sk.shell(box(), 3))
    assert out.volume == pytest.approx(75000 - 44 * 44 * 24, rel=1e-6)   # walls, not the inner box
    assert len(out.shells()) == 2 and len(out.solids()) == 1
    assert sk.shell(box(), 3, []).volume == pytest.approx(out.volume)


def test_outside_adds_the_walls_around_the_body_with_sharp_corners():
    out = healthy(sk.shell(box(), 3, ["top"], direction="outside"))
    assert out.volume == pytest.approx(56 * 56 * 33 - 75000, rel=1e-6)   # INTERSECTION: 28488, ARC gave 27818.5
    bb = out.bounding_box()
    assert [bb.min.X, bb.max.X, bb.min.Z, bb.max.Z] == pytest.approx([-28, 28, -18, 15], abs=1e-6)
    closed = healthy(sk.shell(box(), 3, direction="outside"))
    assert closed.volume == pytest.approx(56 * 56 * 36 - 75000, rel=1e-6)


def test_the_legacy_open_face_grammar_still_builds():
    assert sk.shell(box(), 3, open_face="top").volume == pytest.approx(22728, rel=1e-6)
    assert sk.shell(box(), 3, open_face="none").volume == pytest.approx(28536, rel=1e-6)
    # a stored faces list beats it
    assert sk.shell(box(), 3, faces=[], open_face="top").volume == pytest.approx(28536, rel=1e-6)
    import blocks
    assert blocks.shell_out(box(), 3, open_face="bottom").volume == pytest.approx(22728, rel=1e-6)


@pytest.mark.parametrize("kwargs, words", [
    (dict(thickness=0, faces=["top"]), "thickness must be positive"),
    (dict(thickness=-2, faces=["top"]), "thickness must be positive"),
    (dict(thickness=3, faces=["top"], direction="both"), 'direction must be "inside" or "outside"'),
    (dict(thickness=3, open_face="left"), "open_face must be"),
    (dict(thickness=3, faces=[7]), "an opening is a face name"),
    (dict(thickness=3, faces=7), "faces must be a list of openings"),   # not iterable at all
    (dict(thickness=3, faces=True), "faces must be a list of openings"),
    (dict(thickness=3, faces=["north"]), "not a direction"),
    (dict(thickness=25, faces=["top"]), "nothing was hollowed"),        # the UNCHANGED body
    (dict(thickness=40, faces=["top"]), "leave a broken solid"),         # the open shell
    (dict(thickness=25), "do not fit this body"),                       # RuntimeError translated
    (dict(thickness=24.9), "do not fit this body"),                     # the bare ValueError translated
])
def test_every_refusal_is_a_sentence_in_the_shells_own_words(kwargs, words):
    with pytest.raises(ValueError, match=words) as e:
        sk.shell(box(), **kwargs)
    for leak in ("TopoDS", "Standard_", "BRep", "offset Error"):
        assert leak not in str(e.value)


def lumps3():
    """three separate 20 x 20 x 10 boxes as ONE body — what a linear_pattern of
    a boss hands the tree, and what a cut that severs a plate leaves behind"""
    import pattern
    return pattern.linear_pattern(b3d.Box(20.0, 20.0, 10.0), count=3, dx=40.0)


def test_a_lump_with_no_opening_is_refused_not_left_a_solid_block():
    """Measured in the review of fb0b8c8: `offset(openings=[…])` shells only the
    lumps a listed face belongs to and returns the raw offset SOLID for the
    rest — [1952, 1536, 1536] inside (2464 is a closed shell) and
    [2912, 8064, 8064] outside (blocks GROWN by 2 mm), every one of them
    watertight, healthy and green. A failed feature beats a corrupt body."""
    body = lumps3()
    assert len(body.solids()) == 3
    for direction in ("inside", "outside"):
        with pytest.raises(ValueError, match="3 separate lumps and 2 of them have no face open"):
            sk.shell(body, 2, ["top"], direction)


def test_every_lump_open_and_no_lump_open_both_still_build_exactly():
    body = lumps3()
    tops = [f for f in body.faces()
            if abs(f.center().Z - 5) < 1e-6 and sk.face_plane(f) is not None]
    assert len(tops) == 3
    refs = [{"center": list(f.center()), "normal": [0, 0, 1]} for f in tops]
    # an opening on EVERY lump: the kernel is exact — 20*20*10 - 16*16*8 each
    out = healthy(sk.shell(body, 2, refs))
    assert [round(s.volume, 2) for s in out.solids()] == [pytest.approx(1952, rel=1e-6)] * 3
    # no opening at all: the difference route is exact per lump, both directions
    assert [round(s.volume, 2) for s in sk.shell(body, 2).solids()] \
        == [pytest.approx(4000 - 16 * 16 * 6, rel=1e-6)] * 3
    assert [round(s.volume, 2) for s in sk.shell(body, 2, direction="outside").solids()] \
        == [pytest.approx(24 * 24 * 14 - 4000, rel=1e-6)] * 3


def test_a_curved_opening_is_refused_with_its_type():
    cyl = b3d.Cylinder(25, 40)
    wall = next(f for f in cyl.faces() if f.geom_type.name == "CYLINDER")
    c = wall.center()
    with pytest.raises(ValueError, match="FLAT face — that face is CYLINDER"):
        sk.shell(cyl, 2, [{"center": [c.X, c.Y, c.Z], "normal": None}])
    # its caps are fine
    assert healthy(sk.shell(cyl, 2, ["top"])).volume > 0


def test_the_catalogue_knows_every_key_and_a_strict_add_refuses_a_stranger():
    assert [n for n, _ in op_params("shell")] == ["thickness", "faces", "direction", "open_face"]
    d = Document(name="strict")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
    with pytest.raises(ValueError):
        d.add("s", "shell", {"thickness": 3, "openings": ["top"]}, ["b"], strict=True)


# ------------------------------------------------------------- the document ---

def plate_doc():
    d = Document(name="plan")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
    d.rebuild()
    return d


PTOP = dict(face_center=[0, 0, 6], face_normal=[0, 0, 1])
PLATE_TOP_OPEN = 28800 - 54 * 34 * 9          # 12276


def last(d):
    return d.features[-1]


def test_a_shell_feature_builds_eats_its_body_and_rides_an_upstream_change():
    d = plate_doc()
    d.add("s", "shell", {"thickness": 3, "faces": ["top"]}, ["b"])
    d.rebuild()
    assert last(d).status == "ok"
    assert last(d).volume == pytest.approx(PLATE_TOP_OPEN, rel=1e-6)
    d.edit_many("b", {"thickness": 20})
    d.rebuild()
    assert last(d).volume == pytest.approx(60 * 40 * 20 - 54 * 34 * 17, rel=1e-6)


def test_a_failing_shell_is_a_red_row_with_a_sentence_not_a_missing_body():
    d = plate_doc()
    d.add("s", "shell", {"thickness": 30, "faces": ["top"]}, ["b"])
    d.rebuild()
    f = last(d)
    assert f.status == "failed" and f.problems
    assert "shell:" in f.problems[0] and "Standard_" not in f.problems[0]


# ----------------------------------------------------------------- the plan ---

def ok(plan):
    assert plan["ok"], plan
    json.dumps(plan)                       # must survive the API boundary
    return plan


def test_the_opening_click_is_the_first_face_and_the_arrow_points_into_the_material():
    p = ok(toolplan.plan(plate_doc(), {"tool": "shell", "body_id": "b", **PTOP}))
    assert p["op"] == "shell" and p["mode"] == "face" and p["input"] == "b" == p["target_body"]
    assert p["n_open"] == 1 and len(p["faces"]) == 1
    assert p["faces"][0]["center"] == pytest.approx([0, 0, 6], abs=1e-6)
    assert p["faces"][0]["normal"] == pytest.approx([0, 0, 1], abs=1e-6)
    assert p["origin"] == pytest.approx([0, 0, 6], abs=1e-6)
    assert p["axis"] == pytest.approx([0, 0, -1], abs=1e-6)          # INTO the material
    assert len(p["edges"]) == 4 and all(len(e["points"]) >= 2 for e in p["edges"])
    assert p["direction"] == "inside"
    assert p["seed_words"] == "1 face open of b"
    assert "open now" in p["click_words"]


def test_a_second_click_on_an_open_face_closes_it_and_the_words_say_so():
    d = plate_doc()
    p = ok(toolplan.plan(d, {"tool": "shell", "body_id": "b", **PTOP}))
    q = ok(toolplan.plan(d, {"tool": "shell", "body_id": "b", **PTOP, "faces": p["faces"],
                             "face_toggle": {"center": [0, 0, 6], "normal": [0, 0, 1]}}))
    assert q["n_open"] == 0 and q["faces"] == [] and q["edges"] == []
    assert q["seed_words"] == "no face open — a closed hollow body"
    assert "closed again" in q["click_words"]
    # the arrow moves to the largest flat face and still points inward
    assert abs(q["origin"][2]) == pytest.approx(6, abs=1e-6)
    assert q["axis"][2] * q["origin"][2] < 0


def test_a_click_on_another_face_opens_it_too():
    d = plate_doc()
    p = ok(toolplan.plan(d, {"tool": "shell", "body_id": "b", **PTOP}))
    q = ok(toolplan.plan(d, {"tool": "shell", "body_id": "b", **PTOP, "faces": p["faces"],
                             "face_toggle": {"center": [30, 0, 0], "normal": [1, 0, 0]}}))
    assert q["n_open"] == 2 and len(q["edges"]) == 8
    assert q["seed_words"] == "2 faces open of b"
    assert q["origin"] == pytest.approx([0, 0, 6], abs=1e-6)         # the FIRST opening keeps the arrow


def test_outside_flips_the_arrow_and_an_unknown_direction_is_refused():
    d = plate_doc()
    p = ok(toolplan.plan(d, {"tool": "shell", "body_id": "b", **PTOP, "direction": "outside"}))
    assert p["axis"] == pytest.approx([0, 0, 1], abs=1e-6) and p["direction"] == "outside"
    r = toolplan.plan(d, {"tool": "shell", "body_id": "b", **PTOP, "direction": "both"})
    assert not r["ok"] and "inside" in r["error"]


def test_a_faces_list_is_the_selection_even_when_empty():
    p = ok(toolplan.plan(plate_doc(), {"tool": "shell", "body_id": "b", **PTOP, "faces": []}))
    assert p["n_open"] == 0


def test_edit_reads_the_stored_set_names_stay_names_and_legacy_rows_open():
    d = plate_doc()
    d.add("s", "shell", {"thickness": 3, "faces": ["top"], "direction": "outside"}, ["b"])
    d.add("legacy", "shell", {"thickness": 3, "open_face": "bottom"}, ["b"])
    d.rebuild()
    p = ok(toolplan.plan(d, {"tool": "shell", "feature_id": "s"}))
    assert p["faces"] == ["top"] and p["n_open"] == 1 and p["direction"] == "outside"
    assert p["origin"] == pytest.approx([0, 0, 6], abs=1e-6)
    assert p["axis"] == pytest.approx([0, 0, 1], abs=1e-6)             # outside: OUT of the material
    q = ok(toolplan.plan(d, {"tool": "shell", "feature_id": "legacy"}))
    assert q["faces"] == ["bottom"] and q["n_open"] == 1
    assert q["origin"] == pytest.approx([0, 0, -6], abs=1e-6)
    # a click during the edit toggles against the stored set
    r = ok(toolplan.plan(d, {"tool": "shell", "feature_id": "s",
                             "face_toggle": {"center": [0, 0, 6], "normal": [0, 0, 1]}}))
    assert r["n_open"] == 0


def test_the_plan_agrees_with_the_op():
    d = plate_doc()
    p = ok(toolplan.plan(d, {"tool": "shell", "body_id": "b", **PTOP}))
    d.add("s", "shell", {"thickness": 3, "faces": p["faces"], "direction": p["direction"]}, ["b"])
    d.rebuild()
    assert last(d).status == "ok" and last(d).volume == pytest.approx(PLATE_TOP_OPEN, rel=1e-6)


def test_plan_refuses_with_a_sentence_never_an_exception():
    d = plate_doc()
    # an id that names nothing falls through to the newest solid (_pick_body's
    # rule for every face-mode plan: a pick before any body was named)
    r = toolplan.plan(d, {"tool": "shell", "body_id": "nope", **PTOP})
    assert r["ok"] and r["input"] == "b"
    # a face the body does not have (a preview's own face, a wrong body)
    r = toolplan.plan(d, {"tool": "shell", "body_id": "b",
                          "face_toggle": {"center": [0, 0, 40], "normal": [0, 0, 1]}})
    assert not r["ok"] and "not on b" in r["error"]
    c = Document(name="c")
    c.add("c", "disc", {"radius": 25, "thickness": 40}, [])
    c.rebuild()
    # a click on the cylinder's WALL: a curved face is never on the body's
    # picked-face terms (its centre is off its surface) — a sentence either way
    r = toolplan.plan(c, {"tool": "shell", "body_id": "c",
                          "face_toggle": {"center": [25, 0, 0], "normal": [1, 0, 0]}})
    assert not r["ok"] and r["error"] and "Standard_" not in r["error"]
    e = Document(name="empty")
    r = toolplan.plan(e, {"tool": "shell", "body_id": None})
    assert not r["ok"] and "build a body first" in r["error"]
