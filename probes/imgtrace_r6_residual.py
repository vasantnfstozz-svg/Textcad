"""ROUND SIX — the guard's own give-up, counted and put to the kernel.

`_pull_apart` gives way rather than turn a loop inside out, and until round
six it said nothing when it did. Round five measured 2 of 960 ring traces
ending still inside the hair (worst 0.000259 mm before rounding, 0.000565
after) and running the pass eight more times did not improve them.

Round six makes it report: `image_to_entities` reads the residual back off
the FINAL coordinates, REFUSES a pair that still MEETS (the banned failure —
a pinched face that builds as an open shell) and puts `tight_mm` plus a
sentence on a pair merely inside the hair.

This probe counts, over the ring/plate/comb corpus at many heights:
  * traces refused, and what the refusal says;
  * traces carrying `tight_mm`, and whether they build healthy;
  * the residual's distribution.

Run:  C:/Python314/python.exe probes/imgtrace_r6_residual.py [n] [seed]
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
from imgtrace_r6_truth import pair_min, rings_of, self_min  # noqa: E402


def build(ents):
    try:
        solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    except Exception as exc:                                # noqa: BLE001
        return f"SKETCH FAIL {type(exc).__name__}: {str(exc)[:60]}", None
    bad = inspector.health(solid)
    return (bad[0] if bad else None), float(solid.volume)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args else 40
    seed = int(args[1]) if len(args) > 1 else 6_2026
    rng = np.random.default_rng(seed)
    traces = refused = tight = unhealthy = crossed = 0
    residuals = []
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
                        print(f"  REFUSED {gname}{k} h={h_mm:g}: {exc}")
                    continue
                except Exception as exc:                    # noqa: BLE001
                    print(f"  TRACEBACK {gname}{k}: "
                          f"{type(exc).__name__}: {str(exc)[:60]}")
                    continue
                traces += 1
                rs = rings_of(ents)
                if any(imgtrace._first_crossing([tuple(p) for p in e["points"]])
                       is not None for e in ents):
                    crossed += 1
                if "tight_mm" in info:
                    tight += 1
                    residuals.append(info["tight_mm"])
                    bad, vol = build(ents)
                    truth = min([pair_min(rs[a], rs[b])
                                 for a in range(len(rs))
                                 for b in range(a + 1, len(rs))] or [9e9])
                    print(f"  TIGHT {gname}{k} h={h_mm:g}: "
                          f"tight_mm {info['tight_mm']:.6f}, true pair "
                          f"{truth:.9f}, self {min(self_min(r) for r in rs):.6f}"
                          f" -> {bad or 'healthy'} vol {vol}")
                    if bad:
                        unhealthy += 1
                    print(f"        note: {info.get('note')}")
    residuals.sort()
    print(f"\n{traces} traces built, {refused} refused")
    print(f"  carrying tight_mm       : {tight}")
    print(f"  self-crossing polygons  : {crossed}")
    print(f"  unhealthy among tight   : {unhealthy}")
    if residuals:
        print("  residuals: "
              + ", ".join(f"{v:.6f}" for v in residuals[:10]))


if __name__ == "__main__":
    main()
