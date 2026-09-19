"""ROUND EIGHT — where a self-crossing is BORN inside `_pull_apart`, and
whether `_walks_through_itself`'s new per-pair rule can be walked past.

Round seven rewrote `_walks_through_itself` from "does this loop touch itself
at all" (which waived every push on a block that touched anywhere) to "which
PAIRS touch": a push that adds no new touching pair is allowed however many
were there already.

Two things follow that nothing has measured.

1. The waiver is still a waiver, PER PAIR. A pair that already TOUCHES at a
   point is waived even if the push turns that touch into a deep transversal
   CROSSING — the boolean row cannot tell the two apart.

2. `_split_at_feet` runs BEFORE the guard and its result is taken
   unconditionally (`arr[i] = grown`). Its inserted vertex is rounded onto the
   0.001 mm grid, up to 0.0007 mm off the edge it split. If that insertion
   makes the loop cross itself, the crossing is "pre-existing" for every
   later push of that loop — and `image_to_entities` never re-asks, so it
   walks out to `sketch.py`.

So `_pull_apart` is run with `_split_at_feet` and `_walks_through_itself`
watched, over the ordinary corpus AND over rescaled entities, and every loop
is re-proved with `_first_crossing` at each step.

MEASURED 2026-09-19 at 37eb290, `imgtrace_r8_born.py 8 82026`:

    1302 pipeline runs (ordinary + settle at six scales)
      _split_at_feet insertions             : 4041
        ...that made a simple loop cross    : 0
      pushes offered to the guard           : 70777
        refused by it                       : 8945
        allowed, and made a clean loop cross: 0
        allowed on an ALREADY-touching loop : 0
      polygons that reached sketch.py crossing: 0

Both worries CLEAR on this corpus. `_split_at_feet`'s grid-rounded insertion
never turned a simple loop into a crossing one in 4041 insertions, and the new
per-pair rule never let a push through that made a clean loop cross in 70 777
pushes. The waiver branch — the one that could turn a pre-existing TOUCH into
a deep crossing unseen — was never even reached: once `_round_pts` drops the
duplicate vertex, no loop offered to the guard is self-touching at all.

Run:  C:/Python314/python.exe probes/imgtrace_r8_born.py [n] [seed]
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
from imgtrace_r5_mirror import GENS, HEIGHTS, png           # noqa: E402
from imgtrace_r7_rescale import rescale                     # noqa: E402

SCALES = (1.0, 0.9, 0.5, 0.25, 0.1, 0.05, 0.02)

STATS = {"splits": 0, "split_broke": 0, "pushes": 0, "push_broke": 0,
         "guard_true": 0, "waived_pre": 0, "waived_pre_broke": 0}

_SPLIT = imgtrace._split_at_feet
_WALK = imgtrace._walks_through_itself


def _simple(a) -> bool:
    p = imgtrace._round_pts([(float(x), float(y)) for x, y in a])
    return len(p) < 3 or imgtrace._first_crossing(p) is None


def _split_spy(pts, ring, gap):
    out = _SPLIT(pts, ring, gap)
    if len(out) != len(pts):
        STATS["splits"] += 1
        if _simple(pts) and not _simple(out):
            STATS["split_broke"] += 1
            print("  SPLIT BROKE a simple loop: "
                  f"{len(pts)} -> {len(out)} points")
    return out


def _walk_spy(pts, block, delta):
    ans = _WALK(pts, block, delta)
    STATS["pushes"] += 1
    if ans:
        STATS["guard_true"] += 1
        return ans
    cand = pts.copy()
    cand[block] += delta
    was, now = _simple(pts), _simple(cand)
    if was and not now:
        STATS["push_broke"] += 1
        print(f"  GUARD LET A PUSH THROUGH that makes a clean loop cross "
              f"({len(pts)} points, block {len(block)}, "
              f"delta {tuple(np.round(delta, 6))})")
    if not was:
        STATS["waived_pre"] += 1
        if not now:
            # already not simple - did the push make it WORSE?
            n_was = _count(pts)
            n_now = _count(cand)
            if n_now > n_was:
                STATS["waived_pre_broke"] += 1
                print(f"  GUARD WAIVED a push on an already-touching loop "
                      f"and the touching pairs went {n_was} -> {n_now}")
    return ans


def _count(a):
    """how many non-adjacent edge pairs of this loop touch or cross"""
    pts = np.asarray(a, float)
    m = len(pts)
    if m < 4:
        return 0
    r = np.roll(pts, -1, axis=0) - pts
    idx = np.arange(m)
    n = 0
    for i in range(m):
        adj = (np.abs(idx - i) <= 1) | (np.abs(idx - i) >= m - 1)
        n += int(imgtrace._edge_hits(pts, r, i, adj).sum())
    return n // 2


imgtrace._split_at_feet = _split_spy
imgtrace._walks_through_itself = _walk_spy


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args else 10
    seed = int(args[1]) if len(args) > 1 else 8_2026
    rng = np.random.default_rng(seed)

    runs = escaped = 0
    for k in range(n):
        for gname, gen in GENS:
            data = png(gen(rng))
            for h_mm in HEIGHTS:
                try:
                    ents, _i = imgtrace.image_to_entities(data, height_mm=h_mm)
                except ValueError:
                    continue
                runs += 1
                for e in ents:
                    if imgtrace._first_crossing(
                            [tuple(p) for p in e["points"]]) is not None:
                        escaped += 1
                        print(f"  ESCAPED to sketch.py: {gname}{k} h={h_mm:g}")
                        break
                if len(ents) < 2:
                    continue
                for s in SCALES[1:]:
                    sc = rescale(ents, s)
                    try:
                        out, _note = imgtrace.settle(sc)
                    except ValueError:
                        continue
                    runs += 1
                    for e in out:
                        if imgtrace._first_crossing(
                                [tuple(p) for p in e["points"]]) is not None:
                            escaped += 1
                            print(f"  ESCAPED from settle: {gname}{k} "
                                  f"h={h_mm:g} s={s:g}")
                            break

    print(f"\n{runs} pipeline runs (ordinary + settle), seed {seed}")
    print(f"  _split_at_feet insertions            : {STATS['splits']}")
    print(f"    ...that made a simple loop cross   : {STATS['split_broke']}")
    print(f"  pushes offered to the guard          : {STATS['pushes']}")
    print(f"    refused by it                      : {STATS['guard_true']}")
    print(f"    allowed, and made a clean loop cross: "
          f"{STATS['push_broke']}")
    print(f"    allowed on an ALREADY-touching loop: "
          f"{STATS['waived_pre']}")
    print(f"      ...and added touching pairs      : "
          f"{STATS['waived_pre_broke']}")
    print(f"  polygons that reached sketch.py crossing: {escaped}")


if __name__ == "__main__":
    main()
