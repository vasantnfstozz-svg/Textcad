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

# A face supplies the plane's POSITION; its ORIENTATION is always the part's
# own. Chasing one sign rule for "into the material" on every face was the
# first attempt (2026-08-27) and it cost a silent MIRROR: a right-handed frame
# whose normal points -Z has to flip an in-plane axis, so the esp32 cavity came
# out mirrored in y and non-manifold. Coordinates that never move matter more
# than signs that never change.

@pytest.mark.parametrize("face", ["top", "bottom", "+x", "-x", "front", "back"])
def test_coordinates_never_mirror_on_any_face(face):
    """The property the whole method rests on: an entity authored at (x, y)
    lands at the same in-plane point whichever face it is drawn on. Only the
    plane's position may differ."""
    box = blocks.plate(40, 30, 12)
    pl = sk.face_sketch_plane(sk.named_face(box, face))
    s = sk.sketch_on_face(box, face=face,
                          entities=[{"kind": "rectangle", "w": 6, "h": 4,
                                     "x": 10, "y": 8}])
    local = pl.to_local_coords(s.center())
    assert (local.X, local.Y) == pytest.approx((10, 8), abs=1e-6),         f"{face} moved the entity to ({local.X:.2f}, {local.Y:.2f})"


@pytest.mark.parametrize("face,axis", [("top", "z"), ("bottom", "z"),
                                       ("+x", "x"), ("-x", "x"),
                                       ("front", "y"), ("back", "y")])
def test_offset_runs_along_the_canonical_axis(face, axis):
    """`offset` moves along the principal plane's normal (+Z for a Z-facing
    face, +X for X, -Y for Y) — the same direction a `plane:` sketch's offset
    moves, whichever side of the part the face is on."""
    box = blocks.plate(40, 30, 12)
    pl = sk.face_sketch_plane(sk.named_face(box, face))
    want = {"z": (0, 0, 1), "x": (1, 0, 0), "y": (0, -1, 0)}[axis]
    assert (pl.z_dir.X, pl.z_dir.Y, pl.z_dir.Z) == pytest.approx(want, abs=1e-6)
    at = sk.sketch_on_face(box, face=face,
                           entities=[{"kind": "circle", "r": 4}]).center()
    moved = sk.sketch_on_face(box, face=face, offset=3.0,
                              entities=[{"kind": "circle", "r": 4}]).center()
    delta = (moved.X - at.X, moved.Y - at.Y, moved.Z - at.Z)
    assert delta == pytest.approx(tuple(3.0 * w for w in want), abs=1e-6)


def test_into_the_material_is_opposite_on_the_two_faces():
    """The cost of a non-mirroring frame, stated as a test so nobody has to
    rediscover it: a top-face pocket cuts with flip, a bottom-face one without.
    Both remove material; neither is ambiguous."""
    box = blocks.plate(40, 30, 12)                 # spans z -6 .. +6
    top = sk.sketch_on_face(box, face="top", entities=[{"kind": "circle", "r": 4}])
    bot = sk.sketch_on_face(box, face="bottom", entities=[{"kind": "circle", "r": 4}])
    assert sk.extrude_sketch(top, amount=3, flip=True).bounding_box().min.Z         == pytest.approx(6.0 - 3.0, abs=1e-6)      # from the top face, down 3
    assert sk.extrude_sketch(bot, amount=3).bounding_box().max.Z         == pytest.approx(-6.0 + 3.0, abs=1e-6)     # from the bottom face, up 3
    for solid in (sk.extrude_sketch(top, amount=3, flip=True),
                  sk.extrude_sketch(bot, amount=3)):
        assert (box - solid).volume < box.volume - 100


def test_a_bottom_face_offset_IS_a_height_above_the_bottom():
    """Why the esp32 cavity hangs off the bottom face: offset 3 means "leave a
    3mm floor", and it stays 3mm when the stock thickness changes."""
    for thickness, want_z in ((12.0, 3.0), (10.0, 3.0), (20.0, 3.0)):
        plate = blocks.plate(40, 30, thickness)    # bottom at -thickness/2
        s = sk.sketch_on_face(plate, face="bottom", offset=3.0,
                              entities=[{"kind": "circle", "r": 4}])
        above_bottom = s.center().Z - (-thickness / 2)
        assert above_bottom == pytest.approx(want_z, abs=1e-6), thickness


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


