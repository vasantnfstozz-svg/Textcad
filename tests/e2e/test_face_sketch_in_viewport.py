"""E2E: face sketches live IN the viewport (S4 of SKETCH-MODE-PLAN.md).

Reported: "when I am selecting any face and sketch on that particular face,
it simply goes to a 2D flat sketch" — the docked 2D editor was a separate
screen: the model vanished and the view could not be orbited (fusion-parity
rule 9 violation). S4 deleted that editor. A face sketch is now the SAME
in-viewport mode as a plane sketch: the grid lands on the picked face, every
body stays visible, right-drag orbits while drawing, the face boundary shows
as snappable reference geometry, and Finish creates the sketch_on_face
feature ONLY (extrude/boss/pocket is Extrude's job, like Fusion).
"""
import pytest

pytest.importorskip("playwright.sync_api")

BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 60, depth: 40, thickness: 20 },
      inputs: [] }, 'add');
  await loadMesh(true);
}
"""

# the plate spans z -10..+10 -> top face center (0,0,10), normal +Z; picking
# it and creating a sketch is exactly what the viewport's face pick emits
OPEN_FACE_SKETCH = """
async () => {
  const { bus } = await import('/static/js/bus.js');
  bus.emit('sketch-on-face', { center: [0, 0, 10], normal: [0, 0, 1],
                               body: 'b' });
}
"""

IS_ACTIVE = """
async () => (await import('/static/js/sketch3d.js')).sketch3DActive()
"""
NOT_ACTIVE = """
async () => !(await import('/static/js/sketch3d.js')).sketch3DActive()
"""

# hover then click a plane-local point, exactly what a mouse does
ACT = """
async (args) => {
  const [x, y, tol, click] = args;
  const { bus } = await import('/static/js/bus.js');
  bus.emit('sk3d-move', { x, y, tol, down: false });
  await new Promise(r => setTimeout(r, 100));
  if (click) { bus.emit('sk3d-down', { x, y, tol }); bus.emit('sk3d-up', {}); }
  await new Promise(r => setTimeout(r, 120));
  const snap = document.getElementById('sk3dSnap');
  return { label: snap ? snap.textContent : '',
           coords: document.getElementById('sk3dCoords').textContent };
}
"""

# canvas drag with a chosen mouse button -> how far the camera moved (mm);
# waits out OrbitControls damping first (see test_camera_zup for why)
DRAG_JS = """
async (args) => {
  const [dx, dy, button] = args;
  const vp = window.__vp;
  const cv = document.querySelector('#viewer canvas');
  cv.setPointerCapture = () => {};
  cv.releasePointerCapture = () => {};
  const r = cv.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const settle = async () => {
    let last = vp.camera.position.clone(), still = 0;
    for (let i = 0; i < 60 && still < 3; i++) {
      await new Promise(res => requestAnimationFrame(res));
      if (vp.camera.position.distanceTo(last) < 1e-4) still++; else still = 0;
      last = vp.camera.position.clone();
    }
  };
  await settle();
  const before = vp.camera.position.clone();
  const buttons = button === 2 ? 2 : 1;
  const ev = (t, x, y, down) => cv.dispatchEvent(new PointerEvent(t,
    { clientX: x, clientY: y, bubbles: true, pointerId: 1, isPrimary: true,
      button, buttons: down ? buttons : 0 }));
  ev('pointerdown', cx, cy, true);
  for (let i = 1; i <= 8; i++)
    ev('pointermove', cx + dx * i / 8, cy + dy * i / 8, true);
  ev('pointerup', cx + dx, cy + dy, false);
  await new Promise(res => setTimeout(res, 400));
  return vp.camera.position.distanceTo(before);
}
"""

# "the enter-tween has fully landed": entering sketch mode synchronously
# starts a camera tween that DISABLES OrbitControls and re-enables them only
# after the tween ends and the grid is refit — so controls.enabled is the
# exact signal. (A camera-stillness settle is NOT: before the tween's first
# frame the camera is also still, and clicking then snaps against the
# pre-tween grid — a real flake we hit.)
TWEEN_DONE = "() => window.__vp.getControls().enabled === true"

DRAW_RECT = """
async (args) => {
  const [ax, ay, bx, by] = args;
  const sk = await import('/static/js/sketcher.js');
  const { bus } = await import('/static/js/bus.js');
  sk.setSketchTool('rectangle');
  bus.emit('sk3d-down', { x: ax, y: ay, tol: 2 }); bus.emit('sk3d-up', {});
  bus.emit('sk3d-down', { x: bx, y: by, tol: 2 }); bus.emit('sk3d-up', {});
  sk.setSketchTool('rectangle');            // toggle the tool back off
}
"""


@pytest.fixture()
def face_sketch(page, fresh_doc):
    page.evaluate(BUILD)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.evaluate(OPEN_FACE_SKETCH)
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.wait_for_timeout(200)
    return page


def test_face_sketch_is_in_viewport_with_model_visible(face_sketch):
    """The literal regression: face sketch != separate 2D screen. The body
    must still be a real solid in the scene, and right-drag must navigate
    (pan, per the 2026-08-31 mapping) while a draw tool is armed."""
    page = face_sketch
    assert page.evaluate("window.__vp.bodyCount()") == 1, "body vanished"
    assert page.evaluate("document.getElementById('sketchDialog')") is None
    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.setSketchTool('rectangle');
    }""")
    page.wait_for_timeout(200)
    moved = page.evaluate(DRAG_JS, [70, -25, 2])
    assert moved > 1.0, f"right-drag nav dead in a FACE sketch ({moved:.2f}mm)"
    assert page.errors == []


