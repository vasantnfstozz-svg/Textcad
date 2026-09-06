"""Pattern (LAUNCH-PLAN.md P4, specs/pattern.md): Circular / Rectangular
Pattern as the two ops that already existed, grown to repeat a FEATURE — its
delta (before − after cut again, after − before fused again) about an axis or
along a direction — plus the planner that hands the tool its ring, its arrows
and the seed in stored form.

probes/pattern_probe.py (2026-09-06) found in the kernel:

    before − after / after − before   -> exact solids (a hole's `added` is empty)
    N rotated plugs cut again         -> exact volumes, healthy, on every corpus body
    a copy that misses the body       -> removes EXACTLY 0.0 and "succeeds"
    a copy tangent to an edge         -> an OPEN SHELL is_valid calls fine
    Face(outer_wire).center()         -> the face centre a hole cannot move
    a cylindrical Face                -> axis_of_rotation

Every geometric claim is checked against the kernel: volumes against formulas,
copy positions against the centroids of the material that went away.
"""
import math

import build123d as b3d
import pytest
from build123d import Cylinder, Pos

import blocks
import inspector
import pattern
import sketch as sk
import toolplan
from document import Document, op_params

PI = math.pi
PLUG = PI * 9 * 12                       # a ⌀6 through hole in 12 mm: what one copy removes
TOP = dict(face_center=[0.0, 0.0, 6.0], face_normal=[0.0, 0.0, 1.0])
AXIS_TOP = {"face_center": [0.0, 0.0, 6.0], "face_normal": [0.0, 0.0, 1.0]}


def box(w=80.0, d=80.0, t=12.0):
    return b3d.Box(w, d, t)              # centred on the origin: top face at z = 6


def holed(b=None, at=(20, 0), d=6):
    b = b if b is not None else box()
    return b, sk.hole(b, **TOP, at=list(at), diameter=d, depth=1, through=True)


def healthy(part):
    assert inspector.health(part) == []
    return part


def plugs_xy(before, after):
    """where the material went: the (x, y) centroid of every separate lump"""
    gone = before - after
    return sorted((round(s.center().X, 3), round(s.center().Y, 3)) for s in gone.solids())


def angles_of(pts):
    return sorted(round(math.degrees(math.atan2(y, x)) % 360, 1) for x, y in pts)


# ------------------------------------------------------------ circular: the op ---

def test_circular_repeats_a_holes_delta_exactly():
    b, h = holed()
    out = healthy(pattern.polar_pattern(h, 6, axis=AXIS_TOP, seed="hole1", _before=b, _after=h))
    assert b.volume - out.volume == pytest.approx(6 * PLUG, rel=1e-6)
    pts = plugs_xy(b, out)
    assert len(pts) == 6
    assert all(math.hypot(x, y) == pytest.approx(20, abs=1e-3) for x, y in pts)
    assert angles_of(pts) == [0, 60, 120, 180, 240, 300]


def test_a_partial_angle_spreads_the_copies_from_the_seed_to_the_angle():
    b, h = holed()
    out = healthy(pattern.polar_pattern(h, 3, axis=AXIS_TOP, angle=180, seed="hole1",
                                        _before=b, _after=h))
    assert angles_of(plugs_xy(b, out)) == [0, 90, 180]     # Fusion's Angle type: the last copy AT the angle


def test_a_boss_added_material_is_fused_again():
    base = box()
    boss = Pos(20, 0, 6 + 4) * Cylinder(4, 8)
    with_boss = base + boss
    out = healthy(pattern.polar_pattern(with_boss, 4, axis=AXIS_TOP, seed="boss",
                                        _before=base, _after=with_boss))
    assert out.volume == pytest.approx(base.volume + 4 * PI * 16 * 8, rel=1e-6)
    assert len(out.solids()) == 1


def test_a_fillet_sliver_rounds_every_corner():
    b = b3d.Box(50, 50, 30)
    edge = max((e for e in b.edges() if abs(e.length - 30) < 1e-6),
               key=lambda e: e.center().X + e.center().Y)
    fb = b.fillet(5, [edge])
    out = healthy(pattern.polar_pattern(fb, 4, seed="fillet1", _before=b, _after=fb))  # axis None: world Z
    assert out.volume == pytest.approx(b.volume - 4 * (25 - 25 * PI / 4) * 30, rel=1e-6)
    assert len(out.faces()) == 10


