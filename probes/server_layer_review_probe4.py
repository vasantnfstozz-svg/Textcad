"""Section 12 review probe, part 4: is a bad spec value a ONE-OFF error, or
does it poison the tab and the file?

Run:  C:\\Python314\\python.exe probes/server_layer_review_probe4.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      tempfile.mkdtemp(prefix="textcad-probe-"))

from fastapi.testclient import TestClient      # noqa: E402

import studio                                   # noqa: E402


def fresh():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(studio.sample_flange())
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


c = fresh()
r = c.post("/api/spec", json={"spec": {"volume": "50"}})
print("POST /api/spec {'volume': '50'} ->", r.status_code,
      str(r.json().get("error"))[:80])
print("   doc.spec is now:", studio._doc().spec)
for step in ("edit", "doc", "edit again"):
    if step == "doc":
        r2 = c.get("/api/doc")
    else:
        r2 = c.post("/api/edit", json={"feature_id": "bore",
                                       "param": "radius", "value": 9})
    print(f"   after that, {step:11s} -> {r2.status_code} "
          f"{str(r2.json().get('error'))[:70]}")
studio._doc().name = "_probe-spec-poison"
sv = c.post("/api/save").json()
p = studio.DESIGNS / "_probe-spec-poison.tcad.json"
print("   save ->", sv.get("saved") or str(sv.get("error"))[:70])
if p.exists():
    print("   spec written to the file:",
          json.loads(p.read_text(encoding="utf-8")).get("spec"))
    p.unlink()

print()
print("and a WRONG size on one axis is still caught (no false pass):")
c = fresh()
d = c.post("/api/spec", json={"spec": {"size": [999, None, None]}}).json()
print("   size [999, null, null] -> ok:", d.get("ok"),
      " problems:", d.get("spec_problems"))
