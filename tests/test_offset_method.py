"""The OFFSET METHOD (user mandate 2026-08-27).

Every design is built base-first, and every sketch after the base lives on a
FACE of the current body with its depth stated as an offset FROM that face —
never as an absolute Z. Before this rule, 251 of the 274 sketches in the
designs/ folder hardcoded an absolute Z, so changing a base thickness left
every downstream feature stranded at the wrong height and the user had to
re-derive dozens of numbers by hand.

These tests lock in the three things that make the method work:
  * a face can be named ("top", "+x") so authoring never invents a coordinate,
  * `offset` means the same thing on EVERY face (negative = into the material),
  * the sketch RIDES the face when an upstream dimension changes.
"""
import pytest

import blocks
import sketch as sk
import inspector
import author
from document import Document


# ---------------------------------------------------------------------------
# naming a face instead of computing its centre
# ---------------------------------------------------------------------------

def test_named_face_directions_point_the_right_way():
    box = blocks.plate(40, 30, 12)            # centred: top at z=+6
    expect = {"top": (0, 0, 1), "bottom": (0, 0, -1),
              "+x": (1, 0, 0), "-x": (-1, 0, 0),
              "front": (0, -1, 0), "back": (0, 1, 0)}
    for name, (dx, dy, dz) in expect.items():
        pl = sk.face_plane(sk.named_face(box, name))
        assert (pl.z_dir.X, pl.z_dir.Y, pl.z_dir.Z) == pytest.approx(
            (dx, dy, dz), abs=1e-6), name


def test_named_face_takes_the_OUTERMOST_face_not_a_pocket_floor():
    """A part with a pocket has two upward-facing faces. "top" must be the
    outer one — otherwise every later feature would quietly sink into the
    first pocket that got cut."""
    doc = Document(name="pocketed")
    doc.add("base_sketch", "sketch",
            {"plane": "XY", "entities": [{"kind": "rectangle", "w": 40, "h": 30}]})
    doc.add("base", "extrude", {"amount": 12}, inputs=["base_sketch"])
    doc.add("pocket_sketch", "sketch_on_face",
            {"face": "top", "entities": [{"kind": "rectangle", "w": 20, "h": 10}]},
            inputs=["base"])
    doc.add("pocket_tool", "extrude", {"amount": 3, "flip": True},
            inputs=["pocket_sketch"])
    doc.add("pocket", "cut", inputs=["base", "pocket_tool"])
    assert doc.rebuild(), doc.tree()
    part = doc.result()
    assert sk.named_face(part, "top").center().Z == pytest.approx(12, abs=1e-6)
    # and it is the outer ring (40*30 - 20*10), not the 200mm2 pocket floor
    assert sk.named_face(part, "top").area == pytest.approx(1000, rel=1e-6)


def test_named_face_rejects_a_direction_that_is_not_one():
    with pytest.raises(ValueError, match="not a direction"):
        sk.named_face(blocks.plate(40, 30, 12), "topp")


def test_sketch_on_face_needs_some_way_to_say_which_face():
    with pytest.raises(ValueError, match="face="):
        sk.sketch_on_face(blocks.plate(40, 30, 12),
                          entities=[{"kind": "circle", "r": 4}])


# ---------------------------------------------------------------------------
# what `offset` and `flip` mean — the SAME thing on every face
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("face", ["top", "bottom", "+x", "-x", "front", "back"])
def test_negative_offset_goes_INTO_the_material_on_every_face(face):
    box = blocks.plate(40, 30, 12)
    f = sk.named_face(box, face)
    n = sk.face_plane(f).z_dir
    at_face = sk.sketch_on_face(box, face=face,
                                entities=[{"kind": "circle", "r": 4}])
    inside = sk.sketch_on_face(box, face=face, offset=-3.0,
                               entities=[{"kind": "circle", "r": 4}])
    outside = sk.sketch_on_face(box, face=face, offset=+2.0,
                                entities=[{"kind": "circle", "r": 4}])
    reach = lambda s: (s.center().X * n.X + s.center().Y * n.Y
                       + s.center().Z * n.Z)
    assert reach(inside) == pytest.approx(reach(at_face) - 3.0, abs=1e-6)
    assert reach(outside) == pytest.approx(reach(at_face) + 2.0, abs=1e-6)


