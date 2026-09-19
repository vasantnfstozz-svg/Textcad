"""ROUND SEVEN — the bigger rigid nudges, put to the KERNEL across the corpus.

Round six snapped the push onto the 0.001 mm grid, so every move is now at
least one grid step and `span = 4 * |move|` is at least 0.004 mm. A bigger
span makes `_hair_cluster` walk further, so the block that moves RIGIDLY is
bigger than it was. Round six put that to the tests and to the user's five
traced recipes; it never put it to the kernel across the corpus.

This does. Every trace in the ring/plate/comb/rings corpus is EXTRUDED and its
health read, and the push is instrumented so the report can say how big the
blocks really got:

  * moves made, the biggest block (points) and the biggest block as a
    FRACTION of its loop;
  * the move lengths;
  * unhealthy or invalid solids, with the picture written out.

Run:  C:/Python314/python.exe probes/imgtrace_r7_kernel.py [n] [seed]
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

MOVES: list = []


def instrument():
    real = imgtrace._hair_cluster

    def cluster(pts, v, span):
        out = real(pts, v, span)
        if out is not None:
            MOVES.append((len(out), len(pts), float(span) / 4.0))
        return out

    imgtrace._hair_cluster = cluster


def build(ents):
    try:
        solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
    except Exception as exc:                                # noqa: BLE001
        return f"SKETCH FAIL {type(exc).__name__}: {str(exc)[:70]}", None
    bad = inspector.health(solid)
    return (bad[0] if bad else None), float(solid.volume)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args else 20
    seed = int(args[1]) if len(args) > 1 else 7_2026
    instrument()
    rng = np.random.default_rng(seed)
    traces = refused = tight = unhealthy = failed = 0
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
                        print(f"  REFUSED {gname}{k} h={h_mm:g}")
                    continue
                except Exception as exc:                    # noqa: BLE001
                    print(f"  TRACEBACK {gname}{k}: "
                          f"{type(exc).__name__}: {str(exc)[:60]}")
                    continue
                traces += 1
                tight += 1 if "tight_mm" in info else 0
                bad, vol = build(ents)
                if bad and bad.startswith("SKETCH FAIL"):
                    failed += 1
                    print(f"  {bad}  {gname}{k} h={h_mm:g}")
                elif bad:
                    unhealthy += 1
                    with open(os.path.join(HERE,
                                           f"_r7_bad_{gname}{k}_{h_mm:g}.png"),
                              "wb") as fh:
                        fh.write(data)
                    print(f"  UNHEALTHY {gname}{k} h={h_mm:g}: {bad} "
                          f"vol {vol} info {info}")
    print(f"\n{traces} traces built, {refused} refused")
    print(f"  carrying tight_mm : {tight}")
    print(f"  sketch failures   : {failed}")
    print(f"  unhealthy/invalid : {unhealthy}")
    if MOVES:
        blocks = sorted(m[0] for m in MOVES)
        frac = sorted(m[0] / m[1] for m in MOVES)
        step = sorted(m[2] for m in MOVES)
        print(f"  rigid moves       : {len(MOVES)}")
        print(f"    block points  : min {blocks[0]}, median "
              f"{blocks[len(blocks) // 2]}, max {blocks[-1]}")
        print(f"    block fraction: median {frac[len(frac) // 2]:.3f}, "
              f"max {frac[-1]:.3f}")
        print(f"    move length   : min {step[0]:.6f}, median "
              f"{step[len(step) // 2]:.6f}, max {step[-1]:.6f} mm")


if __name__ == "__main__":
    main()
