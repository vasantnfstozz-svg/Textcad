r"""Lead 1 of the 916a731 brief: what is left of a Trim click is `sk.compose`.

OUT OF THIS WORKTREE'S FENCE — `sketch.py` is another agent's.  This probe
only MEASURES what a cheap change there would be worth, so the judgement in
the review report is a number rather than an opinion.  It edits nothing.

Three candidates, on the real cluster of `rocky-balboa/field_sketch`:

  1. the faces are rebuilt from JSON three times per click — `_outline`,
     `compose_order` and `compose` each call `sketch._entity` on every entity;
  2. `build123d.SkipClean` around the boolean chain;
  3. one multi-argument fuse for each run of consecutive ADDs, instead of
     N sequential `result + shape` booleans.

    C:\Python314\python.exe probes/trim_compose_lead.py
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build123d as b3d                                       # noqa: E402
import numpy as np                                            # noqa: E402
import sketch as sk                                           # noqa: E402


def load(design: str, sketch_id: str):
    d = json.loads((ROOT / "designs" / f"{design}.tcad.json")
                   .read_text(encoding="utf-8"))
    return next(f["params"]["entities"] for f in d["features"]
                if f.get("id") == sketch_id)


def area(shape):
    return sum(f.area for f in shape.faces()) if shape is not None else 0.0


def main():
    ents = load("rocky-balboa", "field_sketch")
    modes = [e.get("mode", "add") for e in ents]
    print(f"{len(ents)} entities, "
          f"{sum(1 for m in modes if m == 'subtract')} of them cuts")

    t = time.perf_counter()
    shapes = [sk._entity(e) for e in ents]
    t_build = time.perf_counter() - t
    edge_counts = sorted(len(s.faces()[0].outer_wire().edges())
                         for s in shapes)
    print(f"outer-wire edge counts: {edge_counts}")
    print(f"\n1. rebuilding every entity from JSON: {t_build:.2f} s ONCE.")
    print(f"   a Trim click does it 3x (outline, compose_order, compose) = "
          f"{3 * t_build:.2f} s; the caller already holds the faces.")

    t = time.perf_counter()
    base = sk.compose(ents, note=False)
    t_plain = time.perf_counter() - t
    print(f"\n2. sk.compose as it stands      : {t_plain:6.2f} s, "
          f"area {area(base):.4f}")

    t = time.perf_counter()
    with b3d.SkipClean():
        skipped = sk.compose(ents, note=False)
    t_skip = time.perf_counter() - t
    print(f"   sk.compose inside SkipClean  : {t_skip:6.2f} s, "
          f"area {area(skipped):.4f}  "
          f"({t_plain / max(t_skip, 1e-9):.2f}x, "
          f"same area: {abs(area(skipped) - area(base)) < 1e-6})")
    print(f"   faces {len(base.faces())} -> {len(skipped.faces())}, "
          f"edges {len(base.edges())} -> {len(skipped.edges())}")

    # 3. one fuse for each run of consecutive adds
    order = sk.compose_order(ents)
    runs, cur = [], []
    for i in order:
        if modes[i] == "subtract":
            if cur:
                runs.append(cur)
                cur = []
            runs.append([i])
        else:
            cur.append(i)
    if cur:
        runs.append(cur)
    print(f"\n3. the composition order is {len(runs)} run(s): "
          f"{[len(r) for r in runs]} "
          f"({sum(1 for r in runs if len(r) > 1)} of them fusible together)")
    t = time.perf_counter()
    result = None
    for run in runs:
        if modes[run[0]] == "subtract":
            if result is not None:
                result = result - shapes[run[0]]
        elif result is None and len(run) == 1:
            result = shapes[run[0]]
        else:
            block = shapes[run[0]]
            for j in run[1:]:
                block = block + shapes[j]       # placeholder: same pairwise
            result = block if result is None else result + block
    t_runs = time.perf_counter() - t
    print(f"   the boolean chain alone (faces already built): {t_runs:.2f} s "
          f"for {len(order)} booleans, area {area(result):.4f}")
    print(f"   -> of the {t_plain:.2f} s sk.compose call, {t_build:.2f} s is "
          f"rebuilding faces and {t_runs:.2f} s is OCCT booleans")


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
