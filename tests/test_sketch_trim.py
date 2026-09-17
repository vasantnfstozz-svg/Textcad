"""Trim tool geometry (sketch_trim.py) — the last P1 backlog item.

Trim = click a piece of an entity outline between intersections:
  * seam between material regions   -> dissolved (shapes union-rebuilt)
  * boundary of an enclosed gap     -> gap filled into the profile
  * outer boundary                  -> refused with a clear message
  * crossing-free entity            -> deleted whole (Fusion parity)
Rebuilt clusters become exact path/circle entities; untouched entities
stay parametric.
"""
import math
import pytest

import sketch as sk
import sketch_trim as tr

RECT = {"kind": "rectangle", "mode": "add", "x": 0, "y": 0, "w": 40, "h": 20}


def area_of(entities):
    return sk.make_sketch("XY", 0, entities).area


def mid(piece):
    return piece["pts"][len(piece["pts"]) // 2]


def circle_piece(pieces, ent, pred):
    return next(p for p in pieces if p["ent"] == ent and pred(mid(p)))


# ---------------------------------------------------------------- pieces --

def test_pieces_split_at_intersections():
    ents = [dict(RECT), {"kind": "circle", "mode": "subtract",
                         "x": 20, "y": 0, "r": 8}]
    pieces = tr.trim_pieces(ents)
    # rect outline cut in 2, circle outline cut in 2 — none "whole"
    assert len([p for p in pieces if p["ent"] == 0]) == 2
    assert len([p for p in pieces if p["ent"] == 1]) == 2
    assert not any(p["whole"] for p in pieces)
    assert all(len(p["pts"]) >= 2 for p in pieces)


def test_crossing_free_entity_is_one_whole_piece():
    ents = [dict(RECT), {"kind": "circle", "mode": "add",
                         "x": 100, "y": 0, "r": 5}]
    pieces = tr.trim_pieces(ents)
    lone = [p for p in pieces if p["ent"] == 1]
    assert len(lone) == 1 and lone[0]["whole"]


# ----------------------------------------------------------------- apply --

def test_trim_dangling_arc_dissolves_to_material():
    """Cut circle biting the rect edge: trimming the OUTSIDE (dangling) arc
    keeps the bite — material is untouched, the dangle just disappears."""
    ents = [dict(RECT), {"kind": "circle", "mode": "subtract",
                         "x": 20, "y": 0, "r": 8}]
    dangle = circle_piece(tr.trim_pieces(ents), 1, lambda m: m[0] > 20.05)
    res = tr.trim_apply(ents, dangle["id"])
    bite = math.pi * 64 / 2                       # half the disc is inside
    assert area_of(res["entities"]) == pytest.approx(800 - bite, abs=0.5)


def test_trim_bite_arc_fills_exactly_the_inside_cell():
    """Trimming the bite boundary INSIDE the rect fills only the inside half
    of the disc (a U-minus-M component spans both halves — the arrangement
    cell must be clipped to the rect)."""
    ents = [dict(RECT), {"kind": "circle", "mode": "subtract",
                         "x": 20, "y": 0, "r": 8}]
    arc = circle_piece(tr.trim_pieces(ents), 1, lambda m: m[0] < 19.95)
    res = tr.trim_apply(ents, arc["id"])
    assert area_of(res["entities"]) == pytest.approx(800, abs=0.2)


def test_trim_seam_of_two_add_circles_gives_exact_union():
    A = {"kind": "circle", "mode": "add", "x": 0, "y": 0, "r": 10}
    B = {"kind": "circle", "mode": "add", "x": 12, "y": 0, "r": 10}
    ents = [A, B]
    inner = circle_piece(tr.trim_pieces(ents), 0, lambda m: m[0] > 2.05)
    res = tr.trim_apply(ents, inner["id"])
    lens = 2 * 100 * math.acos(0.6) - 6 * math.sqrt(400 - 144)
    union = 2 * math.pi * 100 - lens
    assert len(res["entities"]) == 1
    assert res["entities"][0]["kind"] == "path"
    assert area_of(res["entities"]) == pytest.approx(union, abs=0.2)


def test_trim_outer_boundary_is_refused():
    A = {"kind": "circle", "mode": "add", "x": 0, "y": 0, "r": 10}
    B = {"kind": "circle", "mode": "add", "x": 12, "y": 0, "r": 10}
    outer = circle_piece(tr.trim_pieces([A, B]), 0, lambda m: m[0] < 1.95)
    with pytest.raises(ValueError, match="outer boundary"):
        tr.trim_apply([A, B], outer["id"])


def test_trim_whole_deletes_entity_and_hole_gesture():
    # far-away circle: whole-delete
    ents = [dict(RECT), {"kind": "circle", "mode": "add",
                         "x": 100, "y": 0, "r": 5}]
    whole = next(p for p in tr.trim_pieces(ents) if p["ent"] == 1)
    res = tr.trim_apply(ents, whole["id"])
    assert [e["kind"] for e in res["entities"]] == ["rectangle"]
    # a hole fully inside is also crossing-free: clicking it removes the hole
    holed = [dict(RECT), {"kind": "circle", "mode": "subtract",
                          "x": 0, "y": 0, "r": 4}]
    hw = next(p for p in tr.trim_pieces(holed) if p["ent"] == 1)
    res = tr.trim_apply(holed, hw["id"])
    assert area_of(res["entities"]) == pytest.approx(800, abs=0.1)


def test_untouched_entities_stay_parametric():
    """Only the overlapping CLUSTER is rebuilt as paths; a far-away rectangle
    and a hole inside it survive as their original parametric kinds."""
    far_rect = {"kind": "rectangle", "mode": "add", "x": 200, "y": 0,
                "w": 30, "h": 30}
    far_hole = {"kind": "circle", "mode": "subtract", "x": 200, "y": 0, "r": 5}
    A = {"kind": "circle", "mode": "add", "x": 0, "y": 0, "r": 10}
    B = {"kind": "circle", "mode": "add", "x": 12, "y": 0, "r": 10}
    ents = [far_rect, far_hole, A, B]
    inner = circle_piece(tr.trim_pieces(ents), 2, lambda m: 2.05 < m[0] < 12)
    res = tr.trim_apply(ents, inner["id"])
    kinds = [(e["kind"], e["mode"]) for e in res["entities"]]
    assert ("rectangle", "add") in kinds and ("circle", "subtract") in kinds
    assert any(k == "path" for k, _ in kinds)


def test_cluster_rebuild_preserves_full_circles_as_circles():
    """A hole contained in the cluster (no outline crossing) is rebuilt as a
    parametric circle entity, not a path."""
    hole = {"kind": "circle", "mode": "subtract", "x": -10, "y": 0, "r": 3}
    bump = {"kind": "circle", "mode": "add", "x": 20, "y": 0, "r": 6}
    ents = [dict(RECT), hole, bump]                # bump crosses the rect edge
    seam = circle_piece(tr.trim_pieces(ents), 2, lambda m: m[0] < 19.95)
    res = tr.trim_apply(ents, seam["id"])
    circles = [e for e in res["entities"]
               if e["kind"] == "circle" and e["mode"] == "subtract"]
    assert len(circles) == 1
    assert circles[0]["r"] == pytest.approx(3, abs=1e-3)
    exp = 800 + math.pi * 36 / 2 - math.pi * 9    # rect + half bump - hole
    assert area_of(res["entities"]) == pytest.approx(exp, abs=0.5)


def test_result_feeds_extrude():
    A = {"kind": "circle", "mode": "add", "x": 0, "y": 0, "r": 10}
    B = {"kind": "circle", "mode": "add", "x": 12, "y": 0, "r": 10}
    inner = circle_piece(tr.trim_pieces([A, B]), 0, lambda m: m[0] > 2.05)
    res = tr.trim_apply([A, B], inner["id"])
    solid = sk.extrude_sketch(sk.make_sketch("XY", 0, res["entities"]), 5)
    assert solid.volume == pytest.approx(area_of(res["entities"]) * 5, rel=1e-3)


def test_stale_piece_id_is_a_clear_error():
    with pytest.raises(ValueError, match="stale"):
        tr.trim_apply([dict(RECT)], "7:3")


# ------------------------------------------------------------- HTTP API --

def test_trim_endpoints_are_stateless_and_speak_errors():
    from fastapi.testclient import TestClient
    import studio
    client = TestClient(studio.app)
    ents = [dict(RECT), {"kind": "circle", "mode": "subtract",
                         "x": 20, "y": 0, "r": 8}]
    pieces = client.post("/api/sketch/trim/pieces",
                         json={"entities": ents}).json()["pieces"]
    assert len(pieces) == 4
    arc = circle_piece(pieces, 1, lambda m: m[0] < 19.95)
    out = client.post("/api/sketch/trim/apply",
                      json={"entities": ents, "piece": arc["id"]}).json()
    assert "error" not in out
    assert area_of(out["entities"]) == pytest.approx(800, abs=0.2)
    # errors arrive as {"error": ...} for the chat toast, never a 500
    bad = client.post("/api/sketch/trim/apply",
                      json={"entities": ents, "piece": "9:9"}).json()
    assert "stale" in bad["error"]
    empty = client.post("/api/sketch/trim/pieces",
                        json={"entities": []}).json()
    assert empty["pieces"] == [] and "error" in empty


# ------------------------------------- an entity is ALL its closed loops --

# The Text entity (d3c8c85) is the first kind whose `sk._entity()` returns
# more than one face — one per glyph piece — and whose faces have HOLES.
# Trim's model used to be "one entity = one face = its outer wire", so a word
# was read as its first letter's outline. Measured on
# `plate + text 'AB' (subtract)` by `probes/trim_text_material_lie.py`:
#   * `_material_at` said MATERIAL at (-7.57, -2.51), inside the engraved
#     letter A, where the builder leaves a hole;
#   * it said NO MATERIAL inside the hole of the B, where the builder leaves
#     material — 2 of 2 probe points classified wrongly;
#   * `trim_pieces` offered ONE piece covering 1 of the 5 loops the sketcher
#     canvas draws for that word;
#   * a circle laid across the A was reported "whole" and a click answered
#     "removed the circle (it crossed nothing)".
#
# The review of 916a731 replaced that with a REFUSAL, which is the right
# direction but far wider than the defect: `probes/trim_refusal_cost.py`
# measured it at **32 of the 90 printable characters a user can type** and at
# EVERY word of two or more letters (two glyph pieces is already "more than
# one face" — LX, 12, v1 all refused), and the refusal came out of `_outline`,
# which runs for every entity in the sketch — so one 'O' 200 mm away, touching
# nothing, stopped Trim on two overlapping rectangles it had nothing to do
# with, on hover AND on click.
#
# An entity is read as EVERY closed loop of every face now — which is what
# `sketch.entity_outlines` already hands the canvas to draw — and even-odd
# across those loops is exactly the builder's region.

WORD = {"kind": "text", "mode": "subtract", "x": 0, "y": 0, "text": "AB",
        "size": 14}
PLATE = {"kind": "rectangle", "mode": "add", "x": 0, "y": 0, "w": 60, "h": 30}


def loops_of(shape):
    """Sampled loops of a built shape — an oracle that shares no code with
    `_material_at`'s replay of the entity list."""
    out = []
    for f in shape.faces():
        for w in f.wires():
            n = int(min(max(w.length / 0.8, 96), 384))
            out.append({"pts": tr._sample_wire(w, n)})
    return out


def in_loops(loops, x, y):
    return sum(tr._inside(o, x, y) for o in loops) % 2 == 1


def test_a_word_is_read_as_every_loop_the_canvas_draws():
    """5 loops for 'AB' — two outers and three counters — not 1."""
    assert len(sk.entity_outlines(WORD)) == 5          # what the canvas draws
    assert len(tr._entity_loops(WORD, 0)) == 5


def test_material_under_an_engraved_word_is_the_builders_answer():
    """The measurement round one made with two probe points, made with 1711.

    `_material_at` replays the add/subtract list; the oracle is the face
    `sketch.py` actually composes. They must agree everywhere.
    """
    ents = [dict(PLATE), dict(WORD)]
    _, loops, crossing = tr._pieces_raw(ents)
    order = tr._cluster(ents, loops, crossing, 0)
    oracle = loops_of(sk.compose(ents, note=False))
    wrong = []
    for gx in range(-29, 30):
        for gy in range(-14, 15):
            x, y = gx + 0.37, gy + 0.21       # off the grid lines on purpose
            if tr._material_at(ents, loops, order, x, y) != \
                    in_loops(oracle, x, y):
                wrong.append((x, y))
    assert not wrong, f"{len(wrong)} of 1711 points disagree with the " \
                      f"builder, e.g. {wrong[:4]}"


def test_a_circle_laid_across_a_letter_is_not_whole():
    """Round one's fourth symptom: the circle crossed the A and Trim said it
    crossed nothing."""
    ents = [dict(PLATE), dict(WORD),
            {"kind": "circle", "mode": "add", "x": -7.5, "y": 0, "r": 4}]
    pieces = tr.trim_pieces(ents)
    mine = [p for p in pieces if p["ent"] == 2]
    assert mine and not any(p["whole"] for p in mine), \
        "a circle drawn across the letter A is not crossing-free"


def test_a_word_elsewhere_does_not_stop_the_rest_of_the_sketch():
    """The refusal's real cost: one 'O' 200 mm away killed the whole tool."""
    plain = [dict(RECT), {"kind": "circle", "mode": "add",
                          "x": 20, "y": 0, "r": 8}]
    far = dict(WORD, text="O", mode="add", x=200, y=200)
    base = tr.trim_pieces(plain)
    with_word = tr.trim_pieces(plain + [far])
    assert len(base) == 4
    # every piece of entities 0 and 1 is untouched by the word
    same = [p for p in with_word if p["ent"] in (0, 1)]
    assert [(p["id"], p["ent"], p["whole"], p["pts"]) for p in same] == \
           [(p["id"], p["ent"], p["whole"], p["pts"]) for p in base]
    pid = next(p["id"] for p in base if not p["whole"])
    assert tr.trim_apply(plain, pid)["message"] == \
        tr.trim_apply(plain + [far], pid)["message"]


def test_a_hole_free_single_letter_still_trims():
    one = dict(WORD, text="L", mode="add", x=0, y=0, size=14)
    faces = sk._entity(one).faces()
    ow = faces[0].outer_wire()
    assert len(faces) == 1 and not [w for w in faces[0].wires()
                                    if not w.is_same(ow)]
    assert tr.trim_pieces([one])


def test_trimming_a_word_off_a_plate_keeps_the_builders_area():
    """A real click on a cluster that holds a word: the rebuilt profile must
    have the area the builder gives, not an area with a letter missing."""
    ents = [dict(PLATE), dict(WORD, x=0, y=0)]
    before = area_of(ents)
    pieces = tr.trim_pieces(ents)
    # the word is inside the plate and crosses nothing, so every loop of it
    # is a WHOLE piece: clicking one takes the whole word away
    mine = [p for p in pieces if p["ent"] == 1]
    assert len(mine) == 5 and all(p["whole"] for p in mine)
    out = tr.trim_apply(ents, mine[0]["id"])
    assert len(out["entities"]) == 1                   # the word is gone
    assert area_of(out["entities"]) == pytest.approx(60 * 30, rel=1e-9)
    assert before < 60 * 30                            # it really was engraved


TEXT_GAUNTLET = {
    "word alone": [WORD.copy() | {"mode": "add"}],
    "word engraved in a plate": [dict(PLATE), dict(WORD)],
    "circle across the A": [dict(PLATE), dict(WORD),
                            {"kind": "circle", "mode": "add",
                             "x": -7.5, "y": 0, "r": 4}],
    "bar across a whole word": [WORD.copy() | {"mode": "add", "size": 18},
                                {"kind": "rectangle", "mode": "add",
                                 "x": 0, "y": 0, "w": 40, "h": 2}],
    "circle in the O counter": [{"kind": "text", "mode": "add", "x": 0, "y": 0,
                                 "text": "O", "size": 24},
                                {"kind": "circle", "mode": "add",
                                 "x": 0, "y": 0, "r": 2.5}],
}


@pytest.mark.parametrize("name", sorted(TEXT_GAUNTLET))
def test_every_click_on_a_word_cluster_is_a_message_or_a_sketch(name):
    """An operation is the feature TIMES the geometry. Reading an entity as
    all its loops lets a multi-face Text entity into the cluster machinery for
    the first time — `_union_faces` unions a Sketch, the cell refinement clips
    a Face by one. Click EVERY piece: only a plain ValueError may come out
    (OCP errors are `Exception`, not `RuntimeError`), and whatever does come
    out must build. `probes/trim_text_gauntlet.py` runs 181 clicks over 15
    such sketches: 0 crashes, 0 results that do not build, 0 invalid faces.
    """
    ents = TEXT_GAUNTLET[name]
    applied = 0
    for piece in tr.trim_pieces(ents):
        try:
            out = tr.trim_apply([dict(e) for e in ents], piece["id"])
        except ValueError:
            continue                              # a refusal is an answer
        applied += 1
        if out["entities"]:
            shape = sk.compose(out["entities"], note=False)
            assert shape.is_valid, f"{piece['id']} built an invalid face set"
    assert applied, f"{name}: not one piece of this sketch did anything"


def test_the_loop_parity_rule_holds_three_deep_and_on_a_tangency():
    """`_in_entity` is even-odd across an entity's loops. Right for a glyph
    with a counter and for concentric rings — and these are the two shapes
    the user's 324 sketches cannot produce, so they are put to the kernel
    instead of assumed. (`probes/trim_loops_edge_cases.py` adds a fourth
    level of nesting and 1445 grid points over the glyphs 8 % B g Q.)
    """
    import build123d as b3d

    def check(shape, pts):
        loops = [tr._loop(w) for f in shape.faces() for w in f.wires()]
        for x, y in pts:
            truth = any(tr._face_contains(f, x, y) for f in shape.faces())
            assert tr._in_entity(loops, x, y) is truth, \
                f"({x}, {y}): parity says {not truth}, the kernel says {truth}"
        return len(loops)

    # a disc inside the hole of a ring — three loops, nested three deep
    nested = (b3d.Circle(20) - b3d.Circle(14)) + b3d.Circle(6)
    assert check(nested, [(r, 0.0) for r in
                          (0.0, 5.9, 6.1, 13.9, 14.1, 19.9, 20.1, 25.0)]) == 3
    # two loops that TOUCH at a point rather than crossing
    tangent_in = (b3d.Circle(20) - b3d.Circle(14)) + \
        b3d.Pos(7.0, 0) * b3d.Circle(7.0)
    check(tangent_in, [(x, 0.0) for x in (-16, -13.9, 0.1, 13.9, 14.1, 21)])
    tangent_out = b3d.Pos(-9, 0) * b3d.Circle(9) + \
        b3d.Pos(9, 0) * b3d.Circle(9)
    check(tangent_out, [(x, 0.0) for x in (-12, -0.2, 0.2, 12, 19.5)])


def test_a_click_on_a_word_cluster_keeps_BOTH_letters_engraved():
    """The sin the removed refusal existed to stop was reading a word as its
    FIRST letter. Measured through a real `trim_apply`, not through
    `trim_pieces`: a point inside each glyph's stroke (found with the kernel,
    because a glyph's centroid is not on the glyph) must stay empty through
    every click that is not the delete gesture — and the delete gesture must
    take the WHOLE word, never half of it."""
    plate = dict(PLATE)
    word = dict(WORD)
    bar = {"kind": "rectangle", "mode": "add", "x": 0, "y": 13.2,
           "w": 70, "h": 3}
    ents = [plate, word, bar]
    glyph = sk._entity(dict(WORD, mode="add"))
    strokes = []
    for f in sorted(glyph.faces(), key=lambda g: g.center().X):
        bb = f.bounding_box()
        strokes.append(next(
            (bb.min.X + (bb.max.X - bb.min.X) * i / 30,
             bb.min.Y + (bb.max.Y - bb.min.Y) * j / 30)
            for i in range(1, 30) for j in range(1, 30)
            if tr._face_contains(f, bb.min.X + (bb.max.X - bb.min.X) * i / 30,
                                 bb.min.Y + (bb.max.Y - bb.min.Y) * j / 30)))
    assert len(strokes) == 2

    def material(shape, at):
        return any(tr._face_contains(f, *at) for f in shape.faces())

    before = sk.compose([dict(e) for e in ents], note=False)
    assert not any(material(before, s) for s in strokes)   # both engraved
    deletes = kept = 0
    for p in tr.trim_pieces(ents):
        try:
            out = tr.trim_apply([dict(e) for e in ents], p["id"])
        except ValueError:
            continue
        after = sk.compose(out["entities"], note=False)
        if p["whole"] and p["ent"] == 1:
            deletes += 1
            assert len(out["entities"]) == 2, "half a word was deleted"
            assert all(material(after, s) for s in strokes), \
                "deleting the word left one letter engraved"
            continue
        kept += 1
        assert not any(material(after, s) for s in strokes), \
            f"{p['id']} filled a letter in: {out['message']}"
    assert deletes == 5 and kept, f"{deletes} deletes, {kept} other clicks"


def test_the_endpoint_answers_pieces_for_a_word():
    from fastapi.testclient import TestClient
    import studio
    client = TestClient(studio.app)
    out = client.post("/api/sketch/trim/pieces",
                      json={"entities": [dict(PLATE), dict(WORD)]}).json()
    assert "error" not in out
    assert len([p for p in out["pieces"] if p["ent"] == 1]) == 5
