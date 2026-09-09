"""Fourth review of the sketch composition order (5f65a7a), 2026-09-09.

Ten independent reviewers with a three-judge panel per finding. The one that
matters is the same twenty lines again, and this time the rule itself was
incomplete rather than inverted.

`_compose_order` puts an outer before whatever is nested inside it, and
5f65a7a then made a cut that ends up FIRST remove nothing - "nothing is
composed yet, so there is nothing to cut". True as far as it goes. But a cut
can be pushed to the front for a reason that has nothing to do with what it
bites: an entity waits only for the shapes it is nested inside, so a cut that
overlaps some material can be ordered ahead of it because THAT material
happens to sit inside a different cut. Dropping it then loses a cut the user
drew.

Measured before this fix:

  [circle r5 add, rect 80x6 subtract]                     22.3648  (correct)
  the same two, plus a rect 40x20 subtract around them    78.5398  (the bar's
                                                          cut lost entirely -
                                                          56.17 mm2 of red
                                                          paint built solid)

The ordering constraint is therefore in two parts, not one:
  - an outer is composed before anything nested inside it (a hole needs its
    material; an island survives its hole);
  - material is composed before a cut that OVERLAPS it without containing it.
A cut that still leads after both is one that genuinely meets nothing, and
only that one is dropped.

Also fixed here, all from the same review:
  - the emptiness reset fired after an ADD as well as a cut, so a single
    entity of area <= 1e-9 (a radius typed as 0.00001 in the tree) raised
    "the cuts removed everything that was drawn" for a sketch with no cut in
    it, where it used to build;
  - the dropped-cut note claimed "nothing in this sketch is drawn beneath it"
    even when material HAD been drawn there and was cut away first;
  - REJECTED, and worth recording because it looked convincing: "the note is
    never rendered, so a dropped cut is still silent". Only extrude.js reads
    f.notes in the frontend, but `Document.warnings` republishes every note as
    "'<feature>': <note>" (document.py:1211) and tree.js renderWarnings shows
    those in its info box. The note IS visible. What WAS real, next to it: a
    SUPPRESSED feature kept its notes, so the box went on stating a fact about
    geometry no longer in the model;
  - a path segment with no "to", or an arc whose "via" holds one number,
    reached the user as KeyError('to') / IndexError - the `via` read was
    moved out of the translator's try in 5f65a7a, but `to` never was;
  - sketch_corner._chain fabricated a start at the origin for a path that has
    none, and set_arc_radius WRITES that start back into the design
    (sketch_corner.py:240) - invented geometry saved to disk;
  - scaleEntity's new guards wrote the same fabricated start into the entity.
"""
import math

import pytest

import sketch as S
import sketch_corner as C


def circ(x, y, r, mode="add"):
    return {"kind": "circle", "x": x, "y": y, "r": r, "mode": mode}


def rect(x, y, w, h, mode="add"):
    return {"kind": "rectangle", "x": x, "y": y, "w": w, "h": h, "mode": mode}


def area(entities):
    return S.make_sketch("XY", 0.0, entities).area


BOSS = circ(0, 0, 5)
BAR = rect(0, 0, 80, 6, "subtract")
POCKET = rect(0, 0, 40, 20, "subtract")
BOSS_LESS_BAR = 22.3648


# --- the P0: a hoisted cut still bites -----------------------------------

def test_a_cut_that_overlaps_material_bites_it():
    """The two-entity control. This never broke; it is the number the
    three-entity case has to agree with."""
    assert area([BOSS, BAR]) == pytest.approx(BOSS_LESS_BAR, abs=1e-3)


def test_an_unrelated_pocket_does_not_cancel_that_cut():
    """Built 78.5398 - the whole boss, as if the bar had never been drawn -
    because the boss sits inside the pocket and therefore waited, which let
    the bar be ordered first and dropped."""
    assert area([BOSS, BAR, POCKET]) == pytest.approx(BOSS_LESS_BAR, abs=1e-3)


