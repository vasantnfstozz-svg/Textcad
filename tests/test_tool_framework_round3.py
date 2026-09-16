"""Section 11, ROUND THREE — round two re-read, plus section 10's carried fix.

PART B (the fix).  Section 10's round two MEASURED a defect in
toolplan._face_of and could not fix it (toolplan.py is section 11's file).
A live face click carries the area of the mesh ON SCREEN; while a Fillet /
Chamfer / Shell panel is open that mesh is the tool's PREVIEW body, so a face
the preview has TRIMMED is clicked at its trimmed size — and since the
face-pick size gate landed (1a8d28f) that trimmed area is the identity
resolve_face uses on the INPUT body.  Two pads, tops 200 mm2 and 180 mm2, and
an r1 blend that leaves exactly 180 of the first: the click on pad P resolved
PAD Q, 50 mm away, and plan_fillet took every edge of pad Q, silently.  With
the pads at different heights the same coincidence refused a face that is
right there instead.  Reproduced in probes/face_of_preview_trim_probe.py.

PART A (round two re-read).  Round two's P0 fix — a tool session lets go when
the document on screen becomes another design — is pinned by round two's own
tests only as SOURCE TEXT, plus a server test that no tool request moves the
active tab.  Neither runs tabMoved, which sits on the path of every
'doc-updated' in the app.  The two node tests below run the SHIPPED
static/js/tool.js against the payloads the product really produces.
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import build123d as b3d
import pytest

import blocks
import toolplan
from document import Document
from tests.gauntlet import BODIES, planar_faces

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "static" / "js"


# ---------------------------------------------------------------------------
# PART B — a click made on the tool's own preview body
# ---------------------------------------------------------------------------

def _pick(face):
    """A click as the browser makes it: studio rounds a face centre to 2
    decimals and a normal to 3; the area is blocks.stored_area."""
    c = face.center()
    n = face.normal_at(c)
    return {"center": [round(float(c.X), 2), round(float(c.Y), 2),
                       round(float(c.Z), 2)],
            "normal": [round(float(n.X), 3), round(float(n.Y), 3),
                       round(float(n.Z), 3)],
            "area": blocks.stored_area(face)}


def _top_at(solid, x, tol=1.0):
    best = None
    for f in solid.faces():
        try:
            c, n = f.center(), f.normal_at(f.center())
        except Exception:
            continue
        if n.Z > 0.99 and abs(c.X - x) <= tol and (best is None or c.Z > best[1]):
            best = (f, c.Z)
    return best[0] if best else None


def _bracket_doc(q_thick):
    """pad P (top 20x10 = 200 mm2) and pad Q (top 20x9 = 180) on a base plate,
    50 mm apart; q_thick sets pad Q's height."""
    doc = Document(name="bracket")
    doc.add("base", "plate", {"width": 120, "depth": 40, "thickness": 10}, [])
    doc.add("p", "plate", {"width": 20, "depth": 10, "thickness": 5}, [])
    doc.add("pm", "move", {"x": -25, "y": 0, "z": 12.5}, ["p"])
    doc.add("f1", "fuse", {}, ["base", "pm"])
    doc.add("q", "plate", {"width": 20, "depth": 9, "thickness": q_thick}, [])
    doc.add("qm", "move", {"x": 25, "y": 0, "z": 10 + q_thick / 2}, ["q"])
    doc.add("body", "fuse", {}, ["f1", "qm"])
    doc.rebuild()
    return doc


def _preview_click(part):
    """The click the user makes on the PREVIEW: an r1 blend on one top edge of
    pad P leaves exactly 180 mm2 of it — pad Q's area."""
    top = _top_at(part, -25)
    edge = max(top.edges(),
               key=lambda e: e.length if abs(e.center().Y) > 1e-6 else -1)
    return _pick(_top_at(b3d.fillet(edge, 1.0), -25))


