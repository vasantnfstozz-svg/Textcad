"""E2E: the grids are ADAPTIVE, Fusion-style — sketch plane AND ground plane.

Reported (2026-08-03/04): "when I am zooming in, there will always be small
boxes, but after a certain point it will end · the starting point should
recognize all box edges, not only the origin · zooming out must NOT keep
growing the plane — there is a limit, and when the design goes beyond the
plane it should automatically get bigger to the next size · the design tab
should have the same adaptive grid."

Locked in:
  1. zooming IN subdivides the cells (1-2-5 ladder) down to a floor of
     gridMm/10 — past that, subdivision STOPS (cells just get bigger);
  2. clicks snap to the visible grid corners, not just the origin;
  3. the plane is a FINITE plate: zooming out shows its edge instead of
     growing it, and it jumps to the next ladder size only when the sketch
     CONTENT outgrows it;
  4. the design tab's ground grid follows the same rules.
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

# same wheel gesture, reporting the DESIGN tab's ground grid instead
WHEEL_GROUND = """
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
  return window.__vp.groundGridInfo();
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


def test_plane_is_finite_when_zooming_out(sketch):
    """Zooming out must show the plate's EDGE, not grow it: the covered area
    never exceeds the plane bounds, and the plane size itself only reacts to
    content, never to the camera."""
    page = sketch
    g0 = page.evaluate(GRID_INFO)
    g = page.evaluate(WHEEL, [80, 120])         # zoom OUT hard
    assert g["half"] == g0["half"], (g0, g)     # camera never grows the plate
    assert g["clip"]["maxX"] - g["clip"]["minX"] <= 2 * g["half"] + 1e-6, g
    assert g["clip"]["maxY"] - g["clip"]["minY"] <= 2 * g["half"] + 1e-6, g
    assert g["step"] <= g["half"] / 2, g        # a plate always shows cells
    assert page.errors == []


def test_plane_grows_to_the_next_size_when_content_exceeds_it(sketch):
    """Drawing past the plate's edge must bump the plane to the NEXT ladder
    size ('automatically bigger to the next size'), like Fusion."""
    page = sketch
    half0 = page.evaluate(GRID_INFO)["half"]
    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.setSketchTool('rectangle');
    }""")
    page.evaluate(ACT, [0, 0, 1.5])                       # corner at the origin
    page.evaluate(ACT, [half0 * 1.05, half0 * 0.2, 1.5])  # corner PAST the edge
    g = page.evaluate(GRID_INFO)
    assert g["half"] > half0, (half0, g)
    ents = page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      return sk.sketchEntities();
    }""")
    assert len(ents) == 1, ents
    assert page.errors == []


def test_ground_grid_is_adaptive_and_finite(page, fresh_doc):
    """The DESIGN tab's ground plane follows the same rules: cells subdivide
    on zoom (with the same floor), and the plate is a finite, model-sized
    square that zooming out cannot grow."""
    page.evaluate("""async () => {
      const { postJSON } = await import('/static/js/api.js');
      const { loadMesh } = await import('/static/js/viewport.js');
      await postJSON('/api/feature/add',
        { id: 'b', op: 'plate', params: { width: 60, depth: 40, thickness: 20 },
          inputs: [] }, 'add');
      await loadMesh(true);
    }""")
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.wait_for_timeout(600)
    g0 = page.evaluate("window.__vp.groundGridInfo()")
    assert g0 and g0["step"] >= 2, g0
    g_in = page.evaluate(WHEEL_GROUND, [40, -120])        # zoom IN
    assert g_in["step"] < g0["step"], (g0, g_in)
    assert g_in["step"] == pytest.approx(1.0), g_in       # same gridMm/10 floor
    g_out = page.evaluate(WHEEL_GROUND, [100, 120])       # zoom OUT hard
    assert g_out["half"] == g0["half"], (g0, g_out)       # finite plate
    assert (g_out["clip"]["maxX"] - g_out["clip"]["minX"]
            <= 2 * g_out["half"] + 1e-6), g_out
    assert page.errors == []
