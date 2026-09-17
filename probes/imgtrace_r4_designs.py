"""REVIEW-QUEUE section 9 ROUND FOUR — the five traced recipes under the four
REAL modules, not a candidate patched into one of them.

`imgtrace_r3_designs.py` compared "r2" (which was the working tree) against a
`cand_mask` patched into it; now that the candidate has SHIPPED both columns
are the same module, so that probe can no longer tell round two from round
three. This one imports round two whole (`probes/_imgtrace_r2.py`, extracted
from 4b3af6a) and runs old / r1 / r2 / shipped side by side.

Run:  C:\\Python314\\python.exe probes/imgtrace_r4_designs.py
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
import _imgtrace_r2 as R2                                   # noqa: E402
from imgtrace_r2_designs import RECIPES                     # noqa: E402

MODS = [("old", OLD), ("r1", R1), ("r2", R2), ("ship", imgtrace)]


def run(mod, data, kw):
    try:
        ents, info = mod.image_to_entities(data, **kw)
    except Exception as e:                                  # noqa: BLE001
        return {"error": f"{type(e).__name__}: {str(e)[:50]}"}
    try:
        area = round(sk.make_sketch("XY", 0, ents).area, 3)
    except Exception as e:                                  # noqa: BLE001
        area = f"sketch {type(e).__name__}"
    return {"c": info["contours"], "h": info["holes"],
            "pts": info["points"], "w": info["width_mm"],
            "ht": info["height_mm"], "area": area}


def main():
    moved = []
    for fn in RECIPES:
        data, kw = fn()
        rows = [(tag, run(mod, data, kw)) for tag, mod in MODS]
        print(f"=== {fn.__name__}  {kw}")
        for tag, r in rows:
            print(f"    {tag:5s} {r}")
        base = rows[0][1]
        for tag, r in rows[1:]:
            if r != base:
                diffs = [f"{k}: {base.get(k)} -> {r.get(k)}"
                         for k in sorted(set(base) | set(r))
                         if base.get(k) != r.get(k)]
                print(f"    -> {tag} DIFFERS from old: {'; '.join(diffs)}")
        if rows[3][1] != rows[0][1]:
            moved.append(fn.__name__)
        if rows[3][1] != rows[2][1]:
            print("    -> !! the SHIPPED rule moves this design vs round two")
        print()
    print(f"designs the SHIPPED rule moves off the ORIGINAL rule: "
          f"{moved or 'none'}")


if __name__ == "__main__":
    main()
