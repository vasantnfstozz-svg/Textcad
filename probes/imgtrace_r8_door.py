"""ROUND EIGHT — the whole fit door, from a real face box to the kernel.

`imgtrace.settle` runs only when `studio._trace_fitted`'s residual `s` is under
1, and round seven's own corpus measured 224 of 224 fits never reaching it. So
this drives the door itself — `studio._trace_fitted`, `_trace_fit_height`, the
90-degree rotate, the rescale and `settle` — over face boxes from a comfortable
60 x 40 mm down to boxes SMALLER THAN A MILLIMETRE, where the art is a few
0.001 mm grid steps across and `_pull_apart`'s 0.01 mm hair is a big fraction
of the whole picture.

For every fit it records what the user gets: the sentence, or the entities put
to the kernel at 2 mm. A refusal that covers art which builds healthy is as bad
as a wrong solid, and this range added two refusals.

Run:  C:/Python314/python.exe probes/imgtrace_r8_door.py [n] [seed]
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import studio                                               # noqa: E402
from imgtrace_r5_mirror import GENS, png                    # noqa: E402
from imgtrace_r8_settle import build                        # noqa: E402

BOXES = ((60.0, 40.0), (20.0, 60.0), (12.0, 14.0), (5.0, 5.0), (2.0, 2.0),
         (1.0, 1.0), (0.6, 0.4), (0.2, 0.2), (40.0, 3.0), (100.0, 2.5))


def fit(data, fw, fh):
    req = studio.TracePngReq(png_base64="", fit_box=[fw, fh, 0.0, 0.0])
    return studio._trace_fitted(data, req, (fw, fh, 0.0, 0.0))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args else 4
    seed = int(args[1]) if len(args) > 1 else 8_2026
    rng = np.random.default_rng(seed)

    tally: dict = {}
    for k in range(n):
        for gname, gen in GENS:
            data = png(gen(rng))
            for fw, fh in BOXES:
                tag = f"  {gname}{k} on {fw:g} x {fh:g} mm"
                try:
                    ents, info = fit(data, fw, fh)
                except ValueError as exc:
                    key = ("REFUSED", str(exc)[:40])
                    tally[key] = tally.get(key, 0) + 1
                    print(tag + f": REFUSED — {str(exc)[:72]}")
                    continue
                except Exception as exc:                    # noqa: BLE001
                    key = ("RAISED", type(exc).__name__)
                    tally[key] = tally.get(key, 0) + 1
                    print(tag + f": {type(exc).__name__}: {str(exc)[:66]}")
                    continue
                bad, vol = build(ents)
                key = ("built", "healthy" if bad is None else str(bad)[:34])
                tally[key] = tally.get(key, 0) + 1
                # does the art still FIT the box it was fitted into?
                xs = [e["x"] + p[0] for e in ents for p in e["points"]]
                ys = [e["y"] + p[1] for e in ents for p in e["points"]]
                off = max(max(xs) - 0.5 * fw, -0.5 * fw - min(xs),
                          max(ys) - 0.5 * fh, -0.5 * fh - min(ys))
                print(tag + f": {info['width_mm']} x {info['height_mm']} mm, "
                      f"{len(ents)} ents, "
                      + ("HEALTHY " + (f"{vol:.4f} mm3" if vol else "")
                         if bad is None else str(bad)[:44])
                      + (f"  OFF THE BOX by {off:.4f} mm" if off > 1e-6
                         else ""))
    print("\n  tally")
    for key, v in sorted(tally.items()):
        print(f"    {key[0]:8s} {key[1]:44s} {v}")


if __name__ == "__main__":
    main()
