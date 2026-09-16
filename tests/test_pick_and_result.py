"""Two ways a design could quietly become a different design.

Both are LAUNCH-PLAN §10 rows, both are the class this project fears most —
geometry that is wrong while every status says `ok`.

1. A STORED FACE PICK IS REMEMBERED IN WORLD COORDINATES. Round one of the
   Move review turned the picked direction into a gate, which stopped a pick
   landing on a face pointing the OTHER way. It did not stop a pick sliding to
   the next face pointing the SAME way. Measured (probes/face_pick_frame_probe
   .py §1) on a 10 mm plate with a r8 x 5 boss: a pick on the boss top follows
   a rigid move only as far as HALF the step. At dz = 2.49 mm it is the boss
   top (201.062 mm2); at dz = 2.50 it is the plate top (998.938 mm2) and the
   design is 18000.0 mm3 where 14010.62 was asked for, tree green, solid
   valid. `move` is the one displacement the document knows exactly, so
   Document.edit carries every pick on the body it moves.

2. A SUPPRESSED FINAL BOOLEAN PROMOTED ITS TOOL. result() walked back past the
   struck cut and stopped at the first solid it met — the cutting prism. On
   the everyday sketch -> tool -> cut chain, striking the cut made a 12000 mm3
   plate report as 452.389 mm3 of prism: the status bar, `measure`, the spec
   check and the exporter's idea of "the result" all followed it
   (probes/suppressed_result_probe.py §1).
"""
import math

import pytest

import blocks
from document import Document

PLATE = 40.0 * 30.0 * 10.0                     # 12000.0
BOSS = math.pi * 8.0 ** 2 * 5.0                # 1005.3096...
BOSS_TOP = [0.0, 0.0, 15.0]
UP = [0.0, 0.0, 1.0]


# ----------------------------------------------------- the pick and the move ---

def stepped(dz=0.0):
    """plate 40 x 30 x 10, a r8 x 5 boss fused on top, the whole thing MOVED,
    then the BOSS TOP picked and pulled up 5 mm and fused back. Two faces
    point +Z, so the pick has something to slide onto."""
    doc = Document(name="t-pick")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30}]})
    doc.add("base", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("boss_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 8, "x": 0, "y": 0}]})
    doc.add("boss", "extrude", {"amount": 5}, inputs=["boss_sk"])
    doc.add("part", "fuse", {}, inputs=["base", "boss"])
    doc.add("placed", "move", {"x": 0, "y": 0, "z": dz}, inputs=["part"])
    doc.add("riser", "extrude_face",
            {"face_center": list(BOSS_TOP), "face_normal": list(UP),
             "amount": 5}, inputs=["placed"])
    doc.add("final", "fuse", {}, inputs=["placed", "riser"])
    doc._cache = {}
    return doc


def test_the_pick_stays_on_the_face_the_user_picked_at_any_distance():
    """THE BUG, as the user meets it: build the boss, then re-open Move and
    drag. Past half the boss height the old code put the riser on the PLATE."""
    doc = stepped()
    assert doc.rebuild(), doc.tree()
    want = doc.result().volume
    assert want == pytest.approx(PLATE + BOSS + BOSS, rel=1e-6)
    for dz in (1.0, 2.5, 4.0, 10.0, -7.0, 0.0):
        doc.edit("placed", "z", dz)
        assert doc.rebuild(), doc.tree()
        got = blocks.resolve_face(doc._parts["placed"],
                                  doc.get("riser").params["face_center"], UP)
        assert got.area == pytest.approx(math.pi * 64, rel=1e-6), \
            f"dz={dz}: the pick left the boss top for a {got.area:.3f} mm2 face"
        assert doc.result().volume == pytest.approx(want, rel=1e-9), \
            f"dz={dz}: the design changed size because the pick moved"


def test_the_carried_pick_comes_back_exactly_when_the_move_is_undone():
    doc = stepped()
    doc.rebuild()
    doc.edit("placed", "z", 6.25)
    doc.edit("placed", "z", -3.5)
    doc.edit("placed", "z", 0)
    assert doc.get("riser").params["face_center"] == pytest.approx(BOSS_TOP)


def test_the_pick_follows_x_and_y_as_well_as_z():
    doc = stepped()
    doc.rebuild()
    doc.edit_many("placed", {"x": 12, "y": -4.5, "z": 9})
    assert doc.get("riser").params["face_center"] == pytest.approx(
        [12.0, -4.5, 24.0])


def test_a_pick_on_a_body_the_move_never_touches_is_left_alone():
    """Two separate bodies. Moving one must not shift the other one's pick —
    the pick would then be looking for a face that never went anywhere."""
    doc = stepped()
    doc.add("other_sk", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 10, "h": 10, "x": 100}]})
    doc.add("other", "extrude", {"amount": 4}, inputs=["other_sk"])
    doc.add("other_face", "extrude_face",
            {"face_center": [100.0, 0.0, 4.0], "face_normal": list(UP),
             "amount": 2}, inputs=["other"])
    doc.rebuild()
    doc.edit("placed", "z", 8)
    assert doc.get("other_face").params["face_center"] == [100.0, 0.0, 4.0]
    assert doc.get("riser").params["face_center"] == pytest.approx(
        [0.0, 0.0, 23.0])


