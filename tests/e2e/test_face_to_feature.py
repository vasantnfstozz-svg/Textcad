"""E2E: click a surface, and the feature tree tells you what made it.

User request (2026-08-25): "when the design is loaded ... if i am selecting a
surface in the design, it should go to or highlight the feature tree, which
sketch is that and what extrude we have over there."

Driven through the real browser on a real pocket chain (the shape every
AI-authored design has): click the pocket floor, and the tree must reveal the
cut that made it while marking the sketch and the extrude behind it.

Clicking uses centroids of the body's OWN mesh triangles, not face centres: a
face centre is often not on its face at all (a ring's centroid sits in its hole,
a cylinder's on its axis), so clicking one hits whatever is behind it.
"""
import httpx
import pytest

pytest.importorskip("playwright.sync_api")

BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh, setView } = await import('/static/js/viewport.js');
  const add = (id, op, params, inputs) =>
    postJSON('/api/feature/add', { id, op, params, inputs }, 'add');
  await add('outline', 'sketch', { plane: 'XY', offset: 0, entities: [
    { kind: 'rectangle', w: 80, h: 60, x: 0, y: 0, mode: 'add' }] }, []);
  await add('body', 'extrude', { amount: 12 }, ['outline']);
  await add('pocket_sketch', 'sketch', { plane: 'XY', offset: 12, entities: [
    { kind: 'circle', r: 12, x: 15, y: 0, mode: 'add' }] }, []);
  await add('pocket_tool', 'extrude', { amount: -5 }, ['pocket_sketch']);
  await add('pocket', 'cut', {}, ['body', 'pocket_tool']);
  await loadMesh(true);
  setView('iso');
}
"""

# a point that really is ON face `fid`: the centroid of its biggest triangle
POINT_ON = """
([d, fid]) => {
  const pos = d.positions, idx = d.indices, fo = d.faceId;
  let best = -1, bc = null;
  for (let t = 0; t < idx.length; t += 3) {
    const a = idx[t], b = idx[t+1], c = idx[t+2];
    if (fo[a] !== fid || fo[b] !== fid || fo[c] !== fid) continue;
    const P = [[pos[a*3],pos[a*3+1],pos[a*3+2]],
               [pos[b*3],pos[b*3+1],pos[b*3+2]],
               [pos[c*3],pos[c*3+1],pos[c*3+2]]];
    const u = [P[1][0]-P[0][0], P[1][1]-P[0][1], P[1][2]-P[0][2]];
    const v = [P[2][0]-P[0][0], P[2][1]-P[0][1], P[2][2]-P[0][2]];
    const cr = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]];
    const ar = Math.hypot(cr[0], cr[1], cr[2]) / 2;
    if (ar > best) { best = ar;
      bc = [0,1,2].map(i => (P[0][i]+P[1][i]+P[2][i]) / 3); }
  }
  return bc;
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

PICKED = """
async () => {
  const { S } = await import('/static/js/state.js');
  const f = S.pickedFace || S.pickedCurved;
  return f ? f.id : null;
}
"""

STATE = """
() => ({
  revealed: (document.querySelector('#tree .node.fromface .nname') || {}).textContent || null,
  chain: [...document.querySelectorAll('#tree .node.fromface-rel .nname')]
           .map(e => e.textContent),
  panel: (document.querySelector('#pickInfo .provchain') || {}).innerText || null,
})
"""


def build(page, server):
    page.evaluate(BUILD)
    page.wait_for_selector("#tree .nrow >> text=pocket")
    page.wait_for_timeout(1800)
    return httpx.get(f"{server}/api/model", timeout=60).json()


def face_of(model, pred):
    body = next(b for b in model["bodies"] if b["result"])
    for f in body["faces"]:
        if pred(f):
            return body, f
    raise AssertionError("no such face in the tagged mesh")


def click_face(page, server, body, face):
    """Click `face` for real, at a point that is genuinely on it."""
    cen = page.evaluate(POINT_ON, [body, face["id"]])
    assert cen, "no triangle belongs to that face"
    sp = page.evaluate(TO_SCREEN, cen)
    page.mouse.click(sp["x"], sp["y"])
    page.wait_for_timeout(900)
    return page.evaluate(PICKED) == face["id"]


def test_clicking_a_pocket_floor_reveals_the_cut_and_names_its_sketch(
        page, server, fresh_doc):
    model = build(page, server)
    # the pocket floor: the small planar face at z = 12 - 5
    body, face = face_of(model, lambda f: f["type"] == "PLANE"
                         and f.get("center") and abs(f["center"][2] - 7) < 0.01)
    assert click_face(page, server, body, face), "could not click the floor"

    st = page.evaluate(STATE)
    # the cut folds onto its tool's row (one operation, one row), so THAT is
    # the row a picked pocket face reveals
    assert st["revealed"] == "pocket_tool"
    # pocket_tool IS the revealed row (it carries the cut), so the rest of the
    # chain is just its sketch
    assert "pocket_sketch" in st["chain"]             # "which sketch is that"
    assert "pocket_sketch" in st["panel"]
    assert "pocket_tool" in st["panel"]
    assert not page.errors, page.errors


def test_clicking_the_untouched_top_face_blames_the_base_extrude(
        page, server, fresh_doc):
    model = build(page, server)
    body, face = face_of(model, lambda f: f["type"] == "PLANE"
                         and f.get("center") and abs(f["center"][2] - 12) < 0.01
                         and f["area"] > 1000)
    assert click_face(page, server, body, face), "could not click the top face"
    st = page.evaluate(STATE)
    assert st["revealed"] == "body"                   # not the later cut
    assert "outline" in st["panel"]
    assert not page.errors, page.errors


def test_the_revealed_row_is_scrolled_into_view(page, server, fresh_doc):
    """On a long tree the row is off screen; highlighting it without scrolling
    highlights nothing the user can see."""
    model = build(page, server)
    body, face = face_of(model, lambda f: f["type"] == "CYLINDER")
    if not click_face(page, server, body, face):
        pytest.skip("the cylinder wall is occluded from this camera")
    inview = page.evaluate("""
      () => {
        const n = document.querySelector('#tree .node.fromface');
        if (!n) return null;
        const a = n.getBoundingClientRect();
        const b = document.getElementById('tree').getBoundingClientRect();
        return a.top >= b.top - 2 && a.bottom <= b.bottom + 2;
      }""")
    assert inview is True
    assert not page.errors, page.errors


def test_picking_is_on_by_default_no_mode_to_enable_first(page, server,
                                                          fresh_doc):
    """Fusion parity: clicking a face selects it — there is no mode to turn on.
    It used to default OFF, so a fresh design ignored every click."""
    assert page.evaluate("() => window.__vp.getPickMode()") is True


def test_an_edge_pick_clears_the_face_answer(page, server, fresh_doc):
    """The 'created by' block describes a FACE; picking an edge must not leave
    it sitting there describing something the user is no longer looking at."""
    model = build(page, server)
    body, face = face_of(model, lambda f: f["type"] == "PLANE"
                         and f.get("center") and abs(f["center"][2] - 12) < 0.01
                         and f["area"] > 1000)
    assert click_face(page, server, body, face)
    assert page.evaluate(STATE)["revealed"] == "body"
    page.evaluate("""
      async () => {
        const { bus } = await import('/static/js/bus.js');
        bus.emit('face-picked', { clear: true });
      }""")
    page.wait_for_timeout(400)
    st = page.evaluate(STATE)
    assert st["revealed"] is None and st["chain"] == [] and not st["panel"]
    assert not page.errors, page.errors
