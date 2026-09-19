"""ROUND SEVEN — what "already touching" costs.

`_walks_through_itself` refuses only a crossing the MOVE MAKES:

    return _edges_hit(cand, edges) and not _edges_hit(pts, edges)

So if ANY of the edges the move changes already touches a non-adjacent edge
of the same loop, EVERY move on that block is waved through — including one
that walks the loop clean through its own far wall. Round six chose that
because refusing outright broke three existing tests, and said nobody had
measured what "worse" costs. This measures it, three ways:

  1. FUNCTION LEVEL — a ribbon that arrives with a hair-touch at one end and
     is then pushed through its own far wall at the other. Both states go to
     the kernel: touching-but-simple vs walked-through.
  2. REACHABILITY — the escape is instrumented over the ring/plate/comb/rings
     corpus: how often does `_edges_hit(pts, edges)` come back True in a real
     trace, and what does the trace that fired it build?
  3. THE INSERTED POINT — `_split_at_feet` rounds its new vertex onto the
     0.001 mm grid, up to ~0.0007 mm off the edge it splits. That is the one
     documented way a loop can arrive at the push already touching itself, so
     it is checked directly: does the split ever make a simple loop touch?

Run:  C:/Python314/python.exe probes/imgtrace_r7_selftouch.py [n] [seed]
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
from imgtrace_r5_mirror import GENS, HEIGHTS, png           # noqa: E402


def build(loops, modes=None):
    ents = []
    for k, p in enumerate(loops):
        mode = (modes or ["add"] + ["subtract"] * 99)[k]
        ents.append(imgtrace._poly_entity([(float(x), float(y))
                                           for x, y in p], mode))
    try:
        solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    except Exception as exc:                                # noqa: BLE001
        return f"SKETCH FAIL {type(exc).__name__}: {str(exc)[:70]}", None
    bad = inspector.health(solid)
    return (bad[0] if bad else None), float(solid.volume)


# ---------------------------------------------------------------- 1. cost

def ribbon_touching(t=0.005, gap=0.005):
    """A ribbon `t` thick folded back on itself, whose slot is PINCHED SHUT at
    its left mouth: the vertex (0.05, y2) sits exactly on the edge
    (0.995, y1) -> (0, y1), so the loop already touches itself there. Every
    other part of it is the round-six serpentine."""
    y1, y2, y3 = t, t + gap, t + gap + t
    return [(0.0, 0.0), (1.0, 0.0), (1.0, y3), (0.05, y3), (0.05, y1),
            (0.995, y2), (0.995, y1), (0.0, y1)]


def ribbon_clean(t=0.005, gap=0.005):
    y1, y2, y3 = t, t + gap, t + gap + t
    return [(0.0, 0.0), (1.0, 0.0), (1.0, y3), (0.05, y3), (0.05, y2),
            (0.995, y2), (0.995, y1), (0.0, y1)]


def below(d=0.0045):
    return [(0.2, -5.0), (5.0, -5.0), (5.0, -d), (0.2, -d)]


def cost():
    print("1. FUNCTION LEVEL — the escape's cost\n")
    for name, rib in (("clean slot ", ribbon_clean()),
                      ("pinched mouth", ribbon_touching())):
        loops = [rib, below()]
        pre = imgtrace._first_crossing(rib)
        out = imgtrace._pull_apart([list(map(tuple, p)) for p in loops])
        post = imgtrace._first_crossing(imgtrace._round_pts(out[0]))
        moved = max(abs(np.asarray(out[0]) - np.asarray(rib, float)).max(),
                    0.0) if len(out[0]) == len(rib) else -1.0
        bad_in, vol_in = build([rib, below()], ["add", "subtract"])
        bad_out, vol_out = build(out, ["add", "subtract"])
        print(f"  {name}: arrives self-crossing? "
              f"{'YES' if pre else 'no'}  ->  leaves self-crossing? "
              f"{'YES' if post else 'no'}   (max point move {moved:.6f} mm)")
        print(f"      as traced : {bad_in or 'healthy'}  vol {vol_in}")
        print(f"      after push: {bad_out or 'healthy'}  vol {vol_out}\n")


# -------------------------------------------------------- 2. reachability

ESCAPES: list = []
SPLIT_BROKE: list = []


def instrument():
    real_walk = imgtrace._walks_through_itself
    real_split = imgtrace._split_at_feet

    def walk(pts, block, delta):
        before = imgtrace._edges_hit(
            pts, sorted({(b - 1) % len(pts) for b in block}
                        | {b % len(pts) for b in block}))
        out = real_walk(pts, block, delta)
        if before:
            cand = pts.copy()
            cand[block] += delta
            raw = [(float(x), float(y)) for x, y in cand]
            after = imgtrace._first_crossing(raw) is not None
            rnd = imgtrace._round_pts(raw)
            settled = (len(rnd) >= 3
                       and imgtrace._first_crossing(rnd) is not None)
            ESCAPES.append((len(pts), float(np.hypot(*delta)), after,
                            settled, len(raw) - len(rnd)))
        return out

    def split(pts, ring, gap):
        out = real_split(pts, ring, gap)
        if len(out) != len(pts):
            a = imgtrace._first_crossing([(float(x), float(y))
                                          for x, y in pts]) is not None
            b = imgtrace._first_crossing([(float(x), float(y))
                                          for x, y in out]) is not None
            if b and not a:
                SPLIT_BROKE.append((len(pts), len(out)))
        return out

    imgtrace._walks_through_itself = walk
    imgtrace._split_at_feet = split


def corpus(n, seed):
    print("2./3. REACHABILITY over the ring/plate/comb/rings corpus\n")
    instrument()
    rng = np.random.default_rng(seed)
    traces = 0
    for k in range(n):
        for gname, gen in GENS:
            data = png(gen(rng))
            for h_mm in HEIGHTS:
                try:
                    imgtrace.image_to_entities(data, height_mm=h_mm)
                except ValueError:
                    continue
                except Exception as exc:                    # noqa: BLE001
                    print(f"  TRACEBACK {gname}{k}: "
                          f"{type(exc).__name__}: {str(exc)[:60]}")
                    continue
                traces += 1
    print(f"  {traces} traces")
    print(f"  pushes waved through by the already-touching escape: "
          f"{len(ESCAPES)}")
    for m, d, after, settled, dropped in ESCAPES[:14]:
        print(f"      {m} points, move {d:.6f} mm -> raw "
              f"{'CROSSES' if after else 'clean'}, after _round_pts "
              f"{'CROSSES' if settled else 'clean'} ({dropped} dupes)")
    print(f"  _split_at_feet turning a simple loop into a touching one: "
          f"{len(SPLIT_BROKE)}")
    for a, b in SPLIT_BROKE[:10]:
        print(f"      {a} -> {b} points")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    cost()
    corpus(int(args[0]) if args else 20,
           int(args[1]) if len(args) > 1 else 7_2026)
