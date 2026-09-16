"""A face pick remembers HOW BIG the face was (LAUNCH-PLAN §10's face-pick P1).

The pick is a point and a direction in the room, so on a stepped body a change
somewhere ELSE could slide it onto a different face of the same kind: thicken
the plate under a boss from 10 mm to 14 mm and the plate top climbs to within
1 mm of a pick stored 4 mm above it, on the boss. The design then built
22800.0 mm3 where 18810.62 was asked for, with every tree row `ok` and the
solid valid — the silent kind of wrong this project exists to stop. No carry
can reach it: nothing moved, so there is no delta to add.

The size of the face is what separates them, and the click already knew it —
the server measures every face's area for the viewport's pick panel. Among the
faces still pointing the picked way, the ones still that size are the
candidates and distance decides between THEM.

The whole safety argument is that the gate FAILS OPEN, so these tests pin both
halves: it finds the boss top again (§1), it does not disturb an answer that
was already right (§2, §3), and a pick with no size behaves exactly as it did
before it existed (§4). Measured in probes/face_pick_size_gate_probe.py.
"""
import pytest

import blocks
import toolplan
from document import Document, op_params

UP = [0.0, 0.0, 1.0]
BOSS_TOP = [0.0, 0.0, 15.0]
BOSS_AREA = 201.06                      # π·8² as the viewport rounds it
PLATE_TOP_AREA = 998.94                 # 40×30 minus the boss disc


def stepped(plate_t=10.0, plate_w=40.0, boss_r=8.0, riser=None):
    """A plate with a boss on it — two faces pointing +Z, 5 mm apart. With
    `riser` the pick is USED: a prism pulled out of the face it names."""
    doc = Document(name="t-size")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": plate_w, "h": 30}]})
    doc.add("base", "extrude", {"amount": plate_t}, inputs=["outline"])
    doc.add("boss_sk", "sketch", {"plane": "XY", "offset": plate_t, "entities": [
        {"kind": "circle", "r": boss_r, "x": 0, "y": 0}]})
    doc.add("boss", "extrude", {"amount": 5}, inputs=["boss_sk"])
    doc.add("part", "fuse", {}, inputs=["base", "boss"])
    if riser is not None:
        doc.add("riser", "extrude_face", dict(riser), inputs=["part"])
        doc.add("final", "fuse", {}, inputs=["part", "riser"])
    doc.rebuild()
    return doc


def area_of(face):
    return round(float(face.area), 3)


# --------------------------------------------------------------------------
# §1 the filed case
# --------------------------------------------------------------------------

def test_a_thicker_plate_does_not_steal_a_pick_off_the_boss():
    """THE P1. 10 -> 14 mm under the boss: the pick stays on the boss top."""
    picked = {"face_center": list(BOSS_TOP), "face_normal": list(UP),
              "face_area": BOSS_AREA, "amount": 5}
    for t, want in ((10.0, 14010.619), (12.0, 16410.619),
                    (14.0, 18810.619), (18.0, 23610.619)):
        doc = stepped(plate_t=t, riser=picked)
        part = doc.result()
        assert part is not None
        assert abs(part.volume - want) < 0.01, (
            f"plate {t} mm: {part.volume:.3f} mm3, wanted {want} — the pick "
            f"left the boss")
        assert all(f.status == "ok" for f in doc.features)


def test_without_a_stored_size_the_same_edit_still_loses_the_pick():
    """The bug this closes, pinned on the OLD shape of the pick — so that if
    anyone drops the field, a red test says which failure came back."""
    bare = {"face_center": list(BOSS_TOP), "face_normal": list(UP), "amount": 5}
    assert abs(stepped(plate_t=10.0, riser=bare).result().volume - 14010.619) < 0.01
    slipped = stepped(plate_t=14.0, riser=bare).result()
    assert abs(slipped.volume - 22800.0) < 0.01     # the plate top, silently


def test_the_resolver_answers_the_boss_top_by_size_alone():
    part = stepped(plate_t=14.0)._parts["part"]
    assert area_of(blocks.resolve_face(part, BOSS_TOP, UP)) == 998.938
    assert area_of(blocks.resolve_face(part, BOSS_TOP, UP, BOSS_AREA)) == 201.062


# --------------------------------------------------------------------------
# §2 what must not change
# --------------------------------------------------------------------------

