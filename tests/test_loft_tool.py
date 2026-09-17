"""Loft (Tier 2, specs/loft.md): the order rule that keeps the kernel from
folding a loft through itself, the sentences, `ruled`, and the planner.

Every number came off the kernel first (probes/loft_api_probe.py):

    two sections, any shapes         -> exact (cylinder, frustum, twist)
    three sections, ruled            -> exact piecewise frusta
    three sections, smooth           -> 0.754 of ruled on r5-r2-r5 (a spline)
    coplanar                         -> a 0-volume "solid"
    OUT OF ORDER (z 0, 20, 10)       -> 1.976 x the honest volume, VALID
    the same sketch twice            -> StdFail_NotDone
"""
import json
import math

import pytest

import sketch as sk
import toolplan
from document import Document

KERNEL_WORDS = ("StdFail", "Standard_", "BRep", "TopoDS", "OCP", "NoneType", "Traceback")


def circ(z, r=5.0, x=0.0, plane="XY"):
    return sk.make_sketch(plane=plane, offset=z, entities=[
        {"kind": "circle", "r": r, "x": x, "mode": "add"}])


def rect(z, w=10.0, h=10.0, rot=0.0):
    return sk.make_sketch(plane="XY", offset=z, entities=[
        {"kind": "rectangle", "w": w, "h": h, "rotation": rot, "mode": "add"}])


def frustum(r1, r2, h):
    return math.pi * h / 3 * (r1 * r1 + r1 * r2 + r2 * r2)


def refusal(fn, *needles):
    with pytest.raises(ValueError) as e:
        fn()
    msg = str(e.value)
    assert msg.startswith("loft"), msg
    assert len(msg) > 40 and not any(w in msg for w in KERNEL_WORDS), msg
    for n in needles:
        assert n in msg, (n, msg)
    return msg


# ------------------------------------------------- what builds --------------

def test_two_sections_are_exact():
    assert sk.loft_sketches([circ(0), circ(20)]).volume == pytest.approx(math.pi * 25 * 20, rel=1e-6)
    assert sk.loft_sketches([circ(0), circ(20, 2)]).volume == pytest.approx(frustum(5, 2, 20), rel=1e-6)
    assert sk.loft_sketches([rect(0), rect(20)]).volume == pytest.approx(2000, rel=1e-6)


def test_three_sections_ruled_is_piecewise_and_smooth_is_a_spline():
    ruled = sk.loft_sketches([circ(0), circ(10, 2), circ(20)], ruled=True)
    assert ruled.volume == pytest.approx(2 * frustum(5, 2, 10), rel=1e-6)
    smooth = sk.loft_sketches([circ(0), circ(10, 2), circ(20)])
    assert 0.6 * ruled.volume < smooth.volume < 0.9 * ruled.volume
    assert not __import__("inspector").health(smooth)


def test_sections_may_step_down_the_axis_or_sideways():
    """Descending is one way too; a lateral zigzag keeps its z order."""
    assert sk.loft_sketches([circ(20), circ(0)]).volume == pytest.approx(math.pi * 25 * 20, rel=1e-6)
    z = sk.loft_sketches([circ(0), circ(10, x=40), circ(20)])
    assert z.volume == pytest.approx(math.pi * 25 * 20, rel=1e-6)


def test_perpendicular_planes_loft():
    out = sk.loft_sketches([circ(0), circ(20, plane="YZ")])
    assert out.volume > 0 and not __import__("inspector").health(out)


# ------------------------------------------------- what is refused ----------

def test_out_of_order_sections_are_refused_with_the_right_order():
    """The kernel builds z 0, 20, 10 at 1.976 x the honest volume and calls it
    VALID — only the order can catch it."""
    msg = refusal(lambda: sk.loft_sketches([circ(0), circ(20), circ(10, 2)], ids=["a", "b", "c"]),
                  "do not run one way", "fold", "a, c, b")
    assert "a, b, c would" in msg


def test_coplanar_sections_are_named():
    refusal(lambda: sk.loft_sketches([circ(0), circ(0, 3)], ids=["a", "b"]),
            "'a' and 'b' are on the same plane")


def test_one_section_and_multi_profile_sections_are_refused():
    refusal(lambda: sk.loft_sketches([circ(0)]), "at least 2")
    two = sk.make_sketch(plane="XY", offset=20, entities=[
        {"kind": "circle", "r": 2, "x": -5, "mode": "add"},
        {"kind": "circle", "r": 2, "x": 5, "mode": "add"}])
    refusal(lambda: sk.loft_sketches([circ(0), two], ids=["a", "b"]), "ONE closed profile", "'b' holds 2")
    path = sk.make_sketch(plane="XY", offset=20, entities=[
        {"kind": "path", "closed": False, "start": [0, 0], "segments": [{"type": "line", "to": [10, 0]}]}])
    refusal(lambda: sk.loft_sketches([circ(0), path], ids=["a", "b"]), "'b' holds 0")


def test_loft_geometry_reports_axis_stations_and_areas():
    geo = sk.loft_geometry([circ(0), circ(20, 2)], ["a", "b"])
    assert list(geo["axis"]) == pytest.approx([0, 0, 1], abs=1e-9)
    assert geo["stations"] == pytest.approx([0, 20], abs=1e-9)
    assert geo["areas"] == pytest.approx([math.pi * 25, math.pi * 4], rel=1e-6)
    assert geo["length"] == pytest.approx(20, abs=1e-9)