def test_a_preview_trimmed_face_does_not_resolve_the_pad_next_door():
    """THE P0.  Both pad tops are coplanar +Z, so surface_gap — which ignores
    trimming on purpose — cannot tell them apart, and the answer was silent."""
    doc = _bracket_doc(5.0)
    part = doc._parts["body"]
    click = _preview_click(part)
    assert click["area"] == pytest.approx(180.0, abs=0.01)
    assert blocks.area_of(_top_at(part, 25)) == pytest.approx(180.0, abs=0.01)

    got = toolplan._face_of(part, click, "body")
    assert got.center().X == pytest.approx(-25, abs=0.01), \
        "the click on pad P resolved the pad 50 mm away"
    assert blocks.area_of(got) == pytest.approx(200.0, abs=0.01)


def test_plan_fillet_rounds_the_pad_that_was_clicked():
    """What the user actually does: the whole plan, not just the resolver.
    Every edge of the WRONG pad is 4 edges of a 20x9 rectangle — the right
    answer is the 4 edges of the 20x10 one, and their lengths say which."""
    doc = _bracket_doc(5.0)
    click = _preview_click(doc._parts["body"])
    p = toolplan.plan(doc, {"tool": "fillet", "body_id": "body",
                            "face_toggle": click})
    assert p["ok"], p
    xs = [e["points"][1][0] for e in p["edges"]]
    assert all(x < 0 for x in xs), \
        f"plan_fillet took the edges of the OTHER pad: {xs}"
    lens = sorted(round(e["length"], 2) for e in p["edges"])
    assert lens == [10.0, 10.0, 20.0, 20.0], lens        # 20x10, not 20x9


def test_the_same_coincidence_at_another_height_is_not_refused():
    """The other half of the same defect: with the pads at different heights
    surface_gap DOES notice, and a perfectly good click was refused."""
    doc = _bracket_doc(4.0)                      # pad Q's top is 1 mm lower
    part = doc._parts["body"]
    click = _preview_click(part)
    got = toolplan._face_of(part, click, "body")       # must not raise
    assert got.center().X == pytest.approx(-25, abs=0.01)
    assert blocks.area_of(got) == pytest.approx(200.0, abs=0.01)


def test_the_documented_tie_still_answers_the_size_the_pick_carries():
    """The one case the size gate exists to decide must be untouched: a flush
    pad in a round pocket has two +Z faces whose centroids are the SAME point
    (blocks.resolve_face's own docstring, tests/test_face_pick_size.py).  The
    new rule may not switch between them — nothing is closer than 0 mm."""
    part = b3d.Part() + b3d.extrude(b3d.Plane.XY * b3d.Circle(20), amount=10)
    part -= b3d.Pos(0, 0, 5) * b3d.extrude(b3d.Plane.XY * b3d.Circle(12), amount=5)
    part += b3d.Pos(0, 0, 5) * b3d.extrude(b3d.Plane.XY * b3d.Circle(6), amount=5)
    tops = [f for f in part.faces()
            if abs(f.center().Z - 10) < 1e-6 and f.normal_at(f.center()).Z > 0.99]
    assert len(tops) == 2
    for f in tops:
        got = toolplan._face_of(part, _pick(f), "pocket")
        assert blocks.area_of(got) == pytest.approx(blocks.area_of(f), abs=0.01)


def test_a_face_whose_centroid_is_off_its_own_material_still_resolves():
    """An annulus's centroid is in its hole, so provenance.OnFace says False
    for a perfectly good pick — which is why containment can only ever CHOOSE
    BETWEEN candidates here, never gate.  The existing washer test sends no
    area; this one does, which is the new path."""
    doc = Document(name="wash")
    doc.add("d", "disc", {"radius": 10, "thickness": 5}, [])
    doc.add("h", "with_center_hole", {"radius": 4}, ["d"])
    doc.rebuild()
    ring = next(f for f in doc._parts["h"].faces()
                if blocks._gtype(f) == "PLANE" and f.center().Z > 0)
    assert abs(ring.center().X) < 1e-6 and abs(ring.center().Y) < 1e-6
    got = toolplan._face_of(doc._parts["h"], _pick(ring), "h")
    assert blocks._shape_key(got) == blocks._shape_key(ring)


