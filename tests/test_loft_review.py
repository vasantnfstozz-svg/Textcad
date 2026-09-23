"""Review of the Loft tool (ec45cf1), 2026-09-23.

The order guard's "same plane" test compared the sections' stations along the
MEAN normal; a third, tilted section leans that axis, so two profiles side by
side on ONE plane read as millimetres apart. The plan's re-sort of a U-bend
pick (A, B, C -> A, C, B) produced exactly that pair, and the loft built green
(220.60 mm3, valid, health clean). Measured in probes/loft_reorder_probe.py
and probes/loft_review_probe.py.
"""
import build123d as b3d
import pytest

import sketch as sk
import toolplan
from document import Document


def ubend():
    d = Document(name="ubend")
    d.add("A", "sketch", {"plane": "XY", "entities": [{"kind": "rectangle", "w": 4, "h": 4}]})
    d.add("B", "sketch", {"plane": "YZ", "offset": 10, "entities": [
        {"kind": "rectangle", "w": 4, "h": 4, "x": 0, "y": 10}]})
    d.add("C", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 4, "h": 4, "x": 20, "y": 0}]})
    d.rebuild()
    return d


def test_a_u_bend_pick_is_refused_not_re_sorted_into_a_flat_loft():
    d = ubend()
    plan = toolplan.plan(d, {"tool": "loft", "sketch_ids": ["A", "B", "C"]})
    assert not plan["ok"], plan.get("order")
    assert "U-turn" in plan["error"] and "fewer" in plan["error"]
    assert "Loft them in the order" not in plan["error"]     # no order offered that is refused


def test_two_profiles_side_by_side_on_one_plane_are_refused_whatever_else_is_lofted():
    d = ubend()
    d.add("L", "loft", {}, inputs=["A", "C", "B"])
    d.rebuild()
    f = d.get("L")
    assert f.status == "failed", "built green through a flat segment"
    assert "'A' and 'C' are on the same plane" in f.problems[0]


def test_parallel_planes_out_of_order_are_still_re_sorted():
    d = Document(name="stack")
    for i, z in (("a", 0), ("b", 20), ("c", 10)):
        d.add(i, "sketch", {"plane": "XY", "offset": z, "entities": [
            {"kind": "rectangle", "w": 4, "h": 4}]})
    d.rebuild()
    plan = toolplan.plan(d, {"tool": "loft", "sketch_ids": ["a", "b", "c"]})
    assert plan["ok"] and plan["order"] == ["a", "c", "b"] and plan["reordered"]


def _square(pl):
    return b3d.Sketch(children=[pl * b3d.Rectangle(4, 4)])


def test_an_empty_blend_is_not_called_the_same_plane():
    """XY square lofted to a YZ-plane square: the kernel's loft is 0.0 mm3."""
    a = _square(b3d.Plane.XY)
    b = _square(b3d.Plane(origin=(10, 0, 10), x_dir=(0, 1, 0), z_dir=(1, 0, 0)))
    with pytest.raises(ValueError) as e:
        sk.loft_sketches([a, b])
    assert "same plane" not in str(e.value) and "no volume" in str(e.value)


def test_two_profiles_level_along_the_loft_say_so():
    a = _square(b3d.Plane.XY)
    b = _square(b3d.Plane(origin=(10, 0, -10), x_dir=(0, 1, 0), z_dir=(1, 0, 0)))
    with pytest.raises(ValueError) as e:
        sk.loft_geometry([a, b], ["a", "b"])
    assert "level with each other" in str(e.value) and "same plane" not in str(e.value)
