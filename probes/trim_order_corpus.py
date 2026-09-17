r"""The rebuilt entities did not move when `_wire_entity` stopped re-sorting.

`probes/trim_wire_entity_identity.py` proves it wire by wire on a hand-built
battery.  This puts the OLD call (`wire.order_edges()`) back and compares the
WHOLE `trim_apply` answer — message and every rebuilt entity — on real clicks
in the user's own designs (READ ONLY).

    C:\Python314\python.exe probes/trim_order_corpus.py
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np                                            # noqa: E402
import sketch_trim as tr                                      # noqa: E402

NEW = tr._ordered_edges


def old_ordered_edges(wire):
    return wire.order_edges()


WANT = [("rocky-balboa", "field_sketch"), ("esp32-remote", "sketch28"),
        ("rocky-keychain", None), ("bit-tray", None), ("hole-box", None),
        ("my-part-8", None), ("autonomiq-panel", None)]
PER_SKETCH = 4


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


def main() -> int:
    rows = list(sketches())
    todo = []
    for design, sid in WANT:
        for d, s, e in rows:
            if d == design and (sid is None or s == sid):
                todo.append((d, s, e))
                if sid is None:
                    break
    bad = clicked = 0
    t_old = t_new = 0.0
    for design, sid, ents in todo:
        tr._ordered_edges = NEW
        ids = [p["id"] for p in tr.trim_pieces(ents)]
        step = max(1, len(ids) // PER_SKETCH)
        ids = ids[::step][:PER_SKETCH]
        for pid in ids:
            out = []
            for fn in (old_ordered_edges, NEW):
                tr._ordered_edges = fn
                t = time.perf_counter()
                try:
                    out.append(json.dumps(tr.trim_apply(ents, pid),
                                          sort_keys=True))
                except Exception as ex:                       # noqa: BLE001
                    out.append(f"REFUSED {ex}")
                dt = time.perf_counter() - t
                if fn is NEW:
                    t_new += dt
                else:
                    t_old += dt
            clicked += 1
            if out[0] != out[1]:
                bad += 1
                print(f"  DIFFERS {design}/{sid} piece {pid}")
                print(f"    order_edges: {out[0][:200]}")
                print(f"    edges()    : {out[1][:200]}")
        print(f"  {design}/{sid} ({len(ents)} entities): {len(ids)} clicks")
    tr._ordered_edges = NEW
    print(f"\n{clicked} clicks, {clicked - bad} identical, {bad} differ")
    print(f"order_edges {t_old:6.1f} s total   edges() {t_new:6.1f} s total   "
          f"{t_old / max(t_new, 1e-9):.1f}x")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    np.seterr(all="ignore")
    sys.exit(main())
