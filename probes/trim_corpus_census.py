r"""What is IN the 324-sketch corpus the identity claim of 916a731 rests on?

"It matched on 324 sketches" is evidence, not proof — the question is what the
324 do not contain.  This reads `designs/` (READ ONLY, new sampler only, so it
is cheap) and reports:

  * every entity KIND and how often it appears,
  * every wire's edge count and OCCT geometry types,
  * how many entities build MORE THAN ONE FACE (Trim keeps only `faces()[0]`),
  * how many entities build a face WITH HOLES (Trim keeps only the outer wire),
  * how many sketches `trim_pieces` REFUSES — those sketches prove nothing
    about identity, they only refuse the same way twice.

    C:\Python314\python.exe probes/trim_corpus_census.py
"""
from __future__ import annotations
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np                                            # noqa: E402
import sketch as sk                                           # noqa: E402
import sketch_trim as tr                                      # noqa: E402


def sketches():
    for path in sorted((ROOT / "designs").glob("*.tcad.json")):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception:                                     # noqa: BLE001
            continue
        if not isinstance(d, dict) or "features" not in d:
            continue
        for f in d["features"]:
            ents = (f.get("params") or {}).get("entities")
            if isinstance(ents, list) and ents:
                yield path.name[:-len(".tcad.json")], f.get("id"), ents


def main():
    rows = list(sketches())
    kinds = Counter()
    edge_counts = Counter()
    geom = Counter()
    multi_face = []
    holed = []
    build_fail = Counter()
    for design, sid, ents in rows:
        for i, e in enumerate(ents):
            kinds[e.get("kind")] += 1
            try:
                faces = sk._entity(e).faces()
            except Exception as ex:                           # noqa: BLE001
                build_fail[type(ex).__name__] += 1
                continue
            if len(faces) > 1:
                multi_face.append((design, sid, i, e.get("kind"), len(faces)))
            f = faces[0]
            ow = f.outer_wire()
            if len([w for w in f.wires() if not w.is_same(ow)]):
                holed.append((design, sid, i, e.get("kind")))
            es = ow.edges()
            edge_counts[min(len(es), 400)] += 1
            for ed in es:
                geom[str(ed.geom_type)] += 1

    print(f"{len(rows)} sketches in {len({r[0] for r in rows})} designs, "
          f"{sum(len(r[2]) for r in rows)} entities\n")
    print("entity kinds:")
    for k, v in kinds.most_common():
        print(f"   {str(k):18s} {v}")
    print("\nOCCT edge geom types across every outer wire:")
    for k, v in geom.most_common():
        print(f"   {k:34s} {v}")
    print("\nouter-wire edge counts (edges -> how many entities):")
    for k in sorted(edge_counts):
        print(f"   {k:4d} edges : {edge_counts[k]}")
    print(f"\nentities that build MORE THAN ONE FACE: {len(multi_face)}")
    for row in multi_face[:10]:
        print(f"   {row}")
    print(f"entities whose first face HAS HOLES: {len(holed)}")
    for row in holed[:10]:
        print(f"   {row}")
    if build_fail:
        print(f"entities that do not build at all: {dict(build_fail)}")

    print("\nhow much of the 324 is actually an identity comparison?")
    ok = refused = 0
    reasons = Counter()
    for design, sid, ents in rows:
        try:
            tr._pieces_raw(ents)
            ok += 1
        except Exception as ex:                               # noqa: BLE001
            refused += 1
            reasons[str(ex)[:70]] += 1
    print(f"   {ok} sketches produce pieces, {refused} REFUSE "
          f"(those prove nothing about identity)")
    for k, v in reasons.most_common(8):
        print(f"      {v:3d}x {k}")


if __name__ == "__main__":
    np.seterr(all="ignore")
    main()
