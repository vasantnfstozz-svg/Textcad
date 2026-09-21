"""Move the sketch plane — Create Sketch's Offset step (sketchplane.js).

The user (2026-09-21): "if I want to draw shapes on top of the body or sketch
I need to move the sketch plane, which is not available in the tool right
now, because when I am drawing or using loft I cannot draw any shapes on top
of them". The kernel always had it — every sketch carries an `offset` — but
the UI never let anyone set it: a face sketch made by hand did not even send
the key. Now the picked plane or face is shown where the sketch WILL open,
with one arrow along its normal and an Offset box; OK opens the sketch there.

Backend facts this leans on (R1 — the browser draws what the server says):
  * /api/face-outline reports `into_sign`: which sign of the offset goes INTO
    the material. The frame is canonical (face_sketch_plane), so it is NOT one
    sign per axis pair the way sketch_on_face's docstring says: +y's frame z
    points -Y, so on a +y face POSITIVE goes in. Measured, not derived.
  * the frame moves along its own z by the offset — the same Plane.offset the
    sketch build uses, so grid and geometry cannot differ.
  * `offset` on a sketch_on_face is an ordinary parameter: the tree edits it
    and downstream rebuilds.
The node test runs the SHIPPED sketchplane.js against stubs of its neighbours:
a plane pick, a typed offset and OK must open the sketch AT that offset; Esc
must open nothing and release the modal lock; a face pick must carry the
offset into openSketchOnFace.
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import build123d as b3d
import pytest

import sketch as sk
from document import Document

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "static" / "js"

CIRCLE = [{"kind": "circle", "r": 5}]


def plate():
    return b3d.Box(60, 40, 20)          # centred: top z = +10, bottom z = -10


# --------------------------------------------------------------- backend ---

@pytest.mark.parametrize("face, sign, axis, inside", [
    ("top", -1, 2, 7), ("bottom", 1, 2, -7),
    ("+x", -1, 0, 27), ("-x", 1, 0, -27),
    ("+y", 1, 1, 17), ("-y", -1, 1, -17)])
def test_face_outline_says_which_sign_goes_into_the_material(face, sign, axis, inside):
    out = sk.face_outline_2d(plate(), face=face)
    assert out["planar"] and out["into_sign"] == sign
    # and it is the truth: 3 mm with that sign puts the frame origin 3 mm
    # INSIDE the 60 x 40 x 20 box on that face's axis
    moved = sk.face_outline_2d(plate(), face=face, offset=sign * 3)
    assert moved["frame"]["origin"][axis] == pytest.approx(inside, abs=1e-3)


def test_face_outline_frame_moves_by_the_offset_along_its_own_z():
    p = plate()
    o0 = sk.face_outline_2d(p, face="top")
    o5 = sk.face_outline_2d(p, face="top", offset=-5)
    z = o0["frame"]["z_dir"]
    for i in range(3):
        assert o5["frame"]["origin"][i] == pytest.approx(
            o0["frame"]["origin"][i] - 5 * z[i], abs=1e-3)
    assert o5["frame"]["origin"][2] == pytest.approx(5, abs=1e-3)
    # the 2D boundary is the same picture — only the plane moved
    assert o5["outer"] == o0["outer"]
    assert o5["into_sign"] == o0["into_sign"]


def test_face_sketch_offset_places_the_profile_where_the_frame_says():
    p = plate()
    placed = sk.sketch_on_face(p, face="top", offset=-5, entities=CIRCLE)
    bb = placed.bounding_box()
    assert bb.min.Z == pytest.approx(5) and bb.max.Z == pytest.approx(5)
    frame = sk.face_outline_2d(p, face="top", offset=-5)["frame"]
    assert frame["origin"][2] == pytest.approx(5, abs=1e-3)


def test_face_sketch_offset_is_an_editable_parameter_that_rebuilds():
    d = Document(name="t")
    d.add("b", "plate", {"width": 60, "depth": 40, "thickness": 20}, [])
    d.add("s", "sketch_on_face",
          {"face": "top", "offset": 0, "entities": CIRCLE}, ["b"])
    d.rebuild()
    assert d._parts["s"].bounding_box().center().Z == pytest.approx(10)
    d.edit("s", "offset", -5)                 # what the tree's offset row does
    d.rebuild()
    assert [f.status for f in d.features] == ["ok", "ok"]
    assert d._parts["s"].bounding_box().center().Z == pytest.approx(5)


def test_plane_sketch_offset_lands_the_profile_at_that_height():
    """the loft case: sections stacked on XY before any body exists"""
    d = Document(name="t")
    d.add("s1", "sketch", {"plane": "XY", "offset": 0, "entities": CIRCLE}, [])
    d.add("s2", "sketch", {"plane": "XY", "offset": 20, "entities": CIRCLE}, [])
    d.rebuild()
    assert d._parts["s1"].bounding_box().center().Z == pytest.approx(0)
    assert d._parts["s2"].bounding_box().center().Z == pytest.approx(20)


# ------------------------------------------------- the shipped sketchplane.js ---

_API_STUB = """
export const calls = [];
export async function planRequest(req) { calls.push(['plan', req]);
  return { ok: true, frame: { origin: [1, 2, 0], x_dir: [1, 0, 0], y_dir: [0, 1, 0],
                              z_dir: [0, 0, 1] } }; }