def test_lint_rejects_an_absolute_Z_routed_through_a_construction_plane():
    """The banned form with one row in between. A construction plane off a
    PRINCIPAL plane is a hardcoded absolute Z exactly as a floating sketch is —
    it rides nothing — so a sketch drawn on it once a body exists is the same
    old habit, and the exemption that keeps a plane-row sketch out of this rule
    must not cover it (code review 2026-09-23)."""
    probs = _lint(_BASE + [
        {"id": "lid_plane", "op": "offset_plane",
         "params": {"plane": "XY", "offset": 9.0}},
        {"id": "pocket_sketch", "op": "sketch",
         "params": {"plane": "lid_plane",
                    "entities": [{"kind": "circle", "r": 5}]}},
        {"id": "pocket_tool", "op": "extrude", "inputs": ["pocket_sketch"],
         "params": {"amount": 3}},
        {"id": "pocket", "op": "cut", "inputs": ["base", "pocket_tool"]},
    ])
    assert probs, "an offset_plane off XY is an absolute Z with an extra row"
    assert "lid_plane" in probs[0] and "absolute Z" in probs[0], probs
    assert "offset_plane" in probs[0] and "face" in probs[0], "say the fix"


def test_lint_passes_a_sketch_on_a_plane_measured_from_a_face():
    """The plane the exemption was written for: it has a body input, so it
    rides that face exactly as sketch_on_face does."""
    assert _lint(_BASE + [
        {"id": "floor", "op": "offset_plane", "inputs": ["base"],
         "params": {"face": "top", "offset": -3.0}},
        {"id": "pocket_sketch", "op": "sketch",
         "params": {"plane": "floor",
                    "entities": [{"kind": "circle", "r": 5}]}},
    ]) == []


def test_lint_survives_a_sketch_offset_driven_by_a_named_parameter():
    """`float("lid_z")` raised ValueError straight out of the lint, and
    `lint_baseline` runs on the USER's own document before an AI job starts —
    so asking the AI to change a design that drives a sketch offset from a
    named parameter answered "the model failed: could not convert string to
    float". A formula is a named number, not a hardcoded one (2026-09-23)."""
    doc = Document(name="lint")
    doc.set_parameter("lid_z", 9)
    for f in _BASE + [
        {"id": "pocket_sketch", "op": "sketch",
         "params": {"plane": "XY", "offset": "lid_z",
                    "entities": [{"kind": "circle", "r": 5}]}},
    ]:
        doc.add(f["id"], f["op"], f.get("params") or {}, f.get("inputs") or [])
    assert doc.rebuild(), [(f.id, f.problems) for f in doc.features]
    assert author.lint_tree(doc.features) == []
    assert author.lint_baseline(doc.features)          # no raise: the point


def test_lint_still_catches_an_absolute_offset_written_as_a_string():
    """Crash-proofing the rule must not narrow it: "9" is the hardcoded form
    spelled with quotes, and only a name it cannot evaluate is a formula."""
    probs = _lint(_BASE + [
        {"id": "pocket_sketch", "op": "sketch",
         "params": {"plane": "XY", "offset": "9",
                    "entities": [{"kind": "circle", "r": 5}]}},
    ])
    assert probs and "floats at absolute Z" in probs[0], probs


def test_a_design_that_already_floats_a_plane_does_not_refuse_the_AI_a_job():
    """`lint_baseline` runs on the USER's document: a rule about history they
    wrote is a wall the job can never get past, so the new plane rule has to
    be forgiven there exactly as the sketch rule is."""
    tree = _BASE + [
        {"id": "lid_plane", "op": "offset_plane",
         "params": {"plane": "XY", "offset": 30.0}},
        {"id": "lid_sketch", "op": "sketch",
         "params": {"plane": "lid_plane",
                    "entities": [{"kind": "circle", "r": 5}]}},
    ]
    doc = Document(name="lint")
    for f in tree:
        doc.add(f["id"], f["op"], f.get("params") or {}, f.get("inputs") or [])
    assert author.lint_tree(doc.features), "the fixture must break the new rule"
    baseline = author.lint_baseline(doc.features)
    assert author._lint_since(doc.features, baseline) == []


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


