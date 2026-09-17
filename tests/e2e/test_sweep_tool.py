"""E2E: Sweep — the first Tier 2 tool (LAUNCH-PLAN.md §4, specs/sweep.md).
Real clicks, and every geometric claim checked against the kernel: the built
volume against area × length (Pappus), the arrow's home against the profile.
"""
import math

import httpx
import pytest

pytest.importorskip("playwright.sync_api")

R = 3.0
A = math.pi * R * R
L_PATH = 40.0        # up 20, then 20 across

# a plate, a circle on its top face (centre (5, 0, 6)) and a PATH sketch on
# XZ placed so it starts at that centre: up 20, across 20
BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh, setView } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 60, depth: 40, thickness: 12 }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'p', op: 'sketch_on_face',
      params: { face: 'top', offset: 0,
                entities: [{ kind: 'circle', r: 3, x: 5, y: 0, mode: 'add' }] },
      inputs: ['b'] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'rail', op: 'sketch',
      params: { plane: 'XZ', offset: 0,
                entities: [{ kind: 'path', closed: false, x: 5, y: 6, start: [0, 0],
                             segments: [{ type: 'line', to: [0, 20] },
                                        { type: 'line', to: [20, 20] }] }] },
      inputs: [] }, 'add');
  await loadMesh(true);
  setView('iso');
}
"""
# the same, without any path sketch
BUILD_NO_PATH = BUILD.split("  await postJSON('/api/feature/add',\n    { id: 'rail'")[0] + \
    "  await loadMesh(true);\n  setView('iso');\n}\n"
assert "rail" not in BUILD_NO_PATH


def row(page, fid):
    return page.locator("#tree .nrow", has=page.locator(".nname", has_text=fid))


def press_sweep(page, fid):
    r = row(page, fid)
    r.hover()
    r.locator("button[title^='sweep this sketch']").click()


def open_sweep(page, fid):
    press_sweep(page, fid)
    page.wait_for_selector("#sweepDialog", state="visible", timeout=15000)


def feature(server, fid):
    doc = httpx.get(f"{server}/api/doc", timeout=30).json()
    return next((f for f in doc["features"] if f["id"] == fid), None)


def wait_feature(page, server, fid, timeout_ms=15000):
    for _ in range(timeout_ms // 200):
        f = feature(server, fid)
        if f and f["status"] in ("ok", "failed"):
            return f
        page.wait_for_timeout(200)
    raise AssertionError(f"{fid} never built")


def chat_text(page):
    return page.locator("#chatLog").inner_text() if page.locator("#chatLog").count() \
        else page.locator("body").inner_text()


def drag_arrow(page, pixels=70):
    """Grab the arrow at its middle and drag it ALONG the way it points."""
    ax = page.evaluate("""async () => {
      const vp = await import('/static/js/viewport.js');
      return vp.extrudeArrowAxisScreen();
    }""")
    bx, by = ax["base"]["x"], ax["base"]["y"]
    tx, ty = ax["tip"]["x"], ax["tip"]["y"]
    L = ((tx - bx) ** 2 + (ty - by) ** 2) ** 0.5
    ux, uy = (tx - bx) / L, (ty - by) / L
    gx, gy = bx + ux * L * 0.5, by + uy * L * 0.5
    page.mouse.move(gx, gy)
    page.mouse.down()
    for i in range(1, 6):
        page.mouse.move(gx + ux * pixels * i / 5, gy + uy * pixels * i / 5)
        page.wait_for_timeout(30)
    return gx + ux * pixels, gy + uy * pixels


def setup(page, build):
    page.evaluate(build)
    page.wait_for_timeout(1500)


def test_open_from_the_tree_row_and_drag_the_arrow(page, fresh_doc, server):
    """Honest zero, the gold path and the arrow on the profile, the ghost
    while dragging, one verified solid on release whose volume is A × d."""
    setup(page, BUILD)
    doc = httpx.get(f"{server}/api/doc", timeout=30).json()
    flags = {f["id"]: f["path_sketch"] for f in doc["features"]}
    assert flags == {"b": False, "p": False, "rail": True}, flags
    assert row(page, "rail").locator("button[title^='extrude this sketch']").count() == 0, \
        "a path sketch offers no pull buttons"
    open_sweep(page, "p")
    assert page.input_value("#swDist") == "0"
    assert not page.is_checked("#swFull")
    assert page.eval_on_selector("#swPath", "el => el.value") == "rail"
    g = page.evaluate("() => window.__vp.gizmos()")
    assert g["path"] and g["arrow"] and not g["sweep"], g
    assert page.evaluate("() => window.__vp.bodyCount()") == 1, "opening builds nothing"
    assert feature(server, "sweep1") is None

    drag_arrow(page, 60)
    assert page.evaluate("() => window.__vp.gizmos()")["sweep"], "the ghost follows the drag"
    ghost = page.evaluate("async () => (await import('/static/js/viewport.js')).sweepGhostInfo()")
    assert ghost and ghost["triangles"] > 100, ghost
    page.mouse.up()
    f = wait_feature(page, server, "sweep1")
    assert f["status"] == "ok", f["problems"]
    d = f["params"]["distance"]
    assert 0 < d <= L_PATH, d
    assert f["volume"] == pytest.approx(A * d, rel=2e-3), (f["volume"], d)
    assert float(page.input_value("#swDist")) == pytest.approx(d, abs=0.11)
    assert not page.evaluate("() => window.__vp.gizmos()")["sweep"], "the solid replaced the ghost"
    assert not page.errors, page.errors


def test_whole_path_ok_then_edit_and_cancel(page, fresh_doc, server):
    setup(page, BUILD)
    open_sweep(page, "p")
    page.wait_for_timeout(800)
    page.check("#swFull")
    f = wait_feature(page, server, "sweep1")
    assert f["status"] == "ok", f["problems"]
    assert f["params"]["full"] is True and f["params"]["path"] == "rail"
    assert f["volume"] == pytest.approx(A * L_PATH, rel=1e-4)
    assert float(page.input_value("#swDist")) == pytest.approx(L_PATH, abs=0.01)
    assert page.is_disabled("#swDist")
    page.click("#swOk")
    page.wait_for_selector("#sweepDialog", state="hidden", timeout=15000)
    page.wait_for_timeout(500)
    assert "Sweep created" in chat_text(page)
    doc = httpx.get(f"{server}/api/doc", timeout=30).json()
    assert doc["bodies"] == 2, "New body: the plate and the swept tube"

    row(page, "sweep1").dblclick()
    page.wait_for_selector("#sweepDialog", state="visible", timeout=15000)
    page.wait_for_timeout(800)
    assert page.is_checked("#swFull")
    assert page.eval_on_selector("#swPath", "el => el.value") == "rail"
    assert page.evaluate("() => window.__vp.gizmos()")["path"]
    page.click("#swCancel")
    page.wait_for_selector("#sweepDialog", state="hidden", timeout=15000)
    page.wait_for_timeout(500)
    f2 = feature(server, "sweep1")
    assert f2["params"] == f["params"] and f2["volume"] == f["volume"]
    assert not page.errors, page.errors


def test_without_a_path_sketch_the_tool_says_what_to_draw(page, fresh_doc, server):
    setup(page, BUILD_NO_PATH)
    press_sweep(page, "p")
    page.wait_for_timeout(1200)
    assert not page.is_visible("#sweepDialog")
    assert "Path tool" in chat_text(page)
    assert feature(server, "sweep1") is None
    assert not page.errors, page.errors


def test_the_path_tool_draws_an_open_chain(page, fresh_doc, server):
    """The sketch ribbon's Path tool: three clicks and a double-click leave
    the chain OPEN (`closed: false`); finishing the sketch makes a path sketch
    the server flags as one."""
    page.evaluate("""async () => {
      const sk = await import('/static/js/sketcher.js');
      sk.openSketchEditor('XZ');
      await new Promise(r => setTimeout(r, 900));
      sk.setSketchTool('openpath');
    }""")
    click = """
    async (args) => {
      const [x, y] = args;
      const { bus } = await import('/static/js/bus.js');
      bus.emit('sk3d-move', { x, y, tol: 1, down: false });
      bus.emit('sk3d-down', { x, y, tol: 1 }); bus.emit('sk3d-up', {});
      await new Promise(r => setTimeout(r, 120));
    }
    """
    for pt in ([0, 0], [0, 20], [20, 20]):
        page.evaluate(click, pt)
    page.evaluate("""async () => {
      const { bus } = await import('/static/js/bus.js');
      bus.emit('sk3d-dbl', {});
      await new Promise(r => setTimeout(r, 150));
    }""")
    ents = page.evaluate("async () => (await import('/static/js/sketcher.js')).sketchEntities()")
    assert len(ents) == 1 and ents[0]["kind"] == "path" and ents[0]["closed"] is False, ents
    assert len(ents[0]["segments"]) == 2, ents[0]
    page.evaluate("async () => (await import('/static/js/sketcher.js')).finishSketch()")
    page.wait_for_timeout(1500)
    doc = httpx.get(f"{server}/api/doc", timeout=30).json()
    sk = [f for f in doc["features"] if f["op"] == "sketch"]
    assert len(sk) == 1 and sk[0]["status"] == "ok" and sk[0]["path_sketch"] is True, sk
    assert not page.errors, page.errors
