"""probes/imgtrace_library_audit.py - REVIEW-QUEUE section 9.

READ-ONLY audit of every polygon entity in the saved designs (the three
traced ones above all) for what a traced outline can carry: self-crossings,
duplicate points, fewer than 3 points, sub-0.1mm edges.
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from imgtrace_spike_probe import crossings  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    files = sorted(glob.glob(os.path.join(ROOT, "designs", "*.tcad.json")))
    tot = bad = 0
    for path in files:
        try:
            doc = json.load(open(path, encoding="utf-8"))
        except Exception:                        # noqa: BLE001
            continue
        rows = []
        for f in doc.get("features", []):
            for k, e in enumerate(f.get("params", {}).get("entities", []) or []):
                if e.get("kind") != "polygon":
                    continue
                p = [tuple(q) for q in e.get("points", [])]
                tot += 1
                notes = []
                if len(p) < 3:
                    notes.append(f"{len(p)} points")
                else:
                    n = len(p)
                    x = crossings(p)
                    if x:
                        notes.append(f"{len(x)} SELF-CROSSINGS")
                    if any(p[i] == p[(i + 1) % n] for i in range(n)):
                        notes.append("duplicate consecutive points")
                    mn = min(np.hypot(p[(i + 1) % n][0] - p[i][0],
                                      p[(i + 1) % n][1] - p[i][1])
                             for i in range(n))
                    if mn < 0.1:
                        notes.append(f"shortest edge {mn:.4f}mm")
                if notes:
                    bad += 1
                    rows.append(f"    {f['id']} ent{k} ({len(p)} pts): "
                                + "; ".join(notes))
        if rows:
            print(os.path.basename(path))
            print("\n".join(rows[:12]))
    print(f"\n{tot} polygon entities in {len(files)} designs; "
          f"{bad} with something a sketch would rather not see")


if __name__ == "__main__":
    main()