def test_a_face_a_stationary_tool_cut_is_not_carried():
    """Only bodies that moved RIGIDLY are carried. A pocket cut by a tool that
    did not move keeps its floor where the tool put it, so a pick on that
    floor must stay put too — carrying it would be a new bug, not a fix."""
    doc = Document(name="t-static-tool")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30}]})
    doc.add("base", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("placed", "move", {"x": 0, "y": 0, "z": 0}, inputs=["base"])
    doc.add("tool_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 6}]})
    doc.add("tool", "extrude", {"amount": -4}, inputs=["tool_sk"])
    doc.add("pocketed", "cut", {}, inputs=["placed", "tool"])
    doc.add("deeper", "extrude_face",
            {"face_center": [0.0, 0.0, 6.0], "face_normal": [0, 0, -1],
             "amount": 2}, inputs=["pocketed"])
    doc._cache = {}
    doc.rebuild()
    doc.edit("placed", "z", 5)
    assert doc.get("deeper").params["face_center"] == [0.0, 0.0, 6.0]


def test_a_struck_row_does_not_end_the_chain():
    """A switched-off feature hands its first input on, so the body below it
    still moved and the picks below it must still be carried."""
    doc = stepped()
    doc.rebuild()
    doc.get("riser").suppressed = True
    doc._mark_stale()
    doc.edit("placed", "z", 5)
    assert doc.get("riser").params["face_center"] == pytest.approx(
        [0.0, 0.0, 20.0])


def test_an_ordinary_parameter_edit_carries_nothing():
    doc = stepped()
    doc.rebuild()
    doc.edit("base", "amount", 12)
    doc.edit("riser", "amount", 7)
    assert doc.get("riser").params["face_center"] == BOSS_TOP


def test_a_suppressed_move_carries_nothing():
    """Its geometry is not in the model, so neither is its displacement."""
    doc = stepped()
    doc.rebuild()
    doc.get("placed").suppressed = True
    doc.edit("placed", "z", 9)
    assert doc.get("riser").params["face_center"] == BOSS_TOP


def test_a_face_pick_stored_inside_a_dict_param_is_carried_too():
    """A Pattern axis and a Mirror plane hold the pick one level down
    ({"face_center": …, "face_normal": …}); the same move must reach it."""
    doc = stepped()
    doc.add("mirrored", "mirror",
            {"plane": {"face_center": [0.0, 0.0, 15.0],
                       "face_normal": [0.0, 0.0, 1.0]}},
            inputs=["final"])
    doc.rebuild()
    doc.edit("placed", "z", 3)
    assert doc.get("mirrored").params["plane"]["face_center"] == pytest.approx(
        [0.0, 0.0, 18.0])
    assert doc.get("mirrored").params["plane"]["face_normal"] == [0.0, 0.0, 1.0]


def moved_plate_and_boss(dz=0.0):
    """The same plate and boss, MOVED — with nothing hanging off the pick yet,
    so a caller can hang a shell or a fillet on it."""
    doc = Document(name="t-carry")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30}]})
    doc.add("base", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("boss_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 8, "x": 0, "y": 0}]})
    doc.add("boss", "extrude", {"amount": 5}, inputs=["boss_sk"])
    doc.add("part", "fuse", {}, inputs=["base", "boss"])
    doc.add("placed", "move", {"x": 0, "y": 0, "z": dz}, inputs=["part"])
    doc._cache = {}
    return doc


def test_a_shell_opening_is_carried_by_the_move_too():
    """A shell keeps its opening in `faces` — a LIST of {center, normal}, not a
    `face_center` — so the first carry walked straight past it. Measured
    (probes/move_carries_which_picks_probe.py): moving the body 8 mm reopened
    the shell on the PLATE top, where a 2 mm wall does not fit, and 6597.628
    mm3 became 13005.31 with a red row."""
    doc = moved_plate_and_boss()
    doc.add("hollow", "shell", {"thickness": 2.0, "faces": [
        {"center": list(BOSS_TOP), "normal": list(UP)}]}, inputs=["placed"])
    doc.rebuild()
    before = doc.result().volume
    doc.edit("placed", "z", 8)
    doc.rebuild()
    assert doc.get("hollow").params["faces"][0]["center"] == pytest.approx(
        [0.0, 0.0, 23.0])
    assert doc.get("hollow").params["faces"][0]["normal"] == UP   # a direction
    assert doc.get("hollow").status == "ok"
    assert doc.result().volume == pytest.approx(before, abs=1e-6)


def test_a_picked_edge_is_carried_by_the_move_too():
    """The silent one. A fillet keeps its pick in `edges` — {mid, dir, faces:
    [{center, normal}]} — and none of those is a `face_center`. Moving the body
    8 mm rounded a DIFFERENT edge with every row still `ok`: 12994.824 mm3
    against 13016.398."""
    doc = moved_plate_and_boss()
    doc.rebuild()
    part = doc._parts["placed"]
    rim = next(e for e in part.edges()
               if str(e.geom_type).endswith("CIRCLE")
               and abs(float((e @ 0.5).Z) - 15.0) < 1e-6)
    ref = blocks.edge_ref(part, rim)
    for host in ref["faces"]:                      # the old shape: no size
        host.pop("area", None)
    doc.add("round", "fillet", {"radius": 1.0, "edges": [ref]},
            inputs=["placed"])
    doc.rebuild()
    before = doc.result().volume
    doc.edit("placed", "z", 8)
    doc.rebuild()
    got = doc.get("round").params["edges"][0]
    assert got["mid"] == pytest.approx([-8.0, 0.0, 23.0])
    assert got["dir"] == ref["dir"]                # a direction does not move
    assert [h["center"][2] for h in got["faces"]] == pytest.approx(
        [h["center"][2] + 8.0 for h in blocks.edge_ref(part, rim)["faces"]])
    assert doc.get("round").status == "ok"
    assert doc.result().volume == pytest.approx(before, abs=1e-6)


# ------------------------------------------------- two faces in one place ---

def flush_pad():
    """A round pocket with a flush round pad in the middle — a locating pad.
    The outer top (893.142 mm2) and the pad top (314.159 mm2) are coplanar,
    both point +Z, and share a centroid exactly."""
    doc = Document(name="t-tie")
    doc.add("o", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 40}]})
    doc.add("plate", "extrude", {"amount": 10}, inputs=["o"])
    doc.add("pocket_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 15}]})
    doc.add("pocket_tool", "extrude", {"amount": -3}, inputs=["pocket_sk"])
    doc.add("pocketed", "cut", {}, inputs=["plate", "pocket_tool"])
    doc.add("pad_sk", "sketch", {"plane": "XY", "offset": 7, "entities": [
        {"kind": "circle", "r": 10}]})
    doc.add("pad", "extrude", {"amount": 3}, inputs=["pad_sk"])
    doc.add("part", "fuse", {}, inputs=["pocketed", "pad"])
    doc._cache = {}
    doc.rebuild()
    return doc.result()


def test_two_faces_in_the_same_place_are_one_stored_pick():
    """The queued `resolve_face` shared-centre item, pinned with its numbers.

    A flush pad in a round pocket gives two planar +Z faces whose centroids
    agree to more decimals than a pick carries, so ONE stored pick describes
    both and the resolver answers with whichever the kernel lists first.

    This test does NOT say that answer is right — it is a coin toss and it is
    a LAUNCH-PLAN §10 row. It says what is true today and must stay true while
    the row is open: the tie is real, and the answer is at least STABLE, so it
    cannot flip under the user between one rebuild and the next. Refusing the
    tie was built and measured out: Shell asks this question once per lump and
    a post inside a ring is two concentric lumps that tie exactly, so the
    refusal broke a shell the kernel builds perfectly. The fix belongs in the
    pickers (say WHICH face — an area, a lump), not in the resolver."""
    part = flush_pad()
    tops = [f for f in part.faces()
            if str(f.geom_type).split(".")[-1] == "PLANE"
            and f.normal_at(f.center()).Z > 0.9
            and round(f.center().Z, 2) == 10.0]
    assert len(tops) == 2, "the case needs two faces on the same plane"
    a, b = (f.center() for f in tops)
    assert (round(a.X, 2), round(a.Y, 2), round(a.Z, 2)) == \
           (round(b.X, 2), round(b.Y, 2), round(b.Z, 2))
    assert sorted(round(f.area, 3) for f in tops) == [314.159, 893.142]
    first = blocks.resolve_face(part, [0.0, 0.0, 10.0], UP)
    again = blocks.resolve_face(flush_pad(), [0.0, 0.0, 10.0], UP)
    assert round(first.area, 3) == round(again.area, 3)


def test_the_other_picks_on_that_body_still_resolve():
    part = flush_pad()
    floor = blocks.resolve_face(part, [0.0, 0.0, 7.0], UP)
    assert floor.area == pytest.approx(math.pi * (15 ** 2 - 10 ** 2), rel=1e-6)
    bottom = blocks.resolve_face(part, [0.0, 0.0, 0.0], [0, 0, -1])
    assert bottom.area == pytest.approx(1600.0, rel=1e-6)


def test_a_curved_face_tied_with_a_flat_one_still_answers():
    """A cylinder's centre() is ON its own surface, so a pick can sit exactly
    between it and the disc capping it. resolve_face must still answer: the
    caller's own "that surface is curved" refusal is the one that should speak
    there (tests/test_fillet_tool.py's disc band), and a resolver that raised
    instead swallowed that sentence."""
    doc = Document(name="t-cyl")
    doc.add("c_sk", "sketch", {"plane": "XY", "entities": [
        {"kind": "circle", "r": 10}]})
    doc.add("cyl", "extrude", {"amount": 20}, inputs=["c_sk"])
    doc._cache = {}
    doc.rebuild()
    part = doc.result()
    wall = [f for f in part.faces()
            if str(f.geom_type).split(".")[-1] == "CYLINDER"][0]
    top = [f for f in part.faces()
           if str(f.geom_type).split(".")[-1] == "PLANE"
           and f.center().Z > 19.9][0]
    a, b = wall.center(), top.center()
    pick = [(a.X + b.X) / 2, (a.Y + b.Y) / 2, (a.Z + b.Z) / 2]

    def d2(f):
        c = f.center()
        return sum((u - v) ** 2 for u, v in zip((c.X, c.Y, c.Z), pick))

    assert d2(wall) == pytest.approx(d2(top)), "the case needs an exact tie"
    got = blocks.resolve_face(part, pick)          # must answer, not refuse
    assert got.area > 0


def test_a_stepped_body_resolves_its_own_pick():
    """The everyday shape: two faces point +Z, 5 mm apart, and the pick lands
    on the one it was taken from."""
    doc = stepped()
    doc.rebuild()
    got = blocks.resolve_face(doc._parts["placed"], BOSS_TOP, UP)
    assert got.area == pytest.approx(math.pi * 64, rel=1e-6)


# --------------------------------------- a struck boolean and "the result" ---

def cut_chain():
    doc = Document(name="t-struck")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30}]})
    doc.add("body", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("tool_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 6}]})
    doc.add("tool", "extrude", {"amount": -4}, inputs=["tool_sk"])
    doc.add("pocket", "cut", {}, inputs=["body", "tool"])
    doc._cache = {}
    return doc


def test_striking_the_last_cut_leaves_the_plate_as_the_result():
    doc = cut_chain()
    assert doc.rebuild()
    doc.get("pocket").suppressed = True
    doc._mark_stale()
    assert doc.rebuild(), doc.tree()
    assert doc._result_feature().id == "body"
    assert doc.result().volume == pytest.approx(PLATE, rel=1e-9)


def test_striking_the_last_fuse_does_not_promote_the_boss():
    doc = Document(name="t-struck-fuse")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30}]})
    doc.add("body", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("boss_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 8}]})
    doc.add("boss", "extrude", {"amount": 5}, inputs=["boss_sk"])
    doc.add("joined", "fuse", {}, inputs=["body", "boss"])
    doc._cache = {}
    assert doc.rebuild()
    doc.get("joined").suppressed = True
    doc._mark_stale()
    assert doc.rebuild(), doc.tree()
    assert doc._result_feature().id == "body"
    assert doc.result().volume == pytest.approx(PLATE, rel=1e-9)


def test_a_whole_struck_chain_walks_back_to_the_body_it_passes_through():
    doc = cut_chain()
    doc.add("s2", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 3, "x": 10}]})
    doc.add("t2", "extrude", {"amount": -4}, inputs=["s2"])
    doc.add("c2", "cut", {}, inputs=["pocket", "t2"])
    assert doc.rebuild()
    for fid in ("pocket", "c2"):
        doc.get(fid).suppressed = True
    doc._mark_stale()
    assert doc.rebuild(), doc.tree()
    assert doc._result_feature().id == "body"
    assert doc.result().volume == pytest.approx(PLATE, rel=1e-9)


