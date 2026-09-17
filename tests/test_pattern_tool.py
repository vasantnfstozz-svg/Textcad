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


def test_a_symmetric_body_patterns_to_itself_instead_of_failing():
    """A body pattern whose copies land back on the body is a no-op, NOT a
    failure. Measuring the union against the body and refusing broke every
    saved design with a rotationally symmetric body pattern — at rebuild, the
    one thing a design may never do (P4 code review). What is refused is a
    pattern that asks for no motion at all, by name, below."""
    out = healthy(pattern.polar_pattern(b3d.Cylinder(10, 5), 4))   # about its own axis
    assert out.volume == pytest.approx(PI * 100 * 5)


def test_a_body_pattern_with_no_step_at_all_is_refused_by_name():
    with pytest.raises(ValueError, match=r"the step is 0, so all 4 copies land on the seed"):
        pattern.linear_pattern(box(20, 20, 5), 4)         # count, but no dx / dy / dz


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


# ------------------------------------------- what the P4 code review found ---
# Seven fixes, each with the failure it prevents. The three frontend ones
# (a cancelled row-wait hijacking the next tool, a tree row hiding a curved
# pick, a Direction-2-only pattern refused as empty) are in
# tests/e2e/test_pattern_tool.py — they are browser behaviour.

def doc_with_pattern(at=(20, 0)):
    doc = doc_with_hole(at)
    doc.add("pat1", "polar_pattern", {"count": 4, "seed": "hole1", "axis": {"face": "top"}},
            inputs=["hole1"])
    return doc


def test_renaming_a_seed_renames_it_inside_every_pattern_of_it():
    """`inputs` is not the only reference in the tree: a pattern NAMES its seed
    in its params. Renaming used to rewrite only the inputs, so the rename the
    docstring promises can never break the tree broke every pattern of the
    renamed feature ("the seed 'hole1' is not in the tree")."""
    doc = doc_with_pattern()
    assert doc.rebuild(), doc.get("pat1").problems
    doc.rename("hole1", "bolt_hole")
    assert doc.get("pat1").params["seed"] == "bolt_hole"
    assert doc.rebuild(), doc.get("pat1").problems
    assert doc.get("pat1").volume == pytest.approx(80 * 80 * 12 - 4 * PLUG, abs=0.05)


def test_deleting_a_seed_takes_the_patterns_of_it_along():
    """The same blind spot on the way out: healing rewired the pattern's INPUT
    to the seed's upstream body and left `seed` pointing at a ghost."""
    doc = doc_with_pattern()
    assert doc.rebuild()
    plan = doc.remove_plan("hole1")
    assert "pat1" in plan["deleted"]
    doc.remove("hole1")
    assert [f.id for f in doc.features] == ["box1"]
    assert doc.rebuild()


def test_strict_delete_names_a_pattern_as_a_dependent_of_its_seed():
    doc = doc_with_pattern()
    assert doc.rebuild()
    with pytest.raises(ValueError, match=r"cannot remove 'hole1': used by \['pat1'\]"):
        doc.remove("hole1", mode="strict")


def test_striking_a_seed_strikes_the_pattern_that_repeats_it():
    doc = doc_with_pattern()
    assert doc.rebuild()
    doc.strike("hole1")
    assert doc.get("pat1").suppressed and doc.get("hole1").suppressed
    assert doc.rebuild(), doc.get("pat1").problems
    # a struck node is a pass-through: the plate comes back whole, both gone
    assert doc._parts["pat1"].volume == pytest.approx(80 * 80 * 12, abs=0.05)


def test_editing_a_legacy_step_pattern_keeps_its_own_direction_and_distance():
    """A legacy linear_pattern stores (dx, dy, dz) per copy and no direction.
    The plan used to ignore it, so the panel opened aimed at world X and the
    first distance the user has to type re-aimed the pattern from +Y to +X."""
    doc = doc_with_hole()
    doc.add("pat1", "linear_pattern", {"count": 4, "dy": 30}, inputs=["hole1"])
    doc.add("pat2", "linear_pattern", {"count": 3, "dx": 6, "dy": 8}, inputs=["hole1"])
    built(doc)
    p = toolplan.plan(doc, {"tool": "linear_pattern", "feature_id": "pat1"})
    assert p["ok"], p
    assert p["along"] == "y" and p["direction"] == pytest.approx([0, 1, 0])
    assert p["params"]["direction"] == pytest.approx([0, 1, 0])
    assert p["params"]["distance"] == pytest.approx(30)          # the panel opens on 30, not 0
    # a diagonal step is an alternative of its own, and SURVIVES the next plan
    q = toolplan.plan(doc, {"tool": "linear_pattern", "feature_id": "pat2"})
    assert q["along"] == "stored" and q["params"]["distance"] == pytest.approx(10)
    assert q["direction"] == pytest.approx([0.6, 0.8, 0])
    q2 = toolplan.plan(doc, {"tool": "linear_pattern", "feature_id": "pat2", "along": "stored"})
    assert q2["direction"] == pytest.approx([0.6, 0.8, 0])
    assert "stored" in [a["name"] for a in q2["alternatives"]]


