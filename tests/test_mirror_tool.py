"""Mirror (LAUNCH-PLAN.md P4, specs/mirror.md): the `mirror` op that existed,
grown to mirror a FEATURE — its delta (before − after cut again, after − before
fused again) reflected across a plane on the body's current state — or a BODY
fused with its reflection (Fusion's Join), the legacy copy-only call kept; plus
the planner that hands the tool its plane in stored form, the gold quad and
the alternatives.

probes/mirror_probe.py (2026-09-06) found in the kernel:

    Part.mirror(Plane)                 -> a valid solid of positive volume, in place
    a plug reflected and cut again     -> exactly one more plug, healthy
    a plane THROUGH the seed           -> removes EXACTLY 0.0 (image ∩ seed > 0)
    a plane putting the image OFF      -> removes EXACTLY 0.0 (image ∩ seed = 0)
    a body across its own face, fused  -> one solid, twice the volume
    a body across its mid-plane        -> itself (never refused: rebuild safety)
    an image tangent to an edge        -> an OPEN SHELL is_valid calls fine

Every geometric claim is checked against the kernel: volumes against formulas,
image positions against the centroids of the material that went away.
"""
import math

import build123d as b3d
import pytest
from build123d import Cylinder, Location, Pos

import inspector
import pattern
import sketch as sk
import toolplan
from document import Document, MODIFIERS, REF_PARAMS, op_params

PI = math.pi
PLUG = PI * 9 * 12                       # a ⌀6 through hole in 12 mm
BOX = 80 * 80 * 12
TOP = dict(face_center=[0.0, 0.0, 6.0], face_normal=[0.0, 0.0, 1.0])


def box(w=80.0, d=80.0, t=12.0):
    return b3d.Box(w, d, t)              # centred on the origin: top face at z = 6


def holed(b=None, at=(20, 10), d=6):
    b = b if b is not None else box()
    return b, sk.hole(b, **TOP, at=list(at), diameter=d, depth=1, through=True)


def healthy(part):
    assert inspector.health(part) == []
    return part


def lumps_xy(before, after):
    """where the material went: the (x, y) centroid of every separate lump"""
    gone = before - after
    return sorted((round(s.center().X, 3), round(s.center().Y, 3)) for s in gone.solids())


def mirrored(b, h, plane, seed="hole1"):
    return pattern.mirror(h, plane, seed=seed, _before=b, _after=h)


# ------------------------------------------------------------------- the op ---

def test_a_holes_delta_is_reflected_exactly():
    b, h = holed()
    out = healthy(mirrored(b, h, "YZ"))
    assert b.volume - out.volume == pytest.approx(2 * PLUG, rel=1e-6)
    assert lumps_xy(b, out) == [(-20.0, 10.0), (20.0, 10.0)]
    assert len(out.solids()) == 1


@pytest.mark.parametrize("plane, at", [
    ("XZ", [(20.0, -10.0), (20.0, 10.0)]),                          # an origin plane
    ("yz", [(-20.0, 10.0), (20.0, 10.0)]),                          # case does not matter
    ({"mid": "Y"}, [(20.0, -10.0), (20.0, 10.0)]),                  # the body's mid-plane (= XZ here)
    ({"origin": [5, 0, 0], "normal": [-2, 0, 0]}, [(-10.0, 10.0), (20.0, 10.0)]),   # explicit, flipped normal
])
def test_every_plane_form_moves_the_image_where_the_plane_says(plane, at):
    b, h = holed()
    out = healthy(mirrored(b, h, plane))
    assert lumps_xy(b, out) == at


def test_plane_of_resolves_every_stored_form_with_words():
    b = box()
    pl, words = pattern.plane_of(b, {"face": "+x"})
    assert list(pl.origin) == pytest.approx([40, 0, 0]) and abs(pl.z_dir.X) == pytest.approx(1)
    assert words == "the +x face's plane"
    pl, words = pattern.plane_of(b, {"face_center": [0, 0, 6], "face_normal": [0, 0, 1]})
    assert list(pl.origin) == pytest.approx([0, 0, 6]) and words == "the top face's plane"
    pl, words = pattern.plane_of(Pos(10, 0, 0) * b, {"mid": "x"})
    assert list(pl.origin) == pytest.approx([10, 0, 0]) and words == "the body's mid-plane across X"
    pl, words = pattern.plane_of(b, "xz")
    assert abs(pl.z_dir.Y) == pytest.approx(1) and words == "the XZ plane (through the origin)"
    pl, words = pattern.plane_of(b, {"origin": [1, 2, 3], "normal": [0, 0, 2]})
    assert list(pl.origin) == pytest.approx([1, 2, 3]) and pl.z_dir.Z == pytest.approx(1)
    assert words.startswith("the plane through (1, 2, 3)")