def test_a_design_that_ends_on_a_separate_body_is_unchanged():
    """Nothing struck: a base plate and a boss the user has not joined are two
    bodies, and the LAST one is still the result — as it always was."""
    doc = Document(name="t-two-bodies")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30}]})
    doc.add("body", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("boss_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "circle", "r": 8}]})
    doc.add("boss", "extrude", {"amount": 5}, inputs=["boss_sk"])
    doc._cache = {}
    assert doc.rebuild()
    assert doc._result_feature().id == "boss"
    assert doc.result().volume == pytest.approx(BOSS, rel=1e-6)


def test_the_rollback_bar_still_decides_where_the_result_is():
    doc = cut_chain()
    assert doc.rebuild()
    doc.rollback = "body"
    assert doc.rebuild()
    assert doc._result_feature().id == "body"
    doc.rollback = None
    assert doc.rebuild()
    assert doc._result_feature().id == "pocket"


def test_a_design_of_only_sketches_still_has_no_result():
    doc = Document(name="t-sketch-only")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30}]})
    doc._cache = {}
    assert doc.rebuild()
    assert doc._result_feature() is None
    assert doc.result() is None


# ------------------------------------- where the carried delta must STOP ---
# The carry adds the MOVE's own delta to a stored pick. That is only the right
# arithmetic while every op between the move and the pick hands its input's
# translation straight on. `mirror`, a world-origin `rotate` and a
# `polar_pattern` do not — they place geometry against the WORLD — so carrying
# through them pushes the pick the WRONG WAY. Measured on the design below
# (probes/pick_carry_nonrigid_probe.py): the pick left the boss top for the
# plate top and 720 mm3 became 7560 mm3 with every row `ok`, where NOT moving
# the pick had been right.

