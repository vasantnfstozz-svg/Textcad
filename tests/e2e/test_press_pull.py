"""E2E: Press Pull (LAUNCH-PLAN.md P4, specs/press-pull.md) — Fusion's router
button: the selection picks the command. The steps are REAL — a pixel click
on a face / an edge / a tree row, then the ribbon button — and the one
geometric claim (a 5 mm pull grows the plate by exactly its face area x 5) is
checked against the kernel's volume.
"""
import time

import httpx
import pytest

pytest.importorskip("playwright.sync_api")

# a 60 x 40 x 12 plate centred on the origin (blocks.plate): top face at z = +6
BUILD_BOX = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh, setView } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 60, depth: 40, thickness: 12 }, inputs: [] }, 'add');
  await loadMesh(true);
  setView('iso');
}
"""
# a solid cylinder r 20, 12 tall, centred on the origin: every side point is curved
BUILD_DISC = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh, setView } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'd', op: 'disc', params: { radius: 20, thickness: 12 }, inputs: [] }, 'add');
  await loadMesh(true);
  setView('front');
}
"""
# an unconsumed 30 x 20 rectangle sketch on XY
BUILD_SKETCH = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'sk1', op: 'sketch',
      params: { plane: 'XY', offset: 0,
                entities: [{ kind: 'rectangle', w: 30, h: 20, x: 0, y: 0, mode: 'add' }] },
      inputs: [] }, 'add');
  await loadMesh(true);
}
"""
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
TOP_PICKED = """
async () => {
  const { S } = await import('/static/js/state.js');
  return !!(S.pickedFace && S.pickedFace.normal && S.pickedFace.normal[2] > 0.9);
}
"""
CURVED_PICKED = "async () => !!(await import('/static/js/state.js')).S.pickedCurved"
EDGE_PICKED = "async () => !!(await import('/static/js/state.js')).S.pickedEdge"
MODAL = "async () => (await import('/static/js/state.js')).S.modalTool"
# the top rim's straight edges of body `b`, as the viewport drew them
TOP_EDGES = """
(body) => {
  const b = window.__vp.bodyObjsRaw().find(x => x.id === body);
  const zmax = Math.max(...b.data.edges.flatMap(e => e.points.map(p => p[2])));
  return b.data.edges.filter(e => e.type === 'LINE'
    && e.points.every(p => Math.abs(p[2] - zmax) < 1e-3)).map(e => e.id);
}
"""
PT = [10.0, 5.0, 6.0]          # a point on the plate's top face
BOX = 60 * 40 * 12             # 28800


def features(server):
    return httpx.get(f"{server}/api/doc", timeout=30).json()["features"]


def wait_op(server, op, timeout=20):
    """the first feature of that op once it has finished building"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        f = next((x for x in features(server) if x["op"] == op), None)
        if f and f["status"] in ("ok", "failed"):
            return f
        time.sleep(0.25)
    raise AssertionError(f"no finished {op} feature")


def click_world(page, pt):
    sp = page.evaluate(TO_SCREEN, pt)
    page.mouse.click(sp["x"], sp["y"])


def press(page):
    """the ribbon button, in the Modify tab where Fusion keeps it"""
    page.locator("button.tab", has_text="Modify").click()
    page.click("#ribbon .rbtn[title='press_pull']")


def chat(page):
    return page.locator("#chatLog").inner_text()


def wait_bodies(page, n):
    page.wait_for_function(f"() => window.__vp.bodyCount() === {n}", timeout=20000)
    page.wait_for_timeout(800)


# ------------------------------------------------------------------ journeys --

def test_a_flat_face_press_pull_is_extrude_in_face_mode(page, fresh_doc, server):
    """Click the top face, press Press Pull: the EXTRUDE panel opens in face
    mode with the honest zero and nothing built; a typed 5 grows the plate by
    exactly 60 x 40 x 5 as a Join; OK leaves one body."""
    page.evaluate(BUILD_BOX)
    wait_bodies(page, 1)
    click_world(page, PT)
    page.wait_for_function(TOP_PICKED, timeout=15000)
    press(page)
    page.wait_for_selector("#extrudeDialog", state="visible", timeout=15000)
    assert page.evaluate(MODAL) == "Extrude", "the panel is Extrude's, as Fusion's timeline says"
    assert "Extrude" in page.locator("#extrudeDialog > :first-child").inner_text()
    assert page.input_value("#exProfile") == "(selected face)"
    assert page.input_value("#exOp") == "join"
    assert page.input_value("#exDist") == "0"
    assert not any(f["op"] == "extrude_face" for f in features(server)), "opening builds nothing"
    page.fill("#exDist", "5")
    f = wait_op(server, "extrude_face")
    assert f["status"] == "ok", f
    assert f["params"]["amount"] == 5
    j = wait_op(server, "fuse")
    assert j["status"] == "ok" and j["volume"] == pytest.approx(BOX + 60 * 40 * 5, rel=1e-6), j
    page.click("#exOk")
    page.wait_for_selector("#extrudeDialog", state="hidden")
    page.wait_for_timeout(800)
    assert page.evaluate(MODAL) is None
    assert page.evaluate("() => window.__vp.bodyCount()") == 1
    assert page.errors == []