def test_the_panels_first_push_on_a_legacy_pattern_moves_nothing():
    """The measurement behind the fix above: open a legacy body pattern, push
    exactly what the panel would push from the plan, and the solid must be the
    one that was there — not the same pattern re-aimed along world X."""
    doc = doc_with_hole()
    doc.add("pat1", "linear_pattern", {"count": 4, "dy": 30}, inputs=["hole1"])
    built(doc)
    was = doc._parts["pat1"].volume
    p = toolplan.plan(doc, {"tool": "linear_pattern", "feature_id": "pat1"})
    doc.edit_many("pat1", {                       # the panel's boxes, as the tool sends them
        "seed": p["params"]["seed"], "direction": p["params"]["direction"],
        "direction2": p["params"]["direction2"],
        # exactly what the panel shows: the plan's distance when it has one,
        # else the 0 the box opened on
        "distance": p["params"].get("distance", 0),
        "count": 4, "distance_type": "spacing", "count2": 1, "distance2": 0})
    assert doc.rebuild(), doc.get("pat1").problems
    assert doc._parts["pat1"].volume == pytest.approx(was, rel=1e-9)
    moved = doc._parts["pat1"] - doc._parts["hole1"]      # where the copies are
    assert sorted(round(sol.center().Y, 3) for sol in moved.solids()) != [0.0]


def test_a_pattern_already_built_this_session_replans_on_its_own_body():
    """In a NEW session the tool has no `feature_id`, so the planner walked the
    tree down from the seed — straight into the pattern it had just built, and
    the next plan aimed the axis at the already-patterned solid. `own_id` says
    "that one is mine"."""
    doc = doc_with_hole()
    built(doc)
    first = toolplan.plan(doc, {"tool": "polar_pattern", "seed_id": "hole1"})
    assert first["input"] == "hole1"
    doc.add("pat1", "polar_pattern", {"count": 4, "seed": "hole1",
                                      "axis": first["params"]["axis"]}, inputs=[first["input"]])
    built(doc)
    stale = toolplan.plan(doc, {"tool": "polar_pattern", "seed_id": "hole1"})
    assert stale["input"] == "pat1"                        # the walk alone: its own output
    live = toolplan.plan(doc, {"tool": "polar_pattern", "seed_id": "hole1", "own_id": "pat1"})
    assert live["ok"] and live["input"] == "hole1" and live["seed"] == "hole1"
    assert live["radius"] == pytest.approx(20, abs=1e-3)
    assert live["axis"] == {"face": "top"} or "face_center" in live["axis"]
    # in flight (created in the browser, not on the server yet): simply ignored
    assert toolplan.plan(doc, {"tool": "polar_pattern", "seed_id": "hole1",
                               "own_id": "polar_pattern_9"})["ok"]


def test_a_placement_op_folds_to_a_body_seed():
    """P0 of the big Mirror review, generalised: an op that RE-PLACES the whole
    body (rotate, scale, the legacy copy-only mirror) neither adds material nor
    takes it away, so it has no delta to repeat. Folded as a modifier its
    "delta" was the body in the old spot plus the body in the new one, and
    repeating THAT gouged a body-sized lump out of the part while reporting
    success (measured, probes/mirror_p0_probe.py §1: rotate 2475 + 2475,
    scale 0 + 38000, mirror 16000 + 16000). Each folds to a BODY seed."""
    doc = Document("t")
    doc.add("box1", "plate", {"width": 40, "depth": 40, "thickness": 10})
    doc.add("rot", "rotate", {"axis": "Z", "angle_deg": 30}, inputs=["box1"])
    doc.add("big", "scale", {"factor": 1.5}, inputs=["rot"])
    doc.add("copy", "mirror", {"plane": {"origin": [60, 0, 0], "normal": [1, 0, 0]}},
            inputs=["big"])
    assert doc.rebuild(), [f.problems for f in doc.features if f.status != "ok"]

    assert doc.delta_features("rot") == (None, "rot")
    assert doc.delta_features("big") == (None, "big")
    assert doc.delta_features("copy") == (None, "copy")

    # a mirror that ADDS its reflection, and one that repeats a feature, do
    # have a delta and keep it
    doc.add("join", "mirror", {"plane": {"face": "+x"}, "join": True}, inputs=["copy"])
    assert doc.delta_features("join") == ("copy", "join")


