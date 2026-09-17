"""Trim's cost, locked by COUNTS — LAUNCH-PLAN section 10 P2.

The defect: Trim was slow on a big sketch, and it is the one the user feels
with their hand. Profiled 2026-09-17 (`probes/trim_profile.py`) on the user's
own `rocky-balboa/field_sketch`, 23 entities:

    hover  8903 ms  of which  8806 ms sampling outlines,  68 ms pair loop
    click 18021 ms  of which  9152 ms sampling outlines, 4349 ms compose

Not the pair loop the plan suspected — 0.8% — but `wire.position_at()`.
build123d's `Wire._occt_param_at` rebuilds the wire's whole edge table on
EVERY call, so 2671 sample points built 247,466 Edge objects. The table is
the same for every sample of one wire, so `_sample_wire` builds it once.

Seconds are not the test: this box runs several OpenCASCADE agents at once
and the wall clock swings threefold. COUNTS do not swing, so the tests below
count instead — how many times a wire is walked, how many outline pairs are
multiplied out — and, because a speed-up that moves a piece is a correctness
bug and not an improvement, that the pieces are bit-for-bit what the stock
`wire.position_at` loop produced.
"""
from __future__ import annotations
import math
from contextlib import contextmanager

import build123d as b3d
import numpy as np
import pytest

import sketch_trim as tr


# ------------------------------------------------------------- counters --

@contextmanager
def counting_wire_walks():
    """Count `Wire.edges()` — the O(edges) table build inside position_at."""
    seen = {"n": 0}
    original = b3d.Wire.edges

    def edges(self):
        seen["n"] += 1
        return original(self)

    b3d.Wire.edges = edges
    try:
        yield seen
    finally:
        b3d.Wire.edges = original


@contextmanager
def counting_pair_intersections():
    """Count outline PAIRS actually multiplied out by the O(n^2) loop."""
    seen = {"n": 0, "seg_pairs": 0}
    original = tr._poly_intersections

    def counted(a, b):
        seen["n"] += 1
        seen["seg_pairs"] += len(a["pts"]) * len(b["pts"])
        return original(a, b)

    tr._poly_intersections = counted
    try:
        yield seen
    finally:
        tr._poly_intersections = original


@contextmanager
def stock_sampler():
    """`_outline` as it stood before the fix: one position_at per point."""
    original = tr._sample_wire

    def sample(wire, n):
        pts = np.empty((n, 2))
        for i in range(n):
            p = wire.position_at(i / n)
            pts[i] = (p.X, p.Y)
        return pts

    tr._sample_wire = sample
    try:
        yield
    finally:
        tr._sample_wire = original


# -------------------------------------------------------------- shapes --

def traced(points: int, r: float, x=0.0, y=0.0, mode="add") -> dict:
    """A many-edged polygon like the ones an image trace leaves behind — the
    shape class this defect lives on (`field_sketch` carries 320-edge ones)."""
    pts = []
    for k in range(points):
        a = 2 * math.pi * k / points
        rad = r + 0.07 * r * math.sin(7 * a)
        pts.append([round(rad * math.cos(a), 4), round(rad * math.sin(a), 4)])
    return {"kind": "polygon", "mode": mode, "x": x, "y": y, "points": pts}


RECT = {"kind": "rectangle", "mode": "add", "x": 0, "y": 0, "w": 40, "h": 20}


def fingerprint(entities):
    """Everything Trim promises about a sketch, to full precision."""
    pieces, _, crossing = tr._pieces_raw(entities)
    return ([(p["id"], p["ent"], p["whole"], p["_pts"].tobytes())
             for p in pieces], sorted(crossing))


# ---------------------------------------------- the wire is walked ONCE --

def test_an_outline_walks_its_wire_once_not_once_per_sample():
    """The fix, stated as a count.

    Before it, `_outline` called `wire.position_at` for every sample point and
    each call rebuilt the edge table: 166 walks of this 240-edge polygon,
    39,840 Edge objects. One walk now — and that is the whole speed-up.
    """
    ent = traced(240, 20.0)
    with counting_wire_walks() as seen:
        outline = tr._outline(ent, 0)
    assert len(outline["pts"]) == 166          # unchanged sample budget
    assert seen["n"] <= 4, (
        f"the wire was walked {seen['n']} times for 166 sample points — the "
        f"edge table is supposed to be built once per wire")


def test_the_walk_count_does_not_grow_with_the_sample_count():
    """The invariant behind the count above: the table is per WIRE, not per
    point. Ten points and four hundred must cost the same walk."""
    wire = tr._entity_face(traced(240, 20.0), 0).outer_wire()
    with counting_wire_walks() as few:
        tr._sample_wire(wire, 10)
    with counting_wire_walks() as many:
        tr._sample_wire(wire, 400)
    assert few["n"] == many["n"] == 1


