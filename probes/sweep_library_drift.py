"""Does the Sweep build move ANY of the user's live designs?

`_place_sketch` now sits under every sketch and sketch_on_face, so every
design goes through new code. Run once with the repo root of MASTER and once
with the worktree's, then diff the two files:

    python probes/sweep_library_drift.py <repo-root> <designs-dir> <out.json>

Prints one line per design: the volume of every leaf body, 4 decimals, and
the design's warnings. Nothing is written to designs/; every design is read
with Document.from_data.
"""
import glob
import json
import os
import sys
import time

root, designs, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, root)
os.chdir(root)
from document import Document  # noqa: E402

out = {}
for path in sorted(glob.glob(os.path.join(designs, "*.tcad.json"))):
    name = os.path.basename(path)[:-len(".tcad.json")]
    try:
        with open(path, encoding="utf-8") as fh:
            doc = Document.from_data(json.load(fh))
        t0 = time.perf_counter()
        doc.rebuild()
        vols = []
        for fid in doc.leaf_solid_ids():
            p = doc._parts.get(fid)
            try:
                vols.append([fid, round(float(p.volume), 4)])
            except Exception:
                vols.append([fid, None])
        failed = [f.id for f in doc.features if f.status == "failed"]
        out[name] = {"n": len(doc.features), "vols": vols, "failed": failed,
                     "warn": sorted(doc.warnings),
                     "secs": round(time.perf_counter() - t0, 2)}
    except Exception as ex:
        out[name] = {"error": f"{type(ex).__name__}: {ex}"}
    print(f"  {name:30s} {out[name].get('error') or out[name]['vols']}"[:150], flush=True)

with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=1, sort_keys=True)
print("wrote", out_path)
