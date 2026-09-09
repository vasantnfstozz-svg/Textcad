"""Third review of the sketch composition order (6e2cae9), 2026-09-09.

The second fix pass replaced a sort-by-depth with `_compose_order` — a real
topological order — and then DEFERRED a leading subtraction to just after the
first add, so the sketch would keep the area it had before. The two cancel:
`_compose_order` hoists a subtraction in FRONT of the add nested inside it
*precisely so that add survives as an island*, and the deferral subtracted it
from exactly that add.

Ground truth for what a sketch means: the sketcher paints every entity on its
own — `add` fills GREEN, `subtract` fills RED (`sketcher.js:1611`); there is
no even-odd canvas fill. A green region the kernel builds away is the same
class of defect as the first review's F1 (a disc built where a washer was
drawn).

Measured before the fix (`probes/sketcher_review3_probe.py`):

F1 (P0) `[r20 subtract, r10 add]` built area **0.0** and reported `ok` — a
        successful empty sketch, the second banned failure. Three identical
        bars inside one subtract blob built 144.0 instead of 216.0: the FIRST
        bar silently missing, the other two there. The user's own
        `esp32-remote/logo_1_sketch` built 4.3671 where the editor shows
        4.3671 + a 3.2985 mm2 green bar = 7.6656; `_compose_order` returns
        `[1, 0, 2, 3]` specifically to save that bar.
F2 (P1) a result cut away to nothing reached `_as_sketch` as an empty
        Compound: `pl * <empty>` is a plain `list`, so the user got
        `AttributeError: 'list' object has no attribute 'faces'` in the tree.
F3 (P2) a subtraction applied to an already-empty result raised build123d's
        `ValueError: Dimensions of objects to subtract from are inconsistent`
        verbatim.
F4 (P3) an arc segment with no `via` at all reported "the middle point lies
        on the straight line between its ends" — a sentence about a point
        that is not there. `_validate_path` guards with `s.get("via")`, so
        the `KeyError` fell into the arc translator's `except Exception`.
F5 (P2) a `path` entity with no `start` is refused by every reader in the
        editor (`outlinePts`, `hitTest`, `entityHandles`, `collectSnapPoints`
        all guard `&& e.start`) — invisible and unclickable — yet the backend
        defaulted it to the origin and built it anyway. The editor and the
        kernel must not disagree about what a sketch contains.
"""
import math

import pytest

import sketch as S


def circ(x, y, r, mode="add"):
    return {"kind": "circle", "x": x, "y": y, "r": r, "mode": mode}


def rect(x, y, w, h, mode="add"):
    return {"kind": "rectangle", "x": x, "y": y, "w": w, "h": h, "mode": mode}


def area(entities):
    return S.make_sketch("XY", 0.0, entities).area


# --- F1 (P0): a leading subtraction has nothing to cut -------------------

def test_island_inside_a_leading_subtraction_survives():
    """The add nested inside a leading subtraction is the whole reason the
    subtraction was hoisted in front of it. Built 0.0 before the fix."""
    a = area([circ(0, 0, 20, "subtract"), circ(0, 0, 10)])
    assert a == pytest.approx(math.pi * 100, abs=1e-3)


def test_every_bar_in_a_subtract_blob_survives():
    """Three identical bars inside one subtract blob: 144.0 before the fix
    (the first bar eaten), 216.0 after."""
    a = area([rect(0, 0, 40, 20, "subtract"), rect(-12, 0, 6, 12),
              rect(0, 0, 6, 12), rect(12, 0, 6, 12)])
    assert a == pytest.approx(216.0, abs=1e-6)


def test_logo_1_topology_keeps_its_bar():
    """The shape of the user's `esp32-remote/logo_1_sketch`: a small add
    centred inside a bigger subtract, then two unrelated adds. 4.3671 mm2
    before the fix, 7.6656 after — the bar the editor paints green."""
    ents = [rect(0, 0, 5.3, 0.67), rect(0, 0, 8.2, 4.05, "subtract"),
            rect(40, 0, 9.8, 2.5), rect(60, 0, 2.4, 0.7)]
    a = area(ents)
    assert a == pytest.approx(5.3 * 0.67 + 9.8 * 2.5 + 2.4 * 0.7, abs=1e-6)