def test_the_axis_of_a_bore_comes_from_its_cylindrical_face():
    b = box()
    ring = sk.hole(b, **TOP, at=[-15, 0], diameter=10, depth=1, through=True)   # the bore
    h = sk.hole(ring, **TOP, at=[5, 0], diameter=4, depth=1, through=True)      # the seed
    wall = next(f for f in h.faces() if f.geom_type == b3d.GeomType.CYLINDER
                and abs(f.center().X + 15) < 6)
    o, d, words = pattern.face_axis(wall)
    assert words == "axis of the ⌀10 bore"
    assert [round(o.X, 3), round(o.Y, 3)] == [-15, 0] and abs(abs(d.Z) - 1) < 1e-9
    out = healthy(pattern.polar_pattern(h, 2, seed="hole2", _before=ring, _after=h,
                                        axis={"face_center": list(wall.center()),
                                              "face_normal": list(wall.normal_at(wall.center()))}))
    assert plugs_xy(ring, out) == [(-35.0, 0.0), (5.0, 0.0)]    # 180° about x = -15


def test_the_default_face_axis_ignores_the_hole_the_face_carries():
    """Face.center() of a holed face moves toward the material (probe §5) —
    the axis goes through the OUTER wire's centre, so a bolt circle is centred
    on the plate, not 0.24 mm off it."""
    b, h = holed()
    face = max((f for f in h.faces() if f.geom_type == b3d.GeomType.PLANE), key=lambda f: f.center().Z)
    assert abs(face.center().X) > 0.05                         # the centroid HAS moved
    o, d, words = pattern.face_axis(face)
    assert [round(o.X, 6), round(o.Y, 6)] == [0, 0]
    assert words == "normal of the top face through its centre"


def test_count_one_returns_the_body_untouched():
    b, h = holed()
    assert pattern.polar_pattern(h, 1, axis=AXIS_TOP, seed="hole1", _before=b, _after=h) is h


def test_legacy_body_patterns_are_unchanged():
    blade = Pos(20, 0, 0) * b3d.Box(24, 3, 10)
    pat = pattern.polar_pattern(blade, 5)                     # world Z through the origin
    assert len(pat.solids()) == 5 and pat.volume == pytest.approx(5 * 720)
    assert blocks.polar_pattern(blade, 5).volume == pytest.approx(pat.volume)   # the old name still works
    row = blocks.linear_pattern(blocks.disc(5, 2), count=4, dx=30)
    assert len(row.solids()) == 4 and row.volume == pytest.approx(4 * PI * 25 * 2)


@pytest.mark.parametrize("kw, said", [
    (dict(count=0), "count must be a whole number ≥ 1"),
    (dict(count=2.5), "count must be a whole number ≥ 1"),
    (dict(count=4, angle=0), "angle must be between 0 and 360"),
    (dict(count=4, angle=400), "angle must be between 0 and 360"),
    (dict(count=4, axis="+Q"), "not a world axis"),
    (dict(count=4, axis={"foo": 1}), "`axis` must be"),
    (dict(count=4, axis={"dir": [0, 0, 0]}), "must not be the zero vector"),
])
def test_circular_refusals_are_sentences(kw, said):
    b, h = holed()
    with pytest.raises(ValueError, match=said):
        pattern.polar_pattern(h, seed="hole1", _before=b, _after=h, **kw)


def test_a_seed_needs_its_bodies_and_a_seed_that_changed_nothing_is_refused():
    b, h = holed()
    with pytest.raises(ValueError, match="needs its before / after bodies"):
        pattern.polar_pattern(h, 4, seed="hole1")
    with pytest.raises(ValueError, match="neither removed nor added material"):
        pattern.polar_pattern(b, 4, seed="fillet1", _before=b, _after=b)


def test_a_copy_that_lands_off_the_body_is_refused_not_skipped():
    b, h = holed(box(60, 40, 12), at=(25, 0))          # copy 2 at (0, 25): off a 40 mm plate
    with pytest.raises(ValueError, match=r"copy 2 of 4 lands off the body"):
        pattern.polar_pattern(h, 4, axis=AXIS_TOP, seed="hole1", _before=b, _after=h)