BOSS_TOP_AREA = 12.0 * 12.0            # square bosses: every rival face is PLANAR,
#                                   so resolve_face's direction gate applies


def placed(op, params, move_x=30.0, pick_index=0, riser=True):
    """plate 60 x 30 x 10, two 12 x 12 x 5 bosses 30 mm apart, moved +x, then
    `op` — and a riser pulled off one boss top of whatever `op` produced."""
    doc = Document(name="t-stop")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 60, "h": 30}]})
    doc.add("base", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("boss_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "rectangle", "w": 12, "h": 12, "x": -15, "y": 0},
        {"kind": "rectangle", "w": 12, "h": 12, "x": 15, "y": 0}]})
    doc.add("boss", "extrude", {"amount": 5}, inputs=["boss_sk"])
    doc.add("part", "fuse", {}, inputs=["base", "boss"])
    doc.add("placed", "move", {"x": move_x, "y": 0, "z": 0}, inputs=["part"])
    doc.add("flip", op, dict(params), inputs=["placed"])
    doc._cache = {}
    assert doc.rebuild(), doc.tree()
    if not riser:
        return doc, None
    top = boss_top_centres(doc._parts["flip"])[pick_index]
    doc.add("riser", "extrude_face",
            {"face_center": list(top), "face_normal": list(UP), "amount": 5},
            inputs=["flip"])
    doc._cache = {}
    assert doc.rebuild(), doc.tree()
    return doc, top