def test_a_dropped_cut_is_not_silent():
    """It removes nothing, so it must not fail the feature — but the user is
    told, in the feature's notes, not left to wonder."""
    S.drain_notes()
    area([circ(0, 0, 20, "subtract"), circ(0, 0, 10)])
    notes = S.drain_notes()
    assert any("nothing" in n.lower() and "cut" in n.lower() for n in notes), \
        notes


def test_a_nested_island_still_composes_in_order():
    """The first review's F2, unchanged: outer, hole, island = 1884.96."""
    a = area([circ(0, 0, 30), circ(0, 0, 20, "subtract"), circ(0, 0, 10)])
    assert a == pytest.approx(math.pi * 600, abs=1e-3)


def test_a_hole_still_cuts_the_outer_it_sits_in():
    """A leading subtraction cutting nothing must not weaken the ordinary
    case: a washer is still a washer."""
    a = area([circ(0, 0, 30), circ(0, 0, 20, "subtract")])
    assert a == pytest.approx(math.pi * 500, abs=1e-3)


# --- F2/F3 (P1/P2): an empty result speaks for itself --------------------

def test_all_material_cut_away_says_so():
    """`AttributeError: 'list' object has no attribute 'faces'` before."""
    with pytest.raises(ValueError) as exc:
        area([circ(0, 0, 10), circ(0, 0, 10, "subtract")])
    msg = str(exc.value).lower()
    assert "empty" in msg or "cut away" in msg
    assert "attribute" not in msg


def test_a_cut_on_an_emptied_result_does_not_reach_the_kernel():
    """build123d's `Dimensions of objects to subtract from are inconsistent`
    before — kernel text in the tree (rule 5)."""
    with pytest.raises(ValueError) as exc:
        area([circ(0, 0, 10), circ(0, 0, 10, "subtract"),
              circ(0, 0, 3, "subtract")])
    assert "dimensions" not in str(exc.value).lower()


def test_an_add_after_everything_was_cut_away_still_builds():
    """Emptied is not failed: the next add starts the profile again."""
    a = area([circ(0, 0, 10), circ(0, 0, 10, "subtract"), circ(100, 0, 5)])
    assert a == pytest.approx(math.pi * 25, abs=1e-3)


def test_a_sketch_of_nothing_but_cuts_is_still_refused():
    with pytest.raises(ValueError) as exc:
        area([circ(0, 0, 20, "subtract"), circ(0, 0, 10, "subtract")])
    assert "cut" in str(exc.value).lower()


# --- F4 (P3): the message names the mistake that was made ----------------

def test_an_arc_with_no_via_says_via():
    with pytest.raises(ValueError) as exc:
        area([{"kind": "path", "start": [0, 0], "segments": [
            {"type": "line", "to": [10, 0]},
            {"type": "arc", "to": [0, 10]},
            {"type": "line", "to": [0, 0]}]}])
    msg = str(exc.value).lower()
    assert "through" in msg or "middle point" in msg
    assert "straight line between its ends" not in msg


def test_an_arc_whose_via_is_collinear_still_says_so():
    """The real collinear message must survive the one above."""
    with pytest.raises(ValueError) as exc:
        area([{"kind": "path", "start": [0, 0], "segments": [
            {"type": "line", "to": [10, 0]},
            {"type": "arc", "via": [10, 5], "to": [10, 10]},
            {"type": "line", "to": [0, 10]},
            {"type": "line", "to": [0, 0]}]}])
    assert "straight line" in str(exc.value).lower()


# --- F5 (P2): the editor and the kernel agree on what is there -----------

def test_a_path_with_no_start_is_refused():
    """Invisible in the editor (every reader guards `&& e.start`), built from
    the origin by the backend before this."""
    with pytest.raises(ValueError) as exc:
        area([{"kind": "path", "segments": [
            {"type": "line", "to": [10, 0]},
            {"type": "line", "to": [10, 10]},
            {"type": "line", "to": [0, 0]}]}])
    assert "start" in str(exc.value).lower()


def test_a_path_starting_at_the_origin_is_fine():
    """[0, 0] is a start point, not a missing one."""
    a = area([{"kind": "path", "start": [0, 0], "segments": [
        {"type": "line", "to": [10, 0]},
        {"type": "line", "to": [10, 10]},
        {"type": "line", "to": [0, 10]}]}])
    assert a == pytest.approx(100.0, abs=1e-6)