def test_a_copy_tangent_to_an_edge_is_a_broken_solid_and_refused():
    b, h = holed(box(60, 40, 12), at=(17, 0))          # copy 2 at (0, 17): its ⌀6 kisses y = 20
    with pytest.raises(ValueError, match="leaves a broken solid"):
        pattern.polar_pattern(h, 4, axis=AXIS_TOP, seed="hole1", _before=b, _after=h)


def test_a_body_pattern_whose_copies_lie_on_the_body_is_refused():
    with pytest.raises(ValueError, match="every copy lies on the body itself"):
        pattern.polar_pattern(b3d.Cylinder(10, 5), 4)     # about its own axis: 4 × the same


# ------------------------------------------------------- rectangular: the op ---

def test_spacing_puts_the_copies_that_far_apart():
    b, h = holed(at=(-30, 0))
    out = healthy(pattern.linear_pattern(h, 6, direction=[1, 0, 0], distance=12, seed="hole1",
                                         _before=b, _after=h))
    assert b.volume - out.volume == pytest.approx(6 * PLUG, rel=1e-6)
    assert plugs_xy(b, out) == [(x, 0.0) for x in (-30.0, -18.0, -6.0, 6.0, 18.0, 30.0)]


def test_extent_fits_the_copies_inside_the_distance():
    b, h = holed(at=(-30, 0))
    out = healthy(pattern.linear_pattern(h, 4, direction=[1, 0, 0], distance=30,
                                         distance_type="extent", seed="hole1", _before=b, _after=h))
    assert plugs_xy(b, out) == [(-30.0, 0.0), (-20.0, 0.0), (-10.0, 0.0), (0.0, 0.0)]


def test_a_second_direction_makes_a_grid():
    b, h = holed(at=(-30, -20))
    out = healthy(pattern.linear_pattern(h, 3, direction=[1, 0, 0], distance=15, seed="hole1",
                                         count2=2, direction2=[0, 1, 0], distance2=20,
                                         _before=b, _after=h))
    assert plugs_xy(b, out) == [(-30.0, -20.0), (-30.0, 0.0), (-15.0, -20.0), (-15.0, 0.0),
                                (0.0, -20.0), (0.0, 0.0)]
    assert b.volume - out.volume == pytest.approx(6 * PLUG, rel=1e-6)


def test_a_negative_distance_goes_the_other_way():
    b, h = holed(at=(20, 0))
    out = healthy(pattern.linear_pattern(h, 2, direction=[1, 0, 0], distance=-25, seed="hole1",
                                         _before=b, _after=h))
    assert plugs_xy(b, out) == [(-5.0, 0.0), (20.0, 0.0)]


@pytest.mark.parametrize("kw, said", [
    (dict(count=2, direction=[1, 0, 0], distance=0), "distance must not be 0"),
    (dict(count=2, direction=[1, 0, 0], distance=5, distance_type="foo"), "distance_type must be"),
    (dict(count=2, direction=[1, 0, 0], distance=5, count2=2), "second direction is needed"),
    (dict(count=2, direction=[1, 0, 0], distance=5, count2=2, direction2=[0, 1, 0]),
     "second distance must not be 0"),
    (dict(count=2, direction=[0, 0, 0], distance=5), "must not be the zero vector"),
    (dict(count=2, direction=[1, 0, 0], distance=200), "copy 2 of 2 lands off the body"),
])
def test_rectangular_refusals_are_sentences(kw, said):
    b, h = holed()
    with pytest.raises(ValueError, match=said):
        pattern.linear_pattern(h, seed="hole1", _before=b, _after=h, **kw)


# --------------------------------------------------------- in the document ---

def doc_with_hole(at=(20, 0)):
    doc = Document("t")
    doc.add("box1", "plate", {"width": 80, "depth": 80, "thickness": 12})
    doc.add("hole1", "hole", {"face": "top", "at": list(at), "diameter": 6, "through": True,
                              "depth": 1}, inputs=["box1"])
    return doc


