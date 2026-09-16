"""Section 11, ROUND TWO — measuring the fix commit a3d6b03's own new code.

Two questions, both answered by measurement, never by reading:

1. planRequest's new `!r.ok` branch.  /api/tool/plan is NOT in studio's
   _JOB_OPEN_POSTS, so while the AI is building in the active tab the
   one-writer middleware answers it 400 with the project's own refusal shape
   {"error": <sentence>} — never `detail`.  Round one reads `detail` only, so
   the sentence the server wrote is thrown away.  Measured end to end: the
   real status + body out of studio, then the REAL static/js/api.js run in
   node against that body.

2. the Spec dialog.  Round one guarded the holes box.  The six NUMBER boxes
   of the same handler go through `num()`, which is `Number(v)` — so a box
   that is not a number is NaN, JSON.stringify writes null, and /api/spec
   drops every null key.  The requirement is deleted and the next line says
   the design verifies against the new requirements.

Run:  C:\\Python314\\python.exe probes/tool_framework_round2_probe.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("TEXTCAD_HISTORY_ROOT", tempfile.mkdtemp())

from fastapi.testclient import TestClient  # noqa: E402

import studio  # noqa: E402

c = TestClient(studio.app)

print("=" * 72)
print("1. /api/tool/plan while the AI is building in this tab")
print("=" * 72)

c.post("/api/new", json={"name": "round2"})
c.post("/api/feature/add", json={
    "id": "b", "op": "plate",
    "params": {"width": 60, "depth": 40, "thickness": 20}, "inputs": []})
c.post("/api/feature/add", json={
    "id": "s1", "op": "sketch_on_face",
    "params": {"face": "top", "entities": [{"kind": "circle", "r": 6}]},
    "inputs": ["b"]})

tab = c.get("/api/doc").json()["active_tab"]
r = c.post("/api/tool/plan", json={"tool": "extrude", "sketch_id": "s1"})
print(f"  no job:   status {r.status_code}  ok={r.json().get('ok')}")

# the exact state the middleware guards: an unfinished chat job on this tab
studio.JOBS["probe-job"] = {"done": False, "tab": tab}
try:
    r_busy = c.post("/api/tool/plan", json={"tool": "extrude", "sketch_id": "s1"})
finally:
    studio.JOBS.pop("probe-job", None)

print(f"  AI busy:  status {r_busy.status_code}")
print(f"            body   {json.dumps(r_busy.json())}")
print(f"  /api/tool/plan in _JOB_OPEN_POSTS? {'/api/tool/plan' in studio._JOB_OPEN_POSTS}")

# ---- now run the REAL api.js against that answer, in node --------------
harness = r"""
import { planRequest } from '../static/js/api.js';
import { bus } from '../static/js/bus.js';

const CASES = JSON.parse(process.argv[2]);

globalThis.document = { getElementById: () => ({ style: {}, textContent: '' }) };
bus.on('msg', (who, t) => console.log('   chat:', t));

for (const [label, status, body] of CASES) {
  globalThis.fetch = async () => ({
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  });
  const out = await planRequest({ tool: 'extrude', sketch_id: 's1' });
  console.log(`  ${label}`);
  console.log(`     planRequest -> ${JSON.stringify(out)}`);
  console.log(`     the panel says: "\u26a0 Extrude cannot start: ${out.error}."`);
}
"""
cases = [
    ["AI busy (400, the server's own sentence)", r_busy.status_code, r_busy.json()],
]
# and the 422 round one set out to fix, for contrast
r422 = c.post("/api/tool/plan",
              json={"tool": "fillet", "body_id": "b", "chain": "maybe"})
cases.append(["pydantic (422, `detail`)", r422.status_code, r422.json()])

hp = ROOT / "probes" / "_round2_harness.mjs"
hp.write_text(harness, encoding="utf-8")
try:
    out = subprocess.run(
        ["node", str(hp), json.dumps(cases)],
        cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8")
    print(out.stdout or out.stderr)
finally:
    hp.unlink(missing_ok=True)

print("=" * 72)
print("2. the Spec dialog's NUMBER boxes")
print("=" * 72)

c.post("/api/new", json={"name": "round2-spec"})
c.post("/api/feature/add", json={
    "id": "b", "op": "plate",
    "params": {"width": 60, "depth": 40, "thickness": 20}, "inputs": []})
# the user wants TWO bodies and has built one: the spec fails, as it should
d = c.post("/api/spec", json={"spec": {"n_solids": 2}}).json()
print(f"  spec as the user set it: {d['spec']}   doc.ok={d['ok']}")
print(f"  spec_problems: {d.get('spec_problems')}")

# They reopen the dialog to raise it and mistype: the box holds "two".
# dialogs.js `num()` is Number(v) -> NaN; JSON.stringify writes null; and
# /api/spec keeps only `v is not None`.
node_num = subprocess.run(
    ["node", "-e",
     "const num = v => v.trim() === '' ? null : Number(v);"
     "console.log(JSON.stringify({n_solids: num('two'), symmetry: num(''),"
     " tip_radius: num(''), tol: num('')}));"],
    capture_output=True, text=True, encoding="utf-8")
wire = node_num.stdout.strip()
print(f"  the n_solids box holds 'two' -> the browser POSTs {wire}")

d2 = c.post("/api/spec", json={"spec": json.loads(wire)}).json()
print(f"  spec after that OK:      {d2['spec']}")
print(f"  n_solids requirement:    {'STILL THERE' if 'n_solids' in d2['spec'] else 'GONE'}")
print(f"  doc.ok (what the chat then says): {d2['ok']}")
print("  the chat line the handler prints:",
      "✓ Spec updated — design verifies against the new requirements."
      if d2["ok"] else "✗ Spec updated — does NOT meet it yet")
