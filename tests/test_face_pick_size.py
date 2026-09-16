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
