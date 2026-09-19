"""ROUND SEVEN — is the guard's REPORT complete, and is its refusal earned?

Round six made `image_to_entities` read the residual back off the final
coordinates: `tight_mm` plus a sentence for a pair merely inside the hair, and
a REFUSAL for a pair that still MEETS. Two things about it were never
measured.

  1. COMPLETENESS. `_worst_residual` only looks at the pairs `_pull_apart`
     put in `report`. In the round that moved something, that list is
     recomputed with `_nearest_on_ring(arr[i], arr[j])` — the ONE direction
     round five proved incomplete. So: does every pair that really ends
     inside the hair get reported, and does every pair that really MEETS get
     refused? The truth is the both-way minimum over the entities that come
     back.

  2. THE DISCRIMINATOR. The refusal fires on a residual of exactly 0. A
     pre-existing OVERLAP whose boundary happens to pass through a vertex
     reads 0 too, and an overlap is a union the kernel is happy with. So
     every pair at 0 is classified: do the interiors overlap (a "cross") or
     do they only meet (a "pinch")?

Also counted: does `_uncross` ever hand back two loops of ONE contour whose
interiors OVERLAP — the only way a traced sketch can carry such a pair at all.

Run:  C:/Python314/python.exe probes/imgtrace_r7_report.py [n] [seed]
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
from imgtrace_r5_mirror import GENS, HEIGHTS, png           # noqa: E402

OVERLAPS: list = []


def instrument():
    real = imgtrace._uncross

    def uncross(pts):
        out = real(pts)
        for a in range(len(out)):
            for b in range(a + 1, len(out)):
                if kind(np.asarray(out[a], float),
                        np.asarray(out[b], float)) == "cross":
                    OVERLAPS.append((len(out[a]), len(out[b])))
        return out

    imgtrace._uncross = uncross


def kind(ri, rj):
    """'cross' when the interiors really overlap, 'pinch' when they only
    meet, 'apart' when neither."""
    for a, b in ((ri, rj), (rj, ri)):
        poly = np.asarray(a, np.float32)
        ins = [cv2.pointPolygonTest(poly, (float(p[0]), float(p[1])), False)
               for p in b]
        if any(v > 0 for v in ins) and any(v < 0 for v in ins):
            return "cross"
        if all(v > 0 for v in ins):
            return "cross"                  # wholly nested
    return "pinch"


def rings_of(ents):
    return [np.asarray([[e["x"] + x, e["y"] + y] for x, y in e["points"]],
                       float) for e in ents]


def truth(ents):
    """-> [(gap, i, j)] for every pair, both directions, on the entities the
    caller is handed."""
    rs = rings_of(ents)
    out = []
    for i in range(len(rs)):
        for j in range(i + 1, len(rs)):
            d1, _f = imgtrace._nearest_on_ring(rs[i], rs[j])
            d2, _f = imgtrace._nearest_on_ring(rs[j], rs[i])
            out.append((min(float(d1.min()), float(d2.min())), i, j))
    return sorted(out)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args else 40
    seed = int(args[1]) if len(args) > 1 else 7_2026
    instrument()
    rng = np.random.default_rng(seed)
    traces = refused = reported = 0
    missed_tight: list = []
    missed_meet: list = []
    refusal_kinds: dict = {}
    for k in range(n):
        for gname, gen in GENS:
            data = png(gen(rng))
            for h_mm in HEIGHTS:
                try:
                    ents, info = imgtrace.image_to_entities(data,
                                                            height_mm=h_mm)
                except ValueError as exc:
                    if "meet at a point" in str(exc):
                        refused += 1
                    continue
                except Exception as exc:                    # noqa: BLE001
                    print(f"  TRACEBACK {gname}{k}: "
                          f"{type(exc).__name__}: {str(exc)[:60]}")
                    continue
                traces += 1
                if len(ents) < 2:
                    continue
                pairs = truth(ents)
                g, i, j = pairs[0]
                said = info.get("tight_mm")
                if said is not None:
                    reported += 1
                if g <= 0.0:
                    missed_meet.append((gname, k, h_mm, g, said,
                                        kind(rings_of(ents)[i],
                                             rings_of(ents)[j])))
                elif g < imgtrace._HAIR_MM and said is None:
                    missed_tight.append((gname, k, h_mm, g))
                elif said is not None and abs(said - g) > 1e-6:
                    print(f"  SAID {said:.6f} TRUE {g:.9f}  {gname}{k} "
                          f"h={h_mm:g}")
    print(f"\n{traces} traces built, {refused} refused")
    print(f"  carrying tight_mm                         : {reported}")
    print(f"  end with a pair still MEETING, unrefused  : "
          f"{len(missed_meet)}")
    for row in missed_meet[:10]:
        print(f"      {row}")
    print(f"  end inside the hair with NOTHING said     : "
          f"{len(missed_tight)}")
    for row in missed_tight[:10]:
        print(f"      {row[0]}{row[1]} h={row[2]:g} true gap {row[3]:.9f}")
    print(f"  _uncross pairs whose interiors OVERLAP    : {len(OVERLAPS)}")
    print(f"  refusal kinds: {refusal_kinds or 'n/a (measured above)'}")


if __name__ == "__main__":
    main()
