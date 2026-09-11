"""E2E: pushing a picked FACE into the body makes a pocket, not a no-op.

Section 7 review, 2026-09-11. Extrude's face mode defaulted to Join and the
Join/Cut rule that reads the drag direction was written for face SKETCHES only
(`!isFace(st)`), so pulling a face INWARD fused a prism that was already inside
the body: measured plate 24 000, prism 9 600, join 24 000 mm3 — three green
rows, an unchanged body, and not one word. Fusion's parity rule 6 is "dragging
INTO the body + Cut = pocket"; the plan already ships `into_sign` for a face
pick, so the same rule now runs in face mode.
"""
import pytest

pytest.importorskip("playwright.sync_api")

PLATE = 60 * 40 * 20

BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh, setView } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 60, depth: 40, thickness: 20 },
      inputs: [] }, 'add');
  await loadMesh(true);
  setView('iso');
}
"""

PICK_TOP = """
async () => {
  const { S } = await import('/static/js/state.js');
  const faces = window.__vp.bodyObjsRaw()[0].data.faces;
  const top = faces.find(f => f.normal && f.normal[2] > 0.9);
  S.pickedFace = { center: top.center, normal: top.normal, body: 'b' };
  return top;
}
"""


def drag_arrow(page, pixels):
    """Grab the arrow at its middle and drag it along its on-screen direction —
    a NEGATIVE distance is the user pushing it back INTO the body."""
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
    page.mouse.up()


@pytest.fixture()
def top_face_extrude(page, fresh_doc):
    page.evaluate(BUILD)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.wait_for_timeout(600)
    top = page.evaluate(PICK_TOP)
    assert top["normal"][2] > 0.9, top
    page.click("#ribbon .rbtn[title='extrude']")
    page.wait_for_function("() => document.getElementById('extrudeDialog')"
                           ".style.display === 'block'", timeout=10000)
    page.wait_for_function(
        "() => { const g = window.__vp.gizmos(); return g.arrow && g.ghost; }",
        timeout=10000)
    page.wait_for_timeout(300)
    return page


def test_pushing_the_face_in_cuts_a_pocket(top_face_extrude):
    page = top_face_extrude
    assert page.eval_on_selector("#exOp", "e => e.value") == "join"
    # THROUGH ALL has no meaning in face mode (extrude_face takes no `through`),
    # so its row must not be reachable there
    assert page.eval_on_selector("#exThroughRow", "e => e.style.display") == "none"

    drag_arrow(page, -70)                       # push the face INTO the body
    page.wait_for_timeout(1800)

    assert page.eval_on_selector("#exOp", "e => e.value") == "cut", \
        "an inward pull must become a Cut (parity rule 6)"
    doc = page.evaluate("async () => (await fetch('/api/doc')).json()")
    ex = next(f for f in doc["features"] if f["op"] == "extrude_face")
    assert ex["status"] == "ok", ex
    assert ex["params"]["amount"] < 0, ex["params"]
    cut = next(f for f in doc["features"] if f["op"] == "cut")
    assert cut["status"] == "ok", cut
    assert cut["volume"] < PLATE - 100, (cut["volume"], "no material was removed")
    assert doc["warnings"] == [], doc["warnings"]
    assert page.errors == []


def test_pulling_the_face_out_still_joins(top_face_extrude):
    page = top_face_extrude
    drag_arrow(page, 70)                        # pull the face OUT of the body
    page.wait_for_timeout(1800)
    assert page.eval_on_selector("#exOp", "e => e.value") == "join"
    doc = page.evaluate("async () => (await fetch('/api/doc')).json()")
    join = next(f for f in doc["features"] if f["op"] == "fuse")
    assert join["volume"] > PLATE + 100, (join["volume"], "no material was added")
    assert page.errors == []
