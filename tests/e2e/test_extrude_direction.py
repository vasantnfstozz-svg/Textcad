"""E2E: the extrude arrow, the ghost box and the built solid must all go the
SAME way.

Reported 2026-09-01: "when I am pushing the arrow mark one side, the ghost box
goes to another side, but the body is generated as intended direction
sometimes... sometimes the arrow mark goes another side, when I am moving to
one direction".

Root cause (probed): ONE extrude carried THREE direction sources.
  * the arrow followed the picked face's OUTWARD normal;
  * the ghost box grew along the sketch frame's z_dir, which sketch.py
    canonicalises to +Z / +X / -Y — the SAME frame for both faces of an axis
    pair, so it is OPPOSITE the outward normal on a bottom / -x / +y face;
  * the solid followed whichever the backend op reads: extrude_face goes along
    the outward normal, extrude_sketch along the sketch's own plane.
So on half the faces of a box the ghost (face pick) or the arrow (face sketch)
pointed the wrong way. These tests pick the BOTTOM face — the axis where the
two frames disagree — and assert all three agree.
"""
import pytest

pytest.importorskip("playwright.sync_api")

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

# open Extrude on the BOTTOM face without a pixel click: from iso the bottom
# face is hidden behind the solid, and this test is about DIRECTION, not about
# the face picker (which test_user_workflow already drives with real clicks).
PICK_BOTTOM = """
async () => {
  const { S } = await import('/static/js/state.js');
  const faces = window.__vp.bodyObjsRaw()[0].data.faces;
  const bottom = faces.find(f => f.normal && f.normal[2] < -0.9);
  S.pickedFace = { center: bottom.center, normal: bottom.normal, body: 'b' };
  return bottom;
}
"""

DIRS = "() => window.__vp.extrudeDirs()"


def dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def drag_arrow(page, pixels=70):
    """Grab the arrow at its middle and drag it ALONG the direction it points
    on screen — i.e. the user pushing the arrow the way it aims."""
    ax = page.evaluate("""async () => {
      const vp = await import('/static/js/viewport.js');
      return vp.extrudeArrowAxisScreen();
    }""")
    bx, by = ax["base"]["x"], ax["base"]["y"]
    tx, ty = ax["tip"]["x"], ax["tip"]["y"]
    L = ((tx - bx) ** 2 + (ty - by) ** 2) ** 0.5
    ux, uy = (tx - bx) / L, (ty - by) / L
    gx, gy = bx + ux * L * 0.5, by + uy * L * 0.5      # the arrow's middle
    page.mouse.move(gx, gy)
    page.mouse.down()
    for i in range(1, 6):                              # a real, gradual drag
        page.mouse.move(gx + ux * pixels * i / 5, gy + uy * pixels * i / 5)
        page.wait_for_timeout(30)
    return gx + ux * pixels, gy + uy * pixels


@pytest.fixture()
def bottom_face_extrude(page, fresh_doc):
    page.evaluate(BUILD)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.wait_for_timeout(600)
    bottom = page.evaluate(PICK_BOTTOM)
    assert bottom["normal"][2] < -0.9, bottom
    page.click("#ribbon .rbtn[title='extrude']")
    page.wait_for_function("() => document.getElementById('extrudeDialog')"
                           ".style.display === 'block'", timeout=10000)
    page.wait_for_function(
        "() => { const g = window.__vp.gizmos(); return g.arrow && g.ghost; }",
        timeout=10000)
    page.wait_for_timeout(300)          # the frame comes back from the server
    return page


def test_face_extrude_arrow_ghost_and_body_agree(bottom_face_extrude):
    """Pull the arrow on the BOTTOM face: the arrow, the ghost box and the
    solid must all go DOWN. The ghost used to grow UP (the canonicalised frame
    points +Z on a bottom face) while the body came out right."""
    page = bottom_face_extrude
    d0 = page.evaluate(DIRS)
    # the arrow aims along the face's OUTWARD normal — which is what
    # extrude_face builds along (probed: +5 from the bottom face goes to -Z)
    assert d0["arrow"]["axis"][2] < -0.9, d0

    drag_arrow(page)                                   # still holding the mouse
    d = page.evaluate(DIRS)
    amount = d["arrow"]["amount"]
    assert amount > 1, d                               # dragged with the arrow
    assert d["ghost"]["visible"], d
    # the ghost grows the way the arrow points — the reported bug is exactly
    # this dot product coming out NEGATIVE
    grow = d["ghost"]["grows"]
    assert dot(grow, d["arrow"]["points"]) > 0, d
    assert grow[2] < 0, ("the ghost box grew UP out of a DOWNWARD pull", d)

    page.mouse.up()                                    # one verified rebuild
    page.wait_for_timeout(1500)
    doc = page.evaluate("async () => (await fetch('/api/doc')).json()")
    ex = next(f for f in doc["features"] if f["op"] == "extrude_face")
    assert ex["status"] == "ok", ex
    # and the SOLID went down too — measured on what is actually on screen
    # (the plate alone is z -10..10, so a downward boss pushes zmin below it)
    zmin = page.evaluate("""() => {
      let z = Infinity;
      for (const b of window.__vp.bodyObjsRaw()) {
        const p = b.mesh.geometry.attributes.position.array;
        for (let i = 2; i < p.length; i += 3) z = Math.min(z, p[i]);
      }
      return z;
    }""")
    assert zmin < -10.1, (zmin, "the boss did not grow downward")
    assert page.errors == []


def test_flip_moves_the_arrow_instead_of_negating_it_later(bottom_face_extrude):
    """Ticking Flip must MOVE the arrow (Fusion: the flipped side is where the
    material goes). It used to leave the arrow alone and negate it only at
    apply time, so the arrow jumped to the far side on release."""
    page = bottom_face_extrude
    before = page.evaluate(DIRS)["arrow"]["axis"]
    page.evaluate("""() => {
      const f = document.getElementById('exFlip');
      f.checked = true;
      f.dispatchEvent(new Event('change', { bubbles: true }));
    }""")
    page.wait_for_timeout(500)
    after = page.evaluate(DIRS)["arrow"]["axis"]
    assert dot(before, after) < -0.9, (before, after)
    assert page.errors == []
