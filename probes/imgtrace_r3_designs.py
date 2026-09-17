"""REVIEW-QUEUE section 9 round THREE — the five traced recipes under ALL
THREE shipped rules and the round-three candidate.

Round two compared only pre-4c9ea32 against itself. This re-derives each
recipe from the generator's own source (round two's recipe functions, which
were checked line by line against designs/autonomiq-panel-profile.py,
designs/cam-cover-plaque.py and designs/esp32-remote.py) and runs it through
old / round one / round two / the candidate, comparing contour counts, hole
counts, point counts, the artwork bbox and the composed sketch AREA.

Run:  C:\\Python314\\python.exe probes/imgtrace_r3_designs.py
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
import sketch as sk                                         # noqa: E402
import _imgtrace_old as OLD                                 # noqa: E402
import _imgtrace_r1 as R1                                   # noqa: E402
from imgtrace_r2_designs import RECIPES                     # noqa: E402
from imgtrace_r3_corpus import cand_mask                    # noqa: E402


def run(mod, data, kw, mask_fn=None):
    keep = mod._mask_from_image
    if mask_fn is not None:
        mod._mask_from_image = mask_fn
    try:
        ents, info = mod.image_to_entities(data, **kw)
    except Exception as e:                                  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {str(e)[:50]}"}
    finally:
        mod._mask_from_image = keep
    try:
        area = round(sk.make_sketch("XY", 0, ents).area, 3)
    except Exception as e:                                  # noqa: BLE001
        area = f"sketch {type(e).__name__}"
    return {"c": info["contours"], "h": info["holes"],
            "pts": info["points"], "w": info["width_mm"],
            "ht": info["height_mm"], "area": area}


def main():
    for fn in RECIPES:
        data, kw = fn()
        rows = [("old", run(OLD, data, kw)),
                ("r1", run(R1, data, kw)),
                ("r2", run(imgtrace, data, kw)),
                ("cand", run(imgtrace, data, kw, mask_fn=cand_mask))]
        print(f"=== {fn.__name__}  {kw}")
        for tag, r in rows:
            print(f"    {tag:5s} {r}")
        base = rows[0][1]
        for tag, r in rows[1:]:
            if r != base:
                diffs = [f"{k}: {base.get(k)} -> {r.get(k)}"
                         for k in set(base) | set(r) if base.get(k) != r.get(k)]
                print(f"    -> {tag} DIFFERS from old: {'; '.join(diffs)}")
        if rows[2][1] != rows[3][1]:
            print("    -> !! the CANDIDATE moves this design vs round two")
        print()


if __name__ == "__main__":
    main()