def test_delta_features_is_the_trees_folding_rule():
    doc = doc_with_hole()
    doc.add("sk1", "sketch_on_face", {"face": "top", "entities": [
        {"kind": "circle", "cx": -20, "cy": 0, "r": 3}]}, inputs=["hole1"])
    doc.add("ex1", "extrude", {"amount": 5, "flip": True}, inputs=["sk1"])
    doc.add("cut1", "cut", {}, inputs=["hole1", "ex1"])
    doc.add("fil1", "fillet", {"radius": 1, "edges": "vertical"}, inputs=["cut1"])
    assert doc.delta_features("hole1") == ("box1", "hole1")     # a modifier of a body
    assert doc.delta_features("ex1") == ("hole1", "cut1")       # a pulled tool: its folded boolean
    assert doc.delta_features("cut1") == ("hole1", "cut1")      # the boolean itself
    assert doc.delta_features("fil1") == ("cut1", "fil1")
    assert doc.delta_features("box1") == (None, "box1")         # a creator: the whole body
    with pytest.raises(ValueError, match="a sketch is not a feature to repeat"):
        doc.delta_features("sk1")
    with pytest.raises(ValueError, match="not in the tree"):
        doc.delta_features("nope")
    doc.get("hole1").suppressed = True
    with pytest.raises(ValueError, match="struck out"):
        doc.delta_features("hole1")


def test_the_document_builds_a_pattern_of_a_hole_and_it_rides_the_seed():
    doc = doc_with_hole()
    doc.add("pat1", "polar_pattern", {"count": 4, "seed": "hole1", "axis": {"face": "top"}},
            inputs=["hole1"])
    assert doc.rebuild(), doc.get("pat1").problems
    f = doc.get("pat1")
    assert f.status == "ok" and f.pieces == 1
    assert f.volume == pytest.approx(80 * 80 * 12 - 4 * PLUG, abs=0.05)
    gone = doc._parts["box1"] - doc._parts["pat1"]
    assert all(math.hypot(s.center().X, s.center().Y) == pytest.approx(20, abs=1e-3)
               for s in gone.solids())
    doc.edit("hole1", "at", [30, 0])                            # move the seed: the pattern follows
    assert doc.rebuild()
    gone = doc._parts["box1"] - doc._parts["pat1"]
    assert all(math.hypot(s.center().X, s.center().Y) == pytest.approx(30, abs=1e-3)
               for s in gone.solids())


def test_a_seed_off_the_bodys_history_and_a_body_named_as_seed_are_refused():
    doc = doc_with_hole()
    doc.add("box2", "plate", {"width": 20, "depth": 20, "thickness": 5})
    doc.add("pat1", "polar_pattern", {"count": 3, "seed": "hole1"}, inputs=["box2"])
    doc.add("pat2", "polar_pattern", {"count": 3, "seed": "box1"}, inputs=["hole1"])
    doc.rebuild()
    assert "not part of box2's history" in doc.get("pat1").problems[0]
    assert "is a whole body, not a feature of one" in doc.get("pat2").problems[0]


def test_op_params_hide_the_documents_own_parameters():
    names = {n for n, _ in op_params("polar_pattern")}
    assert {"count", "axis", "angle", "seed"} <= names and "_before" not in names
    names = {n for n, _ in op_params("linear_pattern")}
    assert {"count", "dx", "direction", "distance", "distance_type", "count2"} <= names
    assert not any(n.startswith("_") for n in names)


# ------------------------------------------------------------------ the plan ---

def built(doc):
    assert doc.rebuild(), [f.problems for f in doc.features if f.status != "ok"]
    return doc


def test_the_plan_for_a_tree_row_puts_the_ring_on_the_seeds_face():
    doc = built(doc_with_hole())
    p = toolplan.plan(doc, {"tool": "polar_pattern", "seed_id": "hole1"})
    assert p["ok"], p
    assert p["input"] == "hole1" and p["seed"] == "hole1" and p["op"] == "polar_pattern"
    assert p["axis_words"] == "normal of the top face through its centre"
    assert p["radius"] == pytest.approx(20, abs=1e-3)
    assert p["origin"] == pytest.approx([0, 0, 0], abs=1e-3)       # the centre's foot on the axis
    assert p["frame"]["z_dir"] == pytest.approx([0, 0, 1])
    assert p["frame"]["x_dir"] == pytest.approx([1, 0, 0], abs=1e-6)  # toward the seed
    assert p["params"]["axis"]["face_normal"] == pytest.approx([0, 0, 1])
    assert p["params"]["seed"] == "hole1"