export function setBusy() {} export function clearBusy() {} export function isBusy() { return false; }
export async function getJSON() { return {}; } export async function postJSON() { return {}; }
export function noteRecovery() { return false; } export function noteArrival() { return false; }
"""
_VIEWPORT_STUB = """
export const holdViewport = async fn => await fn();
export const gizmo = { arrow: null, ghost: null, ghostAt: null, retaken: 0 };
export function beginExtrudeArrow(o, n, a, onChange, onCommit) {
  gizmo.arrow = { o, n, a, onChange, onCommit }; }
export function endExtrudeArrow() { gizmo.arrow = null; }
export function setExtrudeArrowAmount(a) { if (gizmo.arrow) gizmo.arrow.a = a; }
export function beginPlaneGhost(frame, loops) { gizmo.ghost = { frame, loops }; gizmo.ghostAt = 0; }
export function setPlaneGhost(off) { gizmo.ghostAt = off; }
export function endPlaneGhost() { gizmo.ghost = null; }
export function retakeSectionHandles() { gizmo.retaken++; }
export function cancelPlanePick() {} export function beginProfilePick() {}
export function cancelProfilePick() {} export function beginEdgePick() {}
export function endEdgePick() {} export function clearPick() {}
export function pickWhat() { return 'a sketch'; } export function profilePickArmed() { return false; }
"""
_SKETCHER_STUB = """
export const opened = [];
export async function openSketchEditor(plane, offset) { opened.push(['plane', plane, offset]); }
export async function openSketchOnFace(info, offset) { opened.push(['face', info.center, offset]); }
export async function fetchFaceOutline(req) {
  return { planar: true, outer: [[-30, -20], [30, -20], [30, 20], [-30, 20]], holes: [],
           frame: { origin: [0, 0, 10], x_dir: [1, 0, 0], y_dir: [0, 1, 0], z_dir: [0, 0, 1] },
           into_sign: -1, req }; }
"""
_BOOT = """
const els = new Map();
const el = id => { if (!els.has(id)) els.set(id, { id, value: '', textContent: '',
  innerHTML: '', disabled: false, title: '', style: { display: 'none' }, options: [],
  firstElementChild: { textContent: '' }, focus() {}, select() {} }); return els.get(id); };
const keyHandlers = [];
globalThis.document = { addEventListener() {}, getElementById: el };
globalThis.window = { addEventListener(t, fn) { if (t === 'keydown') keyHandlers.push(fn); },
                      removeEventListener(t, fn) { const i = keyHandlers.indexOf(fn);
                        if (i >= 0) keyHandlers.splice(i, 1); } };
const { bus } = await import('./bus.js');
const { S } = await import('./state.js');
S.lastDoc = { features: [{ id: 'b', op: 'plate', params: {}, inputs: [], volume: 100,
                            status: 'ok' }] };
const said = []; bus.on('msg', (_w, t) => said.push(t));
const { gizmo } = await import('./viewport.js');
const { opened } = await import('./sketcher.js');
const sp = await import('./sketchplane.js');
const base = keyHandlers.length;   // tool.js's own Esc listener, registered at import
const mine = () => keyHandlers.length - base;
sp.initSketchPlane();
const tick = () => new Promise(r => setTimeout(r, 0));
const out = {};

// 1. a plane pick: the step opens, the arrow sits on the plan's frame, modal held
await sp.stageSketchPlane('plane', 'XY'); await tick();
out.plane_open = { panel: el('planeDialog').style.display, modal: S.modalTool,
  what: el('plWhat').textContent, arrowO: gizmo.arrow.o, arrowN: gizmo.arrow.n,
  ghost: !!gizmo.ghost, keyHandlers: mine(), stage: sp.sketchPlaneStage() };
// dragging the arrow: box and ghost follow, nothing opens yet
gizmo.arrow.onChange(19.96);
out.plane_drag = { box: el('plOffset').value, ghostAt: gizmo.ghostAt, opened: opened.length };
// typing 20 and OK: the sketch opens AT 20, the lock is released, gizmos gone
el('plOffset').value = '20'; el('plOffset').oninput();
out.plane_typed = { ghostAt: gizmo.ghostAt, arrowA: gizmo.arrow.a };
el('plOk').onclick(); await tick();
out.plane_ok = { opened: opened.slice(), modal: S.modalTool, panel: el('planeDialog').style.display,
  arrow: gizmo.arrow, ghost: gizmo.ghost, retaken: gizmo.retaken, keyHandlers: mine(),
  stage: sp.sketchPlaneStage() };