def test_a_body_pattern_refuses_a_union_that_is_not_one_sound_solid():
    """P0 of the big Mirror review: `_body_pattern` fused the copies and
    returned them with NO health gate, so a copy tangent to the body along one
    edge came back as a success — `is_valid` True, an open shell (measured:
    dx = the bounding box's own width). What it must NOT do is refuse the two
    cases every saved design relies on: separate pieces, and a symmetric body
    that patterns to itself."""
    diamond = b3d.Rot(0, 0, 45) * b3d.Box(30, 30, 10)      # +x extreme is an edge
    with pytest.raises(ValueError) as e:
        pattern.linear_pattern(diamond, 2, dx=diamond.bounding_box().size.X)
    assert "the pattern leaves a broken solid" in str(e.value)
    assert "it touches the body along an edge only" in str(e.value)

    apart = pattern.linear_pattern(diamond, 3, dx=100)     # separate pieces: fine
    assert inspector.health(apart) == [] and len(apart.solids()) == 3
    square = b3d.Box(40, 40, 10)                           # 4-fold symmetric: itself
    same = pattern.polar_pattern(square, 4)
    assert inspector.health(same) == []
    assert float(same.volume) == pytest.approx(40 * 40 * 10, abs=0.05)


# ------------------------------------------------------------------------
# The two follow-ups found while fixing the big P4 review's P0s
# (probes/pattern_barrier_probe.py).
# ------------------------------------------------------------------------

class _KernelBoom(Exception):
    """what OCP raises: an Exception, NOT a RuntimeError — an
    `except RuntimeError` barrier does not catch it"""


class _Boom:
    """a shape whose boolean fails in the kernel"""

    def __sub__(self, other):
        raise _KernelBoom("StdFail_NotDone: BRepAlgoAPI_Cut::Build() failed")


def test_a_kernel_failure_in_the_seeds_delta_becomes_a_sentence():
    """`delta` subtracted OUTSIDE any barrier and `_seed` calls it at the op's
    TOP level, so an OCCT failure there escaped as a raw kernel exception and
    `document.rebuild` stored it as `repr(e)` — gibberish in the tree, and one
    of the two failure modes the house rules ban outright."""
    with pytest.raises(ValueError) as e:
        pattern.delta(_Boom(), _Boom())
    assert "could not work out what the feature changed" in str(e.value)

    body = b3d.Box(40, 40, 10)
    for call in (lambda: pattern.mirror(body, "YZ", seed="h",
                                        _before=_Boom(), _after=_Boom()),
                 lambda: pattern.polar_pattern(body, 3, axis="+z", seed="h",
                                               _before=_Boom(), _after=_Boom()),
                 lambda: pattern.linear_pattern(body, 2, dx=20, seed="h",
                                                _before=_Boom(), _after=_Boom())):
        with pytest.raises(ValueError) as e:      # never _KernelBoom
            call()
        assert "could not work out what 'h' changed" in str(e.value), str(e.value)
        assert str(e.value).split(":")[0] in ("mirror", "polar_pattern", "linear_pattern")

    # the plan says the same thing rather than leaking the kernel's words
    doc = Document("t")
    doc.add("box1", "plate", {"width": 40, "depth": 40, "thickness": 10})
    doc.add("hole1", "hole", {"face": "top", "at": [10, 0], "diameter": 6,
                              "through": True, "depth": 1}, inputs=["box1"])
    assert doc.rebuild()
    doc._parts["box1"] = _Boom()                  # the kernel fails on THIS body
    p = toolplan.plan(doc, {"tool": "polar_pattern", "seed_id": "hole1"})
    assert not p["ok"] and "could not work out what 'hole1' changed" in p["error"], p


