"""E2E: the user's REAL journey, end to end — not isolated steps.

User feedback (2026-08-04): "the test case has to test the feature we are
improving... simply drawing a t-washer won't help at all." This file replays
the exact reported workflow through the real UI entry points — ribbon button,
a REAL pixel click on the block's face, grid hovering, drawing, the Finish
button — and asserts the two things that were reported broken:

  1. while drawing, EVERY grid cell corner is recognized (visible pick box /
     hover lock), not just the origin;
  2. after finishing the face sketch and extruding it, the MAIN BODY must
     still be there — it used to vanish.
"""
import pytest

pytest.importorskip("playwright.sync_api")

BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh, setView } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 60, depth: 40, thickness: 20 },
      inputs: [] }, 'add');
  await loadMesh(true);
  setView('iso');
}
"""

# world point -> client pixel via the live camera (to click the REAL face)
TO_SCREEN = """
(w) => {
  const vp = window.__vp;
  const cv = document.querySelector('#viewer canvas');
  const r = cv.getBoundingClientRect();
  const V3 = vp.camera.position.constructor;
  const v = new V3(w[0], w[1], w[2]).project(vp.camera);
  return { x: r.left + (v.x + 1) / 2 * r.width,
           y: r.top + (1 - (v.y + 1) / 2) * r.height };
}
"""

IS_ACTIVE = """
async () => (await import('/static/js/sketch3d.js')).sketch3DActive()
"""
NOT_ACTIVE = """
async () => !(await import('/static/js/sketch3d.js')).sketch3DActive()
"""
TWEEN_DONE = "() => window.__vp.getControls().enabled === true"

HOVER = """
async (args) => {
  const [x, y, tol] = args;
  const { bus } = await import('/static/js/bus.js');
  bus.emit('sk3d-move', { x, y, tol, down: false });
  await new Promise(r => setTimeout(r, 120));
  const sk = await import('/static/js/sketcher.js');
  return sk.hoverInfo();
}
"""

CLICK = """
async (args) => {
  const [x, y, tol] = args;
  const { bus } = await import('/static/js/bus.js');
  bus.emit('sk3d-down', { x, y, tol }); bus.emit('sk3d-up', {});
  await new Promise(r => setTimeout(r, 120));
}
"""


@pytest.fixture()
def face_sketch_via_real_click(page, fresh_doc):
    """Create Sketch pressed in the ribbon, then a REAL pixel click on the
    block's top face — the entry point a user actually takes (a bus-emitted
    shortcut would bypass the face picker, which has had its own bug)."""
    page.evaluate(BUILD)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.wait_for_timeout(800)
    page.click("#ribbon .rbtn[title='Create Sketch']")
    page.wait_for_timeout(500)
    top = page.evaluate(TO_SCREEN, [5, 3, 10])       # a point on the TOP face
    page.mouse.click(top["x"], top["y"], button="left")
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.wait_for_timeout(200)
    return page


def test_grid_corners_are_recognized_while_drawing(face_sketch_via_real_click):
    page = face_sketch_via_real_click
    step = page.evaluate(
        "async () => (await import('/static/js/sketch3d.js')).gridStep()")
    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.setSketchTool('rectangle');
    }""")
    # hovering BETWEEN grid lines, away from any geometry: the cursor must
    # lock onto the nearest cell corner and say so (the Fusion pick box)
    h = page.evaluate(HOVER, [1.46 * step, 0.7 * step, 1.5])
    assert h["snap"] is None, h                       # no geometry nearby
    assert h["grid"] is not None, "grid corner not recognized"
    for v in (h["grid"]["x"], h["grid"]["y"]):
        assert v / step == pytest.approx(round(v / step), abs=1e-6), (h, step)
    # near the origin, the geometry snap must still OUTRANK the grid box
    h0 = page.evaluate(HOVER, [0.4, 0.3, 3.0])
    assert h0["snap"] and "origin" in h0["snap"]["label"], h0
    assert h0["grid"] is None, h0
    assert page.errors == []


def test_extruding_a_face_sketch_keeps_the_main_body(face_sketch_via_real_click):
    """The reported bug, replayed exactly: block -> sketch on its face ->
    draw -> Finish (real button) -> extrude the sketch -> BOTH bodies must
    be real, opaque solids in the scene."""
    page = face_sketch_via_real_click
    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.setSketchTool('circle');
    }""")
    page.evaluate(CLICK, [10, 10, 1.5])              # centre on a cell corner
    page.evaluate(CLICK, [20, 10, 1.5])              # radius point
    ents = page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      return sk.sketchEntities();
    }""")
    assert len(ents) == 1 and ents[0]["kind"] == "circle", ents

    page.click("#ribbon .rbtn[title='Finish Sketch']")
    page.wait_for_function(NOT_ACTIVE, timeout=15000)
    page.wait_for_timeout(600)
    doc = page.evaluate("async () => (await fetch('/api/doc')).json()")
    sk_feat = next(f for f in doc["features"] if f["op"] == "sketch_on_face")
    assert sk_feat["status"] == "ok", sk_feat

    page.evaluate("""async (skId) => {
      const { postJSON } = await import('/static/js/api.js');
      const { loadMesh } = await import('/static/js/viewport.js');
      await postJSON('/api/feature/add',
        { id: 'boss', op: 'extrude', params: { amount: 8 },
          inputs: [skId] }, 'extrude');
      await loadMesh(true);
    }""", sk_feat["id"])
    page.wait_for_timeout(800)

    assert page.evaluate("window.__vp.bodyCount()") == 2, \
        "the main body vanished after extruding the face sketch"
    info = page.evaluate("window.__vp.bodyInfo()")
    ids = sorted(x["id"] for x in info)
    assert ids == ["b", "boss"], info
    for x in info:                       # a ghosted body passes DOM checks
        assert x["opacity"] == 1 and not x["transparent"], info
    assert page.errors == []