def test_that_result_does_not_depend_on_the_drawing_order():
    """A cut and the material it bites are ordered by geometry now, so the
    order the three shapes were DRAWN in cannot change the solid."""
    seen = set()
    for a, b, c in ((0, 1, 2), (0, 2, 1), (1, 0, 2),
                    (1, 2, 0), (2, 0, 1), (2, 1, 0)):
        ents = [[BOSS, BAR, POCKET][i] for i in (a, b, c)]
        seen.add(round(area(ents), 3))
    assert seen == {round(BOSS_LESS_BAR, 3)}, seen


def test_a_cut_that_meets_nothing_is_still_dropped():
    """The island case the previous round exists for: the only thing the cut
    contains is an add, which must survive it."""
    assert area([circ(0, 0, 20, "subtract"), circ(0, 0, 10)]) == \
        pytest.approx(math.pi * 100, abs=1e-3)


def test_a_hole_still_cuts_the_outer_it_sits_in():
    """The plain washer, unchanged."""
    assert area([circ(0, 0, 30), circ(0, 0, 20, "subtract")]) == \
        pytest.approx(math.pi * 500, abs=1e-3)


def test_the_three_bars_case_from_the_last_round_is_unchanged():
    assert area([rect(0, 0, 40, 20, "subtract"), rect(-12, 0, 6, 12),
                 rect(0, 0, 6, 12), rect(12, 0, 6, 12)]) == \
        pytest.approx(216.0, abs=1e-6)


def test_ordering_a_sketch_with_no_cut_costs_no_measurement():
    """An all-add sketch must not pay for any of this - the containment and
    overlap measurements are only reached when something subtracts."""
    calls = []
    real = S._containment
    S._containment = lambda shapes: (calls.append(1), real(shapes))[1]
    try:
        area([circ(0, 0, 10), circ(30, 0, 10), circ(60, 0, 10)])
    finally:
        S._containment = real
    assert calls == []


# --- the emptiness reset belongs to cuts only ----------------------------

def test_one_tiny_shape_with_no_cut_still_builds():
    """A radius of 0.00001 typed into the tree gives an area of 3.1e-10, which
    tripped the reset and raised "the cuts removed everything that was drawn"
    - for a sketch containing no cut at all. It built before 5f65a7a and
    builds again."""
    assert area([circ(0, 0, 1e-5)]) > 0


def test_a_cut_that_empties_everything_still_says_so():
    with pytest.raises(ValueError) as exc:
        area([circ(0, 0, 10), circ(0, 0, 10, "subtract")])
    assert "cuts removed everything" in str(exc.value).lower()


def test_an_add_after_everything_was_cut_away_still_builds():
    assert area([circ(0, 0, 10), circ(0, 0, 10, "subtract"),
                 circ(100, 0, 5)]) == pytest.approx(math.pi * 25, abs=1e-3)


# --- the note has to be true, and has to be visible ----------------------

def test_the_note_does_not_claim_an_empty_canvas_when_material_was_cut_away():
    """[add r10, cut r10, cut r3, add r5 far away]: the second entity empties
    the profile, so the third meets no material - but something HAD been
    drawn beneath it, so "nothing in this sketch is drawn beneath it" is a
    false statement about the user's own sketch."""
    S.drain_notes()
    area([circ(0, 0, 10), circ(0, 0, 10, "subtract"),
          circ(0, 0, 3, "subtract"), circ(100, 0, 5)])
    notes = " ".join(S.drain_notes()).lower()
    assert "already been cut away" in notes
    assert "nothing in this sketch is drawn beneath it" not in notes


def test_the_note_still_names_an_empty_canvas_when_that_is_the_truth():
    S.drain_notes()
    area([circ(0, 0, 20, "subtract"), circ(0, 0, 10)])
    notes = " ".join(S.drain_notes()).lower()
    assert "nothing" in notes and "cut" in notes


def test_the_note_names_the_row_the_user_is_looking_at():
    """The number in the note is the entity's position in the STORED list -
    the order the tree shows - not its position in the composition order."""
    S.drain_notes()
    area([circ(0, 0, 20, "subtract"), circ(0, 0, 10)])
    assert "entity 1" in " ".join(S.drain_notes())


