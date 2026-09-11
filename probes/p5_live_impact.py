"""How many of the user's LIVE designs would the P5 'add' job refuse to touch?

Read-only: Document.load + rebuild, never /api/open (which pushes a version).
A design with ANY red feature, or a parked rollback bar, makes author._apply_step's
whole-tree health check undo every correct AI step.
"""
import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pathlib import Path
from document import Document

out = []
for p in sorted(Path("designs").glob("*.tcad.json")):
    try:
        d = Document.load(str(p))
        d.rebuild()
        red = [(f.id, f.status) for f in d.features
               if f.status != "ok" and not f.suppressed]
        out.append({"name": p.stem, "features": len(d.features),
                    "red": red[:4], "n_red": len(red)})
    except Exception as e:
        out.append({"name": p.stem, "error": repr(e)[:120]})
Path("probes/_p5_live_impact.json").write_text(json.dumps(out, indent=1))
bad = [o for o in out if o.get("n_red")]
err = [o for o in out if o.get("error")]
print(f"designs: {len(out)}  with a RED feature: {len(bad)}  unloadable: {len(err)}")
for o in bad:
    print(f"  {o['name']}: {o['n_red']} red — {o['red']}")