def test_a_boss_added_material_is_fused_again():
    b = box()
    bossed = b + Cylinder(5, 8).move(Location((20, 10, 10)))
    out = healthy(pattern.mirror(bossed, "YZ", seed="boss", _before=b, _after=bossed))
    assert out.volume - bossed.volume == pytest.approx(PI * 25 * 8, rel=1e-6)
    assert [round(s.center().X, 3) for s in (out - bossed).solids()] == [-20.0]


def test_a_fillet_sliver_rounds_the_opposite_corner():
    b = box()
    corner = [e for e in b.edges().filter_by(b3d.Axis.Z) if e.center().X > 0 and e.center().Y > 0]
    fil = b.fillet(3, corner)
    out = healthy(pattern.mirror(fil, "YZ", seed="fil", _before=b, _after=fil))
    assert len(fil.faces()) == 7 and len(out.faces()) == 8
    assert fil.volume - out.volume == pytest.approx(b.volume - fil.volume, rel=1e-6)


def test_a_body_joins_with_its_reflection_and_the_legacy_call_returns_the_copy():
    half = Pos(20, 0, 0) * b3d.Box(40, 30, 12)                     # x in [0, 40]
    join = healthy(pattern.mirror(half, {"face": "+x"}, join=True))
    assert join.volume == pytest.approx(2 * half.volume) and len(join.solids()) == 1
    assert len(join.faces()) == 6                                  # one box, twice as long
    same = healthy(pattern.mirror(half, {"mid": "X"}, join=True))  # its own symmetry plane: itself
    assert same.volume == pytest.approx(half.volume) and len(same.solids()) == 1
    copy = pattern.mirror(half, "YZ")                              # legacy: the copy alone
    assert copy.volume == pytest.approx(half.volume)
    assert list(copy.center()) == pytest.approx([-20, 0, 0])
    apart = pattern.mirror(half, {"origin": [50, 0, 0], "normal": [1, 0, 0]}, join=True)
    assert len(apart.solids()) == 2                                # separate pieces: reported, not refused


@pytest.mark.parametrize("plane, said", [
    ("ZZ", "is not an origin plane"),
    (5, 'plane must be "XY", "XZ" or "YZ"'),
    ({"mid": "W"}, 'mid must be "X", "Y" or "Z"'),
    ({"normal": [0, 0, 0]}, "must not be the zero vector"),
    ({"face": "sideways"}, "the plane face is gone — face 'sideways' is not a direction"),
    ({"face": "+x"}, "the mirror image of 'hole1' lands off the body"),
    ({"origin": [20, 0, 0], "normal": [1, 0, 0]}, "the mirror image of 'hole1' is the seed itself"),
    ({"origin": [28.5, 0, 0], "normal": [1, 0, 0]}, "leaves a broken solid"),   # tangent to x = 40
])
def test_refusals_are_sentences(plane, said):
    b, h = holed()
    with pytest.raises(ValueError, match="^mirror: ") as e:
        mirrored(b, h, plane)
    assert said in str(e.value)


def test_a_curved_face_is_not_a_plane_and_a_seed_needs_its_bodies():
    b, h = holed()
    wall = next(f for f in h.faces() if f.geom_type == b3d.GeomType.CYLINDER)
    c, n = wall.center(), wall.normal_at(wall.center())
    with pytest.raises(ValueError, match="the picked face is CYLINDER"):
        pattern.plane_of(h, {"face_center": list(c), "face_normal": list(n)})
    with pytest.raises(ValueError, match="needs its before / after bodies"):
        pattern.mirror(h, "YZ", seed="hole1")
    with pytest.raises(ValueError, match="neither removed nor added material — there is nothing to mirror"):
        pattern.mirror(b, "YZ", seed="nop", _before=b, _after=b)


def test_an_added_image_inside_the_body_is_refused():
    b = box()
    bossed = b + Cylinder(5, 8).move(Location((20, 10, 10)))      # z in [6, 14], on the top
    # the plate's top plane (named "top" would now be the BOSS's top, z = 14)
    with pytest.raises(ValueError, match="adds nothing \\(it lies inside the body\\)"):
        pattern.mirror(bossed, {"face_center": [0, 0, 6], "face_normal": [0, 0, 1]},
                       seed="boss", _before=b, _after=bossed)


