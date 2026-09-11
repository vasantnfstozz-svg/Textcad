"""Move and Rotate (LAUNCH-PLAN.md P4, specs/move-rotate.md): the two ops that
place a body — `move` by relative offsets, `rotate` about a world axis through
a PIVOT — and the planners that hand the tools their handles.

probes/move_rotate_probe.py (2026-09-11) found in the kernel:

    Part.rotate(Axis(pivot, dir), deg)   -> turns about THAT pivot
    the sign is the right-hand rule      -> +90 about Z takes +X to +Y
    bounding_box().center()              -> exact on box / cylinder / sphere
    a pivoted turn                       -> same centre, volume and health

Every geometric claim below is measured on the kernel's result: bounding-box
centres, volumes, and the ring frame against what `rotate` actually does.
"""
import json
import math

import build123d as b3d
import pytest

import author
import blocks
import inspector
import toolplan
from document import Document, op_params


def plate_at(x=0.0, y=0.0, z=0.0):
    return b3d.Pos(x, y, z) * b3d.Box(60.0, 40.0, 12.0)


def centre(part):
    c = part.bounding_box().center()
    return [c.X, c.Y, c.Z]


def size(part):
    s = part.bounding_box().size
    return [s.X, s.Y, s.Z]


def healthy(part):
    assert inspector.health(part) == []
    return part


def build(*feats):
    d = Document(name="t")
    for fid, op, params, inputs in feats:
        d.add(fid, op, params, inputs)
    d.rebuild()
    return d


def ok(plan):
    assert plan["ok"], plan
    json.dumps(plan)                        # must survive the API boundary
    return plan


# ------------------------------------------------------------- the rotate op --

@pytest.mark.parametrize("axis", ["X", "Y", "Z"])
def test_rotate_about_the_centre_keeps_the_centre_the_volume_and_the_health(axis):
    body = plate_at(100, 20, -5)
    out = healthy(blocks.rotate(body, axis, 37.0, pivot="center"))
    assert centre(out) == pytest.approx(centre(body), abs=1e-6)
    assert out.volume == pytest.approx(body.volume, rel=1e-9)


def test_rotate_in_place_by_90_about_z_swaps_the_footprint():
    out = blocks.rotate(plate_at(100, 0, 0), "Z", 90, pivot="center")
    assert size(out) == pytest.approx([40, 60, 12], abs=1e-6)
    assert centre(out) == pytest.approx([100, 0, 0], abs=1e-6)


def test_the_legacy_default_is_unchanged_the_world_origin():
    """every design saved before the pivot existed turns about the WORLD
    origin (probes/boolean_review_probe.py §1) — absent and "origin" both"""
    body = plate_at(100, 0, 0)
    for pivot in ({}, {"pivot": None}, {"pivot": "origin"}):
        out = blocks.rotate(body, "Z", 90.0, **pivot)
        assert centre(out) == pytest.approx([0, 100, 0], abs=1e-6), pivot
        assert size(out) == pytest.approx([40, 60, 12], abs=1e-6)


def test_an_explicit_pivot_point():
    # a point at +X turned +90 about Z through (100, 0, 0): it stays put
    dot = b3d.Pos(100, 0, 0) * b3d.Box(2, 2, 2)
    assert centre(blocks.rotate(dot, "Z", 90, pivot=[100, 0, 0])) == pytest.approx([100, 0, 0], abs=1e-6)
    # ...and through the origin it swings to +Y
    assert centre(blocks.rotate(dot, "Z", 90, pivot=[0, 0, 0])) == pytest.approx([0, 100, 0], abs=1e-6)


@pytest.mark.parametrize("axis, start, end", [
    ("Z", [100, 0, 0], [0, 100, 0]),
    ("X", [0, 100, 0], [0, 0, 100]),
    ("Y", [0, 0, 100], [100, 0, 0]),
])
def test_the_sign_is_the_right_hand_rule_on_every_axis(axis, start, end):
    dot = b3d.Pos(*start) * b3d.Box(2, 2, 2)
    assert centre(blocks.rotate(dot, axis, 90, pivot="origin")) == pytest.approx(end, abs=1e-6)


@pytest.mark.parametrize("kw, words", [
    ({"axis": "W"}, 'axis must be "X", "Y" or "Z" (got \'W\')'),
    ({"pivot": "middle"}, 'pivot must be "center", "origin" or [x, y, z] (got \'middle\')'),
    ({"pivot": [1, 2]}, "pivot must be"),
    ({"pivot": [1, "a", 3]}, "pivot must be"),
    ({"angle_deg": "lots"}, "angle_deg must be a number in degrees (got 'lots')"),
    ({"angle_deg": float("nan")}, "angle_deg must be a number"),
])
def test_every_refusal_is_a_sentence(kw, words):
    args = {"axis": "Z", "angle_deg": 10.0, **kw}
    with pytest.raises(ValueError, match=r"^rotate: ") as e:
        blocks.rotate(plate_at(), **args)
    assert words in str(e.value)