# --- a malformed path says what is wrong, in a sentence ------------------

def test_a_segment_with_no_destination_says_so():
    with pytest.raises(ValueError) as exc:
        area([{"kind": "path", "start": [0, 0], "segments": [
            {"type": "line", "to": [10, 0]},
            {"type": "line"},
            {"type": "line", "to": [0, 0]}]}])
    msg = str(exc.value).lower()
    assert "keyerror" not in msg and "traceback" not in msg
    assert "end point" in msg or "no destination" in msg or "where" in msg


def test_an_arc_via_with_one_number_says_so():
    with pytest.raises(ValueError) as exc:
        area([{"kind": "path", "start": [0, 0], "segments": [
            {"type": "arc", "via": [5], "to": [10, 0]},
            {"type": "line", "to": [0, 0]}]}])
    msg = str(exc.value).lower()
    assert "indexerror" not in msg and "traceback" not in msg
    assert "two numbers" in msg or "x and y" in msg or "point" in msg


def test_a_good_path_still_builds():
    assert area([{"kind": "path", "start": [0, 0], "segments": [
        {"type": "line", "to": [10, 0]},
        {"type": "arc", "via": [12, 5], "to": [10, 10]},
        {"type": "line", "to": [0, 10]}]}]) > 0


# --- the radius edit must not invent a start point -----------------------

def test_the_radius_edit_refuses_a_path_with_no_start():
    """sketch_corner._chain read `ent.get("start") or (0, 0)` and
    set_arc_radius WRITES the start back (sketch_corner.py:240), so editing a
    curve's radius on a start-less path saved a vertex at the origin that the
    user never drew."""
    ent = {"kind": "path", "segments": [
        {"type": "arc", "via": [5, 3], "to": [10, 0]},
        {"type": "line", "to": [10, 10]},
        {"type": "line", "to": [0, 0]}]}
    with pytest.raises(ValueError, match="start"):
        C.path_arcs(ent)
    with pytest.raises(ValueError, match="start"):
        C.set_arc_radius([ent], 0, 0, 4.0)
    assert "start" not in ent, "the entity was mutated by a failed edit"


def test_the_radius_edit_still_works_on_a_good_path():
    ent = {"kind": "path", "start": [0, 0], "segments": [
        {"type": "arc", "via": [5, 3], "to": [10, 0]},
        {"type": "line", "to": [10, 10]},
        {"type": "line", "to": [0, 10]}]}
    out = C.set_arc_radius([ent], 0, 0, 6.0)
    assert out and out[0]["segments"][0]["via"] != [5, 3]


# --- a switched-off feature has nothing to report ------------------------

def test_a_suppressed_feature_stops_publishing_its_note():
    """f.notes rides into `Document.warnings` (document.py:1211) and the tree
    renders those in its info box, so a note is genuinely visible - but the
    suppressed branch of `rebuild` left the notes in place, and the box kept
    stating a fact about geometry no longer in the model."""
    import document
    d = document.Document("probe")
    d.add("s1", "sketch", params={"plane": "XY", "offset": 0, "entities": [
        circ(0, 0, 20, "subtract"), circ(0, 0, 10)]})
    d.add("e1", "extrude", inputs=["s1"], params={"amount": 3})
    d.rebuild()
    assert any("removes nothing" in w for w in d.warnings), d.warnings
    [f] = [x for x in d.features if x.id == "s1"]
    f.suppressed = True
    d.rebuild()
    assert not any("removes nothing" in w for w in d.warnings), d.warnings
    assert f.notes == []


# --- the fifth review of the same code: five follow-ups -----------------
#
# A single reviewer at medium, as REVIEW-BRIEF.md now asks for. It cleared the
# two-part ordering rule (no arrangement makes it worse; termination bounded;
# a 24-entity adversarial sketch orders in 0.11 s) and found five gaps in the
# fix pass itself, all measured below.