def test_the_document_wires_the_op_and_hides_its_own_parameters():
    assert MODIFIERS["mirror"] is pattern.mirror
    assert REF_PARAMS["mirror"] == ("seed",)
    assert "mirror" in pattern.SEEDED_OPS
    names = [n for n, _default in op_params("mirror")]
    assert set(names) >= {"plane", "seed", "join"} and not any(n.startswith("_") for n in names)


# ------------------------------------------------------------ the document ---

def doc_with_hole(at=(20, 10)):
    doc = Document("t")
    doc.add("box1", "plate", {"width": 80, "depth": 80, "thickness": 12})
    doc.add("hole1", "hole", {"face": "top", "at": list(at), "diameter": 6, "through": True,
                              "depth": 1}, inputs=["box1"])
    return doc


def doc_with_mirror(plane="YZ"):
    doc = doc_with_hole()
    doc.add("mirror1", "mirror", {"seed": "hole1", "plane": plane, "join": True}, inputs=["hole1"])
    return doc


def built(doc):
    assert doc.rebuild(), [f.problems for f in doc.features if f.status != "ok"]
    return doc


def test_the_document_builds_a_mirror_of_a_hole_and_it_rides_the_seed():
    doc = built(doc_with_mirror())
    f = doc.get("mirror1")
    assert f.status == "ok" and f.pieces == 1
    assert f.volume == pytest.approx(BOX - 2 * PLUG, abs=0.05)
    assert lumps_xy(doc._parts["box1"], doc._parts["mirror1"]) == [(-20.0, 10.0), (20.0, 10.0)]
    doc.edit("hole1", "at", [30, 10])                              # move the seed: the image follows
    built(doc)
    assert lumps_xy(doc._parts["box1"], doc._parts["mirror1"]) == [(-30.0, 10.0), (30.0, 10.0)]
    doc.edit("mirror1", "plane", "XZ")                             # change the plane: the image moves
    built(doc)
    assert lumps_xy(doc._parts["box1"], doc._parts["mirror1"]) == [(30.0, -10.0), (30.0, 10.0)]


def test_a_folded_pocket_mirrors_as_one_feature():
    """the seed resolver is Pattern's: a pulled tool with its folded cut"""
    doc = doc_with_hole()
    doc.add("sk1", "sketch_on_face", {"face": "top", "entities": [
        {"kind": "circle", "x": 20, "y": -20, "r": 3}]}, inputs=["hole1"])
    doc.add("ex1", "extrude", {"amount": 5, "flip": True}, inputs=["sk1"])
    doc.add("cut1", "cut", {}, inputs=["hole1", "ex1"])
    doc.add("mirror1", "mirror", {"seed": "ex1", "plane": "YZ", "join": True}, inputs=["cut1"])
    built(doc)
    assert doc.delta_features("ex1") == ("hole1", "cut1")
    assert doc.get("cut1").volume - doc.get("mirror1").volume == pytest.approx(PI * 9 * 5, abs=0.05)
    assert lumps_xy(doc._parts["cut1"], doc._parts["mirror1"]) == [(-20.0, -20.0)]


def test_a_seed_off_the_bodys_history_and_a_body_named_as_seed_are_refused():
    doc = doc_with_hole()
    doc.add("box2", "plate", {"width": 20, "depth": 20, "thickness": 5})
    doc.add("m1", "mirror", {"seed": "hole1", "plane": "YZ"}, inputs=["box2"])
    doc.add("m2", "mirror", {"seed": "box1", "plane": "YZ"}, inputs=["hole1"])
    doc.rebuild()
    assert "not part of box2's history — mirror works on a feature" in doc.get("m1").problems[0]
    assert "is a whole body, not a feature of one" in doc.get("m2").problems[0]


def test_a_failing_plane_is_a_failed_feature_with_a_sentence_never_a_wrong_body():
    doc = built(doc_with_mirror())
    doc.edit("mirror1", "plane", {"face": "+x"})                   # the image lands off the plate
    assert not doc.rebuild()
    f = doc.get("mirror1")
    assert f.status == "failed" and "lands off the body" in f.problems[0]


def test_renaming_striking_and_deleting_a_seed_walk_the_mirror():
    doc = built(doc_with_mirror())
    doc.rename("hole1", "pin")
    assert doc.get("mirror1").params["seed"] == "pin"
    built(doc)
    doc.strike("pin")
    assert doc.get("mirror1").suppressed
    built(doc)
    assert doc._parts["mirror1"].volume == pytest.approx(BOX, abs=0.05)   # both gone: the plate whole
    doc = built(doc_with_mirror())
    assert "mirror1" in doc.remove_plan("hole1")["deleted"]
    doc.remove("hole1")
    assert [f.id for f in doc.features] == ["box1"]