def test_the_catalogue_shows_the_pivot_and_its_note():
    assert op_params("rotate") == (("axis", "Z"), ("angle_deg", 90.0), ("pivot", None))
    entry = next(e for e in author.op_catalog() if e["op"] == "rotate")
    assert [p["name"] for p in entry["params"]] == ["axis", "angle_deg", "pivot"]
    assert '"center"' in entry["note"] and "WORLD ORIGIN" in entry["note"]


def test_body_centre_is_the_bounding_box_centre():
    assert blocks.body_centre(plate_at(7, -3, 2)) == pytest.approx([7, -3, 2], abs=1e-6)
    cyl = b3d.Pos(30, 0, 0) * b3d.Cylinder(10, 20)
    assert blocks.body_centre(cyl) == pytest.approx([30, 0, 0], abs=1e-6)


# --------------------------------------------------------- in the document --

def test_the_document_builds_a_move_then_a_rotate_in_place():
    d = build(("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, []),
              ("m", "move", {"x": 20, "y": 0, "z": 5}, ["b"]),
              ("r", "rotate", {"axis": "Z", "angle_deg": 90, "pivot": "center"}, ["m"]))
    assert [f.status for f in d.features] == ["ok", "ok", "ok"]
    assert centre(d._parts["m"]) == pytest.approx([20, 0, 5], abs=1e-6)
    assert centre(d._parts["r"]) == pytest.approx([20, 0, 5], abs=1e-6)
    assert size(d._parts["r"]) == pytest.approx([40, 60, 12], abs=1e-6)
    assert d._parts["r"].volume == pytest.approx(28800)


def test_an_edit_of_the_move_rides_downstream():
    d = build(("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, []),
              ("m", "move", {"x": 20}, ["b"]),
              ("r", "rotate", {"axis": "Z", "angle_deg": 90, "pivot": "center"}, ["m"]))
    d.edit_many("m", {"x": -10, "y": 4, "z": 0})
    d.rebuild()
    assert centre(d._parts["r"]) == pytest.approx([-10, 4, 0], abs=1e-6)


def test_a_bad_move_offset_is_a_sentence_not_python_wording():
    d = build(("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, []),
              ("m", "move", {"x": "abc"}, ["b"]))
    f = next(x for x in d.features if x.id == "m")
    assert f.status == "failed"
    assert f.problems == ["move: x must be a number in mm (got 'abc')"]
    d.edit_many("m", {"x": 1, "y": float("inf"), "z": 0})
    d.rebuild()
    assert next(x for x in d.features if x.id == "m").problems == ["move: y must be a number in mm (got inf)"]


def test_a_move_is_a_placement_a_whole_body_seed():
    d = build(("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, []),
              ("m", "move", {"x": 20}, ["b"]))
    assert d.delta_features("m") == (None, "m")
    assert "move" in Document.PLACEMENT


# ------------------------------------------------------------------ the plans --

PLATE = ("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
MOVED = ("m", "move", {"x": 20, "y": 0, "z": 5}, ["b"])


def test_move_plan_puts_the_arrows_at_the_bodys_centre_along_the_world_axes():
    d = build(PLATE, MOVED)
    p = ok(toolplan.plan(d, {"tool": "move", "body_id": "m",
                             "face_center": [50, 0, 11], "face_normal": [0, 0, 1]}))
    assert p["op"] == "move" and p["input"] == "m" and p["target_body"] == "m"
    assert p["origin"] == pytest.approx(centre(d._parts["m"]), abs=1e-6)
    assert p["axes"] == {"x": [1, 0, 0], "y": [0, 1, 0], "z": [0, 0, 1]}
    assert p["size"] == pytest.approx([60, 40, 12])
    assert p["seed_words"] == "m (60 × 40 × 12 mm)"
    assert p["params"] == {}                # a new move: nothing stored yet


def test_move_plan_for_an_edit_reads_the_stored_offsets_on_the_input_body():
    d = build(PLATE, MOVED)
    p = ok(toolplan.plan(d, {"tool": "move", "feature_id": "m"}))
    assert p["input"] == "b"
    assert p["origin"] == pytest.approx([0, 0, 0], abs=1e-6)     # the body BEFORE the move
    assert p["params"] == {"x": 20.0, "y": 0.0, "z": 5.0}


def test_rotate_plan_ring_sits_at_the_centre_and_is_right_handed_about_each_axis():
    """the ring's positive turn IS the kernel's: a point on the ring's x_dir,
    turned +90 by the op, lands on its y_dir"""
    d = build(PLATE, MOVED)
    body = d._parts["m"]
    for axis in ("X", "Y", "Z"):
        p = ok(toolplan.plan(d, {"tool": "rotate", "body_id": "m", "axis": axis.lower()}))
        assert p["axis"] == axis and p["pivot"] == "center"
        assert p["origin"] == pytest.approx(centre(body), abs=1e-6)
        fr = p["frame"]
        assert fr["origin"] == p["origin"] and fr["z_dir"] == p["axis_dir"]
        x, y, z = (fr[k] for k in ("x_dir", "y_dir", "z_dir"))
        # right-handed: x × y = z
        cross = [x[1] * y[2] - x[2] * y[1], x[2] * y[0] - x[0] * y[2], x[0] * y[1] - x[1] * y[0]]
        assert cross == pytest.approx(z)
        # ...and agrees with the op: a dot on the ring's +x, turned +90, is on its +y
        o = p["origin"]
        dot = b3d.Pos(*(o[i] + 50 * x[i] for i in range(3))) * b3d.Box(2, 2, 2)
        turned = blocks.rotate(dot, axis, 90, pivot=o)
        assert centre(turned) == pytest.approx([o[i] + 50 * y[i] for i in range(3)], abs=1e-6)
        # the ring clears the body in its plane; the axis line spans it
        k = "XYZ".index(axis)
        across = [s for i, s in enumerate(p["size"]) if i != k]
        assert p["radius"] == pytest.approx(max(max(across) / 2 * 1.15, 8))
        assert p["axis_half"] == pytest.approx(max(p["size"]) * 0.8)


def test_rotate_plan_defaults_to_z_and_a_changed_axis_reframes():
    d = build(PLATE)
    p = ok(toolplan.plan(d, {"tool": "rotate", "body_id": "b"}))
    assert p["axis"] == "Z" and p["frame"]["z_dir"] == [0, 0, 1]
    q = ok(toolplan.plan(d, {"tool": "rotate", "body_id": "b", "axis": "X"}))
    assert q["frame"]["z_dir"] == [1, 0, 0] and q["radius"] != p["radius"]


def test_rotate_plan_for_an_edit_reads_the_stored_axis_angle_and_pivot():
    d = build(PLATE, MOVED, ("r", "rotate", {"axis": "Y", "angle_deg": 30}, ["m"]))   # legacy: no pivot
    p = ok(toolplan.plan(d, {"tool": "rotate", "feature_id": "r"}))
    assert p["input"] == "m" and p["axis"] == "Y"
    assert p["pivot"] is None and p["origin"] == [0, 0, 0]      # honest: it turns about the world origin
    assert p["params"] == {"axis": "Y", "angle_deg": 30.0, "pivot": None}
    # the panel's Axis box beats the stored one (the ring lies down at once)
    q = ok(toolplan.plan(d, {"tool": "rotate", "feature_id": "r", "axis": "Z"}))
    assert q["axis"] == "Z"
    # a stored "center" pivot puts the ring on the body
    d.edit_many("r", {"axis": "Y", "angle_deg": 30, "pivot": "center"})
    d.rebuild()
    r = ok(toolplan.plan(d, {"tool": "rotate", "feature_id": "r"}))
    assert r["origin"] == pytest.approx([20, 0, 5], abs=1e-6)


def test_the_plans_refuse_with_a_sentence_never_an_exception():
    empty = Document(name="e")
    empty.rebuild()
    for tool in ("move", "rotate"):
        p = toolplan.plan(empty, {"tool": tool})
        assert p == {"ok": False, "tool": tool, "error": f"no solid to {tool} — build a body first"}
    d = build(PLATE)
    p = toolplan.plan(d, {"tool": "rotate", "body_id": "b", "axis": "W"})
    assert p["ok"] is False and p["error"] == 'axis must be "X", "Y" or "Z" (got \'W\')'
    p = toolplan.plan(d, {"tool": "move", "feature_id": "b"})
    assert p["ok"] is False and p["error"] == "'b' is a plate, not move"
    # an id that names nothing falls through to the newest solid (_pick_body's
    # rule for a pick made before any body was named); a NAMED body that has not
    # built is the sentence
    p = ok(toolplan.plan(d, {"tool": "move", "body_id": "nope"}))
    assert p["input"] == "b"
    d.add("m", "move", {"x": "abc"}, ["b"])
    d.rebuild()
    p = toolplan.plan(d, {"tool": "rotate", "body_id": "m"})
    assert p["ok"] is False and p["error"] == "'m' has not built — fix that feature first, then rotate it"


def test_the_plan_agrees_with_the_op():
    """the ring's centre is where the op turns: the body's centre after the
    rotate equals the plan's origin"""
    d = build(PLATE, MOVED)
    p = ok(toolplan.plan(d, {"tool": "rotate", "body_id": "m"}))
    out = blocks.rotate(d._parts["m"], "Z", 33.0, pivot=p["pivot"])
    assert centre(out) == pytest.approx(p["origin"], abs=1e-6)
    assert math.isclose(out.volume, d._parts["m"].volume)