# ---------------------------------------------------------------------------
# Reported 2026-08-04 (screenshots: dome + rectangle sketch on its flat top):
# "when I am selecting the surface the full circle surface is selecting, and
# the rectangle I can't select it, in order to extrude it ... when I am
# selecting the extruding, I can select the surface freely, it's MY choice —
# it should not automatically select and extrude the drawn sketch."
# ---------------------------------------------------------------------------

DRAW_RECT_ON_FACE = """
async () => {
  const sk = await import('/static/js/sketcher.js');
  const { bus } = await import('/static/js/bus.js');
  sk.setSketchTool('rectangle');
  bus.emit('sk3d-down', { x: -10, y: -10, tol: 1.5 }); bus.emit('sk3d-up', {});
  bus.emit('sk3d-down', { x: 10, y: 10, tol: 1.5 }); bus.emit('sk3d-up', {});
}
"""


@pytest.fixture()
def dome_with_rect_sketch(page, fresh_doc):
    """The user's scene: a dome (flat-topped cone) with a rectangle sketched
    on its circular top face, sketch finished."""
    page.evaluate("""async () => {
      const { postJSON } = await import('/static/js/api.js');
      const { loadMesh, setView } = await import('/static/js/viewport.js');
      await postJSON('/api/feature/add',
        { id: 'dome', op: 'cone',
          params: { bottom_radius: 40, top_radius: 25, height: 20 },
          inputs: [] }, 'add');
      await loadMesh(true);
      setView('iso');
    }""")
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.wait_for_timeout(500)
    # the cone is CENTERED on the origin: height 20 -> flat top at z=+10
    page.evaluate("""async () => {
      const { bus } = await import('/static/js/bus.js');
      bus.emit('sketch-on-face', { center: [0, 0, 10], normal: [0, 0, 1],
                                   body: 'dome' });
    }""")
    page.wait_for_function(IS_ACTIVE, timeout=15000)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.wait_for_timeout(200)
    page.evaluate(DRAW_RECT_ON_FACE)
    page.click("#ribbon .rbtn[title='Finish Sketch']")
    page.wait_for_function(NOT_ACTIVE, timeout=15000)
    page.wait_for_timeout(800)
    return page


def test_sketch_profile_is_pickable_over_the_face_below(dome_with_rect_sketch):
    """Clicking INSIDE the drawn rectangle must select the PROFILE, not the
    circular face it sits on (they are coplanar — the profile wins the tie)."""
    page = dome_with_rect_sketch
    page.evaluate("() => window.__vp.setPickMode(true)")     # picking on (default; explicit so the test cannot flip it off)                          # ◉ Select mode
    inside = page.evaluate(TO_SCREEN, [5, 5, 10])   # inside rect AND circle
    page.mouse.click(inside["x"], inside["y"], button="left")
    page.wait_for_timeout(300)
    picked = page.evaluate(
        "async () => (await import('/static/js/state.js')).S.pickedProfile")
    assert picked and picked["id"] == "sketch1", picked
    info = page.locator("#pickInfo").inner_text()
    assert "Sketch profile" in info, info
    # outside the rectangle but still on the circular top: the FACE is picked
    outside = page.evaluate(TO_SCREEN, [0, -18, 10])
    page.mouse.click(outside["x"], outside["y"], button="left")
    page.wait_for_timeout(300)
    picked = page.evaluate(
        "async () => (await import('/static/js/state.js')).S.pickedProfile")
    face = page.evaluate(
        "async () => (await import('/static/js/state.js')).S.pickedFace")
    assert picked is None and face, (picked, face)
    assert page.errors == []


