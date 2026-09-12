"""P5b review ROUND TWO: is the new unstrike rule ever WORSE than the old one?

bf5550b changed a path every saved design walks. Round one's bug was the
restore putting BACK too much; the regression to hunt is the mirror image — a
restore that now leaves a feature RED, or a volume that moves, where the old
unbounded upstream walk built it.

Two passes, because rebuilding an 81-feature design twice per feature is
hours:

  1. SET pass (no kernel): for every feature of every design, compute the set
     the NEW rule would restore and the set the OLD rule would restore. Pure
     graph work, instant. Where the two agree there is nothing to test.
  2. BUILD pass (kernel): only for the features where they DIFFER, strike and
     restore under the new rule and check that nothing is red that was not red
     to begin with, and that the volumes of what is left match the saved
     design.

Run:  C:\\Python314\\python.exe -u probes/p5b_r2_unstrike_sweep.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from document import Document  # noqa: E402


def old_set(doc: Document, feature_id: str) -> set:
    """The set `unstrike` restored at c11fd74: the plan plus an UNBOUNDED walk
    up through every struck ancestor. Computed, not applied."""
    plan = doc.remove_plan(feature_id, "auto")
    back = set(plan["deleted"])
    by_id = {f.id: f for f in doc.features}
    stack = list(back)
    while stack:
        f = by_id.get(stack.pop())
        if f is None:
            continue
        for dep in f.inputs:
            d = by_id.get(dep)
            if d is not None and d.suppressed and dep not in back:
                back.add(dep)
                stack.append(dep)
    return back


def new_set(doc: Document, feature_id: str) -> set:
    """The set bf5550b restores: the record if there is one (there is not, for
    a design just opened from a file), plus only the struck ancestors whose
    pass-through is unusable."""
    plan = doc.remove_plan(feature_id, "auto")
    recorded = doc._struck_by.get(feature_id)
    back = set(recorded if recorded is not None else plan["deleted"])
    back.add(feature_id)
    by_id = {f.id: f for f in doc.features}
    kinds = doc._kinds()
    still = {f.id for f in doc.features if f.suppressed} - back
    stack = list(back)
    while stack:
        f = by_id.get(stack.pop())
        if f is None:
            continue
        for dep in f.inputs:
            d = by_id.get(dep)
            if d is None or not d.suppressed or dep in back:
                continue
            if doc._passthrough(dep, still, by_id, kinds) is not None:
                continue
            back.add(dep)
            still.discard(dep)
            stack.append(dep)
    return back


def vols(doc: Document) -> dict:
    out = {}
    for fid in doc.leaf_solid_ids():
        p = doc._parts.get(fid)
        try:
            out[fid] = round(float(p.volume), 3)
        except Exception:                     # noqa: BLE001
            out[fid] = None
    return out


def reds(doc: Document) -> list:
    return sorted(f.id for f in doc.features
                  if f.status != "ok" and not f.suppressed)


def sweep(path: Path) -> list:
    data = json.loads(path.read_text(encoding="utf-8"))
    base_doc = Document.from_data(data)
    base_doc.rebuild()
    base_reds, base_vols = reds(base_doc), vols(base_doc)
    struck0 = sorted(f.id for f in base_doc.features if f.suppressed)
    ids = [f.id for f in base_doc.features]
    print(f"\n== {path.name}: {len(ids)} features; struck as saved: {struck0 or 'none'}")
    if base_reds:
        print(f"   red as saved (ignored below): {base_reds}")

    # ---- pass 1: sets only
    differs = []
    for fid in ids:
        d = Document.from_data(data)          # no rebuild: sets are graph work
        try:
            d.strike(fid)
        except (KeyError, ValueError):
            continue
        try:
            a, b = new_set(d, fid), old_set(d, fid)
        except (KeyError, ValueError) as e:
            print(f"   '{fid}': set pass refused: {e}")
            continue
        if a != b:
            differs.append((fid, sorted(b - a), sorted(a - b)))
    print(f"   pass 1: the two rules differ on {len(differs)} of {len(ids)} features")
    for fid, only_old, only_new in differs:
        if only_new:
            print(f"      '{fid}': NEW restores MORE: {only_new} (old kept struck)")
    if differs:
        kept = sorted({i for _, o, _ in differs for i in o})
        print(f"   the new rule leaves struck, where the old one restored: {kept}")

    # ---- pass 2: build only the ones that differ
    worse = []
    for fid, only_old, _ in differs:
        d = Document.from_data(data)
        d.rebuild()
        d.strike(fid)
        d.rebuild()
        d.unstrike(fid)
        d.rebuild()
        new_red = set(reds(d)) - set(base_reds)
        if new_red:
            worse.append((path.name, fid, sorted(new_red)))
            print(f"   *** WORSE '{fid}': red after the restore: {sorted(new_red)}")
        left = sorted(f.id for f in d.features if f.suppressed)
        if left == struck0 and vols(d) != base_vols:
            worse.append((path.name, fid, "volume moved"))
            print(f"   *** VOLUME MOVED on '{fid}': {base_vols} -> {vols(d)}")
    print(f"   pass 2: built {len(differs)}; worse: {len(worse)}")
    return worse


if __name__ == "__main__":
    worse = []
    for p in [ROOT / "designs" / f"{n}.tcad.json"
              for n in ("esp32-remote", "my-part-5", "my-part-8")] + \
             [ROOT / "tests" / "fixtures" / "pump-impeller.tcad.json"]:
        if p.exists():
            worse += sweep(p)
    print(f"\nTOTAL worse-under-the-new-rule: {len(worse)} {worse}")
