"""ROUND SEVEN — what the "already touching" escape costs.

`_walks_through_itself` refuses only a crossing the MOVE MAKES:

    return _edges_hit(cand, edges) and not _edges_hit(pts, edges)

Round six chose that because refusing outright broke three existing tests, and
wrote down that nobody had measured what "worse" costs. Two measurements:

  A. WHEN DOES THE ESCAPE FIRE IN A REAL TRACE? Instrumented over the
     ring/plate/comb/rings corpus it fires, and always for the same reason:
     `_split_at_feet` rounds its inserted vertex onto the 0.001 mm grid and it
     lands ON an existing vertex, so the loop carries a ZERO-LENGTH edge. The
     two edges either side of it touch at that point, `_edges_hit` says "this
     loop already touches itself", and from then on EVERY push on that block
     is waved through. The duplicate itself is harmless — `_round_pts` drops
     it — but the waiver is not: it is a blanket one.

  B. WHAT THE WAIVER LETS THROUGH. Round six's own ribbon, with one duplicate
     point in the block that moves. Nothing else changes. Today's rule waves
     the push through and the loop walks clean through its own far wall;
     comparing the SET of touching pairs instead of a yes/no refuses it, and
     the duplicate — whose pair is there before AND after — still does not
     block the pushes that are needed.

Run:  C:/Python314/python.exe probes/imgtrace_r7_escape.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
import inspector                                            # noqa: E402
import sketch as sk                                         # noqa: E402


def serpentine(t=0.005, gap=0.005):
    y1, y2, y3 = t, t + gap, t + gap + t
    return [(0.0, 0.0), (1.0, 0.0), (1.0, y3), (0.05, y3), (0.05, y2),
            (0.995, y2), (0.995, y1), (0.0, y1)]


def below(d=0.0045):
    return [(0.2, -5.0), (5.0, -5.0), (5.0, -d), (0.2, -d)]


def with_duplicate(pts, at=0):
    """the same ring with one vertex written twice — exactly what
    `_split_at_feet` leaves when its rounded foot lands on an existing
    vertex (6 of 192 traces, probes/imgtrace_r7_selftouch.py)"""
    return pts[:at + 1] + [pts[at]] + pts[at + 1:]


def build(loops):
    ents = [imgtrace._poly_entity([(float(x), float(y)) for x, y in p],
                                  "add" if k == 0 else "subtract")
            for k, p in enumerate(loops)]
    try:
        solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    except Exception as exc:                                # noqa: BLE001
        return f"SKETCH FAIL {type(exc).__name__}: {str(exc)[:70]}", None
    bad = inspector.health(solid)
    return (bad[0] if bad else None), float(solid.volume)


def pairs_hit(pts, edges):
    """every (i, j) pair of NON-adjacent edges of `pts` that touch or cross —
    `_edges_hit`'s own maths and tolerance, as a SET instead of a yes/no"""
    m = len(pts)
    r = np.roll(pts, -1, axis=0) - pts
    idx = np.arange(m)
    tol = 1e-9
    out = set()
    for i in edges:
        adj = (np.abs(idx - i) <= 1) | (np.abs(idx - i) >= m - 1)
        den = r[i, 0] * r[:, 1] - r[i, 1] * r[:, 0]
        safe = np.where(np.abs(den) > 1e-15, den, 1.0)
        d = pts - pts[i]
        t = (d[:, 0] * r[:, 1] - d[:, 1] * r[:, 0]) / safe
        u = (d[:, 0] * r[i, 1] - d[:, 1] * r[i, 0]) / safe
        hit = ((np.abs(den) > 1e-15) & ~adj & (t >= -tol) & (t <= 1.0 + tol)
               & (u >= -tol) & (u <= 1.0 + tol))
        out |= {(i, int(j)) for j in np.flatnonzero(hit)}
    return out


def run(name, rib):
    loops = [rib, below()]
    calls: list = []
    real = imgtrace._walks_through_itself

    def spy(pts, block, delta):
        m = len(pts)
        edges = sorted({(b - 1) % m for b in block} | {b % m for b in block})
        cand = pts.copy()
        cand[block] += delta
        was, now = pairs_hit(pts, edges), pairs_hit(cand, edges)
        out = real(pts, block, delta)
        calls.append((float(np.hypot(*delta)), bool(was), bool(now),
                      bool(now - was), out))
        return out

    imgtrace._walks_through_itself = spy
    try:
        out = imgtrace._pull_apart([list(map(tuple, p)) for p in loops])
    finally:
        imgtrace._walks_through_itself = real
    final = imgtrace._round_pts(out[0])
    print(f"\n{name}")
    print(f"  arrives with {len(rib)} points, "
          f"self-crossing? "
          f"{'YES' if imgtrace._first_crossing(imgtrace._round_pts(rib)) else 'no'}")
    for d, was, now, newpair, refused in calls:
        print(f"    push {d:.6f} mm: already touching {was}, "
              f"touching after {now}, a NEW touching pair {newpair} "
              f"-> {'REFUSED' if refused else 'allowed'}")
    print(f"  leaves self-crossing? "
          f"{'YES' if imgtrace._first_crossing(final) else 'no'}")
    bad_in, vol_in = build([imgtrace._round_pts(rib), below()])
    bad_out, vol_out = build([final, below()])
    print(f"    as traced : {bad_in or 'healthy'}  vol {vol_in}")
    print(f"    after push: {bad_out or 'healthy'}  vol {vol_out}")
    return bad_out


def main():
    run("A. round six's ribbon, clean", serpentine())
    run("B. the SAME ribbon with ONE duplicate vertex in the block",
        with_duplicate(serpentine(), 0))
    run("C. ...the duplicate on the far side of the same block",
        with_duplicate(serpentine(), 7))


if __name__ == "__main__":
    main()