def test_a_start_point_of_one_number_says_so():
    """`IndexError('tuple index out of range')` before: the fourth review's
    own fix checked that `start` EXISTS but not that it holds two numbers."""
    with pytest.raises(ValueError) as exc:
        area([{"kind": "path", "start": [5], "segments": [
            {"type": "line", "to": [10, 0]},
            {"type": "line", "to": [0, 0]}]}])
    msg = str(exc.value).lower()
    assert "two numbers" in msg
    assert "index" not in msg


def test_a_start_point_of_words_says_so():
    """A raw `could not convert string to float: 'a'` before."""
    with pytest.raises(ValueError) as exc:
        area([{"kind": "path", "start": ["a", "b"], "segments": [
            {"type": "line", "to": [10, 0]},
            {"type": "line", "to": [0, 0]}]}])
    assert "two numbers" in str(exc.value).lower()
    assert "convert" not in str(exc.value).lower()


def test_the_radius_row_survives_a_malformed_via():
    """`s["via"]` is read raw in path_arcs and set_arc_radius, and an
    IndexError from there is not in studio.py's catch list: POST
    /api/sketch/path-arcs answered 500 and EVERY radius row in the sketch
    disappeared."""
    ent = {"kind": "path", "start": [0, 0], "segments": [
        {"type": "arc", "via": [5], "to": [10, 0]},
        {"type": "line", "to": [0, 0]}]}
    with pytest.raises(ValueError) as exc:
        C.path_arcs(ent)
    assert "two numbers" in str(exc.value).lower()
    with pytest.raises(ValueError):
        C.set_arc_radius([ent], 0, 0, 4.0)


def test_an_unmeasurable_overlap_is_treated_as_an_overlap():
    """`_overlaps` swallows a boolean that will not run. Answering False
    leaves the cut at the FRONT of the order, where `_compose` drops it - so
    one failed measurement brings the P0 back. True only orders the material
    first, and subtracting a shape that turns out not to overlap removes
    nothing anyway."""
    boss, bar = S._entity(BOSS), S._entity(BAR)
    assert S._overlaps(boss, bar) is True          # the ordinary answer

    class NoBoolean(type(boss)):                   # its `&` will not run
        def __and__(self, other):
            raise RuntimeError("kernel says no")

    blind = S._entity(BOSS)
    blind.__class__ = NoBoolean
    assert S._overlaps(blind, bar) is True,         "an unmeasurable pair must be treated as overlapping, not as apart"


def test_the_boss_survives_its_bar_only_when_the_overlap_is_seen():
    """The consequence of the line above, end to end."""
    real = S._overlaps
    S._overlaps = lambda a, b: False          # every measurement fails
    try:
        blind = area([BOSS, BAR, POCKET])
    finally:
        S._overlaps = real
    assert round(blind, 3) == 78.540, blind          # the P0, reproduced
    assert area([BOSS, BAR, POCKET]) == pytest.approx(BOSS_LESS_BAR, abs=1e-3)


def test_a_rolled_back_feature_reports_no_piece_count():
    """With the bar parked before a severing cut the part is WHOLE, but
    `_check_pieces` filters only `suppressed`, so the panel went on saying
    "leaves the part in 2 separate pieces"."""
    import document
    d = document.Document("probe")
    d.add("plate_s", "sketch", params={"plane": "XY", "offset": 0,
                                       "entities": [rect(0, 0, 60, 20)]})
    d.add("plate", "extrude", inputs=["plate_s"], params={"amount": 5})
    d.add("knife_s", "sketch", params={"plane": "XY", "offset": 0,
                                       "entities": [rect(0, 0, 4, 40)]})
    d.add("knife", "extrude", inputs=["knife_s"], params={"amount": 5})
    d.add("sever", "cut", inputs=["plate", "knife"])
    d.rebuild()
    assert any("2 separate pieces" in w for w in d.warnings), d.warnings
    d.rollback = "knife"
    d.rebuild()
    assert not any("separate pieces" in w for w in d.warnings), d.warnings
