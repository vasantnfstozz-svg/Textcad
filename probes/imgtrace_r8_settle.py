"""ROUND EIGHT — `imgtrace.settle`: does it terminate, and what does it refuse?

Round seven added `settle` to re-prove, after `studio._trace_fitted`'s residual
rescale, the two promises `image_to_entities` ends with. It ITERATES (three
rounds) and it REFUSES two ways:

  * "this artwork is too fine to scale onto this face" — a polygon still
    crosses itself after three rounds;
  * "two parts of this artwork meet at a point once it is scaled to fit this
    face" — `_worst_residual` <= `_MEET_MM`.

It runs only when `s < 1`, which 224 of 224 corpus fits never reach, so almost
nothing exercises it. This probe does, over the round-five corpus at the
scales `probes/imgtrace_r7_fit_shrink.py` measured the fit really reaching,
and for EVERY refusal it builds what would have been handed to `sketch.py` and
asks the kernel. A refusal that covers art which builds healthy is as bad as a
wrong solid.

Reported per (generator, height, s):
  * settle's answer: ok / MEET / FINE / EMPTY
  * how many of the three rounds it used (the termination bound in practice)
  * for a refusal: the solid the un-refused entities build, and its health.

MEASURED 2026-09-19 at 37eb290, `imgtrace_r8_settle.py 6 82026`:

    864 settle runs (6 pictures x 4 generators x 6 heights x 6 scales)
      answers      : {'ok': 834, 'MEET': 30}
      rounds used  : {1: 864}          <- it never needs a second round
      refusals     : 30
      ...that would have BUILT HEALTHY : 26
      ...that would have been BROKEN   : 4

So `settle` TERMINATES: bounded at 3 outer rounds, and 864 of 864 real runs
settled in ONE. The "this artwork is too fine to scale onto this face"
refusal never fired. What did fire, 30 times, is the MEET refusal — and 26 of
those 30 build a healthy solid. `probes/imgtrace_r8_meet.py` says why.

Seed 5150 is where the bound is really reached — `{1: 862, 3: 2}`, and one of
those two ends in the "too fine" refusal — so the third round is not dead
code, it is the last resort it was written to be.

AFTER the overlap rule (`_interiors_overlap`, commit 02d86ce):

    seed 82026: 30 refusals -> 19, and 4 of 4 open shells still refused
    seed  5150: 36 refusals -> 21, and 5 of 5 open shells still refused

27 of 63 refusals removed, 9 of 9 banned failures still caught. The 34 that
remain all carry a real point contact; 20 of those would have built healthy,
and refusing them is the deliberate, conservative half of the rule — there is
no cheap test that tells which point contact OCCT survives, and a failed
feature beats a corrupt body.

Run:  C:/Python314/python.exe probes/imgtrace_r8_settle.py [n] [seed]
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

SCALES = (0.9, 0.5, 0.25, 0.1, 0.05, 0.02)


def settle_open(ents, rounds=3):
    """`imgtrace.settle` with every `raise` turned into a return value, and
    the round counter exposed. Byte-for-byte the same arithmetic otherwise —
    when this says "ok" the entities it returns are settle's own."""
    flat = [imgtrace._round_pts([(float(e["x"] + px), float(e["y"] + py))
                                 for px, py in e["points"]]) for e in ents]
    kinds = [e.get("mode", "add") for e in ents]
    stuck: list = []
    apart: list = []
    used = 0
    why = "ok"
    for _ in range(rounds):
        used += 1
        split, marks = [], []
        for mode, pts in zip(kinds, flat):
            for p in imgtrace._uncross(pts):
                if len(p) >= 3 and abs(imgtrace._area2(p)) > 1e-9:
                    split.append(p)
                    marks.append(mode)
        if not split:
            return None, "EMPTY", used, None
        flat, kinds = split, marks
        stuck = []
        apart = imgtrace._pull_apart(flat, report=stuck)
        flat = [imgtrace._round_pts(p) for p in apart]
        if not any(imgtrace._first_crossing(p) is not None for p in flat):
            break
    else:
        why = "FINE"
    out = [imgtrace._poly_entity(p, m) for m, p in zip(kinds, flat)
           if len(p) >= 3]
    if not out or out[0]["mode"] != "add":
        return None, "EMPTY", used, None
    tight = imgtrace._worst_residual(apart, stuck)
    if why == "ok" and tight is not None and tight <= imgtrace._MEET_MM:
        why = "MEET"
    return out, why, used, tight


def build(ents):
    import inspector
    import sketch as sk
    try:
        solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    except Exception as exc:                                # noqa: BLE001
        return f"SKETCH FAIL {type(exc).__name__}: {str(exc)[:70]}", None
    try:
        bad = inspector.health(solid)
    except Exception as exc:                                # noqa: BLE001
        return f"HEALTH RAISED {type(exc).__name__}", None
    return (bad[0] if bad else None), float(solid.volume)


def crossing_out(ents):
    """polygons that reach sketch.py crossing themselves — asked on the LOCAL
    points, which is what `_poly_entity` writes and `sketch.py` reads"""
    return sum(1 for e in ents
               if imgtrace._first_crossing([tuple(p) for p in e["points"]])
               is not None)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args else 8
    seed = int(args[1]) if len(args) > 1 else 8_2026
    rng = np.random.default_rng(seed)

    tally: dict = {}
    rounds_used: dict = {}
    refusals = []
    runs = 0
    for k in range(n):
        for gname, gen in GENS:
            data = png(gen(rng))
            for h_mm in HEIGHTS:
                try:
                    ents, _i = imgtrace.image_to_entities(data, height_mm=h_mm)
                except ValueError:
                    continue
                if len(ents) < 2:
                    continue
                for s in SCALES:
                    sc = rescale(ents, s)
                    out, why, used, tight = settle_open(sc)
                    runs += 1
                    tally[why] = tally.get(why, 0) + 1
                    rounds_used[used] = rounds_used.get(used, 0) + 1
                    if why != "ok":
                        refusals.append((gname, k, h_mm, s, why, used,
                                         tight, out))
    print(f"{runs} settle runs over {n} pictures x {len(GENS)} generators "
          f"x {len(HEIGHTS)} heights x {len(SCALES)} scales, seed {seed}")
    print(f"  answers      : {tally}")
    print(f"  rounds used  : {dict(sorted(rounds_used.items()))}")
    print(f"  refusals     : {len(refusals)}")
    if not refusals:
        return
    print("\nEVERY REFUSAL, PUT TO THE KERNEL "
          "(what the user would have got had settle allowed it)\n")
    healthy = broken = empty = 0
    for gname, k, h_mm, s, why, used, tight, out in refusals:
        tag = (f"  {gname}{k} h={h_mm:g} s={s:g} {why} "
               f"(round {used}, tight={tight!r})")
        if out is None:
            print(tag + "  -> nothing to build")
            empty += 1
            continue
        xo = crossing_out(out)
        bad, vol = build(out)
        print(tag + f"  self-crossing polys {xo}  -> "
              + (f"HEALTHY {vol:.3f} mm3" if bad is None and vol
                 else f"{bad}" + (f" (vol {vol:.3f})" if vol else "")))
        if bad is None:
            healthy += 1
        else:
            broken += 1
    print(f"\n  refusals that would have BUILT HEALTHY : {healthy}")
    print(f"  refusals that would have been BROKEN   : {broken}")
    print(f"  refusals with nothing to build         : {empty}")


if __name__ == "__main__":
    main()