def test_a_whole_sketch_walks_one_wire_per_entity():
    """`trim_pieces` on a sketch of traced shapes — the user's case."""
    ents = [traced(120, 18.0, x=-30), traced(120, 18.0, x=30),
            traced(90, 10.0, x=0, y=0, mode="subtract"), dict(RECT)]
    with counting_wire_walks() as seen:
        tr.trim_pieces(ents)
    assert seen["n"] <= 4 * len(ents), (
        f"{seen['n']} wire walks for {len(ents)} entities")


# ------------------------------------------ the pair loop stays skipped --

def test_only_outline_pairs_whose_boxes_touch_are_intersected():
    """The bounding-box skip, locked as a count.

    Ten circles in a row that touch nobody plus one overlapping pair: 66
    pairs exist, 1 may be multiplied out. Cheap, and it was already there —
    the profile put the whole pair loop at 68 ms of an 8903 ms hover, which
    is why this defect was NOT fixed by touching it.
    """
    ents = [{"kind": "circle", "mode": "add", "x": 40 * i, "y": 0, "r": 8}
            for i in range(11)]
    ents.append({"kind": "circle", "mode": "subtract", "x": 6, "y": 0, "r": 8})
    with counting_pair_intersections() as seen:
        tr.trim_pieces(ents)
    assert seen["n"] == 1, (
        f"{seen['n']} of 66 outline pairs were intersected; only the one "
        f"overlapping pair has touching boxes")


def test_a_far_apart_sketch_costs_no_pair_work_at_all():
    ents = [traced(60, 6.0, x=100 * i) for i in range(6)]
    with counting_pair_intersections() as seen:
        pieces = tr.trim_pieces(ents)
    assert seen["n"] == 0
    assert all(p["whole"] for p in pieces)


# --------------------------------------- and the pieces have not moved --

IDENTITY_CASES = {
    "rect + circle cut": [dict(RECT), {"kind": "circle", "mode": "subtract",
                                       "x": 20, "y": 0, "r": 8}],
    "two traced blobs crossing": [traced(120, 18.0, x=-12),
                                  traced(96, 15.0, x=12)],
    "traced blob on a rect": [dict(RECT), traced(60, 14.0, x=18, y=6)],
    "ellipse + slot + polygon": [
        {"kind": "ellipse", "mode": "add", "x": 0, "y": 0, "rx": 22, "ry": 9,
         "rotation": 31},
        {"kind": "slot", "mode": "subtract", "x": 6, "y": 0, "length": 30,
         "height": 8, "rotation": 90},
        {"kind": "regular_polygon", "mode": "add", "x": -14, "y": 0,
         "radius": 10, "sides": 7}],
    "path + circle": [
        {"kind": "path", "mode": "add", "x": 0, "y": 0, "start": [0, 0],
         "segments": [{"type": "line", "to": [20, 0]},
                      {"type": "arc", "via": [26, 6], "to": [20, 12]},
                      {"type": "line", "to": [0, 12]},
                      {"type": "arc", "via": [-5, 6], "to": [0, 0]}]},
        {"kind": "circle", "mode": "add", "x": 20, "y": 6, "r": 7}],
    "nested: plate, boss, bore": [
        dict(RECT),
        {"kind": "circle", "mode": "subtract", "x": 0, "y": 0, "r": 8},
        {"kind": "circle", "mode": "add", "x": 0, "y": 0, "r": 3}],
}


@pytest.mark.parametrize("name", sorted(IDENTITY_CASES))
def test_pieces_are_bit_for_bit_the_stock_sampler(name):
    """The rule that governs the whole fix: same count, same points to FULL
    precision, same order. A piece that appears, disappears or moves is a
    defect however fast it is. (Proved over all 324 sketches of the user's 40
    designs too — `probes/trim_identity.py`; frozen here so it stays true.)"""
    ents = IDENTITY_CASES[name]
    with stock_sampler():
        before = fingerprint(ents)
    after = fingerprint(ents)
    assert len(before[0]) == len(after[0]), "the piece COUNT changed"
    assert [p[:3] for p in before[0]] == [p[:3] for p in after[0]]
    for b, a in zip(before[0], after[0]):
        assert b[3] == a[3], f"piece {b[0]} moved"
    assert before[1] == after[1], "which outlines cross changed"


@pytest.mark.parametrize("name", ["rect + circle cut",
                                  "nested: plate, boss, bore",
                                  "two traced blobs crossing"])
def test_every_trim_click_is_bit_for_bit_the_stock_sampler(name):
    """`_face_contains` samples wires too — the fill branch reaches it. Click
    EVERY piece both ways and compare the whole answer, refusals included."""
    ents = IDENTITY_CASES[name]

    def click(pid):
        try:
            return tr.trim_apply(ents, pid)
        except ValueError as ex:
            return f"REFUSED {ex}"

    for piece in tr.trim_pieces(ents):
        with stock_sampler():
            before = click(piece["id"])
        assert click(piece["id"]) == before, f"piece {piece['id']} differs"