def test_face_outline_snaps_and_finish_creates_sketch_only(face_sketch):
    """The face boundary is reference geometry: a sloppy click near the top
    face's corner (30,20) must snap onto it exactly. Finish must create ONE
    sketch_on_face feature and NOTHING else — no auto extrude/boss/pocket."""
    page = face_sketch
    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.setSketchTool('rectangle');
    }""")
    page.wait_for_timeout(200)
    hover = page.evaluate(ACT, [28.4, 18.6, 3.0, True])   # near corner (30, 20)
    assert "30" in hover["coords"] and "20" in hover["coords"], hover
    page.evaluate(ACT, [0.4, 0.3, 3.0, True])             # near the origin
    ents = page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      return sk.sketchEntities();
    }""")
    assert len(ents) == 1, ents
    assert ents[0]["w"] == pytest.approx(30, abs=1e-6), ents[0]
    assert ents[0]["h"] == pytest.approx(20, abs=1e-6), ents[0]

    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.finishSketch();
    }""")
    page.wait_for_function(NOT_ACTIVE, timeout=15000)
    page.wait_for_timeout(600)
    doc = page.evaluate("async () => (await fetch('/api/doc')).json()")
    ops = [(f["id"], f["op"], f["status"]) for f in doc["features"]]
    face_sketches = [f for f in doc["features"] if f["op"] == "sketch_on_face"]
    assert len(face_sketches) == 1, ops
    assert face_sketches[0]["status"] == "ok", face_sketches[0]
    assert face_sketches[0]["inputs"] == ["b"], face_sketches[0]
    extras = [o for o in ops if o[1] in ("extrude", "fuse", "cut")]
    assert not extras, f"Finish auto-created solids (Fusion does not): {extras}"
    assert page.errors == []


def test_named_face_sketch_reopens_for_editing(page, fresh_doc):
    """User report 2026-08-31: 'even after selecting them, I can't edit those
    sketches.' Every AI-authored design names its face (face='top', the offset
    method) instead of storing a face_center — and the edit path posted
    face_center: undefined, which /api/face-outline 422'd before reading, so
    the editor silently never opened."""
    page.evaluate(BUILD)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.evaluate("""async () => {
      const { postJSON } = await import('/static/js/api.js');
      await postJSON('/api/feature/add', { id: 'named', op: 'sketch_on_face',
        params: { face: 'top', offset: -2.0,
                  entities: [{ kind: 'circle', mode: 'add', x: 5, y: 5, r: 4 }] },
        inputs: ['b'] }, 'add');
    }""")
    page.evaluate("""async () => {
      const { bus } = await import('/static/js/bus.js');
      const doc = await (await fetch('/api/doc')).json();
      bus.emit('edit-sketch', doc.features.find(x => x.id === 'named'));
    }""")
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    ents = page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      return sk.sketchEntities();
    }""")
    assert len(ents) == 1 and ents[0]["r"] == pytest.approx(4), ents
    assert page.errors == [], page.errors      # the 422 used to land here