@pytest.mark.parametrize("face", ["top", "bottom", "+x", "front"])
def test_flip_always_means_into_the_body(face):
    """The reason the method is teachable: a pocket is `flip: true` whichever
    face it is on. No per-face sign reasoning, so no per-face sign mistakes."""
    box = blocks.plate(40, 30, 12)
    s = sk.sketch_on_face(box, face=face,
                          entities=[{"kind": "circle", "r": 4}])
    boss = sk.extrude_sketch(s, amount=4.0)              # out into the air
    pocket = sk.extrude_sketch(s, amount=4.0, flip=True)  # into the material
    assert (box + boss).volume > box.volume + 100    # boss added material
    assert (box - pocket).volume < box.volume - 100  # pocket removed material


def test_through_cut_from_a_named_face_clears_the_part():
    doc = Document(name="thru")
    doc.add("base_sketch", "sketch",
            {"plane": "XY", "entities": [{"kind": "rectangle", "w": 40, "h": 30}]})
    doc.add("base", "extrude", {"amount": 12}, inputs=["base_sketch"])
    doc.add("bore_sketch", "sketch_on_face",
            {"face": "top", "entities": [{"kind": "circle", "r": 5}]},
            inputs=["base"])
    doc.add("bore_tool", "extrude", {"through": True, "flip": True, "amount": 1},
            inputs=["bore_sketch"])
    doc.add("part", "cut", inputs=["base", "bore_tool"])
    doc.spec = {"n_solids": 1}
    assert doc.rebuild(), doc.tree()
    got = doc.result()
    assert len(got.solids()) == 1                    # nothing left floating
    import math
    assert got.volume == pytest.approx(40 * 30 * 12 - math.pi * 25 * 12, rel=1e-3)


# ---------------------------------------------------------------------------
# the payoff: features RIDE the geometry
# ---------------------------------------------------------------------------

def test_pocket_stays_at_its_depth_when_the_base_thickness_changes():
    """The whole reason for the mandate. A 3mm pocket in the top face must
    still be 3mm deep in the top face after the base grows — with the old
    absolute-offset style the same edit buried it inside the material."""
    import math
    doc = Document(name="rides")
    doc.add("base_sketch", "sketch",
            {"plane": "XY", "entities": [{"kind": "rectangle", "w": 40, "h": 30}]})
    doc.add("base", "extrude", {"amount": 12}, inputs=["base_sketch"])
    doc.add("pocket_sketch", "sketch_on_face",
            {"face": "top", "entities": [{"kind": "circle", "r": 5}]},
            inputs=["base"])
    doc.add("pocket_tool", "extrude", {"amount": 3, "flip": True},
            inputs=["pocket_sketch"])
    doc.add("part", "cut", inputs=["base", "pocket_tool"])
    doc.spec = {"n_solids": 1}
    assert doc.rebuild(), doc.tree()
    assert doc.result().volume == pytest.approx(
        40 * 30 * 12 - math.pi * 25 * 3, rel=1e-3)

    doc.features[1].params["amount"] = 20            # ONLY the base thickness
    assert doc.rebuild(), doc.tree()
    assert doc.result().volume == pytest.approx(
        40 * 30 * 20 - math.pi * 25 * 3, rel=1e-3)
    # the pocket followed the face: still open at the new top, still 3mm deep
    assert inspector.measure(doc.result())["size"][2] == pytest.approx(20, abs=0.1)
    assert sk.named_face(doc.result(), "top").center().Z == pytest.approx(
        20, abs=1e-6)


