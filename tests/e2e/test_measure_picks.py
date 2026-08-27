"""E2E: Measure keeps BOTH picks visible, and badges them A and B.

User report (2026-08-27): "when i am clicking the sechond face, the selected
first fase color is vansiheg … i can see a and b in the tab, but, when iam
selecting first face, in top of that, a shoould appers in design".

The pick highlight was a single transient object, so clicking the second face
wiped the first — and with nothing marking which pick was which, a wrong
selection was invisible. That is not a cosmetic problem: the same report also
said a move "was not moving", and the cause was a mis-picked pair the user had
no way to see.

Clicking uses centroids of the body's OWN mesh triangles, not face centres: a
face centre is often not on its face at all, so clicking one hits whatever is
behind it (the same trap test_face_to_feature.py documents).
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
    { kind: 'rectangle', w: 60, h: 40, x: 0, y: 0, mode: 'add' }] }, []);
  await add('pocket_tool', 'extrude', { amount: -8 }, ['pocket_sketch']);
  await add('pocket', 'cut', {}, ['body', 'pocket_tool']);
  await loadMesh(true);
  setView('iso');
}
"""

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
  const s = window.__vp.worldToScreen(w);
  return s ? { x: s.x, y: s.y } : null;
}
"""

BADGES = """
() => {
  const vis = id => {
    const e = document.getElementById(id);
    return !!e && getComputedStyle(e).display !== 'none';
  };
  return { A: vis('selBadgeA'), B: vis('selBadgeB') };
}
"""


def build(page, server):
    page.evaluate(BUILD)
    page.wait_for_selector("#tree .nrow >> text=pocket")
    page.wait_for_timeout(1800)
    return httpx.get(f"{server}/api/model", timeout=60).json()


def open_measure(page):
    page.click("#tabstrip button >> text=Inspect")
    page.wait_for_timeout(250)
    page.click("#ribbon button:has-text('Measure')")
    page.wait_for_timeout(400)
    assert page.is_visible("#measureDialog"), "the Measure panel did not open"


def click_face(page, body, face):
    cen = page.evaluate(POINT_ON, [body, face["id"]])
    assert cen, f"no triangle belongs to face {face['id']}"
    sp = page.evaluate(TO_SCREEN, cen)
    assert sp, "that face projects behind the camera"
    page.mouse.click(sp["x"], sp["y"])
    page.wait_for_timeout(900)


def two_walls(model):
    """Two vertical walls of the pocket that both face the iso camera, which is
    the pair a user can actually click without orbiting."""
    body = next(b for b in model["bodies"] if b["result"])
    walls = [f for f in body["faces"]
             if f.get("normal") and abs(f["normal"][2]) < 0.01
             and f["center"][2] > 6]
    # +X-facing and -Y-facing are both toward the iso camera (+X, -Y, +Z)
    ax = next(f for f in walls if f["normal"][0] > 0.99)
    by = next(f for f in walls if f["normal"][1] < -0.99)
    return body, ax, by


def test_both_picks_stay_lit_and_badged(page, server, fresh_doc):
    model = build(page, server)
    body, wall_a, wall_b = two_walls(model)
    open_measure(page)

    assert page.evaluate(BADGES) == {"A": False, "B": False}, \
        "badges showed before anything was picked"

    click_face(page, body, wall_a)
    assert page.evaluate(BADGES) == {"A": True, "B": False}, \
        "the A badge did not appear on the first pick"
    assert page.inner_text("#meSelA").strip() != "—"

    click_face(page, body, wall_b)
    badges = page.evaluate(BADGES)
    # THE REGRESSION: A used to be wiped the moment B was clicked
    assert badges == {"A": True, "B": True}, \
        f"both picks must stay marked, got {badges}"
    assert page.inner_text("#meSelA").strip() != "—", "A was dropped"
    assert page.inner_text("#meSelB").strip() != "—", "B was never set"
    assert page.errors == [], page.errors


def test_reset_clears_both_badges(page, server, fresh_doc):
    model = build(page, server)
    body, wall_a, wall_b = two_walls(model)
    open_measure(page)
    click_face(page, body, wall_a)
    click_face(page, body, wall_b)
    assert page.evaluate(BADGES) == {"A": True, "B": True}
    page.click("#meReset")
    page.wait_for_timeout(500)
    assert page.evaluate(BADGES) == {"A": False, "B": False}, \
        "Reset left badges behind"
    assert page.errors == [], page.errors


def test_a_read_only_measurement_always_says_why(page, server, fresh_doc):
    """Rule 7. A number with no edit box and no reason reads as a broken tool.
    Two perpendicular walls give an angle, which nothing can drive."""
    model = build(page, server)
    body, wall_a, wall_b = two_walls(model)   # +X and -Y facing => 90 degrees
    open_measure(page)
    click_face(page, body, wall_a)
    click_face(page, body, wall_b)
    if page.is_visible("#meEdit"):
        pytest.skip("that pair turned out editable; this test needs a "
                    "read-only one")
    assert page.is_visible("#meDriver"), \
        "no edit box AND no explanation — the user cannot tell why"
    why = page.inner_text("#meDriver").strip()
    assert why, "the explanation was blank"
    assert page.errors == [], page.errors
