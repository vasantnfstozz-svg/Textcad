"""E2E: the viewport is a Z-UP CAD world and every view can be orbited.

Why this exists (S1 of SKETCH-MODE-PLAN.md): the camera used to orbit Y-up
while build123d models, the ground workplane and the origin planes are all
Z-up, so the horizon rolled and nothing lined up. Two regressions are locked
in here:

  1. camera.up is world +Z — and sketch mode, which overrides the orbit axis
     with its plane's up, restores +Z on exit.
  2. No view preset parks ON the orbit pole. Parked there, up is parallel to
     the view direction: the camera basis is degenerate and OrbitControls
     clamps the polar angle, so the view cannot be orbited at all (measured
     0.07mm of camera movement on a full drag before the fix).

Runs its own uvicorn on a private port — never the dev server (several
processes CAN bind one port on Windows, and then responses come from whichever
bound last; see the debug-studio skill).
"""
import pytest

pytest.importorskip("playwright.sync_api")

# server / browser / page fixtures live in tests/e2e/conftest.py (shared so the
# whole e2e run needs one uvicorn and one chromium)

# OrbitControls has damping on, so the camera keeps easing for a while after a
# drag ends. Measuring straight away credits the NEXT drag with the previous
# one's leftover inertia — that showed up as "left-drag orbited 5.9mm" in sketch
# mode where left cannot orbit at all. Wait for the camera to come to rest first.
SETTLE = """
  const settle = async () => {
    let last = vp.camera.position.clone(), still = 0;
    for (let i = 0; i < 60 && still < 3; i++) {
      await new Promise(res => requestAnimationFrame(res));
      if (vp.camera.position.distanceTo(last) < 1e-4) still++; else still = 0;
      last = vp.camera.position.clone();
    }
  };
  await settle();
"""

# canvas drag with a chosen mouse button -> how far the camera moved (mm)
DRAG_JS = """
async (args) => {
  const [dx, dy, button] = args;
  const vp = window.__vp;
  const cv = document.querySelector('#viewer canvas');
  cv.setPointerCapture = () => {};        // a synthetic pointerId would throw
  cv.releasePointerCapture = () => {};
  const r = cv.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
""" + SETTLE + """
  const before = vp.camera.position.clone();
  const buttons = button === 2 ? 2 : 1;
  const ev = (t, x, y, down) => cv.dispatchEvent(new PointerEvent(t,
    { clientX: x, clientY: y, bubbles: true, pointerId: 1, isPrimary: true,
      button, buttons: down ? buttons : 0 }));
  ev('pointerdown', cx, cy, true);
  for (let i = 1; i <= 8; i++)
    ev('pointermove', cx + dx * i / 8, cy + dy * i / 8, true);
  ev('pointerup', cx + dx, cy + dy, false);
  await new Promise(res => setTimeout(res, 400));       // damping settles
  return vp.camera.position.distanceTo(before);
}
"""

# same drag, but reporting how far the ORBIT TARGET moved — pan slides the
# target, orbit leaves it put, so this tells the two apart
PAN_JS = """
async (args) => {
  const [dx, dy, button] = args;
  const vp = window.__vp;
  const cv = document.querySelector('#viewer canvas');
  cv.setPointerCapture = () => {};
  cv.releasePointerCapture = () => {};
  const r = cv.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
""" + SETTLE + """
  const before = vp.getControls().target.clone();
  const buttons = button === 2 ? 2 : (button === 1 ? 4 : 1);
  const ev = (t, x, y, down) => cv.dispatchEvent(new PointerEvent(t,
    { clientX: x, clientY: y, bubbles: true, pointerId: 1, isPrimary: true,
      button, buttons: down ? buttons : 0 }));
  ev('pointerdown', cx, cy, true);
  for (let i = 1; i <= 8; i++)
    ev('pointermove', cx + dx * i / 8, cy + dy * i / 8, true);
  ev('pointerup', cx + dx, cy + dy, false);
  await new Promise(res => setTimeout(res, 400));
  return vp.getControls().target.distanceTo(before);
}
"""

# degrees between the view direction and the orbit axis, folded to the nearest
# pole: ~0 means a degenerate basis / dead orbit
POLE_JS = """
() => {
  const vp = window.__vp;
  const dir = vp.getControls().target.clone()
                .sub(vp.camera.position).normalize();
  const up = vp.camera.up.clone().normalize();
  const a = Math.acos(Math.max(-1, Math.min(1, dir.dot(up)))) * 180 / Math.PI;
  return Math.min(a, 180 - a);
}
"""


def test_world_is_z_up(page):
    assert page.evaluate("window.__vp.camera.up.toArray()") == [0, 0, 1]
    assert page.errors == []


@pytest.mark.parametrize("view", ["iso", "top", "front"])
def test_view_presets_are_off_the_orbit_pole_and_can_orbit(page, view):
    page.evaluate(f"""async () => {{
      const vp = await import('/static/js/viewport.js'); vp.setView('{view}');
    }}""")
    page.wait_for_timeout(400)
    pole = page.evaluate(POLE_JS)
    assert pole > 1.0, f"{view} sits {pole:.2f}deg from the orbit pole"
    # away-from-pole must move; INTO the pole is legitimately clamped at top
    up_drag = page.evaluate(DRAG_JS, [70, -25, 0])
    page.evaluate(f"""async () => {{
      const vp = await import('/static/js/viewport.js'); vp.setView('{view}');
    }}""")
    page.wait_for_timeout(300)
    down_drag = page.evaluate(DRAG_JS, [70, 25, 0])
    assert max(up_drag, down_drag) > 1.0, (
        f"{view}: orbit dead (up {up_drag:.2f}mm, down {down_drag:.2f}mm)")
    assert page.errors == []