# ------------------------------------------------- through the document -----

def doc(third=True):
    d = Document(name="lf")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 12}, [])
    d.add("a", "sketch_on_face", {"face": "top", "offset": 0, "entities": [
        {"kind": "circle", "r": 5, "mode": "add"}]}, ["b"])
    d.add("c", "sketch", {"plane": "XY", "offset": 26, "entities": [
        {"kind": "rectangle", "w": 10, "h": 10, "mode": "add"}]}, [])
    if third:
        d.add("m", "sketch", {"plane": "XY", "offset": 16, "entities": [
            {"kind": "circle", "r": 2, "mode": "add"}]}, [])
    d.rebuild()
    return d


def test_the_document_lofts_in_order_and_takes_ruled():
    d = doc()
    d.add("loft1", "loft", {}, ["a", "m", "c"])
    d.rebuild()
    f = d.get("loft1")
    assert f.status == "ok", f.problems
    smooth = f.volume
    d.edit_many("loft1", {"ruled": True})
    d.rebuild()
    assert d.get("loft1").status == "ok" and d.get("loft1").volume != smooth
    assert d.op_params("loft") if hasattr(d, "op_params") else True
    import document
    assert document.op_params("loft") == (("ruled", False),)


def test_the_document_refuses_a_folded_order_and_a_bad_parameter():
    d = doc()
    d.add("loft1", "loft", {}, ["a", "c", "m"])
    d.rebuild()
    msg = d.get("loft1").problems[0]
    assert "do not run one way" in msg and "a, m, c" in msg, msg
    with pytest.raises(ValueError, match="no parameter"):
        d.check_params("loft", {"twist": 3}, "loft2")


def test_the_document_still_refuses_a_body_and_a_twice_named_sketch():
    d = doc()
    d.add("loft1", "loft", {}, ["a", "b"])
    d.add("loft2", "loft", {}, ["a", "a"])
    d.rebuild()
    assert "solid body" in d.get("loft1").problems[0]
    assert "DIFFERENT" in d.get("loft2").problems[0]


# ------------------------------------------------- the plan -----------------

def ok(plan):
    assert plan["ok"], plan
    json.dumps(plan)
    return plan


def test_plan_with_one_profile_opens_with_a_ring_and_candidates():
    d = doc()
    plan = ok(toolplan.plan(d, {"tool": "loft", "sketch_ids": ["a"]}))
    assert plan["order"] == ["a"] and plan["limits"]["sections"] == 1
    assert len(plan["sections"]) == 1 and len(plan["sections"][0]["ring"]) == toolplan.LOFT_RING
    assert [c["id"] for c in plan["candidates"]] == ["m", "c"]
    assert plan["target_body"] == "b" and "pick a second" in plan["will_build"]


def test_plan_with_two_profiles_builds_the_same_volume_the_op_does():
    d = doc()
    plan = ok(toolplan.plan(d, {"tool": "loft", "sketch_ids": ["a", "c"]}))
    assert plan["order"] == ["a", "c"] and plan["reordered"] is False and plan["note"] is None
    assert plan["limits"]["length"] == pytest.approx(20, abs=1e-3)
    assert [c["id"] for c in plan["candidates"]] == ["m"]
    # the rings sit on the sections' planes
    assert all(abs(p[2] - 6) < 1e-3 for p in plan["sections"][0]["ring"])
    assert all(abs(p[2] - 26) < 1e-3 for p in plan["sections"][1]["ring"])


def test_plan_reorders_out_of_order_picks_and_says_so():
    d = doc()
    plan = ok(toolplan.plan(d, {"tool": "loft", "sketch_ids": ["a", "c", "m"]}))
    assert plan["order"] == ["a", "m", "c"] and plan["reordered"] is True
    assert "order they lie" in plan["note"] and "a, m, c" in plan["note"]
    # the order the plan hands back is one the op accepts
    d.add("loft1", "loft", {}, plan["order"])
    d.rebuild()
    assert d.get("loft1").status == "ok", d.get("loft1").problems


def test_plan_refuses_what_the_op_refuses():
    d = doc()
    d.add("a2", "sketch_on_face", {"face": "top", "offset": 0, "entities": [
        {"kind": "circle", "r": 3, "x": 20, "mode": "add"}]}, ["b"])
    d.rebuild()
    plan = toolplan.plan(d, {"tool": "loft", "sketch_ids": ["a", "a2"]})
    assert not plan["ok"] and "same plane" in plan["error"]
    plan = toolplan.plan(d, {"tool": "loft", "sketch_ids": ["a", "b"]})
    assert not plan["ok"] and "not a sketch" in plan["error"]
    plan = toolplan.plan(d, {"tool": "loft", "sketch_ids": []})
    assert not plan["ok"] and "needs a sketch profile" in plan["error"]


def test_plan_edit_mode_reads_the_inputs_and_ruled():
    d = doc()
    d.add("loft1", "loft", {"ruled": True}, ["a", "m", "c"])
    d.rebuild()
    plan = ok(toolplan.plan(d, {"tool": "loft", "feature_id": "loft1"}))
    assert plan["order"] == ["a", "m", "c"] and plan["stored"] == {"ruled": True}
    assert plan["candidates"] == [], "every profile is consumed by the loft"
