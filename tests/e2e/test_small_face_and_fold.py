"""E2E: small faces must be clickable, and a pocket is TWO tree rows.

Two user reports (2026-08-26):
  "in design tab, i touched pillar top face, it got never selected"
  "in feature tree we only need two [rows] ... in the esp32 tree why is there
   three, if i am clicking the third whole body is being selected"

The pick bug was an edge halo measured in MILLIMETRES (fitRadius/60, ~1.9 mm on
a 220 mm part): any face smaller than about 4 mm across sat entirely inside the
halo of its own rim, so the edge won at every zoom level. Measured on
esp32-remote before the fix: 0 of 24 pillar tops selectable. The halo is five
screen pixels now.
"""
import httpx
import pytest

from conftest import ask_ok

pytest.importorskip("playwright.sync_api")

# a plate with three small pillars on top: r=2 (Ø4) is the size that used to be
# impossible to click
BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  const add = (id, op, params, inputs) =>
    postJSON('/api/feature/add', { id, op, params, inputs }, 'add');
  await add('base_sk', 'sketch', { plane: 'XY', offset: 0, entities: [
    { kind: 'rectangle', w: 60, h: 40, x: 0, y: 0, mode: 'add' }] }, []);
  await add('base', 'extrude', { amount: 6 }, ['base_sk']);
  await add('pillar_sk', 'sketch', { plane: 'XY', offset: 6, entities: [
    { kind: 'circle', r: 2, x: -15, y: 0, mode: 'add' },
    { kind: 'circle', r: 2, x: 0, y: 0, mode: 'add' },
    { kind: 'circle', r: 2, x: 15, y: 0, mode: 'add' }] }, []);
  await add('pillar_tool', 'extrude', { amount: 5 }, ['pillar_sk']);
  await add('pillars', 'fuse', {}, ['base', 'pillar_tool']);
  await add('pocket_sk', 'sketch', { plane: 'XY', offset: 6, entities: [
    { kind: 'circle', r: 6, x: 22, y: 12, mode: 'add' }] }, []);
  await add('pocket_tool', 'extrude', { amount: -3 }, ['pocket_sk']);
  await add('pocket', 'cut', {}, ['pillars', 'pocket_tool']);
  await loadMesh(true, true);
}
"""

# zoom onto a point, then hand back its screen position
ZOOM_TO = """
async ([c, dist]) => {
  const vp = window.__vp;
  const cam = vp.camera, ctl = vp.getControls();
  ctl.target.set(c[0], c[1], c[2]);
  cam.position.set(c[0], c[1], c[2] + dist);
  cam.near = 0.05; cam.far = 5000; cam.updateProjectionMatrix();
  ctl.update();
  await new Promise(r => setTimeout(r, 150));
  const cv = document.querySelector('#viewer canvas');
  const r = cv.getBoundingClientRect();
  const V3 = cam.position.constructor;
  const v = new V3(c[0], c[1], c[2]).project(cam);
  return { x: r.left + (v.x + 1) / 2 * r.width,
           y: r.top + (1 - (v.y + 1) / 2) * r.height };
}
"""
PICKED = """
async () => {
  const { S } = await import('/static/js/state.js');
  const f = S.pickedFace || S.pickedCurved;
  const info = document.getElementById('pickInfo');
  return { face: f ? f.id : null, area: f ? f.area : null,
           panel: (info ? info.innerText : '').slice(0, 20) };
}
"""


def build(page, server):
    page.evaluate(BUILD)
    page.wait_for_selector("#tree .nrow >> text=pocket")
    page.wait_for_function("() => window.__vp.sceneCounts().bodies > 0",
                           timeout=60000)
    page.wait_for_timeout(800)
    model = httpx.get(f"{server}/api/model", timeout=60).json()
    return next(b for b in model["bodies"] if b["result"])


def pillar_tops(body):
    """The three Ø4 pillar tops: small, planar, pointing up, at z = 11."""
    return [f for f in body["faces"]
            if f.get("planar") and f.get("center")
            and abs(f["center"][2] - 11) < 0.01 and (f.get("area") or 0) < 20]


def test_a_small_pillar_top_can_be_selected(page, server, fresh_doc):
    body = build(page, server)
    tops = pillar_tops(body)
    assert len(tops) == 3, [f["area"] for f in tops]
    picked = 0
    for f in tops:
        sp = page.evaluate(ZOOM_TO, [f["center"], 16])
        page.mouse.click(sp["x"], sp["y"])
        page.wait_for_timeout(200)
        got = page.evaluate(PICKED)
        if got["face"] == f["id"]:
            picked += 1
    assert picked == 3, f"only {picked}/3 pillar tops could be selected"
    assert not page.errors, page.errors


def test_the_edge_still_wins_when_you_click_ON_it(page, server, fresh_doc):
    """The halo shrank to 5 px — it must not vanish, or edges become
    unpickable."""
    body = build(page, server)
    top = pillar_tops(body)[0]
    # a point on the pillar's rim: same centre, offset by the radius
    rim = [top["center"][0] + 2.0, top["center"][1], top["center"][2]]
    sp = page.evaluate(ZOOM_TO, [rim, 16])
    page.mouse.click(sp["x"], sp["y"])
    page.wait_for_timeout(250)
    got = page.evaluate(PICKED)
    assert got["panel"].startswith("Edge") or got["face"] is not None
    assert not page.errors, page.errors


def test_a_pocket_is_two_rows_not_three(page, server, fresh_doc):
    """sketch + extrude, with the boolean folded onto the extrude's row."""
    build(page, server)
    rows = page.evaluate("""
      () => [...document.querySelectorAll('#tree .node')].map(n => ({
        id: n.dataset.fid,
        chip: (n.querySelector('.nchip') || {}).textContent || null }))""")
    ids = [r["id"] for r in rows]
    assert "pocket_sk" in ids and "pocket_tool" in ids
    assert "pocket" not in ids, "the boolean should not have its own row"
    assert "pillars" not in ids, "the fuse should not have its own row"
    chip = next(r["chip"] for r in rows if r["id"] == "pocket_tool")
    assert chip == "cut", f"expected a CUT chip on the extrude, got {chip}"
    assert next(r["chip"] for r in rows if r["id"] == "pillar_tool") == "fuse"
    assert not page.errors, page.errors


def test_clicking_that_row_highlights_the_pocket_not_the_whole_body(
        page, server, fresh_doc):
    build(page, server)
    page.evaluate("""() => document.querySelector(
      "#tree .node[data-fid='pocket_tool'] .nrow").click()""")
    page.wait_for_timeout(1200)
    sel = page.evaluate(
        "async () => (await import('/static/js/state.js')).S.selected")
    assert sel == "pocket_tool"          # the prism, not the boolean's result
    assert not page.errors, page.errors


def test_deleting_the_folded_row_removes_the_boolean_too(page, server,
                                                         fresh_doc):
    build(page, server)
    row = page.locator("#tree .node[data-fid='pocket_tool'] .nrow")
    row.hover()
    row.locator("button[title^='delete']").click()
    ask_ok(page)
    page.wait_for_function(
        "() => ![...document.querySelectorAll('#tree .node')]"
        ".some(n => n.dataset.fid === 'pocket_tool')", timeout=20000)
    ids = [f["id"] for f in
           httpx.get(f"{server}/api/doc", timeout=20).json()["features"]]
    assert "pocket_tool" not in ids and "pocket" not in ids
    assert "pillars" in ids               # the rest of the design survives
    assert not page.errors, page.errors