def test_navigation_mapping_is_the_same_in_both_tabs(page):
    """The tabs used to disagree about what each mouse button does (design:
    left orbit / middle dolly / right pan; sketch: left draw / middle pan /
    right orbit), so left-dragging in a sketch drew instead of rotating and
    read as "rotating is broken". RIGHT orbits and MIDDLE pans everywhere now;
    sketch mode only takes LEFT away. Design keeps left-drag orbit by choice.
    Pan is told from orbit by whether the ORBIT TARGET moved."""
    page.evaluate("""async () => {
      const vp = await import('/static/js/viewport.js'); vp.setView('iso');
    }""")
    page.wait_for_timeout(400)

    assert page.evaluate(DRAG_JS, [70, -25, 2]) > 1.0, "design: right must orbit"
    assert page.evaluate(PAN_JS, [70, -25, 2]) < 1.0, "design: right must not pan"
    assert page.evaluate(PAN_JS, [70, -25, 1]) > 1.0, "design: middle must pan"
    assert page.evaluate(DRAG_JS, [70, -25, 0]) > 1.0, "design keeps left orbit"

    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.openSketchEditor('XY');
      await new Promise(r => setTimeout(r, 900));
      sk.setSketchTool('rectangle');           // a draw tool is armed
    }""")
    page.wait_for_timeout(700)
    assert page.evaluate(DRAG_JS, [70, -25, 2]) > 1.0, "sketch: right must orbit"
    assert page.evaluate(PAN_JS, [70, -25, 1]) > 1.0, "sketch: middle must pan"
    assert page.evaluate(DRAG_JS, [70, -25, 0]) < 1.0, "sketch: left draws"
    assert page.errors == []


def test_shift_left_pans_in_both_tabs_and_never_draws(page):
    """Pan lives on the middle button, which is awkward on some mice, so
    Shift+left-drag pans too. OrbitControls reads mouseButtons at pointerdown,
    so the Shift keydown has to have flipped LEFT to PAN by then. In sketch
    mode the same gesture must NOT also drop a sketch point — sketch3d owns
    left-clicks and needs its own shiftKey guard."""
    page.evaluate("""async () => {
      const vp = await import('/static/js/viewport.js'); vp.setView('iso');
    }""")
    page.wait_for_timeout(400)

    page.keyboard.down("Shift")
    page.wait_for_timeout(100)
    assert page.evaluate(
        "async () => (await import('/static/js/viewport.js')).shiftPanActive()")
    assert page.evaluate(PAN_JS, [70, -25, 0]) > 1.0, "design: shift+left pans"
    page.keyboard.up("Shift")
    page.wait_for_timeout(150)
    # released: left goes back to orbiting, not panning
    assert page.evaluate(PAN_JS, [70, -25, 0]) < 1.0, "design: left pans again?"
    assert page.evaluate(DRAG_JS, [70, -25, 0]) > 1.0, "design: left lost orbit"

    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.openSketchEditor('XY');
      await new Promise(r => setTimeout(r, 900));
      sk.setSketchTool('circle');
    }""")
    page.wait_for_timeout(700)
    page.keyboard.down("Shift")
    page.wait_for_timeout(100)
    assert page.evaluate(PAN_JS, [70, -25, 0]) > 1.0, "sketch: shift+left pans"
    entities = page.evaluate(
        "document.querySelectorAll('#skEntities .skent').length")
    assert entities == 0, f"shift+left dropped {entities} sketch point(s)"
    page.keyboard.up("Shift")
    page.wait_for_timeout(150)
    assert page.errors == []


def test_sketch_mode_shows_the_navigation_legend(page):
    """The legend was grey 11px text between the coordinates and the Esc/Del
    keys and went unread — users left-dragged and gave up. It is its own chip
    now, and entering sketch mode also says it once in chat."""
    nav = page.locator("#sk3dBar .sk3dnav")
    assert not nav.is_visible()
    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.openSketchEditor('XY');
    }""")
    page.wait_for_timeout(1100)
    assert nav.is_visible()
    text = " ".join(nav.inner_text().split())
    assert "RIGHT-drag" in text and "orbit" in text, text
    assert "middle" in text and "pan" in text, text
    chat = page.locator("#chatLog").inner_text()
    assert "RIGHT-drag orbits" in chat, chat[-200:]
    assert page.errors == []


def test_sketch_mode_orbits_and_restores_world_up(page):
    """Sketching on XY sets the orbit axis to that plane's up (+Y), so the exit
    path is genuinely exercised — an XZ sketch's up is +Z and would pass even
    if nothing were restored. RIGHT-drag must orbit while a draw tool is armed
    (LEFT draws), which is the whole point of in-viewport sketching."""
    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.openSketchEditor('XY');
    }""")
    page.wait_for_timeout(1200)
    assert page.evaluate(
        "async () => (await import('/static/js/sketch3d.js')).sketch3DActive()")
    assert page.evaluate("window.__vp.camera.up.toArray()") == [0, 1, 0]

    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.setSketchTool('circle');
    }""")
    page.wait_for_timeout(200)
    assert page.evaluate(POLE_JS) > 1.0
    assert page.evaluate(DRAG_JS, [70, -25, 2]) > 1.0, "right-drag must orbit"

    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.cancelSketch();                    // nothing drawn -> no confirm()
    }""")
    page.wait_for_timeout(800)
    assert not page.evaluate(
        "async () => (await import('/static/js/sketch3d.js')).sketch3DActive()")
    assert page.evaluate("window.__vp.camera.up.toArray()") == [0, 0, 1]
    assert page.evaluate(DRAG_JS, [70, -25, 0]) > 1.0, "orbit dead after exit"
    assert page.errors == []
