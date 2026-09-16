"""Section 11 round two — the OTHER door into round one's P0.

Round one (a3d6b03) guarded the tab BAR: a click on a document tab, its ✕ and
the ＋ now go through `modalGuard`.  But the diagnosis in its own commit
message has two halves, and only one was closed:

    "An open panel remembers its feature by ID and NEVER LISTENS FOR
     'doc-updated', and every write it makes ... is addressed to whatever tab
     is ACTIVE."

The active tab also moves with NO tab-bar click at all.  An AI over MCP posts
/api/open/<slug>?external=1 and studio sets STATE["active"] to the arriving
tab — doctabs.js's own closeTab comment records it: "the active tab can move
underneath an open dialog (the MCP doorbell auto-loads arriving designs) —
seen live 2026-09-01".  tool.js still has no 'doc-updated' listener, so the
open panel never hears, and its next write lands in the arriving design.

Run:  C:\\Python314\\python.exe probes/tool_tab_moves_itself_probe.py
"""
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT", tempfile.mkdtemp())

from fastapi.testclient import TestClient  # noqa: E402

import studio  # noqa: E402

# a probe must never save into the user's library
studio.DESIGNS = Path(tempfile.mkdtemp()) / "designs"
studio.DESIGNS.mkdir(parents=True, exist_ok=True)

c = TestClient(studio.app)

js = (ROOT / "static" / "js" / "tool.js").read_text(encoding="utf-8")
listens = bool(re.search(r"bus\.on\(\s*'doc-updated'", js))
print(f"tool.js listens for 'doc-updated'?  {listens}")


def make(name, amount):
    c.post("/api/new", json={"name": name})
    c.post("/api/feature/add", json={
        "id": "b", "op": "plate",
        "params": {"width": 60, "depth": 40, "thickness": 20}, "inputs": []})
    c.post("/api/feature/add", json={
        "id": "s1", "op": "sketch_on_face",
        "params": {"face": "top", "entities": [{"kind": "circle", "r": 6}]},
        "inputs": ["b"]})
    c.post("/api/feature/add", json={
        "id": "extrude1", "op": "extrude",
        "params": {"amount": amount}, "inputs": ["s1"]})
    return c.get("/api/doc").json()["active_tab"]


mine = make("panel-design", 5)             # the design the panel is open on
make("arrives-from-mcp", 9)                # a design that will arrive by itself
slug = c.post("/api/save", json={}).json().get("saved")
c.post("/api/tabs/close", json={"id": c.get("/api/doc").json()["active_tab"]})
c.post("/api/tabs/switch", json={"id": mine})
print(f"active tab with the panel open: {c.get('/api/doc').json()['active_tab']}")

# THE DOORBELL — no tab-bar click anywhere, so modalGuard is never consulted
c.post(f"/api/open/{slug}?external=1", json={})
now = c.get("/api/doc").json()
print(f"after POST /api/open/{slug}?external=1 -> active tab {now['active_tab']}"
      f" ('{now['name']}'), arrival banner owed: {bool(now.get('arrival'))}")

# ...and now the open panel presses OK (or Cancel — the same door)
doc = c.post("/api/feature/params",
             json={"feature_id": "extrude1", "params": {"amount": 30}}).json()
got = next(f for f in doc["features"] if f["id"] == "extrude1")
print(f"the panel's write landed on '{doc['name']}': extrude1 amount = "
      f"{got['params']['amount']}")

back = c.post("/api/tabs/switch", json={"id": mine}).json()
ours = next(f for f in back["features"] if f["id"] == "extrude1")
print(f"the design the panel was opened on ('{back['name']}'): "
      f"extrude1 amount = {ours['params']['amount']}   (untouched)")