def test_plane_pick_refuses_curved_face_out_loud(page, fresh_doc):
    """User report 2026-08-31: 'I draw it, I finish it, it simply vanishes.'
    Clicking a curved face during Create Sketch fell through to the origin
    quad hidden BEHIND the solid, so the sketch landed on a plane inside the
    body and the finished profile was swallowed. A curved-face click must now
    refuse out loud and keep waiting for a real pick."""
    page.evaluate("""async () => {
      const { postJSON } = await import('/static/js/api.js');
      const { loadMesh } = await import('/static/js/viewport.js');
      await postJSON('/api/feature/add',
        { id: 'd', op: 'disc', params: { radius: 20, thickness: 30 },
          inputs: [] }, 'add');
      await loadMesh(true);
    }""")
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.locator('#tabstrip button', has_text="Create").click()
    page.wait_for_timeout(200)
    page.locator('#ribbon button[title="Create Sketch"]').click()
    page.wait_for_timeout(400)
    # look flat-on from the front so the click surely lands on the barrel
    page.click("#vFront")
    page.wait_for_timeout(900)
    s = page.evaluate("(w) => window.__vp.worldToScreen(w)", [0, 0, 3])
    assert s, "disc axis not on screen"
    page.mouse.click(s["x"], s["y"])           # the CYLINDER side, dead centre
    page.wait_for_timeout(1200)
    assert not page.evaluate(IS_ACTIVE), \
        "a curved-face click silently started a sketch (on the plane behind!)"
    hint = page.text_content("#placeHint")
    assert "not flat" in hint, f"the refusal must say WHY: {hint!r}"
    # still waiting for a pick (not cancelled) — the hint stays visible
    assert page.locator("#placeHint").is_visible()
    doc = page.evaluate("async () => (await (await fetch('/api/doc')).json())")
    assert [f["op"] for f in doc["features"]] == ["disc"], doc["features"]


def test_face_sketch_reopens_in_viewport_for_editing(face_sketch):
    """The tree's edit action must route a committed face sketch back into
    the in-viewport mode with its entities loaded — not a dead end."""
    page = face_sketch
    # corners on multiples of EVERY plausible grid step (snap follows the
    # DISPLAYED grid, which can legitimately still be the coarse pre-tween one
    # on a slow run) — snap precision itself is locked in test_adaptive_grid
    page.evaluate(DRAW_RECT, [10, 10, 30, 20])            # a 20x10 rectangle
    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.finishSketch();
    }""")
    page.wait_for_function(NOT_ACTIVE, timeout=15000)
    page.wait_for_timeout(600)
    page.evaluate("""async () => {
      const { bus } = await import('/static/js/bus.js');
      const doc = await (await fetch('/api/doc')).json();
      const f = doc.features.find(x => x.op === 'sketch_on_face');
      bus.emit('edit-sketch', f);
    }""")
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.wait_for_timeout(200)
    ents = page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      return sk.sketchEntities();
    }""")
    assert len(ents) == 1, ents
    assert ents[0]["w"] == pytest.approx(20, abs=1e-6), ents[0]
    assert page.evaluate("window.__vp.bodyCount()") == 1
    assert page.errors == []