# ----------------------------------------------------------------- the plan ---

def test_the_plan_for_a_row_offers_the_planes_and_builds_nothing():
    doc = built(doc_with_hole())
    p = toolplan.plan(doc, {"tool": "mirror", "seed_id": "hole1"})
    assert p["ok"], p
    assert p["input"] == "hole1" and p["seed"] == "hole1" and p["op"] == "mirror"
    assert p["plane"] is None and p["frame"] is None and p["plane_name"] == ""
    assert [a["name"] for a in p["alternatives"]] == ["yz", "xz", "xy", "midx", "midy", "midz"]
    assert p["alternatives"][3]["plane"] == {"mid": "X"} and p["alternatives"][0]["plane"] == "YZ"
    # `join` is a BODY mirror's business, and this is a feature's — see
    # test_a_new_mirror_of_a_feature_is_not_planned_as_a_body_join (P0)
    assert p["params"] == {"seed": "hole1", "plane": None, "join": False}
    assert "no plane yet" in p["will_build"]
    assert p["centre"] == pytest.approx([20, 10, 0], abs=1e-3)


def test_a_click_on_an_origin_plane_or_a_face_sets_the_plane_in_stored_form():
    doc = built(doc_with_hole())
    p = toolplan.plan(doc, {"tool": "mirror", "seed_id": "hole1", "plane_pick": {"world": "YZ"}})
    assert p["plane"] == "YZ" and p["plane_name"] == "yz"
    assert p["plane_words"] == "the YZ plane (through the origin)"
    assert p["frame"]["z_dir"] == pytest.approx([1, 0, 0], abs=1e-6)
    assert p["frame"]["origin"] == pytest.approx([0, 0, 0], abs=1e-3)   # the body's centre, on the plane
    assert p["half"] == pytest.approx(60)
    assert p["params"]["plane"] == "YZ"
    p = toolplan.plan(doc, {"tool": "mirror", "seed_id": "hole1",
                            "plane_pick": {"center": [40, 0, 0], "normal": [1, 0, 0]}})
    assert p["plane"]["face_center"] == pytest.approx([40, 0, 0]) and p["plane_name"] == "face"
    assert p["alternatives"][0]["name"] == "face" and p["alternatives"][0]["label"] == "the +x face's plane"
    assert p["frame"]["origin"] == pytest.approx([40, 0, 0], abs=1e-3)
    part = doc._parts["hole1"]
    wall = next(f for f in part.faces() if f.geom_type == b3d.GeomType.CYLINDER)
    c = wall.center()
    p = toolplan.plan(doc, {"tool": "mirror", "seed_id": "hole1",
                            "plane_pick": {"center": [c.X, c.Y, c.Z], "normal": None}})
    assert not p["ok"] and "the picked face is CYLINDER" in p["error"]


def test_the_panels_choice_names_an_alternative():
    doc = built(doc_with_hole())
    p = toolplan.plan(doc, {"tool": "mirror", "seed_id": "hole1", "plane": "midy"})
    assert p["plane"] == {"mid": "Y"} and p["plane_name"] == "midy"
    assert p["plane_words"] == "the body's mid-plane across Y"
    assert p["frame"]["z_dir"] == pytest.approx([0, 1, 0], abs=1e-6)
    p = toolplan.plan(doc, {"tool": "mirror", "seed_id": "hole1", "plane": "nonsense"})
    assert p["ok"] and p["plane"] is None                          # an unknown name changes nothing


def test_the_plan_for_a_face_pick_asks_provenance_who_made_the_face():
    doc = built(doc_with_hole())
    part = doc._parts["hole1"]
    wall = next(f for f in part.faces() if f.geom_type == b3d.GeomType.CYLINDER)
    c = wall.center()
    p = toolplan.plan(doc, {"tool": "mirror", "body_id": "hole1",
                            "face_center": [c.X, c.Y, c.Z], "face_point": [c.X, c.Y, c.Z]})
    assert p["ok"] and p["seed"] == "hole1", p                    # the hole's wall -> the hole
    p = toolplan.plan(doc, {"tool": "mirror", "body_id": "hole1",
                            "face_center": [0, 0, 6], "face_normal": [0, 0, 1]})
    assert p["ok"] and p["seed"] is None and p["seed_words"] == "the body hole1"
    assert p["params"] == {"seed": None, "plane": None, "join": True}