def test_no_honest_pick_on_the_corpus_is_moved_or_refused():
    """R6 / rule 4: the new rule runs on every face pick every tool makes, so
    it is put to the whole gauntlet corpus.  A click made ON the body carries
    that face's own centroid, and nothing can be closer to it than itself."""
    total = 0
    for name, make in BODIES.items():
        solid = make()
        for idx, f, _c, _n in planar_faces(solid):
            pick = _pick(f)
            if pick["area"] is None:
                continue
            total += 1
            got = toolplan._face_of(solid, pick, name)
            assert blocks._shape_key(got) == blocks._shape_key(f), f"{name}.f{idx}"
    assert total >= 60, total


def test_a_band_only_the_preview_drew_is_still_refused():
    """The refusal _face_of exists for must survive: a blend band has no twin
    on the input body, and its centre must not quietly name the wall beside
    it (the 2026-09-08 review)."""
    part = blocks.plate(40, 30, 20)
    prev = b3d.fillet(part.edges().group_by(b3d.Axis.Z)[-1], 3.0)
    before = {blocks._shape_key(f) for f in part.faces()}
    bands = [f for f in prev.faces()
             if blocks._gtype(f) == "CYLINDER"
             and blocks._shape_key(f) not in before]
    assert bands
    for band in bands:
        with pytest.raises(ValueError, match="not on"):
            toolplan._face_of(part, _pick(band), "b")


# ---------------------------------------------------------------------------
# PART A — round two's let-go, RUN instead of read
# ---------------------------------------------------------------------------

_API_STUB = """
export const calls = [], said = [];
export function setBusy() {} export function clearBusy() {}
export function isBusy() { return false; }
export async function getJSON(u) { calls.push(u); return {}; }
export async function postJSON(url, body) { calls.push(url);
  return { features: [], active_tab: 't3', name: 'bracket' }; }
export async function planRequest(req) { calls.push('/api/tool/plan');
  return { ok: true, input: 'plate1', target_body: 'plate1', edges: [] }; }
export function noteRecovery() { return false; }
export function noteArrival() { return false; }
"""
_VIEWPORT_STUB = """
export const holdViewport = async fn => await fn();
export function cancelPlanePick() {} export function beginProfilePick() {}
export function cancelProfilePick() {} export function beginEdgePick() {}
export function endEdgePick() {} export function clearPick() {}
export function pickWhat() { return 'a sketch'; }
export function profilePickArmed() { return false; }
"""
# the browser globals tool.js touches AT IMPORT TIME, then the real module
_BOOT = """
const els = new Map();
globalThis.document = { addEventListener() {}, getElementById: id => {
  if (!els.has(id)) els.set(id, { id, value: '', innerHTML: '', disabled: false,
    title: '', style: { display: 'none' }, options: [],
    firstElementChild: { textContent: '' } });
  return els.get(id); } };
globalThis.window = { addEventListener() {} };
const { bus } = await import('./bus.js');
const { S } = await import('./state.js');
const { tool } = await import('./tool.js');
const { said } = await import('./api.js');
bus.on('msg', (_w, t) => said.push(t));
const ctl = tool({ name: 'Probe', icon: '^', tool: 'extrude', panel: 'xPanel',
  ids: 'x', ops: { profile: 'extrude' }, fields: { change: [], typed: [] },
  show() {}, params: () => ({ amount: 5 }), snapshot: f => ({ ...(f.params || {}) }),
  isEmpty: () => false, describe: () => '5 mm', nothing: 'nothing',
  gizmos: { begin() {}, end() {} } });
const DOC = (tab, name, extra = {}) => ({ active_tab: tab, name, ok: true,
  features: [{ id: 's1', op: 'sketch', params: {}, inputs: [], volume: null },
             { id: 'p1', op: 'plate', params: {}, inputs: [], volume: 1e3,
               status: 'ok' }], ...extra });
const open = () => els.get('xPanel').style.display === 'block';
const out = {};
async function session(doc) {
  S.lastDoc = doc; S.modalTool = null; els.clear();
  ctl.open('s1'); await new Promise(r => setTimeout(r, 0));
  return { opened: open(), tab: ctl.st && ctl.st.tab };
}
function fire(doc) { said.length = 0; bus.emit('doc-updated', doc);
  return { open: open(), modal: S.modalTool, said: said.slice() }; }

out.opened = await session(DOC('t3', 'bracket'));
out.rebuilt = fire(DOC('t3', 'bracket', { rebuild_ms: 42 }));
out.own_write = fire(DOC('t3', 'bracket', { geom_version: 9 }));
out.undone = fire({ ...DOC('t3', 'bracket'), features: [] });
out.renamed = fire(DOC('t3', 'saved-as-another-name'));
out.struck = fire({ ...DOC('t3', 'saved-as-another-name'),
  features: [{ id: 's1', op: 'sketch', suppressed: true, inputs: [], volume: null }] });
out.restored = fire({ ...DOC('t3', 'saved-as-another-name'), restored: 'v3' });
out.no_tab_in_payload = fire({ name: 'bracket', features: [] });
out.arrived = fire(DOC('t7', 'arrives-from-mcp'));
await session(DOC('t3', 'bracket'));
bus.emit('server-recovered', DOC('t1', 'bracket'));
out.crash_closed_it = !open();
console.log(JSON.stringify(out));
"""