// 2. Esc: nothing opens, lock released
opened.length = 0;
await sp.stageSketchPlane('plane', 'XZ'); await tick();
const esc = { key: 'Escape', repeat: false, preventDefault() {}, stopPropagation() {} };
for (const fn of keyHandlers.slice()) fn(esc);
out.esc = { opened: opened.length, modal: S.modalTool, panel: el('planeDialog').style.display,
  keyHandlers: mine(), said: said.at(-1) };

// 3. a face pick: the outline is fetched on the picked body, into_sign shown,
//    OK carries the offset into openSketchOnFace
opened.length = 0;
await sp.stageSketchPlane('face', { center: [0, 0, 10], normal: [0, 0, 1], area: 2400, body: 'b' });
await tick();
out.face_open = { what: el('plWhat').textContent, into: el('plInto').textContent,
  loops: gizmo.ghost.loops.length, outer: gizmo.ghost.loops[0].outer.length,
  arrowO: gizmo.arrow.o, stage: sp.sketchPlaneStage() };
el('plOffset').value = '-3'; el('plOffset').oninput();
el('plOffset').onkeydown({ key: 'Enter', preventDefault() {} }); await tick();
out.face_ok = { opened: opened.slice(), modal: S.modalTool };

// 4. the document changes under an open step: it lets go
await sp.stageSketchPlane('plane', 'YZ'); await tick();
bus.emit('doc-updated', S.lastDoc);
out.doc_changed = { modal: S.modalTool, panel: el('planeDialog').style.display,
  stage: sp.sketchPlaneStage() };
console.log(JSON.stringify(out));
"""


def _run_sketchplane_js(tmp_path):
    for name in ("sketchplane.js", "tool.js", "bus.js", "state.js", "settings.js"):
        shutil.copy(JS / name, tmp_path / name)
    (tmp_path / "api.js").write_text(_API_STUB, encoding="utf-8")
    (tmp_path / "viewport.js").write_text(_VIEWPORT_STUB, encoding="utf-8")
    (tmp_path / "sketcher.js").write_text(_SKETCHER_STUB, encoding="utf-8")
    (tmp_path / "boot.mjs").write_text(_BOOT, encoding="utf-8")
    r = subprocess.run([shutil.which("node"), str(tmp_path / "boot.mjs")],
                       capture_output=True, text=True, encoding="utf-8",
                       cwd=str(tempfile.gettempdir()))
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout.strip())


@pytest.mark.skipif(not shutil.which("node"), reason="node is not on PATH")
def test_the_shipped_offset_step_opens_the_sketch_at_the_offset(tmp_path):
    out = _run_sketchplane_js(tmp_path)
    o = out["plane_open"]
    assert o["panel"] == "block" and o["modal"] == "Sketch plane", o
    assert o["what"] == "the XY plane" and o["ghost"] and o["keyHandlers"] == 1, o
    assert o["arrowO"] == [1, 2, 0] and o["arrowN"] == [0, 0, 1], o    # the plan's frame
    assert o["stage"]["kind"] == "plane" and o["stage"]["offset"] == 0, o
    d = out["plane_drag"]
    assert d["opened"] == 0 and float(d["box"]) == 20.0 and d["ghostAt"] == 20.0, d
    t = out["plane_typed"]
    assert t["ghostAt"] == 20 and t["arrowA"] == 20, t
    k = out["plane_ok"]
    assert k["opened"] == [["plane", "XY", 20]], k
    assert k["modal"] is None and k["panel"] == "none", k
    assert k["arrow"] is None and k["ghost"] is None and k["retaken"] >= 1, k
    assert k["keyHandlers"] == 0 and k["stage"] is None, k


@pytest.mark.skipif(not shutil.which("node"), reason="node is not on PATH")
def test_the_shipped_offset_step_escape_face_and_document_change(tmp_path):
    out = _run_sketchplane_js(tmp_path)
    e = out["esc"]
    assert e["opened"] == 0 and e["modal"] is None and e["panel"] == "none", e
    assert e["keyHandlers"] == 0 and "cancelled" in e["said"], e
    f = out["face_open"]
    assert f["what"] == 'a face of "b"' and f["into"] == "negative = into the material", f
    assert f["loops"] == 1 and f["outer"] == 4 and f["arrowO"] == [0, 0, 10], f
    assert f["stage"]["kind"] == "face" and f["stage"]["owner"] == "b", f
    assert f["stage"]["intoSign"] == -1, f
    assert out["face_ok"] == {"opened": [["face", [0, 0, 10], -3]], "modal": None}, out["face_ok"]
    c = out["doc_changed"]
    assert c["modal"] is None and c["panel"] == "none" and c["stage"] is None, c