def test_edit_reopens_on_the_stored_plane_and_a_legacy_copy_keeps_join_false():
    doc = built(doc_with_mirror("XZ"))
    p = toolplan.plan(doc, {"tool": "mirror", "feature_id": "mirror1"})
    assert p["ok"] and p["plane"] == "XZ" and p["plane_name"] == "xz"
    assert p["params"] == {"seed": "hole1", "plane": "XZ", "join": True}
    assert p["input"] == "hole1" and p["frame"]["z_dir"] == pytest.approx([0, 1, 0], abs=1e-6)
    legacy = Document("l")
    legacy.add("b", "plate", {"width": 40, "depth": 30, "thickness": 12})
    legacy.add("m", "mirror", {"plane": "YZ"}, inputs=["b"])
    built(legacy)
    p = toolplan.plan(legacy, {"tool": "mirror", "feature_id": "m"})
    assert p["ok"] and p["seed"] is None and p["seed_words"] == "the body b"
    assert p["params"] == {"seed": None, "plane": "YZ", "join": False}   # stays the copy it was
    doc.edit("mirror1", "plane", {"origin": [3, 0, 0], "normal": [1, 0, 0]})
    built(doc)
    p = toolplan.plan(doc, {"tool": "mirror", "feature_id": "mirror1"})
    assert p["plane_name"] == "stored" and p["alternatives"][0]["label"].startswith("the plane through (3, 0, 0)")


def test_a_mirror_already_built_this_session_replans_on_its_own_body():
    doc = built(doc_with_mirror())
    walked = toolplan.plan(doc, {"tool": "mirror", "seed_id": "hole1"})
    assert walked["input"] == "mirror1"                            # the tip: the tool's own output
    own = toolplan.plan(doc, {"tool": "mirror", "seed_id": "hole1", "own_id": "mirror1"})
    assert own["input"] == "hole1" and own["plane"] == "YZ" and own["params"]["join"] is True


def test_the_plan_refuses_a_sketch_and_nothing_with_a_sentence():
    doc = doc_with_hole()
    doc.add("sk1", "sketch", {"plane": "XY", "entities": [{"kind": "circle", "cx": 0, "cy": 0, "r": 3}]})
    built(doc)
    p = toolplan.plan(doc, {"tool": "mirror", "seed_id": "sk1"})
    assert not p["ok"] and "a sketch is not a feature" in p["error"]
    p = toolplan.plan(doc, {"tool": "mirror"})
    assert not p["ok"] and p["error"].startswith("Mirror needs a feature or a body to mirror")


def test_the_request_model_carries_own_id_and_plane_pick():
    """found writing specs/mirror.md: `own_id` was never a field of the HTTP
    request model, so pydantic dropped it and Pattern's replan-on-its-own-body
    fix (P4 review) never reached the server from the browser"""
    import studio
    req = studio.ToolPlanReq(tool="mirror", own_id="m", plane_pick={"world": "YZ"},
                             plane="midx").model_dump()
    assert req["own_id"] == "m" and req["plane_pick"] == {"world": "YZ"} and req["plane"] == "midx"


# ---------------------------------------------- P4 review: the five findings ---

@pytest.mark.parametrize("boom", [
    Exception("BRepAlgoAPI_Common: boom"),                      # a raw OCCT failure
    ValueError("Cannot intersect shape with empty compound"),   # build123d's own guard
])
def test_a_failed_discriminator_keeps_the_refusal_that_is_true(monkeypatch, boom):
    """`image & seed` only tells the two "it cut nothing" refusals apart, and it
    is a kernel boolean like any other. When IT fails the cut has already run
    and demonstrably removed nothing, so the honest sentence is still "lands off
    the body" — never "the kernel could not build", which blames the op for a
    boolean that succeeded, and never build123d's own ValueError raw (it went
    straight through `except ValueError: raise` with no "mirror: " prefix)."""
    b, h = holed()

    def explode(self, other):
        raise boom
    monkeypatch.setattr(b3d.Compound, "__and__", explode)     # what delta() returns

    with pytest.raises(ValueError, match="^mirror: ") as e:
        mirrored(b, h, {"origin": [200, 0, 0], "normal": [1, 0, 0]})
    assert "lands off the body (nothing to cut there)" in str(e.value)
    assert "the kernel could not build" not in str(e.value)


def face_at(part, center, normal):
    """the plan's own input: what the viewport sends for a clicked face"""
    return {"center": [float(v) for v in center], "normal": [float(v) for v in normal]}