def test_identical_bosses_are_still_told_apart_by_distance():
    """Four same-size faces all pass the size gate, so the nearest must win —
    otherwise a pattern of bosses would collapse onto one pick."""
    doc = Document(name="t-four")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 80, "h": 60}]})
    doc.add("base", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("boss_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 6, "x": x, "y": y}
        for x, y in ((-25, -15), (25, -15), (-25, 15), (25, 15))]})
    doc.add("boss", "extrude", {"amount": 5}, inputs=["boss_sk"])
    doc.add("part", "fuse", {}, inputs=["base", "boss"])
    doc.rebuild()
    part = doc._parts["part"]
    for x, y in ((-25, -15), (25, -15), (-25, 15), (25, 15)):
        c = blocks.resolve_face(part, [float(x), float(y), 15.0], UP,
                                113.10).center()
        assert (round(c.X, 3), round(c.Y, 3), round(c.Z, 3)) == (x, y, 15.0)


def test_it_fails_open_when_the_picked_face_is_the_one_that_changed():
    """Widen the plate and the PLATE top's own area changes. Nothing is that
    size any more, so the gate is skipped and the old answer stands."""
    for w, want in ((40.0, 998.938), (60.0, 1598.938), (90.0, 2498.938),
                    (30.0, 698.938)):
        part = stepped(plate_w=w)._parts["part"]
        got = blocks.resolve_face(part, [0.0, 0.0, 10.0], UP, PLATE_TOP_AREA)
        assert area_of(got) == want, f"plate {w} mm wide"


def test_a_nonsense_size_is_ignored_rather_than_obeyed():
    part = stepped()._parts["part"]
    plain = blocks._shape_key(blocks.resolve_face(part, BOSS_TOP, UP))
    for junk in (None, 0, -5.0, float("nan"), float("inf"), "big", [], {}):
        got = blocks.resolve_face(part, BOSS_TOP, UP, junk)
        assert blocks._shape_key(got) == plain, f"{junk!r} changed the answer"


def test_the_size_gate_never_refuses():
    """A failed feature beats a corrupt body, but this gate is not allowed to
    be the one that fails: with no match it hands the whole list back."""
    part = stepped()._parts["part"]
    for a in (1.0, 1e6, 201.06):
        assert blocks.resolve_face(part, BOSS_TOP, UP, a) is not None


# --------------------------------------------------------------------------
# §3 the size travels with the pick
# --------------------------------------------------------------------------

def test_every_op_that_stores_a_pick_accepts_its_size():
    for op in ("sketch_on_face", "extrude_face", "revolve_face", "hole"):
        names = [n for n, _d in op_params(op)]
        assert "face_area" in names, f"{op} cannot store the size of its pick"


def test_a_stored_pick_with_a_size_survives_the_file():
    doc = stepped(riser={"face_center": list(BOSS_TOP), "face_normal": list(UP),
                         "face_area": BOSS_AREA, "amount": 5})
    back = Document.from_data(doc.to_data())
    back.rebuild()
    assert back.get("riser").params["face_area"] == BOSS_AREA
    assert abs(back.result().volume - 14010.619) < 0.01


def test_the_hole_plan_answers_with_the_size_of_the_face_it_drilled():
    doc = stepped()
    plan = toolplan.plan(doc, {"tool": "hole", "body_id": "part",
                               "face_center": BOSS_TOP, "face_normal": UP})
    assert plan["ok"], plan.get("error")
    assert abs(plan["face_area"] - 201.06) < 0.01
    # and a named face has no pick to size
    named = toolplan.plan(doc, {"tool": "hole", "body_id": "part",
                                "face_center": None, "face": "top"})
    if named.get("ok"):
        assert named["face_area"] is None


def test_a_picked_edge_carries_the_size_of_both_its_faces():
    part = stepped()._parts["part"]
    edge = next(e for e in part.edges() if abs(float(e.length) - 30.0) < 1e-6)
    ref = blocks.edge_ref(part, edge)
    assert len(ref["faces"]) == 2
    assert all(f.get("area") for f in ref["faces"]), ref["faces"]
    assert blocks.resolve_edge(part, ref) is not None


# --------------------------------------------------------------------------
# §4 cost
# --------------------------------------------------------------------------

def test_areas_are_only_measured_when_a_pick_carries_one():
    """The area is a second BRepGProp integration, as dear as the centre. A
    resolve that names a face by direction alone must not pay for it."""
    # a body no other test has built: the rebuild cache hands out the SAME
    # Part object for identical parameters, and with it whatever another test
    # already asked that shape for
    part = stepped(plate_w=37.0)._parts["part"]

    def slots():
        ent = blocks._SHAPE_CACHES.get(id(part))
        return set(ent[1]) if ent and ent[0] is part else set()

    blocks.resolve_face(part, BOSS_TOP, UP)
    assert "faces" in slots() and "face_areas" not in slots()
    blocks.resolve_face(part, BOSS_TOP, UP, BOSS_AREA)
    assert "face_areas" in slots()
    assert len(blocks._face_areas(part)) == len(blocks._face_rows(part))


