"""P5b review: the journey runner filed `strike-restore-mismatch` on
esp32-remote (seed 5002, step 43). Is it real?

In designs/esp32-remote the user has the LOGO switched off: logo_0_sketch,
logo_0_tool, logo_0, logo_1_sketch, logo_1_tool, logo_1 are all struck out.
Document.unstrike walks UPSTREAM of everything it restores and un-strikes
every struck ancestor it meets, so restoring any feature downstream of the
logo brings the logo back too.

This probe measures: which features come back, what the part's volume does,
and whether the un-strike was needed at all (a struck node with inputs is a
pass-through, so the chain builds through it).

Run:  C:\\Python314\\python.exe probes/p5b_unstrike_ancestors.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from document import Document  # noqa: E402


def load(p: Path) -> Document:
    return Document.from_data(json.loads(p.read_text(encoding="utf-8")))


def vol(doc: Document):
    part = doc.result()
    return None if part is None else round(float(part.volume), 3)


def struck(doc: Document):
    return {f.id for f in doc.features if f.suppressed}


def case(path: Path, target: str):
    print(f"\n== {path.name}: strike '{target}', then restore it ==")
    doc = load(path)
    doc.rebuild()
    v0, s0 = vol(doc), struck(doc)
    print(f"  as saved:      {len(doc.features)} features, struck {sorted(s0)}")
    print(f"                 result volume {v0}")
    doc.strike(target)
    doc.rebuild()
    v1, s1 = vol(doc), struck(doc)
    print(f"  after strike:  struck +{sorted(s1 - s0)}  volume {v1}")
    plan = doc.unstrike(target)
    doc.rebuild()
    v2, s2 = vol(doc), struck(doc)
    print(f"  after restore: struck {sorted(s2)}  volume {v2}")
    print(f"  restore plan said it put back: {plan.get('restored')}")
    lost = s0 - s2
    if lost:
        print(f"  *** the user's own struck features came back: {sorted(lost)}")
        print(f"  *** volume {v0} -> {v2}  (delta {None if None in (v0, v2) else round(v2 - v0, 3)})")
    else:
        print("  clean: strike + restore is the identity")
    return bool(lost)


def pass_through_check(path: Path, keep_struck: str, downstream: str):
    """Was bringing the ancestor back NECESSARY? Strike + restore `downstream`
    by hand, leaving `keep_struck` struck, and see whether it builds."""
    print(f"\n== is un-striking '{keep_struck}' needed for '{downstream}' to build? ==")
    doc = load(path)
    doc.strike(downstream)
    # restore ONLY the plan set, without the upstream walk
    plan = doc.remove_plan(downstream, "auto")
    for f in doc.features:
        if f.id in set(plan["deleted"]):
            f.suppressed = False
    doc._mark_stale()
    doc.rebuild()
    reds = [f"{f.id} ({f.op}): {'; '.join(f.problems)}" for f in doc.features
            if f.status != "ok" and not f.suppressed]
    print(f"  '{keep_struck}' still struck: {doc.get(keep_struck).suppressed}")
    print(f"  red features: {reds or 'none'}")
    print(f"  result volume {vol(doc)}")


def survey():
    print("\n== which saved designs carry struck features at all? ==")
    hits = []
    for p in sorted((ROOT / "designs").glob("*.tcad.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        s = [f["id"] for f in data.get("features", []) if f.get("suppressed")]
        if s:
            hits.append((p.name, s))
    for name, s in hits:
        print(f"  {name}: {len(s)} struck -> {s}")
    print(f"  {len(hits)} of the saved designs have at least one struck feature")


if __name__ == "__main__":
    fix = ROOT / "tests" / "fixtures" / "esp32-remote.tcad.json"
    live = ROOT / "designs" / "esp32-remote.tcad.json"
    case(fix, "tail_fold_scoop_sketch")
    case(fix, "tail_fold_scoop")
    if live.exists():
        case(live, "tail_fold_scoop_sketch")
    pass_through_check(fix, "logo_1", "tail_fold_scoop")
    survey()