# ---------------------------------------------------------------------------
# the frame a face sketch draws in — world-aligned, and it must NOT drift
# ---------------------------------------------------------------------------

def test_face_frame_reproduces_the_principal_planes():
    """A sketch on the top face of a T-thick plate must be the same frame as
    `plane: "XY", offset: T`. That equivalence is what makes stating a depth
    from a face a safe substitute for an absolute Z rather than a new
    coordinate system to learn."""
    from build123d import Plane
    box = blocks.plate(40, 30, 12)
    for name, want in (("top", Plane.XY), ("+x", Plane.YZ), ("front", Plane.XZ)):
        pl = sk.face_sketch_plane(sk.named_face(box, name))
        for axis in ("x_dir", "y_dir", "z_dir"):
            assert getattr(pl, axis).dot(getattr(want, axis)) == pytest.approx(
                1.0, abs=1e-9), f"{name}.{axis}"


def test_a_top_face_sketch_equals_a_plane_sketch_at_that_height():
    box = blocks.plate(40, 30, 12)               # top at z=+6
    ents = [{"kind": "circle", "r": 4, "x": -11, "y": 7}]
    on_face = sk.sketch_on_face(box, face="top", entities=ents)
    on_plane = sk.make_sketch("XY", 6.0, ents)
    for a, b in zip(tuple(on_face.center()), tuple(on_plane.center())):
        assert a == pytest.approx(b, abs=1e-6)


def test_the_face_frame_does_not_follow_the_face_CENTROID():
    """build123d's Plane(face) origin IS the centroid, and the top face of a
    shell is the rim minus every pocket cut so far — so a centroid-based frame
    would shift every entity on it whenever an upstream feature changed."""
    prof = sk.make_sketch("XY", 0, [{"kind": "rectangle", "w": 60, "h": 40,
                                     "x": 0, "y": 30}])
    body = sk.extrude_sketch(prof, amount=12)
    at_origin = lambda solid: sk.sketch_on_face(
        solid, face="top", entities=[{"kind": "circle", "r": 3}]).center()

    before = at_origin(body)
    assert (before.X, before.Y, before.Z) == pytest.approx((0, 0, 12), abs=1e-6)

    # a lopsided pocket drags the top face's centroid a long way
    tool = sk.extrude_sketch(sk.sketch_on_face(
        body, face="top",
        entities=[{"kind": "rectangle", "w": 40, "h": 10, "x": 0, "y": 42}]),
        amount=3, flip=True)
    cut = body - tool
    moved = sk.named_face(cut, "top").center()
    assert moved.Y != pytest.approx(30, abs=0.5)      # the centroid DID move

    after = at_origin(cut)                            # the frame did not
    assert (after.X, after.Y, after.Z) == pytest.approx((0, 0, 12), abs=1e-6)


def test_the_ui_frame_and_the_geometry_agree():
    """/api/face-outline hands the sketcher the frame it draws in; if it ever
    disagreed with the frame the geometry is built in, everything the user
    drew would land somewhere else."""
    box = blocks.plate(40, 30, 12)
    out = sk.face_outline_2d(box, [0, 0, 6], [0, 0, 1])
    assert out["planar"]
    pl = sk.face_sketch_plane(sk.named_face(box, "top"))
    assert out["frame"]["origin"] == [pytest.approx(v, abs=1e-4)
                                      for v in (pl.origin.X, pl.origin.Y,
                                                pl.origin.Z)]
    assert out["frame"]["x_dir"] == [pytest.approx(v, abs=1e-4)
                                     for v in (pl.x_dir.X, pl.x_dir.Y,
                                               pl.x_dir.Z)]
