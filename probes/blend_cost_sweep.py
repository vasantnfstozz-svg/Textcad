"""How long does rounding N edges of a traced outline really take?

Three of the overnight run's eight findings are one class: a fillet or chamfer
on ALL the edges of a traced-PNG keychain takes MINUTES and the app says
nothing while it does (156 s, 124 s, 630 s). The launch plan's note is
explicit that the answer must not be a refusal on edge count alone — bit-tray
and hole-box round 12-13 edges in milliseconds and the user's real parts live
in that band.

So before any warning is written into the tool's panel, measure where the cost
actually turns: fillet the same body at a growing number of edges and time it.
One body, one radius, serial. Nothing else may run beside this.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import blocks                                      # noqa: E402
from build123d import Part                         # noqa: E402
from document import Document                      # noqa: E402

BEFORE = ROOT / "bugs" / "20260913-014525-rocky-keychain-2-s46966-step15" / "before.tcad.json"

doc = Document.from_data(json.loads(BEFORE.read_text(encoding="utf-8")))
doc.rebuild()
part = Part(doc.result_bodies()[0].wrapped)
edges = part.edges()
faces = part.faces()
print(f"body: {len(faces)} faces, {len(edges)} edges, {part.volume:.4g} mm3")

rows = []
for n in (128, 256, 512, 1024, 2048, len(edges)):
    picks = [blocks.edge_ref(part, e) for e in edges[:n]]
    t0 = time.perf_counter()
    try:
        out = blocks.fillet_edges(part, 0.3, picks)
        ms = (time.perf_counter() - t0) * 1000
        print(f"  {n:4d} edges -> {ms:9.0f} ms   ({out.volume:.6g} mm3)")
        rows.append({"n": n, "ms": round(ms), "ok": True})
    except ValueError as e:
        ms = (time.perf_counter() - t0) * 1000
        print(f"  {n:4d} edges -> {ms:9.0f} ms   refused: {str(e)[:70]}")
        rows.append({"n": n, "ms": round(ms), "ok": False})

(ROOT / "probes" / "_sidecar_tmp" / "blend_cost_high.json").write_text(
    json.dumps({"faces": len(faces), "edges": len(edges), "rows": rows}, indent=1))
print("\nwrote probes/_sidecar_tmp/blend_cost.json")