def test_the_plan_for_a_face_pick_asks_provenance_who_made_the_face():
    doc = built(doc_with_hole())
    part = doc._parts["hole1"]
    wall = next(f for f in part.faces() if f.geom_type == b3d.GeomType.CYLINDER)
    c = wall.center()
    p = toolplan.plan(doc, {"tool": "polar_pattern", "body_id": "hole1",
                            "face_center": [c.X, c.Y, c.Z], "face_point": [c.X, c.Y, c.Z]})
    assert p["ok"] and p["seed"] == "hole1", p                   # the hole's wall -> the hole
    p = toolplan.plan(doc, {"tool": "polar_pattern", "body_id": "hole1",
                            "face_center": [0, 0, 6], "face_normal": [0, 0, 1]})
    assert p["ok"] and p["seed"] is None, p                      # the plate's own top -> the body
    assert p["seed_words"] == "the body hole1"
    assert p["axis_words"] == "world Z through the origin"


def test_the_plan_reopens_a_pattern_on_its_stored_axis_and_a_click_re_aims_it():
    doc = doc_with_hole()
    doc.add("bore", "hole", {"face": "top", "at": [-25, 0], "diameter": 10, "through": True,
                             "depth": 1}, inputs=["hole1"])
    doc.add("pat1", "polar_pattern", {"count": 4, "seed": "hole1", "axis": {"face": "top"}},
            inputs=["bore"])
    built(doc)
    p = toolplan.plan(doc, {"tool": "polar_pattern", "feature_id": "pat1"})
    assert p["ok"] and p["axis"] == {"face": "top"} and p["radius"] == pytest.approx(20, abs=1e-3)
    part = doc._parts["bore"]
    wall = next(f for f in part.faces() if f.geom_type == b3d.GeomType.CYLINDER
                and abs(f.center().X + 25) < 6)
    c, n = wall.center(), wall.normal_at(wall.center())
    p = toolplan.plan(doc, {"tool": "polar_pattern", "feature_id": "pat1",
                            "axis_pick": {"center": [c.X, c.Y, c.Z], "normal": [n.X, n.Y, n.Z]}})
    assert p["ok"], p
    assert p["axis_words"] == "axis of the ⌀10 bore"
    assert p["radius"] == pytest.approx(45, abs=1e-3)
    assert "face_center" in p["axis"] and "face" not in p["axis"]   # ONE stored form


def test_the_rectangular_plan_offers_the_faces_axes_and_swaps_them():
    doc = built(doc_with_hole())
    p = toolplan.plan(doc, {"tool": "linear_pattern", "seed_id": "hole1"})
    assert p["ok"], p
    assert p["direction"] == pytest.approx([1, 0, 0]) and p["direction2"] == pytest.approx([0, 1, 0])
    assert [a["name"] for a in p["alternatives"]] == ["x", "y"] and p["along"] == "x"
    assert p["centre"] == pytest.approx([20, 0, 0], abs=1e-3)
    p = toolplan.plan(doc, {"tool": "linear_pattern", "seed_id": "hole1", "along": "y"})
    assert p["direction"] == pytest.approx([0, 1, 0]) and p["direction2"] == pytest.approx([1, 0, 0])
    doc.add("pat1", "linear_pattern", {"count": 3, "seed": "hole1", "direction": [0, 1, 0],
                                       "distance": 10, "direction2": [1, 0, 0]}, inputs=["hole1"])
    built(doc)
    p = toolplan.plan(doc, {"tool": "linear_pattern", "feature_id": "pat1"})
    assert p["ok"] and p["along"] == "y" and p["direction"] == pytest.approx([0, 1, 0])


def test_the_plan_refuses_a_sketch_and_nothing_with_a_sentence():
    doc = doc_with_hole()
    doc.add("sk1", "sketch", {"plane": "XY", "entities": [{"kind": "circle", "cx": 0, "cy": 0, "r": 3}]})
    built(doc)
    p = toolplan.plan(doc, {"tool": "polar_pattern", "seed_id": "sk1"})
    assert not p["ok"] and "a sketch is not a feature to repeat" in p["error"]
    p = toolplan.plan(doc, {"tool": "linear_pattern"})
    assert not p["ok"] and "needs a feature or a body to repeat" in p["error"]