# --------------------------------------------------------------------------
# §5 the tie LAUNCH-PLAN §10 carries as its own row
# --------------------------------------------------------------------------

def test_two_faces_in_the_SAME_place_are_told_apart_by_their_size():
    """A round pocket with a flush round pad in it has two +Z faces whose
    centroids are BOTH (0, 0, 10): one stored pick, two faces, and `min`
    answers with whichever the kernel lists first. Distance cannot break that
    tie — there is no distance. The size can, and only for a pick that carries
    one; without it the coin toss is exactly as it was."""
    doc = Document(name="t-tie")
    doc.add("sk", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30}]})
    doc.add("base", "extrude", {"amount": 10}, inputs=["sk"])
    doc.add("pk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 10}]})
    doc.add("pk_tool", "extrude", {"amount": -4}, inputs=["pk"])
    doc.add("pocket", "cut", {}, inputs=["base", "pk_tool"])
    doc.add("pad", "sketch", {"plane": "XY", "offset": 6, "entities": [
        {"kind": "circle", "r": 6}]})
    doc.add("pad_tool", "extrude", {"amount": 4}, inputs=["pad"])
    doc.add("part", "fuse", {}, inputs=["pocket", "pad_tool"])
    doc.rebuild()
    part = doc._parts["part"]
    at = [0.0, 0.0, 10.0]
    assert area_of(blocks.resolve_face(part, at, UP, 113.10)) == 113.097
    assert area_of(blocks.resolve_face(part, at, UP, 885.84)) == 885.841


# --------------------------------------------------------------------------
# §6 the corpus: an operation is the feature TIMES the geometry
# --------------------------------------------------------------------------

def test_every_face_of_the_corpus_still_names_itself():
    """The size gate sits in the resolver EVERY face-eating op shares, so it is
    not enough that it helps a plate with a boss: on all nine bodies of
    tests/gauntlet.py, every flat face asked for BY ITS OWN size and centre has
    to come back as itself. If the gate ever narrowed the field to the wrong
    face, this is where a body with repeated geometry would say so."""
    from gauntlet import BODIES, planar_faces
    checked = 0
    for name, make in BODIES.items():
        solid = make()
        for _i, face, centre, normal in planar_faces(solid):
            area = round(float(face.area), 2)
            got = blocks.resolve_face(solid, list(centre), list(normal), area)
            assert blocks._shape_key(got) == blocks._shape_key(face), (
                f"{name}: a face of {area} mm2 at {centre} resolved to a "
                f"different face of {area_of(got)} mm2")
            # and the size must not change an answer that was already right
            bare = blocks.resolve_face(solid, list(centre), list(normal))
            if blocks._shape_key(bare) == blocks._shape_key(face):
                assert blocks._shape_key(got) == blocks._shape_key(bare), name
            checked += 1
    assert checked > 40, f"only {checked} faces exercised"


# --------------------------------------------------------------------------
# §7 the gate must not make the EDGE resolver refuse an edge that is there
#
# resolve_face itself never refuses (§2) — it hands the whole list back. But
# resolve_edge asks it TWICE, once per host face of a stored edge, and then
# demands that the two answers still meet. So the narrowing CAN refuse, one
# level up: narrow one host face onto a same-sized face somewhere else and the
# two no longer share an edge, which reads as "an upstream change removed it".
# Measured 2026-09-16 (probes/section10_pick_probe2.py §4).
# --------------------------------------------------------------------------

def two_pads(pad_w=20.0):
    """A plate with TWO pads on top whose top faces are the same 200 mm2 —
    20 x 10 and 25 x 8. Everyday geometry, not a contrivance: two pads a
    design happens to give the same area."""
    doc = Document(name="t-pads")
    doc.add("plate", "plate", {"width": 90, "depth": 40, "thickness": 10})
    doc.add("skP", "sketch", {"plane": "XY", "offset": 5, "entities": [
        {"kind": "rectangle", "w": pad_w, "h": 10, "x": -25, "y": 0}]})
    doc.add("padP", "extrude", {"amount": 6}, inputs=["skP"])
    doc.add("joinP", "fuse", {}, inputs=["plate", "padP"])
    doc.add("skQ", "sketch", {"plane": "XY", "offset": 5, "entities": [
        {"kind": "rectangle", "w": 25, "h": 8, "x": 25, "y": 0}]})
    doc.add("padQ", "extrude", {"amount": 6}, inputs=["skQ"])
    doc.add("joinQ", "fuse", {}, inputs=["joinP", "padQ"])
    assert doc.rebuild(), doc.tree()
    return doc._parts["joinQ"]


def _pad_p_top_rim(part):
    """the +X rim of pad P's top face — the edge a chamfer would be put on"""
    top = next(f for f in part.faces()
               if abs(f.normal_at(f.center()).Z - 1) < 1e-6
               and abs(f.center().Z - 11) < 1e-6 and f.center().X < 0)
    return max(blocks._face_edges(part, top), key=lambda e: (e @ 0.5).X)


def test_a_wider_pad_does_not_lose_the_rim_it_was_chamfered_on():
    """Pad P is widened 20 -> 24 mm, so its top grows 200 -> 240 mm2 and no
    longer matches the size the pick recorded. The gate then fell through to
    pad Q's top — 50 mm away, still 200 mm2 — and the two faces it had to
    share an edge did not meet: the feature went RED, blaming an upstream
    change for removing an edge that is sitting at (-13, 0, 11)."""
    ref = blocks.edge_ref(two_pads(20.0), _pad_p_top_rim(two_pads(20.0)))
    assert ref["mid"][0] == -15.0, ref["mid"]
    assert sorted(f["area"] for f in ref["faces"]) == [60.0, 200.0], ref["faces"]
    got = blocks.resolve_edge(two_pads(24.0), ref)      # RED before the fix
    assert round((got @ 0.5).X, 3) == -13.0, (got @ 0.5)


def test_the_sizeless_rule_is_what_answers_when_the_sized_one_cannot():
    """...and the answer is exactly the one yesterday's rule gave, because the
    fix is a fall-back and not a new rule."""
    wide = two_pads(24.0)
    ref = blocks.edge_ref(two_pads(20.0), _pad_p_top_rim(two_pads(20.0)))
    bare = {**ref, "faces": [{k: v for k, v in f.items() if k != "area"}
                             for f in ref["faces"]]}
    assert blocks._shape_key(blocks.resolve_edge(wide, ref)) \
        == blocks._shape_key(blocks.resolve_edge(wide, bare))


def test_an_edge_whose_two_faces_do_not_meet_is_still_refused():
    """The fall-back must not cost the refusal its job. Neither pass can make
    the top of pad P and the bottom of the plate share an edge, so the
    sentence still comes — a failed feature beats a rounded wrong edge."""
    ref = {"mid": [0.0, 0.0, 0.0], "dir": [1.0, 0.0, 0.0], "type": "LINE",
           "faces": [{"center": [-25.0, 0.0, 11.0], "normal": UP, "area": 200.0},
                     {"center": [0.0, 0.0, -5.0], "normal": [0.0, 0.0, -1.0],
                      "area": 3600.0}]}
    with pytest.raises(ValueError, match="no longer on the body"):
        blocks.resolve_edge(two_pads(20.0), ref)


def test_the_fall_back_is_right_across_the_whole_sweep_not_just_at_24():
    """ROUND TWO. The test above proves the fall-back ANSWERS at one pad width;
    the danger it cannot see is that the answer is WRONG — dropping the size is
    a fall-back to the very rule the size gate exists to correct, so "it stopped
    refusing" is not the same news as "it is right".

    So the pick is stored once at 20 mm and re-resolved at every width from 16
    to 34, against the edge that body really has. Measured 2026-09-16
    (probes/section10_round2_probe.py §1d): the sized pass refuses at 11 of the
    12 widths — every one of them a red feature before the fall-back — and the
    sizeless rule names the correct rim at all 12, never a neighbour's."""
    ref = blocks.edge_ref(two_pads(20.0), _pad_p_top_rim(two_pads(20.0)))
    rescued = 0
    for w in (16, 18, 19, 20, 21, 22, 24, 26, 28, 30, 32, 34):
        part = two_pads(float(w))
        got = blocks.resolve_edge(part, ref)   # raises at 11 of 12 before the fix
        assert blocks._shape_key(got) == blocks._shape_key(_pad_p_top_rim(part)), \
            f"w={w}: the fall-back named {got @ 0.5}, not pad P's own rim"
        if not blocks._shared_edges(part, ref["faces"], True):
            rescued += 1                       # the sized pass alone was RED here
    assert rescued >= 10, f"only {rescued} widths exercised the fall-back"
