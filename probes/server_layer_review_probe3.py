"""Section 12 review probe, part 3: the spec dialog's own values, and the
export-name question.

Run:  C:\\Python314\\python.exe probes/server_layer_review_probe3.py
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
from history import content_hash                # noqa: E402


def fresh():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio._new_tab(studio.sample_flange())
    studio._rebuild_and_mesh()
    return TestClient(studio.app)


print("=" * 70)
print("A. what the SPEC DIALOG itself can send (dialogs.js:396-404)")
cases = [
    ("only the X box filled", {"size": [100, None, None]}),
    ("holes typed as a LIST", {"holes": [4, 6]}),
    ("holes typed as a number", {"holes": 6}),
    ("size with two boxes", {"size": [100, 100, None]}),
]
for what, spec in cases:
    c = fresh()
    r = c.post("/api/spec", json={"spec": spec})
    d = r.json()
    print(f"   {what:26s} -> {r.status_code} err={str(d.get('error'))[:60]}")
    print(f"      spec_problems={str(d.get('spec_problems'))[:100]}")
    # is the tab poisoned? try an ordinary edit afterwards
    r2 = c.post("/api/edit", json={"feature_id": "bore", "param": "radius",
                                   "value": 9})
    d2 = r2.json()
    print(f"      a later /api/edit -> {r2.status_code} "
          f"err={str(d2.get('error'))[:60]}")
    print(f"      spec now stored in the document: {studio._doc().spec}")

print("=" * 70)
print("B. does the poisoned spec reach the FILE?")
c = fresh()
c.post("/api/spec", json={"spec": {"size": [100, None, None]}})
studio._doc().name = "_probe-spec-file"
sv = c.post("/api/save").json()
p = studio.DESIGNS / "_probe-spec-file.tcad.json"
print("   saved:", sv.get("saved") or sv.get("error"))
if p.exists():
    print("   spec on disk:", json.loads(p.read_text(encoding="utf-8"))
          .get("spec"))
    p.unlink()

print("=" * 70)
print("C. the export name: sample flange vs the library's flange-100")
print("   sample_flange().name =", studio.sample_flange().name)
lib = studio.DESIGNS / "flange-100.tcad.json"
if lib.exists():
    same = content_hash(json.loads(lib.read_text(encoding="utf-8"))) == \
        content_hash(studio.sample_flange().to_data())
    print("   designs/flange-100.tcad.json exists; same content as the "
          "sample?", same)
print("   names of the 50 library designs whose doc.name is not the slug: 0 "
      "(measured earlier)")