def test_a_selected_sketch_row_press_pull_is_extrude_on_that_profile(page, fresh_doc, server):
    """The tree is a selection surface: a sketch row selected, Press Pull opens
    Extrude on that profile with nothing built."""
    page.evaluate(BUILD_SKETCH)
    page.wait_for_selector("#tree .nrow", timeout=20000)
    page.wait_for_timeout(800)
    page.locator("#tree .nrow", has=page.locator(".nname", has_text="sk1")).first.click()
    page.wait_for_timeout(300)
    press(page)
    page.wait_for_selector("#extrudeDialog", state="visible", timeout=15000)
    assert page.evaluate(MODAL) == "Extrude"
    assert page.input_value("#exProfile") == "sk1"
    assert page.input_value("#exDist") == "0"
    assert not any(f["op"] == "extrude" for f in features(server)), "opening builds nothing"
    page.click("#exCancel")
    page.wait_for_selector("#extrudeDialog", state="hidden")
    assert page.errors == []


def test_an_edge_press_pull_is_fillet(page, fresh_doc, server):
    """Click a top edge, press Press Pull: the chat names the switch and the
    FILLET panel opens; no Extrude panel, nothing built."""
    page.evaluate(BUILD_BOX)
    wait_bodies(page, 1)
    idx = page.evaluate(TOP_EDGES, "b")[0]
    s = page.evaluate("([b, i]) => window.__vp.edgeScreen(b, i)", ["b", idx])
    assert s, "the top edge is off screen"
    page.mouse.click(s["x"], s["y"])
    page.wait_for_function(EDGE_PICKED, timeout=15000)
    press(page)
    page.wait_for_selector("#flDialog", state="visible", timeout=15000)
    assert page.evaluate(MODAL) == "Fillet"
    assert not page.is_visible("#extrudeDialog")
    assert "Press Pull on an edge is Fillet" in chat(page)
    assert all(f["op"] == "plate" for f in features(server)), "opening builds nothing"
    page.click("#flCancel")
    page.wait_for_selector("#flDialog", state="hidden")
    assert page.errors == []


def test_a_curved_face_press_pull_says_why_and_opens_nothing(page, fresh_doc, server):
    """Click the cylinder's side, press Press Pull: one sentence (Offset Face
    does not exist here), no panel, no lock, nothing built."""
    page.evaluate(BUILD_DISC)
    wait_bodies(page, 1)
    click_world(page, [0.0, -20.0, 0.0])          # the side, facing the front camera
    page.wait_for_function(CURVED_PICKED, timeout=15000)
    press(page)
    page.wait_for_timeout(600)
    assert "curved face would offset it" in chat(page)
    assert not page.is_visible("#extrudeDialog")
    assert not page.is_visible("#flDialog")
    assert page.evaluate(MODAL) is None
    assert [f["op"] for f in features(server)] == ["disc"]
    assert page.errors == []


def test_a_curved_face_press_pull_drops_the_pending_pick(page, fresh_doc, server):
    """Press Pull's curved branch RETURNS — so it must leave the state every
    other branch clears. A pick armed by an earlier button (Create Sketch's
    plane pick: no panel, so no modal lock, so the ribbon lets Press Pull
    through) is still waiting after the sentence, and the next click — the very
    click the sentence asks for — falls into THAT pick instead."""
    page.evaluate(BUILD_DISC)
    wait_bodies(page, 1)
    click_world(page, [0.0, -20.0, 0.0])          # the curved side
    page.wait_for_function(CURVED_PICKED, timeout=15000)
    page.locator("button.tab", has_text="Create").click()
    page.click("#ribbon .rbtn[title='Create Sketch']")   # arms a plane pick
    assert page.is_visible("#placeHint"), "the plane pick is armed"
    press(page)
    page.wait_for_timeout(600)
    assert "curved face would offset it" in chat(page)
    assert page.evaluate(MODAL) is None
    assert not page.is_visible("#placeHint"), \
        "the pending plane pick survived Press Pull's curved branch"
    # and the consequence: a click in the viewport must not land in the sketch
    # editor on an origin plane nobody asked for
    click_world(page, [35.0, 0.0, 0.0])           # empty space, on the XZ plane
    page.wait_for_timeout(800)
    assert not page.evaluate(
        "() => document.getElementById('ribbon').classList.contains('sketchctx')"), \
        "the next click opened the SKETCH EDITOR on a leftover plane pick"
    assert page.errors == []
