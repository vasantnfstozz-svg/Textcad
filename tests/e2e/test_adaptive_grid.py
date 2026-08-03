"""E2E: the sketch grid is ADAPTIVE, Fusion-style.

Reported (2026-08-03, after S4): "when I am zooming in, there will always be
small boxes, but after a certain point it will end · the starting point should
recognize all box edges, not only the origin · when I am drawing big boxes the
plane should extend."

Locked in:
  1. zooming IN subdivides the cells (1-2-5 ladder) down to a floor of
     gridMm/10 — past that, subdivision STOPS (cells just get bigger);
  2. clicks snap to the visible grid corners, not just the origin;
  3. the grid follows the view when panning — the plane never ends.
"""
import pytest

pytest.importorskip("playwright.sync_api")

OPEN_SKETCH = """
async () => {
  const sk = await import('/static/js/sketcher.js');
  sk.openSketchEditor('XY');
}
"""

GRID_INFO = """
async () => (await import('/static/js/sketch3d.js')).gridInfo()
"""

# real wheel events at the canvas centre; OrbitControls dollies -> the
# 'view-changed' bus event refits the grid
WHEEL = """
async (args) => {
  const [ticks, deltaY] = args;
  const cv = document.querySelector('#viewer canvas');
  const r = cv.getBoundingClientRect();
  for (let i = 0; i < ticks; i++) {
    cv.dispatchEvent(new WheelEvent('wheel',
      { clientX: r.left + r.width / 2, clientY: r.top + r.height / 2,
        deltaY, bubbles: true, cancelable: true }));
    await new Promise(res => setTimeout(res, 5));
  }
  await new Promise(res => setTimeout(res, 300));
  return (await import('/static/js/sketch3d.js')).gridInfo();
}
"""

# middle-button drag = pan (the app-wide mapping)
PAN = """
async (args) => {
  const [dx, dy] = args;
  const cv = document.querySelector('#viewer canvas');
  cv.setPointerCapture = () => {};
  cv.releasePointerCapture = () => {};
  const r = cv.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const ev = (t, x, y, down) => cv.dispatchEvent(new PointerEvent(t,
    { clientX: x, clientY: y, bubbles: true, pointerId: 3, isPrimary: true,
      button: 1, buttons: down ? 4 : 0 }));
  ev('pointerdown', cx, cy, true);
  for (let i = 1; i <= 8; i++)
    ev('pointermove', cx + dx * i / 8, cy + dy * i / 8, true);
  ev('pointerup', cx + dx, cy + dy, false);
  await new Promise(res => setTimeout(res, 500));
  return (await import('/static/js/sketch3d.js')).gridInfo();
}
"""

# where the viewport centre currently sits on the sketch plane (world == plane
# local for an XY sketch at offset 0)
VIEW_CENTRE = """
async () => {
  const THREE = await import('three');
  const vp = window.__vp;
  const cv = document.querySelector('#viewer canvas');
  const ray = new THREE.Raycaster();
  ray.setFromCamera(new THREE.Vector2(0, 0), vp.camera);
  const hit = new THREE.Vector3();
  ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 0, 1), 0), hit);
  return { x: hit.x, y: hit.y };
}
"""

ACT = """
async (args) => {
  const [x, y, tol] = args;
  const { bus } = await import('/static/js/bus.js');
  bus.emit('sk3d-down', { x, y, tol }); bus.emit('sk3d-up', {});
  await new Promise(r => setTimeout(r, 100));
}
"""

# "the enter-tween has landed": entering sketch mode synchronously starts a
# camera tween that DISABLES OrbitControls and re-enables them only after the
# tween ends and the grid is refit — the exact wait signal (a fixed timeout or
# camera-stillness check races the tween's first frame; both flaked for real)
TWEEN_DONE = "() => window.__vp.getControls().enabled === true"


@pytest.fixture()
def sketch(page, fresh_doc):
    page.evaluate(OPEN_SKETCH)
    page.wait_for_function(TWEEN_DONE, timeout=15000)
    page.wait_for_timeout(200)
    return page


def test_zoom_subdivides_and_stops_at_the_floor(sketch):
    page = sketch
    g0 = page.evaluate(GRID_INFO)
    assert g0 and g0["step"] >= 2, g0           # default view: coarse cells
    g_in = page.evaluate(WHEEL, [40, -120])     # zoom IN hard
    assert g_in["step"] < g0["step"], (g0, g_in)
    assert g_in["step"] == pytest.approx(1.0), g_in   # the gridMm/10 floor
    g_more = page.evaluate(WHEEL, [25, -120])   # keep zooming: must NOT subdivide
    assert g_more["step"] == pytest.approx(1.0), g_more
    g_out = page.evaluate(WHEEL, [80, 120])     # zoom OUT: coarsens again
    assert g_out["step"] >= g0["step"], (g0, g_out)
    assert page.errors == []


def test_clicks_snap_to_the_grid_corners(sketch):
    """A click between grid lines lands EXACTLY on the nearest cell corner —
    every 'box edge' is a start point, not only the origin."""
    page = sketch
    step = page.evaluate(GRID_INFO)["step"]
    assert step > 1, step                       # must actually have room to snap
    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.setSketchTool('rectangle');
    }""")
    # clicks deliberately OFF-grid and far from the origin (tol 1.5 keeps the
    # origin/geometry snap out of play — this must be pure grid snapping)
    page.evaluate(ACT, [2.6 * step + 0.2 * step, 1.4 * step, 1.5])
    page.evaluate(ACT, [5.6 * step, 4.4 * step, 1.5])
    ents = page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      return sk.sketchEntities();
    }""")
    assert len(ents) == 1, ents
    e = ents[0]
    for corner in [e["x"] - e["w"] / 2, e["x"] + e["w"] / 2,
                   e["y"] - e["h"] / 2, e["y"] + e["h"] / 2]:
        assert corner / step == pytest.approx(round(corner / step), abs=1e-6), \
            (e, step)
    assert page.errors == []


def test_grid_follows_the_pan(sketch):
    """Panning away from the origin must bring the grid along — the plane
    never 'ends'. The grid re-centres on major multiples near the view."""
    page = sketch
    g0 = page.evaluate(GRID_INFO)
    g = None
    for _ in range(6):                          # pan hard to the left 6 times
        g = page.evaluate(PAN, [-350, 0])
    assert (g["cx"], g["cy"]) != (g0["cx"], g0["cy"]), (g0, g)
    centre = page.evaluate(VIEW_CENTRE)
    assert abs(g["cx"] - centre["x"]) <= g["size"] / 2 + g["major"], (g, centre)
    assert abs(g["cy"] - centre["y"]) <= g["size"] / 2 + g["major"], (g, centre)
    assert page.errors == []
