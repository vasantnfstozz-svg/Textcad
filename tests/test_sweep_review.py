"""Review of the Sweep tool (36ee69c), 2026-09-23: THE PIVOT.

The kernel carries the profile rigidly along the path and turns it about the
point where the path STARTS - not about the profile's centre, which is what
the guards, the volume check and the planner's ghost all assumed (every
earlier probe used straight paths, where the pivot cannot show).
Measured in probes/sweep_pivot_probe.py and probes/sweep_review_probe.py.
"""
import math

import build123d as b3d
import pytest

import sketch as sk
import toolplan
from document import Document


def path(segments, start=(0, 0), plane="XZ"):
    return sk.make_sketch(plane=plane, entities=[
        {"kind": "path", "closed": False, "start": list(start), "segments": segments}])


def rect(w, h):
    return sk.make_sketch(plane="XY", entities=[{"kind": "rectangle", "w": w, "h": h}])


def circ(r):
    return sk.make_sketch(plane="XY", entities=[{"kind": "circle", "r": r}])


def bend(R, start=(0.0, 0.0), deg=90.0, up=10.0, run=10.0):
    """up +Z from `start`, an arc of `deg` and radius R turning toward +X,
    then `run` along the new tangent (XZ plane: local x = world X, y = Z)."""
    x0, z0 = start[0], 0.0
    t = math.radians(deg)
    cx = x0 + R
    end = (cx - R * math.cos(t), up + R * math.sin(t))
    mid = (cx - R * math.cos(t / 2), up + R * math.sin(t / 2))
    far = (end[0] + run * math.sin(t), end[1] + run * math.cos(t))
    return path([{"type": "line", "to": [x0, up]},
                 {"type": "arc", "via": list(mid), "to": list(end)},
                 {"type": "line", "to": list(far)}], start=(x0, z0))


def sweep(profile, p):
    return sk.sweep_sketch(profile, path="rail", _path_sketch=p, full=True)


def kernel(profile, p):
    """The op's own kernel call with no guard in front of it."""
    return b3d.sweep(profile, path=sk.sketch_paths(p)[0], transition=b3d.Transition.RIGHT)


def test_a_fold_the_pivot_hides_is_refused():
    """A circle r2 whose path starts 1 mm off-centre reaches 3 mm toward a
    2.5 mm bend - past the bend's centre. OCCT calls it valid; the guard
    measured 2 mm from the centre and the op BUILT it, green."""
    p = bend(2.5, start=(-1, 0), deg=30, run=50)
    assert kernel(circ(2), p).is_valid, "the kernel alone says nothing"
    with pytest.raises(ValueError, match="toward its inside"):
        sweep(circ(2), p)
    # ...and the same circle with its path at the centre still builds
    assert sweep(circ(2), bend(2.5, deg=30, run=50)).volume > 0


def test_a_correct_sweep_from_an_off_centre_start_builds_at_its_true_volume():
    """A 4 x 4 square, path started 1.5 mm off-centre, bend 10: the kernel
    gives 1.066 x A*L (its centroid travels the longer arc). The volume check
    compared it with A*L and refused it as 'folded over itself'."""
    sk.drain_notes()
    p = bend(10, start=(1.5, 0))
    out = sweep(rect(4, 4), p)
    assert out.volume == pytest.approx(kernel(rect(4, 4), p).volume, rel=1e-9)
    L = sk.sketch_paths(p)[0].length
    assert out.volume == pytest.approx(16 * (L + 1.5 * math.pi / 2), rel=1e-6)
    assert any("carried at that distance" in n for n in sk.drain_notes())
    # the other side of the path: the shorter arc
    p = bend(10, start=(-1.5, 0))
    assert sweep(rect(4, 4), p).volume == pytest.approx(
        16 * (sk.sketch_paths(p)[0].length - 1.5 * math.pi / 2), rel=1e-6)


def test_a_mitred_corner_from_an_off_centre_start_builds_at_its_true_volume():
    p = path([{"type": "line", "to": [1, 10]}, {"type": "line", "to": [11, 10]}], start=(1, 0))
    out = sweep(rect(4, 4), p)
    assert out.volume == pytest.approx(kernel(rect(4, 4), p).volume, rel=1e-9)
    assert out.volume == pytest.approx(16 * (20 + 2 * 1 * math.tan(math.pi / 4)), rel=1e-6)