def test_a_pattern_axis_click_must_be_a_face_the_body_really_has():
    """The framework hands this tool clicks on its OWN result body, and
    `sk.pick_face`'s nearest-centre match is unbounded, so a click on a COPY's
    bore wall came back as a face of the pre-pattern body 21 mm away and the
    pattern silently re-aimed to it. Mirror's `_plane_face` rule does not
    transfer — a mirror plane is the same wherever the face sits, an axis is
    not — so what is checked is that the click is somewhere the body really has
    that face: inside the resolved face's own bounding box."""
    doc = Document("t")
    doc.add("box1", "plate", {"width": 80, "depth": 80, "thickness": 12})
    doc.add("hole1", "hole", {"face": "top", "at": [-25, 0], "diameter": 6,
                              "through": True, "depth": 1}, inputs=["box1"])
    doc.add("pat", "polar_pattern", {"seed": "hole1", "count": 3,
                                     "axis": {"face": "top"}}, inputs=["hole1"])
    assert doc.rebuild(), [f.problems for f in doc.features if f.status != "ok"]

    def pick_of(face):
        c = face.center()
        n = face.normal_at(c)
        return {"center": [round(c.X, 2), round(c.Y, 2), round(c.Z, 2)],
                "normal": [round(n.X, 3), round(n.Y, 3), round(n.Z, 3)]}

    def plan_with(pick):
        return toolplan.plan(doc, {"tool": "polar_pattern", "feature_id": "pat",
                                   "axis_pick": pick})

    bores = sorted((f for f in doc._parts["pat"].faces()
                    if f.geom_type == b3d.GeomType.CYLINDER),
                   key=lambda f: (f.center().X, f.center().Y))
    assert len(bores) == 3                        # the seed and its two copies

    # a wall only a COPY has: refused, with what to click instead
    p = plan_with(pick_of(bores[-1]))
    assert not p["ok"], p
    assert "that face is not on hole1" in p["error"]
    assert "only a copy has" in p["error"]

    # the SEED's own bore still aims the axis at itself. Its face centre sits
    # ON the wall, a radius off the axis (measured: -28 for a ⌀6 bore at -25),
    # which is exactly why the bound is bounding-box containment and not a
    # distance from the axis
    seed_bore = min(bores, key=lambda f: f.center().X)
    sc = seed_bore.center()
    p = plan_with(pick_of(seed_bore))
    assert p["ok"], p
    assert p["axis"]["face_center"] == pytest.approx([sc.X, sc.Y, sc.Z], abs=0.01), p
    assert "bore" in p["axis_words"] or "axis" in p["axis_words"], p["axis_words"]

    # and the plate's top face, which the RESULT body shares though its
    # centroid moved when the pattern punched two more holes in it
    top = max((f for f in doc._parts["pat"].faces()
               if f.geom_type == b3d.GeomType.PLANE
               and abs(f.normal_at(f.center()).Z - 1) < 1e-6),
              key=lambda f: f.center().Z)
    p = plan_with(pick_of(top))
    assert p["ok"] and p["axis_words"] == "normal of the top face through its centre", p

    # a click on nothing at all
    p = plan_with({"center": [200, 0, 0], "normal": [0, 0, 1]})
    assert not p["ok"] and "that face is not on hole1" in p["error"], p


# ---------------------------------------------------------------------------
# A pattern fed a SKETCH  (LAUNCH-PLAN §10, measured 2026-09-11 and 2026-09-17,
# probes/s10_pattern_kind_probe.py). It answered with a diagnosis about a shape
# the user never asked for:
#   "linear_pattern: the pattern leaves a broken solid (non-positive volume (0)
#    — empty solid) — a copy touches the body along an edge only; a smaller
#    count, a shorter distance, or another direction"
# The combiners have refused a wrong-KIND input BY NAME since §4 and the
# sketch-consuming modifiers since §7; these are the same family, in the
# opposite direction.
# ---------------------------------------------------------------------------

CIRCLE_ENTS = [{"kind": "circle", "x": 0, "y": 0, "r": 5, "mode": "add"}]
TWO_CIRCLE_ENTS = [{"kind": "circle", "x": -15, "y": 0, "r": 5, "mode": "add"},
                   {"kind": "circle", "x": 15, "y": 0, "r": 5, "mode": "add"}]
KIND_KERNEL_WORDS = ("Standard_", "StdFail", "TopoDS", "BRep_API", "NCollection",
                     "empty solid", "non-positive")


def _sketch_then(op, params, entities=None):
    d = Document(name="k")
    d.add("s1", "sketch",
          {"entities": entities or CIRCLE_ENTS, "plane": "XY", "offset": 0.0}, [])
    d.add("p1", op, params, ["s1"])
    d.rebuild()
    return d.get("p1")


@pytest.mark.parametrize("op,params", [
    ("linear_pattern", {"count": 3, "dx": 20}),
    ("polar_pattern", {"count": 4}),
])
def test_a_pattern_fed_a_sketch_is_refused_by_name(op, params):
    f = _sketch_then(op, params)
    assert f.status == "failed"
    msg = " ".join(f.problems)
    assert msg == (f"{op} repeats a SOLID body, and 's1' is a sketch — "
                   f"extrude or revolve it first, then {op} the body")
    assert not any(w in msg for w in KIND_KERNEL_WORDS), msg