def test_a_click_on_the_mirror_image_is_refused_not_snapped_to_another_face():
    """P4 review: the framework hands Mirror clicks on its OWN result body
    (tool.js armRepick accepts `st.featureId`), the plan resolves them on the
    body BEFORE the mirror, and sk.pick_face's nearest-centre match is
    unbounded — so a face that exists only on the image silently came back as
    some other face of the input body and the mirror re-aimed without a word.
    The clicked PLANE decides now: a face of the image lying in a plane the
    body really has still counts, the rest is refused by sentence."""
    doc = built(doc_with_hole())
    part = doc._parts["hole1"]                       # 80 x 80 x 12, x in [-40, 40]

    # a face 200 mm away is on nothing: it used to snap to the nearest face
    p = toolplan.plan(doc, {"tool": "mirror", "seed_id": "hole1",
                            "plane_pick": face_at(part, [200, 0, 0], [1, 0, 0])})
    assert not p["ok"], p
    assert "that face is not on hole1" in p["error"]
    assert "not one that only its mirror image has" in p["error"]

    # a real face of the body still resolves, in the one stored form
    p = toolplan.plan(doc, {"tool": "mirror", "seed_id": "hole1",
                            "plane_pick": face_at(part, [40, 0, 0], [1, 0, 0])})
    assert p["ok"] and p["plane"]["face_center"] == [40.0, 0.0, 0.0]
    assert p["plane_words"] == "the +x face's plane"

    # and a face the IMAGE shares with the body (the doubled plate's top) counts
    p = toolplan.plan(doc, {"tool": "mirror", "seed_id": "hole1",
                            "plane_pick": face_at(part, [70, 0, 6], [0, 0, 1])})
    assert p["ok"] and p["plane"]["face_normal"] == [0.0, 0.0, 1.0], p


# ------------------------------------------------------------------------
# The four P0 "silent wrong geometry" findings of the big P4 review, each
# reproduced by measurement first (probes/mirror_p0_probe.py).
# ------------------------------------------------------------------------

def test_mirroring_a_legacy_copy_row_means_its_BODY_not_a_body_sized_delta():
    """P0 §1. A LEGACY copy-only mirror does not add to or take from its input
    — it RE-PLACES it. Folded as a modifier its "delta" was the whole body in
    the old spot plus the whole body in the new one (measured: 16000 mm³
    removed + 16000 added of a 16000 mm³ body), so selecting such a row and
    pressing Mirror gouged a body-sized lump out of the part somewhere else
    and reported success. It folds to a BODY seed: what it produces is a body.
    The user's designs/sat-side-panel corner_dimples_diag2 is such a row."""
    doc = doc_with_hole()
    doc.add("copy1", "mirror", {"plane": {"origin": [45, 0, 0], "normal": [1, 0, 0]}},
            inputs=["hole1"])                        # the legacy call: the copy alone
    built(doc)
    assert doc.delta_features("copy1") == (None, "copy1")

    plan = toolplan.plan(doc, {"tool": "mirror", "seed_id": "copy1"})
    assert plan["ok"] and plan["seed"] is None, plan   # a body, not a feature
    assert plan["seed_words"] == "the body copy1"
    assert plan["params"]["join"] is True

    # and a design that stores such a row AS a seed is refused, not gouged
    doc.add("m2", "mirror", {"seed": "copy1", "plane": "XZ"}, inputs=["copy1"])
    assert not doc.rebuild()
    assert "is a whole body, not a feature of one" in doc.get("m2").problems[0]

    # a mirror that really does add material keeps its delta
    doc2 = doc_with_hole()
    doc2.add("half", "mirror", {"plane": {"face": "+x"}, "join": True}, inputs=["hole1"])
    built(doc2)
    assert doc2.delta_features("half") == ("hole1", "half")


def test_a_new_mirror_of_a_feature_is_not_planned_as_a_body_join():
    """P0 §2. `join` belongs to a BODY mirror. Stamped on a seeded row it was
    a loaded gun: the op branches on the truthiness of `seed`, so the moment a
    seed arrived empty the feature mirror became a whole-body Join at twice the
    size, with no complaint."""
    doc = built(doc_with_hole())
    p = toolplan.plan(doc, {"tool": "mirror", "seed_id": "hole1", "plane": "yz"})
    assert p["params"] == {"seed": "hole1", "plane": "YZ", "join": False}, p["params"]

    p = toolplan.plan(doc, {"tool": "mirror", "seed_id": "box1", "plane": "yz"})
    assert p["params"] == {"seed": None, "plane": "YZ", "join": True}, p["params"]

    # an edit still reads the STORED value: a legacy copy edited stays a copy
    doc2 = doc_with_hole()
    doc2.add("copy1", "mirror", {"plane": "YZ"}, inputs=["hole1"])
    built(doc2)
    assert toolplan.plan(doc2, {"tool": "mirror", "feature_id": "copy1"})["params"]["join"] is False
    doc3 = built(doc_with_mirror())
    assert toolplan.plan(doc3, {"tool": "mirror", "feature_id": "mirror1"})["params"]["join"] is True