@pytest.mark.parametrize("R", [5.0, 1.5, 1.1])
def test_a_flat_strip_bends_across_its_thin_side(R):
    """2 wide (across the bend) x 20 deep: nothing reaches past 1 mm toward
    the bend's centre, and the kernel builds it valid and exact. The guard
    took the 10.05 mm corner-to-corner reach and refused every one."""
    out = sweep(rect(2, 20), bend(R))
    assert out.is_valid
    assert out.volume == pytest.approx(40 * sk.sketch_paths(bend(R))[0].length, rel=1e-6)


def test_the_same_strip_across_its_wide_side_is_still_refused():
    with pytest.raises(ValueError, match="toward its inside"):
        sweep(rect(20, 2), bend(5))


def test_a_flat_strip_turns_a_sharp_corner_on_a_short_leg():
    p = path([{"type": "line", "to": [0, 10]}, {"type": "line", "to": [3, 10]}])
    assert sweep(rect(2, 20), p).volume == pytest.approx(40 * 13, rel=1e-6)
    p = path([{"type": "line", "to": [0, 10]}, {"type": "line", "to": [0.8, 10]}])
    with pytest.raises(ValueError, match="shorter than"):
        sweep(rect(2, 20), p)


def test_the_plan_turns_the_ghost_about_the_same_pivot():
    """The ghost's stations were moved to start at the profile's centre, so on
    any bend the preview and the solid parted; now both turn about the path's
    start, and the loops are given relative to it."""
    d = Document(name="pivot")
    d.add("prof", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 4, "h": 4}]})
    d.add("rail", "sketch", {"plane": "XZ", "entities": [
        {"kind": "path", "closed": False, "start": [1.5, 0], "segments": [
            {"type": "line", "to": [1.5, 10]},
            {"type": "arc", "via": [4.4289, 17.0711], "to": [11.5, 20]},
            {"type": "line", "to": [21.5, 20]}]}]})
    d.rebuild()
    plan = toolplan.plan(d, {"tool": "sweep", "sketch_id": "prof", "path_id": "rail"})
    assert plan["ok"], plan.get("error")
    assert plan["stations"][0]["p"] == pytest.approx([1.5, 0, 0], abs=1e-6)
    assert plan["stations"][-1]["p"] == pytest.approx([21.5, 0, 20], abs=1e-3)
    assert plan["frame"]["origin"] == pytest.approx([1.5, 0, 0], abs=1e-6)
    xs = [q[0] for loop in plan["loops"] for q in loop["outer"]]
    assert min(xs) == pytest.approx(-3.5, abs=1e-6) and max(xs) == pytest.approx(0.5, abs=1e-6)


def _slant_bend(R, toward=+1, deg=45.0, leg=10.0, turn=60.0, run=30.0):
    """XZ plane: a first leg at `deg` from +Z, then an arc of `turn` degrees
    and radius R turning further toward +X (toward=+1) or back (-1)."""
    a = math.radians(deg)
    p1 = (leg * math.sin(a), leg * math.cos(a))
    nrm = (math.cos(a) * toward, -math.sin(a) * toward)
    c = (p1[0] + R * nrm[0], p1[1] + R * nrm[1])
    b = math.radians(turn) * toward
    a0 = math.atan2(p1[1] - c[1], p1[0] - c[0])

    def on(t):
        return (c[0] + R * math.cos(a0 - t), 0, c[1] + R * math.sin(a0 - t))
    mid, end = on(b / 2), on(b)
    far = (end[0] + run * math.sin(a + b), 0, end[2] + run * math.cos(a + b))
    return b3d.Wire([b3d.Line((0, 0, 0), (p1[0], 0, p1[1])),
                     b3d.ThreePointArc((p1[0], 0, p1[1]), mid, end), b3d.Line(end, far)])


@pytest.mark.parametrize("toward", [+1, -1])
def test_a_slanted_profile_folds_sooner_and_is_refused(toward):
    """Round two: a circle r3 the path leaves at 45 deg folds on any bend up to
    3/cos45 = 4.24 (its far side sweeps backwards through the profile's
    plane). The kernel calls every one valid at exactly A*L*cos45; round
    one's rule measured 3*cos45 = 2.12 across the path and built R = 2.2."""
    faces = circ(3).faces()
    for R in (2.2, 3.0, 4.0):
        with pytest.raises(ValueError, match="toward its inside"):
            sk._sweep_solid(faces, _slant_bend(R, toward), 0, True)
    assert sk._sweep_solid(faces, _slant_bend(4.5, toward), 0, True).volume > 0