def test_a_sketch_of_disjoint_islands_is_refused_the_same_way():
    """The gate tests SOLIDS and AREA, never `is_sketch`: disjoint entities can
    compose into a Compound that is not a Sketch instance, and the §7 gate
    lets exactly those extrude."""
    f = _sketch_then("linear_pattern", {"count": 3, "dx": 40}, TWO_CIRCLE_ENTS)
    assert f.status == "failed"
    assert "is a sketch" in " ".join(f.problems)


def test_the_pattern_refusal_beats_the_axis_check_to_it():
    """The kind of the input is the more basic fact: a sketch patterned about
    a bad axis used to be told about the axis, which is not the problem."""
    f = _sketch_then("polar_pattern", {"count": 4, "axis": "Z"})
    assert "is a sketch" in " ".join(f.problems)


@pytest.mark.parametrize("op,params,want", [
    ("linear_pattern", {"count": 3, "dx": 20}, 6000.0),
    ("polar_pattern", {"count": 4, "axis": "+z"}, 2000.0),
    ("mirror", {"plane": "YZ"}, 2000.0),
])
def test_a_pattern_of_a_solid_still_builds(op, params, want):
    d = Document(name="s")
    d.add("b1", "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
    d.add("p1", op, params, ["b1"])
    assert d.rebuild() is True, d.get("p1").problems
    assert d.get("p1").volume == pytest.approx(want, abs=0.01)


@pytest.mark.parametrize("op,params", [
    ("mirror", {"plane": "YZ"}),
    ("scale", {"factor": 2}),
    ("rotate", {"axis": "Z", "angle_deg": 45}),
])
def test_the_gate_does_not_widen_to_the_ops_that_move_a_sketch(op, params):
    """Measured: `mirror`, `scale` and `rotate` all take a sketch and answer
    with a sketch. Refusing them would take away work that is correct today,
    which is why SOLID_REPEATING_MODIFIERS is pattern.PATTERN_OPS and not
    pattern.SEEDED_OPS."""
    f = _sketch_then(op, params)
    assert f.status == "ok", f.problems


# --- review of eed6a33: the gate stopped one op short -------------------------
# `mirror` was left out because it "mirrors a SKETCH correctly (status ok)".
# That is true of the mirror that RETURNS THE COPY. With join=true mirror fuses
# the body with its reflection through pattern._body_pattern — the very
# function the two pattern ops use — so a sketch there answered with the same
# diagnosis about a solid the user never asked for (measured 2026-09-17,
# probes/s10_pattern_gate_review_probe.py §1):
#   "mirror: the mirror image leaves a broken solid (non-positive volume (0)
#    — empty solid) — it touches the body along an edge only; pick another
#    plane"

def test_mirror_with_join_fed_a_sketch_is_refused_by_name_too():
    f = _sketch_then("mirror", {"plane": "YZ", "join": True})
    assert f.status == "failed"
    msg = " ".join(f.problems)
    assert msg == ("mirror with join fuses a SOLID body with its reflection, "
                   "and 's1' is a sketch — extrude or revolve it first, then "
                   "mirror the body (without join it returns the reflected "
                   "sketch)")
    assert not any(w in msg for w in KIND_KERNEL_WORDS), msg


def test_mirror_with_join_of_a_solid_still_joins():
    """The other direction of the same flag: join on a BODY is untouched."""
    d = Document(name="j")
    d.add("b1", "plate", {"width": 20, "depth": 20, "thickness": 5}, [])
    d.add("m1", "move", {"x": 30}, ["b1"])
    d.add("j1", "mirror", {"plane": "YZ", "join": True}, ["m1"])
    assert d.rebuild() is True, d.get("j1").problems
    assert d.get("j1").volume == pytest.approx(4000.0, abs=0.01)


def test_a_seeded_mirror_keeps_its_own_sentence():
    """join is ignored when a seed is named (pattern.mirror branches on the
    seed first), so the gate must not step in front of the seed's own,
    accurate refusal."""
    f = _sketch_then("mirror", {"plane": "YZ", "join": True, "seed": "s1"})
    assert f.status == "failed"
    assert "is not a feature to repeat" in " ".join(f.problems), f.problems


def test_a_falsey_join_still_mirrors_a_sketch():
    """The gate asks the same question `pattern.mirror` asks (`if not join`),
    so the two can never disagree about what join means."""
    for falsey in (False, 0, None, ""):
        f = _sketch_then("mirror", {"plane": "YZ", "join": falsey})
        assert f.status == "ok", (falsey, f.problems)