def boss_top_centres(part):
    out = []
    for f in part.faces():
        try:
            n = f.normal_at(f.center())
        except Exception:                        # a face the kernel won't measure
            continue
        if abs(n.Z - 1.0) < 1e-6 and abs(f.area - BOSS_TOP_AREA) < 1e-3:
            c = f.center()
            out.append([round(c.X, 6), round(c.Y, 6), round(c.Z, 6)])
    return sorted(out)


def _pick_survives(op, params, dx=6.0, pick_index=0):
    """Edit the move by `dx` and report the face the stored pick now finds."""
    doc, top = placed(op, params, pick_index=pick_index)
    before = doc.result().volume
    doc.edit("placed", "x", 30.0 + dx)
    assert doc.rebuild(), doc.tree()
    stored = doc.get("riser").params["face_center"]
    face = blocks.resolve_face(doc._parts["flip"], stored, UP)
    return doc, top, stored, face, before


@pytest.mark.parametrize("op,params", [
    ("mirror", {"plane": "YZ"}),
    ("mirror", {"plane": "YZ", "join": True}),
    ("rotate", {"axis": "Z", "angle_deg": 180}),
    ("polar_pattern", {"count": 2, "angle": 90}),
])
def test_the_delta_does_not_cross_an_op_that_places_against_the_world(op, params):
    doc, top, stored, face, before = _pick_survives(op, params)
    assert stored == top, \
        f"{op}: the pick was carried past an op whose output does not move with it"
    assert face.area == pytest.approx(BOSS_TOP_AREA, rel=1e-9), \
        f"{op}: the pick left the boss top for a {face.area:.1f} mm2 face"
    assert doc.result().volume == pytest.approx(before, rel=1e-9), \
        f"{op}: the design changed size because the pick moved"


