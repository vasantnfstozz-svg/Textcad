"""Do REAL bodies carry the degeneracies that make OCCT's blender crash?

my-part-8 s46791's intersect body is valid by BRepCheck_Analyzer and clean by
`.clean()`, but carries a ZERO-area cylindrical face and edges 0.000141 mm
long — and fillet on it either segfaults (8 edges) or returns 25% of the body,
valid and healthy (1 edge). A pre-kernel guard needs to know what honest
bodies look like, so this prints the smallest face and the shortest edge of
every leaf body in every saved design and fixture.

    python probes/sliver_body_corpus.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    from document import Document
    files = sorted((ROOT / "designs").glob("*.tcad.json")) + \
        sorted((ROOT / "tests" / "fixtures").glob("*.tcad.json"))
    rows = []
    for f in files:
        name = f.name[:-len(".tcad.json")]
        try:
            doc = Document.from_data(json.loads(f.read_text(encoding="utf-8")))
            doc.rebuild()
        except Exception as e:                       # noqa: BLE001
            print(f"  !! {name}: {type(e).__name__} {str(e)[:70]}", flush=True)
            continue
        for fid in doc.leaf_solid_ids():
            p = doc._parts.get(fid)
            if p is None:
                continue
            try:
                faces, edges = p.faces(), p.edges()
                if not faces or not edges:
                    continue
                rows.append((name, fid, round(float(p.volume), 2), len(faces),
                             min(f.area for f in faces), min(e.length for e in edges)))
            except Exception as e:                   # noqa: BLE001
                print(f"  ?? {name}/{fid}: {type(e).__name__} {str(e)[:60]}", flush=True)
    rows.sort(key=lambda r: r[4])
    print(f"{'design':26s} {'body':20s} {'vol':>12s} {'nf':>4s} "
          f"{'min face area':>14s} {'min edge len':>13s}", flush=True)
    for r in rows[:25]:
        print(f"{r[0]:26s} {r[1]:20s} {r[2]:12.2f} {r[3]:4d} {r[4]:14.8f} {r[5]:13.8f}",
              flush=True)
    print("   ... (smallest 25 by face area, of "
          f"{len(rows)} bodies)", flush=True)
    fa = sorted(r[4] for r in rows)
    el = sorted(r[5] for r in rows)
    print(f"\nsmallest face area over the library: {fa[0]:.8f} mm2 "
          f"(next {fa[1]:.8f}, {fa[2]:.8f})", flush=True)
    print(f"shortest edge over the library:      {el[0]:.8f} mm "
          f"(next {el[1]:.8f}, {el[2]:.8f})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
