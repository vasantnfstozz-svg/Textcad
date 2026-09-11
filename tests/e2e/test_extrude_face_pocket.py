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


TWO_BODIES = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh, setView } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'a', op: 'plate', params: { width: 60, depth: 40, thickness: 20 },
      inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 30, depth: 30, thickness: 20 },
      inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'bmv', op: 'move', params: { x: 200 }, inputs: ['b'] }, 'add');
  await loadMesh(true);
  setView('iso');
}
"""

PICK_TOP_OF_A = """
async () => {
  const { S } = await import('/static/js/state.js');
  const body = window.__vp.bodyObjsRaw().find(o => o.id === 'a');
  const top = body.data.faces.find(f => f.normal && f.normal[2] > 0.9);
  S.pickedFace = { center: top.center, normal: top.normal, body: 'a' };
  return top;
}
"""


def test_the_auto_cut_lands_on_the_body_whose_face_was_picked(page, fresh_doc):
    """The inward pull now switches to Cut on its own, and a cut is
    destructive — so it must never be aimed at the NEWEST body the way the
    2026-08-24 default was ("that default cut the raw stock instead of the
    user's panel"). The face is picked on the OLDER body 'a'; 'bmv' is newer."""
    page.evaluate(TWO_BODIES)
    page.wait_for_function("() => window.__vp.bodyCount() === 2", timeout=20000)
    page.wait_for_timeout(600)
    page.evaluate(PICK_TOP_OF_A)
    page.click("#ribbon .rbtn[title='extrude']")
    page.wait_for_function("() => document.getElementById('extrudeDialog')"
                           ".style.display === 'block'", timeout=10000)
    page.wait_for_function(
        "() => { const g = window.__vp.gizmos(); return g.arrow && g.ghost; }",
        timeout=10000)
    page.wait_for_timeout(300)
    assert page.eval_on_selector("#exTarget", "e => e.value") == "a"

    drag_arrow(page, -70)
    page.wait_for_timeout(1800)

    assert page.eval_on_selector("#exOp", "e => e.value") == "cut"
    doc = page.evaluate("async () => (await fetch('/api/doc')).json()")
    cut = next(f for f in doc["features"] if f["op"] == "cut")
    assert cut["inputs"][0] == "a", (cut["inputs"], "the cut was aimed elsewhere")
    assert cut["volume"] < 60 * 40 * 20 - 100, cut["volume"]
    moved = next(f for f in doc["features"] if f["id"] == "bmv")
    assert moved["volume"] == 30 * 30 * 20, (moved["volume"], "the other body changed")
    assert page.errors == []


def test_through_all_zeroes_and_parks_the_taper(page, fresh_doc, server):
    """A 2 m tapered prism collapses, so the server builds every through cut
    straight — and used to do it while the panel's taper box and dashed ring
    still read the angle the user had set (measured: a -10 deg through cut
    built 20 x 30 x 2000 mm, dead straight). The box may not lie.

    The tool is opened through its own export rather than by clicking the
    profile: this journey is about the PANEL's field state, and the selection
    path has its own tests."""
    import httpx
    for fid, op, params, inputs in [
        ("part", "plate", {"width": 60, "depth": 40, "thickness": 10}, []),
        ("sk", "sketch_on_face",
         {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
          "entities": [{"kind": "circle", "r": 6}]}, ["part"]),
    ]:
        r = httpx.post(f"{server}/api/feature/add",
                       json={"id": fid, "op": op, "params": params,
                             "inputs": inputs}, timeout=120).json()
        assert not r.get("error"), r.get("error")
    page.reload(wait_until="domcontentloaded")
    page.wait_for_function("() => !!window.__vp", timeout=20000)
    page.wait_for_timeout(1500)
    page.evaluate("""async () => {
      const m = await import('/static/js/extrude.js');
      m.openExtrude('sk');
    }""")
    page.wait_for_selector("#exOk", state="visible", timeout=15000)
    page.wait_for_timeout(800)

    page.select_option("#exOp", "cut")
    page.wait_for_timeout(400)
    assert page.eval_on_selector("#exThroughRow", "e => e.style.display") != "none"
    page.evaluate("""() => {
      const t = document.getElementById('exTaper');
      t.value = '-10';
      t.dispatchEvent(new Event('input', { bubbles: true }));
    }""")
    page.wait_for_timeout(400)
    assert page.eval_on_selector("#exTaper", "e => e.value") == "-10"

    page.check("#exThrough")
    page.wait_for_timeout(1500)
    assert page.eval_on_selector("#exTaper", "e => e.value") == "0", \
        "the taper box went on showing an angle the through cut does not have"
    assert page.eval_on_selector("#exTaper", "e => e.disabled") is True
    assert page.eval_on_selector("#exDist", "e => e.disabled") is True

    page.uncheck("#exThrough")
    page.wait_for_timeout(800)
    assert page.eval_on_selector("#exTaper", "e => e.disabled") is False
    assert page.errors == []


def test_a_pull_deeper_than_the_body_does_not_report_success(top_face_extrude):
    """The inward pull is a Cut by itself now, so "deeper than the body" is one
    gesture away: the extrude stays perfectly green and the CUT empties the
    design. Measured before the fix — extrude_face ok at 72 000 mm3, the cut
    failed, ZERO bodies on screen, and OK said "Extrude created"."""
    page = top_face_extrude
    page.evaluate("""() => { const d = document.getElementById('exDist');
      d.value = '-30'; d.dispatchEvent(new Event('input', { bubbles: true })); }""")
    page.wait_for_timeout(2500)
    doc = page.evaluate("async () => (await fetch('/api/doc')).json()")
    cut = next(f for f in doc["features"] if f["op"] == "cut")
    assert cut["status"] == "failed", cut          # the kernel refuses it loudly
    assert page.evaluate("() => window.__vp.bodyCount()") == 0

    page.click("#exOk")
    page.wait_for_timeout(2000)
    said = page.text_content("#chatLog")
    assert "Extrude created" not in said, "OK claimed success over an empty viewport"
    assert "the Cut after it was NOT" in said, said[-400:]
    assert page.errors == []
