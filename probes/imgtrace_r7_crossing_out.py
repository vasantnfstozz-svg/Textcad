"""ROUND SEVEN — does a SELF-CROSSING polygon still reach `sketch.py`?

`_uncross` exists so that no polygon handed to `sketch.py` crosses itself; a
polygon that does builds a solid OpenCASCADE calls invalid, with the feature
green (REVIEW-QUEUE section 9, four P0s).

`probes/imgtrace_r7_selftouch.py` measured the two halves of a route past it:

  * `_split_at_feet` rounds its inserted vertex onto the 0.001 mm grid, up to
    0.0007 mm off the edge it splits — 6 splits in 192 traces turned a simple
    loop into one that touches itself;
  * `_walks_through_itself` then waves EVERY push on that block through,
    because it refuses only a crossing the move MAKES — 8 pushes in 192
    traces, every one leaving the loop crossing.

This probe reads the FINAL entities `image_to_entities` returns, asks
`_first_crossing` of each one, and puts every trace that carries one to the
kernel.

Run:  C:/Python314/python.exe probes/imgtrace_r7_crossing_out.py [n] [seed]
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
    rng = np.random.default_rng(seed)
    traces = crossed = unhealthy = 0
    for k in range(n):
        for gname, gen in GENS:
            data = png(gen(rng))
            for h_mm in HEIGHTS:
                try:
                    ents, info = imgtrace.image_to_entities(data,
                                                            height_mm=h_mm)
                except ValueError:
                    continue
                except Exception as exc:                    # noqa: BLE001
                    print(f"  TRACEBACK {gname}{k}: "
                          f"{type(exc).__name__}: {str(exc)[:60]}")
                    continue
                traces += 1
                bads = [e for e in ents
                        if imgtrace._first_crossing(
                            [tuple(p) for p in e["points"]]) is not None]
                if not bads:
                    continue
                crossed += 1
                bad, vol = build(ents)
                if bad:
                    unhealthy += 1
                with open(os.path.join(HERE, f"_r7_cross_{gname}{k}.png"),
                          "wb") as fh:
                    fh.write(data)
                print(f"  CROSSES {gname}{k} h={h_mm:g}: {len(bads)} of "
                      f"{len(ents)} entities self-cross -> "
                      f"{bad or 'healthy'} vol {vol}  info {info}")
    print(f"\n{traces} traces")
    print(f"  traces handing sketch.py a self-crossing polygon: {crossed}")
    print(f"  ...of which build an unhealthy/invalid solid     : {unhealthy}")


if __name__ == "__main__":
    main()