def test_extrude_never_auto_selects_the_sketch(dome_with_rect_sketch):
    """Pressing Extrude with NOTHING selected must not create anything —
    it asks the user to pick. Clicking the rectangle then extrudes THAT
    profile, and both bodies remain."""
    page = dome_with_rect_sketch
    n0 = page.evaluate(
        "async () => (await (await fetch('/api/doc')).json()).features.length")
    page.click("#ribbon .rbtn[title='extrude']")
    page.wait_for_timeout(500)
    n1 = page.evaluate(
        "async () => (await (await fetch('/api/doc')).json()).features.length")
    assert n1 == n0, "Extrude auto-created a feature without the user choosing"
    assert page.locator("#extrudeDialog").is_hidden(), \
        "the panel opened before the user picked a profile"
    hint = page.locator("#placeHint")
    assert hint.is_visible() and "profile" in hint.inner_text(), \
        "no prompt telling the user to pick"

    inside = page.evaluate(TO_SCREEN, [5, 5, 10])   # the user CHOOSES the rect
    page.mouse.click(inside["x"], inside["y"], button="left")
    page.wait_for_timeout(700)
    assert page.locator("#extrudeDialog").is_visible()
    assert page.evaluate("document.getElementById('exProfile').value") \
        == "sketch1"
    # type a distance — the real create path (lazy until the user acts)
    page.evaluate("""() => {
      const d = document.getElementById('exDist');
      d.value = '6';
      d.dispatchEvent(new Event('input', { bubbles: true }));
    }""")
    page.wait_for_timeout(1500)
    page.click("#exOk")
    page.wait_for_timeout(800)
    doc = page.evaluate("async () => (await (await fetch('/api/doc')).json())")
    ex = [f for f in doc["features"] if f["op"] == "extrude"]
    assert len(ex) == 1 and ex[0]["inputs"] == ["sketch1"], ex
    assert page.evaluate("window.__vp.bodyCount()") == 2, \
        "extruding the picked profile lost a body"
    assert page.errors == []


# ---------------------------------------------------------------------------
# Reported 2026-08-04: "what if I want to cut in the body by extruding the
# sketch down — it has to make a cut" + "I am not getting the ghost box ...
# and the round thing (taper ring) also" for face-sketch extrudes, and the
# unproven Operation entries should be locked.
# ---------------------------------------------------------------------------

def test_cut_a_pocket_through_the_real_ui(face_sketch_via_real_click):
    """The full pocket journey: draw a circle on the block's top face, Finish,
    pick the profile, Extrude -> Cut. Choosing Cut must flip the direction
    INTO the body, the ghost + taper ring must exist for the face sketch, and
    the pocket's volume must be exactly plate − cylinder."""
    page = face_sketch_via_real_click
    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.setSketchTool('circle');
    }""")
    # r=5 centred at (10,5): safely INSIDE the 60x40 face — a circle touching
    # the face boundary makes a zero-thickness wall the kernel rightly refuses
    page.evaluate(CLICK, [10, 5, 1.5])               # centre
    page.evaluate(CLICK, [15, 5, 1.5])               # radius = 5
    page.click("#ribbon .rbtn[title='Finish Sketch']")
    page.wait_for_function(NOT_ACTIVE, timeout=15000)
    # the exit tween must FINISH before projecting world->pixels: a fixed
    # sleep raced it under load, the click landed off the profile, the pick
    # fell to the FACE and Cut (sketch-mode-only flip) silently didn't flip
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.wait_for_timeout(400)

    inside = page.evaluate(TO_SCREEN, [10, 5, 10])   # pick the circle profile
    page.evaluate("() => window.__vp.setPickMode(true)")     # picking on (default; explicit so the test cannot flip it off)
    page.mouse.click(inside["x"], inside["y"], button="left")
    page.wait_for_timeout(300)
    page.click("#ribbon .rbtn[title='extrude']")
    page.wait_for_function("() => document.getElementById('extrudeDialog')"
                           ".style.display === 'block'", timeout=10000)
    # the reported gap: face-sketch extrudes had NO ghost box and NO taper ring
    page.wait_for_function(
        "() => { const g = window.__vp.gizmos(); return g.arrow && g.ghost && g.ring; }",
        timeout=10000)
    # the unproven operation stays locked
    assert page.evaluate(
        "document.querySelector('#exOp option[value=intersect]').disabled")

    page.evaluate("""() => {
      const op = document.getElementById('exOp');
      op.value = 'cut';
      op.dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    page.wait_for_timeout(400)
    assert float(page.evaluate(
        "document.getElementById('exDist').value")) < 0, \
        "choosing Cut must point the extrude INTO the body"
    page.evaluate("""() => {
      const d = document.getElementById('exDist');
      d.value = '-6';
      d.dispatchEvent(new Event('input', { bubbles: true }));
    }""")
    page.wait_for_timeout(1800)
    page.click("#exOk")
    page.wait_for_timeout(1000)

    doc = page.evaluate("async () => (await (await fetch('/api/doc')).json())")
    cut = [f for f in doc["features"] if f["op"] == "cut"]
    assert len(cut) == 1 and cut[0]["status"] == "ok", cut
    import math
    expect = 60 * 40 * 20 - math.pi * 5 * 5 * 6
    assert cut[0]["volume"] == pytest.approx(expect, rel=1e-3), cut[0]
    assert page.evaluate("window.__vp.bodyCount()") == 1, \
        "a pocket cut must leave ONE body"
    assert page.errors == []
