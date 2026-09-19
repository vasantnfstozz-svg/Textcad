"""ROUND SIX — what ARE the pairs the segment-to-segment truth reads at 0 mm?

`probes/imgtrace_r6_truth.py` finds 41 traces in 288 where two loops of one
sketch are at a TRUE distance of 0.000000000 mm while the guard's own
vertex-to-outline test reads the 0.010 mm it just pushed them to. This probe
takes those traces apart: are the two loops CROSSING (interiors overlap — a
cut cuts the union, harmless), or TANGENT (the pinch)? Did the crossing exist
before `_pull_apart` ran, or did the push create it? And what are the two
modes — two holes is one thing, an outline crossing a hole is another.

Run:  C:/Python314/python.exe probes/imgtrace_r6_crossings.py [n] [seed]
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
from imgtrace_r6_truth import build, pair_min, rings_of     # noqa: E402

TOUCH = 1e-6


def kind(ri, rj):
    """how loop j sits against loop i"""
    a = np.asarray(ri, np.float32)
    ins = [cv2.pointPolygonTest(a, (float(p[0]), float(p[1])), False)
           for p in rj]
    n_in = sum(1 for v in ins if v > 0)
    n_out = sum(1 for v in ins if v < 0)
    n_on = sum(1 for v in ins if v == 0)
    if n_in and n_out:
        return f"CROSS ({n_in} in / {n_out} out / {n_on} on)"
    if n_in and not n_out:
        return f"j INSIDE i ({n_on} on)"
    if n_out and not n_in:
        return f"j OUTSIDE i ({n_on} on)"
    return f"all ON ({n_on})"


def before_push(data, h_mm):
    """the loops as `image_to_entities` has them the instant before
    `_pull_apart` — the same list, un-pushed"""
    seen = {}
    real = imgtrace._pull_apart

    def spy(loops, gap=imgtrace._HAIR_MM):
        seen["in"] = [np.asarray(p, float) for p in loops]
        out = real(loops, gap)
        seen["out"] = [np.asarray(p, float) for p in out]
        return out

    imgtrace._pull_apart = spy
    try:
        ents, _i = imgtrace.image_to_entities(data, height_mm=h_mm)
    finally:
        imgtrace._pull_apart = real
    return ents, seen


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args else 12
    seed = int(args[1]) if len(args) > 1 else 6_2026
    rng = np.random.default_rng(seed)
    shown = 0
    made_by_push = pre_existing = tangent = 0
    for k in range(n):
        for gname, gen in GENS:
            data = png(gen(rng))
            for h_mm in HEIGHTS:
                try:
                    ents, seen = before_push(data, h_mm)
                except ValueError:
                    continue
                except Exception:                           # noqa: BLE001
                    continue
                rs = rings_of(ents)
                for i in range(len(rs)):
                    for j in range(i + 1, len(rs)):
                        if pair_min(rs[i], rs[j]) >= TOUCH:
                            continue
                        kd = kind(rs[i], rs[j])
                        pre = "?"
                        if "in" in seen and len(seen["in"]) == len(rs):
                            pre = f"{pair_min(seen['in'][i], seen['in'][j]):.9f}"
                            if float(pre) < TOUCH:
                                pre_existing += 1
                            else:
                                made_by_push += 1
                        tang = not kd.startswith("CROSS")
                        tangent += tang
                        if tang or (shown < 8 and "--all" in sys.argv):
                            shown += 1
                            bad, vol = "-", "-"
                            if tang:
                                bad, vol = build(ents)
                            print(f"{'TANGENT ' if tang else ''}{gname}{k} "
                                  f"h={h_mm:g} loops {i},{j} "
                                  f"({ents[i]['mode']}/{ents[j]['mode']}): "
                                  f"{kd}; before the push {pre} mm"
                                  + (f" -> {bad or 'healthy'} vol {vol}"
                                     if tang else ""))
    print(f"\ncontacts at 0: pre-existing {pre_existing}, "
          f"MADE BY THE PUSH {made_by_push}, of which tangent {tangent}")


if __name__ == "__main__":
    main()