def _run_tool_js(tmp_path):
    for name in ("tool.js", "bus.js", "state.js"):
        shutil.copy(JS / name, tmp_path / name)
    (tmp_path / "api.js").write_text(_API_STUB, encoding="utf-8")
    (tmp_path / "viewport.js").write_text(_VIEWPORT_STUB, encoding="utf-8")
    (tmp_path / "boot.mjs").write_text(_BOOT, encoding="utf-8")
    r = subprocess.run([shutil.which("node"), str(tmp_path / "boot.mjs")],
                       capture_output=True, text=True, encoding="utf-8",
                       cwd=str(tempfile.gettempdir()))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip())


@pytest.mark.skipif(not shutil.which("node"), reason="node is not on PATH")
def test_the_shipped_let_go_never_fires_on_the_design_in_front(tmp_path):
    """The let-go is compared on `active_tab` — the server's tab id — and NOT
    on the design's name, so the eight ordinary 'doc-updated' payloads a
    session sees leave the panel open.  A RENAME is the one that would cost
    the user a half-finished panel if the key were the name."""
    out = _run_tool_js(tmp_path)
    assert out["opened"] == {"opened": True, "tab": "t3"}
    for case in ("rebuilt", "own_write", "undone", "renamed", "struck",
                 "restored", "no_tab_in_payload"):
        assert out[case]["open"] is True, f"{case}: the panel let go"
        assert out[case]["modal"] == "Probe", f"{case}: the lock was released"
        assert out[case]["said"] == [], f"{case}: {out[case]['said']}"


@pytest.mark.skipif(not shutil.which("node"), reason="node is not on PATH")
def test_the_shipped_let_go_fires_when_another_design_takes_the_tab(tmp_path):
    """...and it really does fire on the door round two found (the MCP
    doorbell), releasing the one-command-at-a-time lock on the way out so the
    ribbon is not left dead."""
    out = _run_tool_js(tmp_path)
    assert out["arrived"]["open"] is False
    assert out["arrived"]["modal"] is None, "S.modalTool was left held"
    assert any("let go" in s for s in out["arrived"]["said"]), out["arrived"]
    # a CRASH closes the panel through 'server-recovered', which is emitted
    # first, so the let-go never speaks about a tab id the restart re-minted
    assert out["crash_closed_it"] is True
