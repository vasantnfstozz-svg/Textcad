"""Trim and the builder must compose a sketch the SAME way.

LAUNCH-PLAN section 10, P1 (raised by the fourth sketch review 2026-09-09,
fixed 2026-09-11). `sketch_trim.py` kept its own copy of the composition
rule — a sequential add/subtract loop in DRAWING order — while `sketch.py`
orders outers before what nests inside them and material before a cut that
overlaps it. Measured before this fix, on `[boss r5 add, bar 80x6 cut,
pocket 40x20 cut]`:

    sketch.py composes          22.3648 mm2
    sketch_trim composes         0.0     mm2   -> every Trim click on that
                                                 cluster answered "the result
                                                 would have no area left"
    trim's pointwise material test said "empty" at (0, +-4), where the
    builder leaves boss                        -> a Trim click offered to
                                                 dissolve what is really the
                                                 profile's own edge
    deleting one bar from [pocket cut, bar, bar, bar] builds 144.0 mm2 and
    Trim refused it: "delete the cut shapes first"

The fix deletes trim's copy: `sketch.compose` / `sketch.compose_order` are
public now and trim asks them (R1 — never re-derive a backend fact).

And a P0 found in `sketch.py` itself while fixing it, because the Trim fix
inherits whatever the builder's order says. The fourth review's "material
before a cut that overlaps it" pass ran ONLY while the order started with a
cut, so one unrelated shape drawn FIRST switched the whole rule off:

    [boss, bar, pocket]           22.3648   (correct)
    [far circle, boss, bar, pocket]  157.0796  -- the boss built SOLID, the
                                     bar's 56.17 mm2 of red paint lost, green
                                     and silent; the honest answer is 100.9046

The pass runs for every cut now, so where a shape was drawn cannot change
the solid.
"""
import math

import pytest

import sketch as S
import sketch_trim as T


def circ(x, y, r, mode="add"):
    return {"kind": "circle", "x": x, "y": y, "r": r, "mode": mode}


def rect(x, y, w, h, mode="add"):
    return {"kind": "rectangle", "x": x, "y": y, "w": w, "h": h, "mode": mode}


def area(entities):
    return S.make_sketch("XY", 0.0, entities).area


BOSS = circ(0, 0, 5)
BAR = rect(0, 0, 80, 6, "subtract")
POCKET = rect(0, 0, 40, 20, "subtract")
FAR = circ(200, 0, 5)
BOSS_LESS_BAR = 22.3648
FAR_AREA = math.pi * 25


def cluster_of(entities, seed=0):
    outlines = [T._outline(e, i) for i, e in enumerate(entities)]
    _, _, crossing = T._pieces_raw(entities)
    return entities, outlines, T._cluster(entities, outlines, crossing, seed)


# --- the P0 in the builder: a cut hoisted past its material is still lost ---

def test_a_cut_survives_an_unrelated_shape_drawn_in_front_of_it():
    """157.0796 before: the overlap pass gave up the moment the order did not
    START with a cut, and one far-away circle was enough to make that so."""
    assert area([FAR, BOSS, BAR, POCKET]) == \
        pytest.approx(BOSS_LESS_BAR + FAR_AREA, abs=1e-3)


def test_the_far_shape_may_be_drawn_anywhere_in_the_list():
    """The fourth review promised that geometry, not drawing order, decides
    which shape bites which. It held for three entities and broke for four."""
    seen = set()
    for i in range(4):
        ents = [BOSS, BAR, POCKET]
        ents.insert(i, FAR)
        seen.add(round(area(ents), 3))
    assert seen == {round(BOSS_LESS_BAR + FAR_AREA, 3)}, seen


def test_every_drawing_order_of_the_four_gives_one_answer():
    from itertools import permutations
    seen = {round(area(list(p)), 3)
            for p in permutations([FAR, BOSS, BAR, POCKET])}
    assert seen == {round(BOSS_LESS_BAR + FAR_AREA, 3)}, seen