def test_a_rotate_about_the_bodys_own_centre_still_carries_the_pick():
    """The other half of the rule, so it cannot be 'never carry past rotate':
    pivot='center' is what the Rotate tool sends, it turns the body IN PLACE,
    and its output really does travel with the move."""
    doc, top, stored, face, before = _pick_survives(
        "rotate", {"axis": "Z", "angle_deg": 90, "pivot": "center"})
    assert stored == [top[0] + 6.0, top[1], top[2]], \
        "a rotate in place hands the move on; its pick must follow"
    assert face.area == pytest.approx(BOSS_TOP_AREA, rel=1e-9)
    assert doc.result().volume == pytest.approx(before, rel=1e-9)


def test_a_linear_pattern_still_carries_the_pick():
    """Measured to move by exactly the delta (probes/pick_carry_commute
    _probe.py), so the stop rule must not swallow it."""
    doc, top, stored, face, before = _pick_survives(
        "linear_pattern", {"count": 2, "dx": 80})
    assert stored == [top[0] + 6.0, top[1], top[2]]
    assert face.area == pytest.approx(BOSS_TOP_AREA, rel=1e-9)
    assert doc.result().volume == pytest.approx(before, rel=1e-9)


def test_a_mirrors_own_plane_pick_still_follows_the_move():
    """The feature that STOPS the delta still READS the moved body: the plane
    the mirror was given is a face OF that body, so it moves with it. Getting
    this wrong the other way would mirror about a plane 6 mm from the one the
    user picked."""
    doc, _ = placed("mirror", {"plane": {"face_center": [60.0, 0.0, 5.0],
                                         "face_normal": [1.0, 0.0, 0.0]}},
                    riser=False)
    doc.edit("placed", "x", 36.0)
    assert doc.get("flip").params["plane"]["face_center"] == [66.0, 0.0, 5.0]
    assert doc.rebuild(), doc.tree()
    assert doc.get("flip").status == "ok"


def test_a_seeded_pattern_stops_the_carry_too():
    """A seeded pattern repeats a delta taken from ELSEWHERE in the tree, so
    the move's own delta is not what its copies travel by."""
    from document import _hands_on_the_move
    from document import Feature
    plain = Feature(id="p", op="linear_pattern",
                    params={"count": 3, "dx": 12}, inputs=["b"])
    seeded = Feature(id="p", op="linear_pattern",
                     params={"count": 3, "dx": 12, "seed": "hole1"},
                     inputs=["b"])
    assert _hands_on_the_move(plain) is True
    assert _hands_on_the_move(seeded) is False