def test_a_body_join_tangent_to_its_reflection_is_refused_not_returned_broken():
    """P0 §3. `_body_pattern` fused and returned with no health gate, so a
    reflection touching the body along ONE edge came back as a success:
    2 solids, `is_valid` True, an OPEN SHELL (probe §7). A failed feature
    beats a corrupt body."""
    diamond = b3d.Rot(0, 0, 45) * b3d.Box(30, 30, 10)     # its +x extreme is an edge
    edge_x = diamond.bounding_box().max.X
    with pytest.raises(ValueError) as e:
        pattern.mirror(diamond, {"origin": [edge_x, 0, 0], "normal": [1, 0, 0]}, join=True)
    assert "the mirror image leaves a broken solid" in str(e.value)
    assert "along an edge only" in str(e.value)
    assert "not manifold" in str(e.value)

    # what must still build: a reflection that meets a FACE (one solid, 2x) …
    out = healthy(pattern.mirror(box(), {"origin": [40, 0, 0], "normal": [1, 0, 0]},
                                 join=True))
    assert len(out.solids()) == 1 and float(out.volume) == pytest.approx(2 * BOX, abs=0.05)
    # … a body across its own mid-plane (itself — a saved design must rebuild) …
    same = healthy(pattern.mirror(box(), {"mid": "X"}, join=True))
    assert float(same.volume) == pytest.approx(BOX, abs=0.05)
    # … and separate pieces, which the document reports as pieces
    apart = healthy(pattern.mirror(box(), {"origin": [200, 0, 0], "normal": [1, 0, 0]},
                                   join=True))
    assert len(apart.solids()) == 2


def test_a_body_seed_is_not_offered_its_own_mid_planes():
    """P0 §4. A body's own mid-plane runs through its bounding-box centre, so
    a Join across it can never grow the part, and on a symmetric body it
    changes nothing at all while the tool still says "Mirror created"
    (measured: 19200 -> 19200 mm³). The mid-planes are the plane a FEATURE
    wants most; they are not offered for a body. A design that already stores
    one still builds and still shows it (rebuild safety)."""
    doc = built(doc_with_hole())

    def mids(p):
        return [a["name"] for a in p["alternatives"]
                if isinstance(a["plane"], dict) and a["plane"].get("mid")]

    p = toolplan.plan(doc, {"tool": "mirror", "seed_id": "hole1"})
    assert mids(p) == ["midx", "midy", "midz"]            # a FEATURE seed: kept

    p = toolplan.plan(doc, {"tool": "mirror", "seed_id": "box1"})
    assert p["seed"] is None and mids(p) == []
    assert [a["name"] for a in p["alternatives"]] == ["yz", "xz", "xy"]

    doc2 = doc_with_hole()
    doc2.add("m1", "mirror", {"plane": {"mid": "X"}, "join": True}, inputs=["hole1"])
    built(doc2)                                            # it still builds …
    p = toolplan.plan(doc2, {"tool": "mirror", "feature_id": "m1"})
    assert p["ok"] and p["plane_name"] == "stored"          # … and is still offered
    assert p["plane_words"] == "the body's mid-plane across X"


def test_the_ai_is_told_every_plane_form_and_the_right_one_for_half_a_body():
    """P0 §4, the AI path. The op catalogue pinned `mirror.plane` to the three
    origin-plane names, contradicting its own note, and the prompt recommended
    a mid-plane for "model one half" — the one plane that cannot grow a body."""
    import author
    mirror_op = next(e for e in author.op_catalog() if e["op"] == "mirror")
    plane = next(p for p in mirror_op["params"] if p["name"] == "plane")
    assert "enum" not in plane, plane                      # a face / mid / origin+normal too

    seg = author.AUTHOR_PROMPT.split("model one half")[1].split('with "seed"')[0]
    assert '"face"' in seg, seg                            # the halves meet at a FACE
    assert "mid" in seg and "not" in seg.lower(), seg      # and a mid-plane is ruled out


