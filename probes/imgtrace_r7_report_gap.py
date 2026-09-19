"""ROUND SEVEN — the LAST pair the guard's own report does not see.

`_pull_apart` collects the pairs it gave up on in `report`, and
`_worst_residual` reads them back to decide between a note and a refusal. In
the round that MOVED something, that list is rebuilt like this:

    for i, j in pairs:
        d, _f = _nearest_on_ring(arr[i], arr[j])
        if float(d.min()) < gap:
            stuck.append(...)

which is the ONE direction round five proved incomplete: the closest approach
of two polylines sits on a vertex of one OR OF THE OTHER, and a vertex of the
BIGGER loop on the middle of the smaller loop's edge is invisible to it. The
push itself asks the mirror question (`_split_at_feet`); this recompute does
not.

At ordinary sizes it never showed: 0 of 600 traces ended with a pair still
MEETING and unrefused (probes/imgtrace_r7_report.py). Scaled down hard, it
does — 3 of 474 at s = 0.02 (probes/imgtrace_r7_rescale_kind.py). This probe
finds those cases and says, for each, what the guard reported and what the
truth is in BOTH directions.

Run:  C:/Python314/python.exe probes/imgtrace_r7_report_gap.py [n] [seed]
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
from imgtrace_r5_mirror import GENS, png                    # noqa: E402
from imgtrace_r7_rescale import closest, rescale            # noqa: E402

HEIGHTS = (9.5, 12.0, 17.3, 25.0, 33.7, 40.0)


def one_way(loops):
    """what the report's own recompute would read"""
    arr = [np.asarray(p, float) for p in loops]
    size = [abs(imgtrace._area2(p)) for p in loops]
    best = float("inf")
    for i in range(len(arr)):
        for j in range(len(arr)):
            if i != j and size[i] <= size[j]:
                d, _f = imgtrace._nearest_on_ring(arr[i], arr[j])
                best = min(best, float(d.min()))
    return best


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    n = int(args[0]) if args else 20
    seed = int(args[1]) if len(args) > 1 else 720266
    rng = np.random.default_rng(seed)
    found = 0
    for k in range(n):
        for gname, gen in GENS:
            data = png(gen(rng))
            for h_mm in HEIGHTS:
                try:
                    ents, _i = imgtrace.image_to_entities(data,
                                                          height_mm=h_mm)
                except Exception:                           # noqa: BLE001
                    continue
                if len(ents) < 2:
                    continue
                for s in (0.02, 0.05, 0.1):
                    sc = rescale(ents, s)
                    try:
                        out, note = imgtrace.settle(sc)
                    except ValueError:
                        continue
                    g = closest(out)
                    if g > 0.0:
                        continue
                    found += 1
                    rings = [[(e["x"] + x, e["y"] + y)
                              for x, y in e["points"]] for e in out]
                    print(f"  {gname}{k} h={h_mm:g} s={s:g}: settle returned "
                          f"{len(out)} polygons with a pair at {g:.9f} mm, "
                          f"note={note!r}")
                    print(f"      the report's ONE-WAY reading of the same "
                          f"loops: {one_way(rings):.9f} mm")
    print(f"\n{found} traces where `settle` handed back a pair that MEETS")


if __name__ == "__main__":
    main()