def test_the_three_entity_case_and_the_island_case_are_unchanged():
    assert area([BOSS, BAR, POCKET]) == pytest.approx(BOSS_LESS_BAR, abs=1e-3)
    assert area([circ(0, 0, 20, "subtract"), circ(0, 0, 10)]) == \
        pytest.approx(math.pi * 100, abs=1e-3)
    assert area([circ(0, 0, 30), circ(0, 0, 20, "subtract"),
                 circ(0, 0, 10)]) == pytest.approx(math.pi * 600, abs=1e-3)


def test_a_plate_full_of_holes_measures_no_overlap_at_all():
    """Cost: the pass pairs a cut with MATERIAL only, and a hole sitting in
    its plate is a nested pair it skips without asking the kernel. The
    ordinary sketch must not pay for the rule it never needs."""
    calls = []
    real = S._overlaps
    S._overlaps = lambda a, b: (calls.append(1), real(a, b))[1]
    try:
        plate = [rect(0, 0, 100, 60)] + \
            [circ(-40 + 10 * k, 0, 3, "subtract") for k in range(9)]
        assert area(plate) == pytest.approx(6000 - 9 * math.pi * 9, abs=1e-3)
    finally:
        S._overlaps = real
    assert calls == [], f"{len(calls)} overlap booleans on a plate with holes"


# --- there is one composition rule, and trim uses it ----------------------

def test_trim_composes_the_cluster_exactly_as_the_builder_does():
    """0.0 before, against the builder's 22.3648."""
    ents, _, cl = cluster_of([BOSS, BAR, POCKET])
    assert float(T._compose_faces(ents, cl).area) == \
        pytest.approx(BOSS_LESS_BAR, abs=1e-3)


@pytest.mark.parametrize("ents", [
    [BOSS, BAR, POCKET],
    [POCKET, BAR, BOSS],
    [rect(0, 0, 40, 20, "subtract"), rect(-12, 0, 6, 12),
     rect(0, 0, 6, 12), rect(12, 0, 6, 12)],
    [circ(0, 0, 30), circ(0, 0, 20, "subtract"), circ(0, 0, 10)],
    [rect(0, 0, 40, 20), circ(20, 0, 8, "subtract")],
])
def test_trims_composition_equals_the_builders_on_every_cluster(ents):
    entities, outlines, _ = cluster_of(ents)
    _, _, crossing = T._pieces_raw(entities)
    for seed in range(len(entities)):
        cl = T._cluster(entities, outlines, crossing, seed)
        mine = float(T._compose_faces(entities, cl).area)
        theirs = float(S.compose([entities[i] for i in cl], note=False).area)
        assert mine == pytest.approx(theirs, abs=1e-6), (seed, cl)


def test_the_material_test_agrees_with_the_builder_where_it_used_to_lie():
    """(0, +-4) is boss the builder keeps and trim called empty."""
    entities, outlines, cl = cluster_of([BOSS, BAR, POCKET])
    for y in (4.0, -4.0):
        assert T._material_at(entities, outlines, cl, 0.0, y) is True
    assert T._material_at(entities, outlines, cl, 0.0, 0.0) is False


def test_the_material_test_agrees_with_the_builder_across_the_cluster():
    """A grid, not two lucky points. Samples within 0.35 mm of any outline are
    skipped — the boundary is ambiguous for both sides."""
    import numpy as np
    ents = [BOSS, BAR, POCKET]
    entities, outlines, cl = cluster_of(ents)
    built = S.make_sketch("XY", 0.0, ents)
    rings = []
    for f in built.faces():
        ow = f.outer_wire()

        def samp(w):
            n = 240
            return np.array([[(w.position_at(i / n)).X,
                              (w.position_at(i / n)).Y] for i in range(n)])
        rings.append((samp(ow), [samp(w) for w in f.wires()
                                 if not w.is_same(ow)]))

    def in_built(x, y):
        return any(T._inside({"pts": o}, x, y)
                   and not any(T._inside({"pts": h}, x, y) for h in holes)
                   for o, holes in rings)

    bad, tested = [], 0
    for x in np.linspace(-21, 21, 43):
        for y in np.linspace(-11, 11, 23):
            if any(np.hypot(o["pts"][:, 0] - x, o["pts"][:, 1] - y).min() < 0.35
                   for o in outlines):
                continue
            tested += 1
            if T._material_at(entities, outlines, cl, float(x), float(y)) \
                    != in_built(float(x), float(y)):
                bad.append((round(float(x), 2), round(float(y), 2)))
    assert tested > 300
    assert bad == [], f"{len(bad)} of {tested} points disagree, e.g. {bad[:4]}"


