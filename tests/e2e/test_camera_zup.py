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
import threading
import time

import pytest

pw_api = pytest.importorskip("playwright.sync_api")

PORT = 8136
URL = f"http://127.0.0.1:{PORT}"

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


@pytest.fixture(scope="module")
def server():
    import uvicorn
    import studio
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    cfg = uvicorn.Config(studio.app, host="127.0.0.1", port=PORT,
                         log_level="warning")
    srv = uvicorn.Server(cfg)
    threading.Thread(target=srv.run, daemon=True).start()
    import httpx
    for _ in range(80):
        try:
            httpx.get(f"{URL}/api/doc", timeout=1)
            break
        except Exception:
            time.sleep(0.25)
    yield URL
    srv.should_exit = True


@pytest.fixture(scope="module")
def browser():
    """One browser for the whole module — launching chromium per test tripled
    the runtime (88s -> ~30s) for no isolation benefit; each test sets its own
    camera pose and gets a fresh PAGE."""
    with pw_api.sync_playwright() as pw:
        b = pw.chromium.launch()
        yield b
        b.close()


@pytest.fixture()
def page(server, browser):
    pg = browser.new_page(viewport={"width": 1200, "height": 800})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console",
          lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.goto(server)
    pg.wait_for_function("() => !!window.__vp", timeout=20000)
    pg.wait_for_timeout(1200)                      # first render
    pg.errors = errs
    yield pg
    pg.close()


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
