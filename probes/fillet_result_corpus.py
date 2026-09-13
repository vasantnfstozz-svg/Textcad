"""What does an HONEST fillet/chamfer do to a body, measured over the whole
library — so a guard on the RESULT can be set from data, not from taste.

my-part-8 s46791 (2026-09-13 overnight run): fillet(r 0.4) on one picked edge
of a 181.499 mm3 intersect body returned 44.621 mm3, VALID, health [] — and
the same call on all 8 "horizontal" edges SEGFAULTED. So `_finish` needs to
measure what came back. This prints, for every fillet/chamfer feature in every
saved design and fixture:

    d_vol / (v^2 * L)     how much material moved, against the 90-degree ideal
    bbox shrink / v       how far the extremes retracted, against the value

    python probes/fillet_result_corpus.py [--designs a,b]
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
FILLET_OPS = {"fillet", "chamfer"}


def shrink(a, b) -> float:
    """How far b's bounding box pulled IN from a's, mm (negative = grew)."""
    return max(max(getattr(b.min, k) - getattr(a.min, k),
                   getattr(a.max, k) - getattr(b.max, k)) for k in ("X", "Y", "Z"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--designs")
    a = ap.parse_args()
    import blocks
    from document import Document
    files = sorted((ROOT / "designs").glob("*.tcad.json")) + \
        sorted((ROOT / "tests" / "fixtures").glob("*.tcad.json"))
    if a.designs:
        want = set(a.designs.split(","))
        files = [f for f in files if f.name[:-len(".tcad.json")] in want]
    rows, worst_v, worst_b = [], 0.0, 0.0
    for f in files:
        name = f.name[:-len(".tcad.json")]
        try:
            doc = Document.from_data(json.loads(f.read_text(encoding="utf-8")))
            doc.rebuild()
        except Exception as e:                       # noqa: BLE001 — a design that will not open is not this probe's business
            print(f"  !! {name}: {type(e).__name__} {str(e)[:80]}", flush=True)
            continue
        for feat in doc.features:
            if feat.op not in FILLET_OPS or feat.suppressed:
                continue
            src = [doc._parts.get(i) for i in (feat.inputs or [])]
            src = [s for s in src if s is not None and getattr(s, "volume", 0)]
            out = doc._parts.get(feat.id)
            if not src or out is None:
                continue
            part = src[0]
            v = float(feat.params.get("radius") or feat.params.get("length") or 0)
            try:
                picked = blocks.edges_for(part, feat.params.get("edges", "all"))
                L = sum(e.length for e in picked)
                dv = abs(out.volume - part.volume)
                ideal = max(v * v * L, 1e-12)
                sb = shrink(part.bounding_box(), out.bounding_box())
                rows.append((name, feat.id, v, len(picked), round(dv, 4),
                             round(dv / ideal, 4), round(sb, 5), round(sb / v, 4) if v else 0))
                worst_v, worst_b = max(worst_v, dv / ideal), max(worst_b, sb / v if v else 0)
            except Exception as e:                   # noqa: BLE001 — measured, not fatal
                print(f"  ?? {name}/{feat.id}: {type(e).__name__} {str(e)[:70]}", flush=True)
    rows.sort(key=lambda r: -r[5])
    print(f"{'design':28s} {'feature':22s} {'v':>6s} {'n':>4s} {'dvol':>10s} "
          f"{'dvol/v2L':>9s} {'shrink':>9s} {'shrink/v':>8s}", flush=True)
    for r in rows:
        print(f"{r[0]:28s} {r[1]:22s} {r[2]:6g} {r[3]:4d} {r[4]:10.4f} "
              f"{r[5]:9.4f} {r[6]:9.5f} {r[7]:8.4f}", flush=True)
    print(f"\n{len(rows)} fillet/chamfer features. "
          f"worst dvol/(v^2 L) = {worst_v:.4f};  worst bbox shrink / v = {worst_b:.4f}",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