def test_a_feature_offset_from_a_face_follows_it_too():
    """A pilot hole starting at a 3mm recess floor is authored as offset -3
    from the TOP face, so it tracks the top face rather than an absolute Z."""
    box12 = blocks.plate(40, 30, 12)                 # top at +6
    box20 = blocks.plate(40, 30, 20)                 # top at +10
    z = lambda b: sk.sketch_on_face(
        b, face="top", offset=-3.0,
        entities=[{"kind": "circle", "r": 1.5}]).center().Z
    assert z(box12) == pytest.approx(3.0, abs=1e-6)
    assert z(box20) == pytest.approx(7.0, abs=1e-6)   # rode the face, +8mm


# ---------------------------------------------------------------------------
# the lint that keeps the old habit out of authored trees
# ---------------------------------------------------------------------------

def _lint(features):
    doc = Document(name="lint")
    for f in features:
        doc.add(f["id"], f["op"], f.get("params") or {}, f.get("inputs") or [])
    return author.lint_tree(doc.features)


_BASE = [
    {"id": "base_sketch", "op": "sketch",
     "params": {"plane": "XY", "offset": 0,
                "entities": [{"kind": "rectangle", "w": 40, "h": 30}]}},
    {"id": "base", "op": "extrude", "inputs": ["base_sketch"],
     "params": {"amount": 12}},
]


def test_lint_rejects_an_absolute_offset_sketch_once_a_body_exists():
    probs = _lint(_BASE + [
        {"id": "pocket_sketch", "op": "sketch",
         "params": {"plane": "XY", "offset": 9.0,
                    "entities": [{"kind": "circle", "r": 5}]}},
        {"id": "pocket_tool", "op": "extrude", "inputs": ["pocket_sketch"],
         "params": {"amount": 3}},
        {"id": "pocket", "op": "cut", "inputs": ["base", "pocket_tool"]},
    ])
    assert probs and "floats at absolute Z" in probs[0]
    assert "sketch_on_face" in probs[0]      # the message must say the fix


def test_lint_passes_the_offset_method():
    assert _lint(_BASE + [
        {"id": "pocket_sketch", "op": "sketch_on_face", "inputs": ["base"],
         "params": {"face": "top", "offset": 0,
                    "entities": [{"kind": "circle", "r": 5}]}},
        {"id": "pocket_tool", "op": "extrude", "inputs": ["pocket_sketch"],
         "params": {"amount": 3, "flip": True}},
        {"id": "pocket", "op": "cut", "inputs": ["base", "pocket_tool"]},
    ]) == []


def test_lint_still_allows_the_base_sketch_to_carry_an_offset():
    """Before any body exists there is no face to reference, so a principal
    plane with an offset is the only way to say it — and legitimate."""
    assert _lint([
        {"id": "base_sketch", "op": "sketch",
         "params": {"plane": "XY", "offset": 5.0,
                    "entities": [{"kind": "rectangle", "w": 40, "h": 30}]}},
        {"id": "base", "op": "extrude", "inputs": ["base_sketch"],
         "params": {"amount": 12}},
    ]) == []


def test_the_authoring_prompt_teaches_the_method():
    """A rule nothing states is a rule that gets forgotten next design."""
    p = author.AUTHOR_PROMPT
    assert "OFFSET METHOD" in p
    assert "BASE FIRST" in p
    assert 'sketch_on_face' in p and '"face":"top"' in p
    assert '"flip":true' in p and '"through":true' in p
    # the op catalogue the model actually reads must carry the convention note
    cat = {o["op"]: o for o in author.op_catalog()}
    assert "offset method" in (cat["sketch_on_face"]["note"] or "")
    assert "face" in [pp["name"] for pp in cat["sketch_on_face"]["params"]]
    assert "offset" in [pp["name"] for pp in cat["sketch_on_face"]["params"]]
    assert "flip" in [pp["name"] for pp in cat["extrude"]["params"]]