def test_every_click_on_that_cluster_now_does_something():
    """Each of the 16 pieces answered "the result would have no area left"."""
    ents = [BOSS, BAR, POCKET]
    pieces = T.trim_pieces(ents)
    assert len(pieces) == 16
    for p in pieces:
        out = T.trim_apply(ents, p["id"])
        assert area(out["entities"]) > 0


def test_a_hover_does_not_leave_a_note_for_the_next_rebuild():
    """`compose` publishes "entity N removes nothing" into the module note
    list, which `Document.warnings` drains and shows in the tree. A Trim
    click asking a question about the sketch must not put a sentence about
    entity 1 of a CLUSTER into the next feature's warnings."""
    S.drain_notes()
    ents = [BOSS, BAR, POCKET]
    piece = T.trim_pieces(ents)[0]
    T.trim_apply(ents, piece["id"])
    assert S.drain_notes() == []


# --- trim accepts what the builder accepts, and nothing else --------------

def test_deleting_one_bar_from_a_pocket_is_allowed():
    """Refused before with "delete the cut shapes first", for a sketch the
    builder composes at 144.0 mm2."""
    bars = [rect(0, 0, 40, 20, "subtract"), rect(-12, 0, 6, 12),
            rect(0, 0, 6, 12), rect(12, 0, 6, 12)]
    assert area(bars) == pytest.approx(216.0, abs=1e-6)
    whole = next(p for p in T.trim_pieces(bars) if p["ent"] == 1)
    out = T.trim_apply(bars, whole["id"])
    assert area(out["entities"]) == pytest.approx(144.0, abs=1e-6)
    assert out["entities"][0]["mode"] == "subtract"      # and that is fine


def test_deleting_the_only_material_is_still_refused_in_a_sentence():
    ents = [circ(0, 0, 20, "subtract"), circ(0, 0, 10)]
    whole = next(p for p in T.trim_pieces(ents) if p["ent"] == 1)
    with pytest.raises(ValueError) as exc:
        T.trim_apply(ents, whole["id"])
    msg = str(exc.value).lower()
    assert "trim" in msg and "cut" in msg
    assert "traceback" not in msg and "exception" not in msg


def test_a_sketch_that_was_already_broken_is_not_blamed_on_the_click():
    """[r10 add, r10 cut, far cut] does not build before OR after the click.
    Refusing would trap the user inside a sketch they cannot repair with the
    tool they reached for."""
    ents = [circ(0, 0, 10), circ(0, 0, 10, "subtract"),
            circ(100, 0, 5, "subtract")]
    with pytest.raises(ValueError):
        area(ents)
    whole = next(p for p in T.trim_pieces(ents) if p["ent"] == 2)
    out = T.trim_apply(ents, whole["id"])
    assert [e["kind"] for e in out["entities"]] == ["circle", "circle"]


def test_the_refusal_names_the_builders_own_complaint():
    ents = [circ(0, 0, 20, "subtract"), circ(0, 0, 10)]
    whole = next(p for p in T.trim_pieces(ents) if p["ent"] == 1)
    try:
        T.trim_apply(ents, whole["id"])
    except ValueError as ex:
        assert "nothing for them to cut into" in str(ex)
    else:
        pytest.fail("expected a refusal")


# --- the public rule is the only rule ------------------------------------

def test_compose_order_is_the_order_compose_uses():
    ents = [FAR, BOSS, BAR, POCKET]
    order = S.compose_order(ents)
    assert sorted(order) == [0, 1, 2, 3]
    assert order.index(1) < order.index(2), "boss must precede the bar"
    replay = S.compose([ents[i] for i in order], note=False)
    assert float(replay.area) == pytest.approx(area(ents), abs=1e-6)


def test_an_all_add_sketch_is_not_measured_at_all():
    calls = []
    real = S._containment
    S._containment = lambda shapes: (calls.append(1), real(shapes))[1]
    try:
        assert S.compose_order([circ(0, 0, 10), circ(30, 0, 10)]) == [0, 1]
    finally:
        S._containment = real
    assert calls == []
