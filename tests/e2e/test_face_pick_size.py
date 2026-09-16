"""E2E: the face pick that reaches the server carries HOW BIG the face was.

The backend half is measured in tests/test_face_pick_size.py — given a
`face_area`, `resolve_face` keeps a pick on the boss top when the plate under
it is thickened, instead of silently sliding onto the plate top. All of that
is worth nothing if the BROWSER never sends the field, and a server-side test
cannot tell: the same lesson as the doorbell's banner (2026-09-16), where
eight green server tests sat under a browser half that never spoke.

So this drives the real thing: a real click in the viewport, the real Extrude
panel, OK — and then asks the document what got stored.
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
    { kind: 'rectangle', w: 40, h: 30, x: 0, y: 0, mode: 'add' }] }, []);
  await add('base', 'extrude', { amount: 10 }, ['outline']);
  await add('boss_sk', 'sketch', { plane: 'XY', offset: 10, entities: [
    { kind: 'circle', r: 8, x: 0, y: 0, mode: 'add' }] }, []);
  await add('boss', 'extrude', { amount: 5 }, ['boss_sk']);
  await add('part', 'fuse', {}, ['base', 'boss']);
  await loadMesh(true);
  setView('iso');
}
"""

# straight down on the boss top, well inside its rim
CAM_ABOVE = """
([x, y, z]) => {
  const c = window.__vp.getControls();
  c.object.position.set(x, y, z);
  c.target.set(0, 0, 15);
  c.update();
}
"""

PICKED = """
async () => {
  const { S } = await import('/static/js/state.js');
  const f = S.pickedFace;
  return f ? { area: f.area, z: f.center[2] } : null;
}
"""


def test_a_real_click_carries_the_faces_size_into_the_feature(page, server,
                                                              fresh_doc):
    page.evaluate(BUILD)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=30000)
    page.wait_for_timeout(600)

    page.evaluate("() => window.__vp.setPickMode(true)")
    page.evaluate(CAM_ABOVE, [0, -40, 180])
    page.wait_for_timeout(600)
    page.evaluate("(c) => window.__vp.pickAtWorld(c)", [0, 0, 15])
    page.wait_for_timeout(600)

    got = page.evaluate(PICKED)
    assert got, "the click did not land on a face"
    assert abs(got["z"] - 15) < 0.01, got          # the boss top, not the plate
    assert got["area"] == pytest.approx(201.06, abs=0.05), got

    page.click("#ribbon .rbtn[title='extrude']")
    page.wait_for_selector("#exOk", state="visible", timeout=20000)
    page.wait_for_timeout(800)
    page.fill("#exDist", "4")
    page.wait_for_timeout(600)
    page.click("#exOk")
    page.wait_for_timeout(1500)

    feats = httpx.get(f"{server}/api/doc", timeout=30).json()["features"]
    made = [f for f in feats if f["op"] == "extrude_face"]
    assert made, [f["op"] for f in feats]
    params = made[-1]["params"]
    assert params.get("face_area") == pytest.approx(201.06, abs=0.05), params
    assert not page.errors, page.errors
