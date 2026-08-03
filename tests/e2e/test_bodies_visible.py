"""E2E: no body ever "goes blank" (S3 of SKETCH-MODE-PLAN.md).

The reported bug, verbatim: "when I draw second design or something else, and
then when I am extruding it, the first solid box going blank." Cause: only the
RESULT solid was face-tagged and drawn as a real body; other leaf bodies came
back as bare silhouettes and were drawn as translucent grey ghosts. Extruding a
second sketch made THAT the result, so the first body turned into a ghost.

Locked in here: every leaf body renders as an opaque solid in the same material,
each is face-tagged so it can be picked, and a pick reports WHICH body it hit
(tools act on the picked body, not on whatever happens to be the tip).
"""
import pytest

pytest.importorskip("playwright.sync_api")

# add a feature the way the Add-Feature dialog does: POST, then loadMesh.
# (main.js's 3s watcher will NOT refresh here — postJSON already updated
# S.lastDoc, so the signature it compares against is unchanged.)
ADD_JS = """
async (args) => {
  const [id, op, params, inputs] = args;
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  const r = await postJSON('/api/feature/add',
    { id, op, params, inputs: inputs || [] }, 'adding…');
  if (!r.error) await loadMesh(true);
  return r.error || null;
}
"""

RECT = lambda x, w, h: {"plane": "XY", "offset": 0, "entities": [
    {"kind": "rectangle", "mode": "add", "x": x, "y": 0, "w": w, "h": h}]}


def build_two_boxes(page):
    """No fixed sleeps: ADD_JS awaits loadMesh(), so when the evaluate resolves
    the scene is already rebuilt. Poll bodyCount as the completion signal."""
    assert page.evaluate(ADD_JS, ["sk1", "sketch", RECT(0, 60, 40), []]) is None
    assert page.evaluate(ADD_JS, ["box1", "extrude", {"amount": 20},
                                  ["sk1"]]) is None
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    assert page.evaluate(ADD_JS, ["sk2", "sketch", RECT(110, 40, 40), []]) is None
    assert page.evaluate(ADD_JS, ["box2", "extrude", {"amount": 25},
                                  ["sk2"]]) is None
    page.wait_for_function("() => window.__vp.bodyCount() === 2", timeout=20000)
    return page.evaluate("window.__vp.bodyInfo()")


def test_second_extrude_does_not_blank_the_first_body(page, fresh_doc):
    info = build_two_boxes(page)
    ids = sorted(b["id"] for b in info)
    assert ids == ["box1", "box2"], info
    # THE regression: the older body must not be a translucent ghost
    for b in info:
        assert b["opacity"] == 1 and not b["transparent"], b
    assert len({b["color"] for b in info}) == 1, "bodies must look alike"
    assert sum(1 for b in info if b["result"]) == 1, "one result body"
    assert page.errors == []


def test_every_body_is_pickable_and_reports_its_own_id(page, fresh_doc):
    """Clicking the OLD body must pick a face ON IT — previously ghosts were
    not in the raycast set at all, so only the newest body could be selected."""
    build_two_boxes(page)
    page.evaluate("document.getElementById('vSelect').click()")
    page.wait_for_timeout(300)
    for target in ("box1", "box2"):
        hit = page.evaluate("""async (target) => {
          const vp = window.__vp;
          const b = vp.bodyObjsRaw().find(x => x.id === target);
          const top = b.data.faces.filter(f => f.center)
                        .sort((p, q) => q.center[2] - p.center[2])[0];
          return vp.pickAtWorld(top.center);
        }""", target)
        assert hit and hit["body"] == target, (target, hit)
        panel = page.evaluate(
            "document.getElementById('pickInfo').innerText")
        assert target in panel, panel
    assert page.errors == []


def test_overlapping_loads_do_not_duplicate_scene_objects(page, fresh_doc):
    """loadMesh is async and fired from dialogs, tabs and the 3s watcher; with
    no re-entrancy guard two in flight each ADDED their objects while only one
    disposed, stacking duplicate bodies and profiles on the real ones."""
    build_two_boxes(page)
    before = page.evaluate("window.__vp.sceneCounts()")
    page.evaluate("""async () => {
      const { loadMesh } = await import('/static/js/viewport.js');
      await Promise.all([loadMesh(), loadMesh(), loadMesh(), loadMesh()]);
    }""")
    page.wait_for_timeout(400)
    after = page.evaluate("window.__vp.sceneCounts()")
    assert after == before, (before, after)
    assert page.errors == []