def test_editing_a_mirror_whose_seed_stopped_resolving_never_turns_it_into_a_copy():
    """The P0 the /code-review of c4d5961 + 85821be found. On an EDIT the plan
    reads `join` from what was SAVED, and a new seeded mirror now saves
    join:False — so a row whose stored seed no longer resolves to a feature (it
    names a whole body, or a PLACEMENT row that now folds to one) came back as
    "no seed, no join": the LEGACY COPY form. Applying that replaces the body
    with a detached reflection and there is no Join row to undo it from
    (measured: an 80 mm plate moved to x 40..120, ZERO overlap with where it
    was, 76460 mm³ of part silently relocated; on the placement path, 5940 of
    that 76460 mm³ still overlapped — probes/mirror_seed_collapse_probe.py).

    The stored `join` is only meaningful while the stored params and the plan
    AGREE about whether there is a seed; when they disagree the seed collapsed,
    and a body mirror is a JOIN."""
    doc = doc_with_hole()
    doc.add("m1", "mirror", {"seed": "box1", "plane": {"face": "+x"}, "join": False},
            inputs=["hole1"])                      # a seed that names a BODY
    doc.rebuild()
    assert doc.get("m1").status == "failed"         # the op says so, correctly
    assert "is a whole body, not a feature of one" in doc.get("m1").problems[0]

    p = toolplan.plan(doc, {"tool": "mirror", "feature_id": "m1"})
    assert p["ok"] and p["seed"] is None, p
    assert p["params"]["join"] is True, p["params"]  # a JOIN, never the copy

    # applying the plan keeps the body where it is
    out = pattern.mirror(doc._parts["hole1"], p["params"]["plane"],
                         seed=None, join=p["params"]["join"])
    kept = float((doc._parts["hole1"] & out).volume)
    assert kept == pytest.approx(float(doc._parts["hole1"].volume), rel=1e-6)

    # the SECOND collapse path the docstring names: the stored seed is a
    # PLACEMENT row (rotate / scale / a legacy copy-only mirror). Those fold to
    # a BODY seed — delta_features' own P0 — so the plan finds no feature where
    # the stored params claim one, and the legacy copy form would have carried
    # 92% of the part away (measured: only 5940 of 76460 mm³ still overlapping).
    placed = doc_with_hole()
    placed.add("rot", "rotate", {"axis": "Z", "angle_deg": 30}, inputs=["hole1"])
    placed.add("mp", "mirror", {"seed": "rot", "join": False,
                                "plane": {"origin": [40, 0, 0], "normal": [1, 0, 0]}},
               inputs=["rot"])
    placed.rebuild()
    assert placed.delta_features("rot") == (None, "rot")    # a placement seeds a BODY
    assert placed.get("mp").status == "failed"               # the op says so, correctly
    assert "is a whole body, not a feature of one" in placed.get("mp").problems[0]

    p = toolplan.plan(placed, {"tool": "mirror", "feature_id": "mp"})
    assert p["ok"] and p["seed"] is None, p
    assert p["params"]["join"] is True, p["params"]  # a JOIN here too, never the copy

    body = placed._parts["rot"]
    out = pattern.mirror(body, p["params"]["plane"], seed=None, join=True)
    assert float((body & out).volume) == pytest.approx(float(body.volume), rel=1e-6)
    copy = pattern.mirror(body, p["params"]["plane"], seed=None, join=False)
    assert float((body & copy).volume) < 0.1 * float(body.volume)   # what a copy would cost

    # the boundary the fix must not move: the stored value still rules
    # wherever the stored params and the plan agree
    legacy = Document("l")
    legacy.add("b", "plate", {"width": 40, "depth": 30, "thickness": 12})
    legacy.add("copy1", "mirror", {"plane": "YZ"}, inputs=["b"])       # no seed, no join
    built(legacy)
    p = toolplan.plan(legacy, {"tool": "mirror", "feature_id": "copy1"})
    assert p["params"] == {"seed": None, "plane": "YZ", "join": False}   # stays a copy

    seeded = built(doc_with_mirror())               # stored seed + join:True
    p = toolplan.plan(seeded, {"tool": "mirror", "feature_id": "mirror1"})
    assert p["params"]["seed"] == "hole1" and p["params"]["join"] is True

    doc2 = doc_with_hole()                          # stored seed + join:False (what the tool writes now)
    doc2.add("m2", "mirror", {"seed": "hole1", "plane": "YZ", "join": False}, inputs=["hole1"])
    built(doc2)
    p = toolplan.plan(doc2, {"tool": "mirror", "feature_id": "m2"})
    assert p["params"] == {"seed": "hole1", "plane": "YZ", "join": False}
