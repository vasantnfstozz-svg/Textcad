"""ROUND SIX — what the fixes cost the user's OWN traced art.

Round six puts the art-centring shift on the 0.001 mm grid and snaps the
push's move to that grid too. Both are sub-micron by construction, but "by
construction" is not a measurement. This runs the five real traced recipes
(`probes/imgtrace_r2_designs.RECIPES` — the generators of autonomiq-panel,
cam-cover-plaque, esp32-remote, rocky-keychain) under the module as it was
at a chosen commit and under the working tree, side by side, and reports
contour / hole / point counts, the artwork bbox, the composed sketch AREA and
the worst point move.

Run:  C:/Python314/python.exe probes/imgtrace_r6_drift.py [before.py]
      (default: probes/_imgtrace_r6_before.py, written by
       `git show <base>:imgtrace.py`)
"""
from __future__ import annotations

import importlib.util
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

import imgtrace                                             # noqa: E402
import sketch as sk                                         # noqa: E402
from imgtrace_r2_designs import RECIPES                     # noqa: E402


def load(path):
    spec = importlib.util.spec_from_file_location("imgtrace_before", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def area_of(ents):
    tot = 0.0
    for e in ents:
        pts = [(e["x"] + x, e["y"] + y) for x, y in e["points"]]
        a = abs(imgtrace._area2(pts)) / 2.0
        tot += a if e["mode"] == "add" else -a
    return tot


def worst_move(a, b):
    worst = 0.0
    for ea, eb in zip(a, b):
        ra = np.array([[ea["x"] + x, ea["y"] + y] for x, y in ea["points"]])
        rb = np.array([[eb["x"] + x, eb["y"] + y] for x, y in eb["points"]])
        d, _f = imgtrace._nearest_on_ring(rb, ra)
        worst = max(worst, float(d.max()))
    return worst


def run(mod, data, kw):
    try:
        ents, info = mod.image_to_entities(data, **kw)
    except Exception as e:                                  # noqa: BLE001
        return None, {"error": f"{type(e).__name__}: {str(e)[:60]}"}
    return ents, info


def main():
    path = (sys.argv[1] if len(sys.argv) > 1
            else os.path.join(HERE, "_imgtrace_r6_before.py"))
    before = load(path)
    print(f"before = {os.path.basename(path)}\n")
    for make in RECIPES:
        name = make.__name__
        data, kw = make()
        e0, i0 = run(before, data, kw)
        e1, i1 = run(imgtrace, data, kw)
        if e0 is None or e1 is None:
            print(f"{name:<22} before {i0}  after {i1}")
            continue
        same = (len(e0) == len(e1)
                and all(a == b for a, b in zip(e0, e1)))
        a0, a1 = area_of(e0), area_of(e1)
        mv = worst_move(e0, e1) if len(e0) == len(e1) else float("nan")
        print(f"{name:<22} {'IDENTICAL' if same else 'changed  '}  "
              f"ents {len(e0)}->{len(e1)}  pts {i0['points']}->{i1['points']} "
              f" bbox {i0['width_mm']}x{i0['height_mm']}"
              f" -> {i1['width_mm']}x{i1['height_mm']}"
              f"  area {a0:.4f} -> {a1:.4f} ({a1 - a0:+.6f})"
              f"  worst move {mv:.6f} mm")
        for tag, ents in (("before", e0), ("after", e1)):
            try:
                solid = sk.extrude_sketch(sk.make_sketch("XY", 0, ents), 2.0)
                ok = f"vol {solid.volume:.4f} valid {solid.is_valid}"
            except Exception as exc:                        # noqa: BLE001
                ok = f"SKETCH FAIL {type(exc).__name__}: {str(exc)[:50]}"
            print(f"    {tag:<7}{ok}")


if __name__ == "__main__":
    main()
