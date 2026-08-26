"""E2E: deleting the LAST shape in a sketch must not trap the user in sketch mode.

User's report (2026-08-25): "in my design i just want to delete a name, i
clicked delete in the sketch mode, but i can't save the sketch and go to the
normal tab, because it says something."

Reproduction: a sketch whose only content is the name art. Edit it, delete that
shape, press Finish Sketch — the old code answered "the sketch is empty, pick a
shape and draw first" and RETURNED without leaving sketch mode. In sketch mode
the tab strip is only the green contextual tab, so File/Create/Modify are gone:
the only way out was Cancel, which throws the deletion away. The delete could
never be saved.

Locked in here:
  1. emptying an EXISTING sketch and pressing Finish offers to delete the
     sketch feature (naming what goes with it) and leaves sketch mode;
  2. declining that offer keeps you in the sketch, with the shapes still gone
     to redraw — never a dead end either way;
  3. pressing Finish on a brand-new sketch with nothing drawn just leaves
     sketch mode instead of refusing.
"""
import httpx
import pytest

pytest.importorskip("playwright.sync_api")

# a body, plus a "name" sketch that feeds an engraved pocket — the shape an AI
# design has when it engraves a logo or a name
BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  const add = (id, op, params, inputs) =>
    postJSON('/api/feature/add', { id, op, params, inputs }, 'add');
  await add('outline', 'sketch', { plane: 'XY', offset: 0, entities: [
    { kind: 'rectangle', w: 80, h: 50, x: 0, y: 0, mode: 'add' }] }, []);
  await add('body', 'extrude', { amount: 10 }, ['outline']);
  await add('name_sk', 'sketch', { plane: 'XY', offset: 10, entities: [
    { kind: 'circle', r: 7, x: 20, y: 0, mode: 'add' }] }, []);
  await add('name_tool', 'extrude', { amount: -2 }, ['name_sk']);
  await add('engrave', 'cut', {}, ['body', 'name_tool']);
  await loadMesh(true);
}
"""

EDIT_SKETCH = """
async (fid) => {
  const { bus } = await import('/static/js/bus.js');
  const { S } = await import('/static/js/state.js');
  bus.emit('edit-sketch', S.lastDoc.features.find(f => f.id === fid));
}
"""

CLICK = """
async (args) => {
  const [x, y] = args;
  const { bus } = await import('/static/js/bus.js');
  bus.emit('sk3d-down', { x, y, tol: 2 }); bus.emit('sk3d-up', {});
  await new Promise(r => setTimeout(r, 150));
}
"""

ENTS = "async () => (await import('/static/js/sketcher.js')).sketchEntities()"
FINISH = """
async () => {
  const sk = await import('/static/js/sketcher.js');
  sk.finishSketch();
  await new Promise(r => setTimeout(r, 150));
}
"""
IN_SKETCH_MODE = ("() => !!document.querySelector('#tabstrip .sketchctx')")


def doc(url):
    return httpx.get(f"{url}/api/doc", timeout=5).json()


def ids(url):
    return [f["id"] for f in doc(url)["features"]]


def empty_the_name_sketch(page, server):
    page.evaluate(BUILD)
    page.wait_for_selector("#tree .nrow >> text=engrave")
    page.evaluate(EDIT_SKETCH, "name_sk")
    page.wait_for_function(IN_SKETCH_MODE, timeout=15000)
    page.wait_for_timeout(800)
    page.evaluate(CLICK, [20, 0])                 # select the name art
    page.keyboard.press("Delete")                 # ...and delete it
    page.wait_for_timeout(300)
    assert page.evaluate(ENTS) == [], "the shape should be gone from the sketch"


def test_emptying_a_sketch_then_finishing_offers_to_delete_it(page, server,
                                                              fresh_doc):
    empty_the_name_sketch(page, server)
    seen = []
    page.on("dialog", lambda d: (seen.append(d.message), d.accept()))
    page.evaluate(FINISH)
    page.wait_for_function(f"() => !({IN_SKETCH_MODE})()", timeout=15000)

    assert seen, "finishing an emptied sketch must ASK, not refuse silently"
    assert "name_sk" in seen[0] and "engrave" in seen[0]
    # normal tabs are back — the user is not stuck in the contextual tab
    assert page.locator("#tabstrip .tab").count() > 1
    assert ids(server) == ["outline", "body"]     # the name and its cut are gone
    assert doc(server)["ok"] and doc(server)["rollback"] is None
    assert not page.errors, page.errors


def test_declining_keeps_the_sketch_open_not_a_dead_end(page, server,
                                                        fresh_doc):
    empty_the_name_sketch(page, server)
    page.on("dialog", lambda d: d.dismiss())
    page.evaluate(FINISH)
    page.wait_for_timeout(800)
    assert page.evaluate(IN_SKETCH_MODE)          # still editing, on purpose
    assert len(ids(server)) == 5                  # nothing deleted
    # and the way out is still there: Cancel leaves sketch mode
    page.evaluate("async () => (await import('/static/js/sketcher.js'))"
                  ".cancelSketch()")
    page.wait_for_function(f"() => !({IN_SKETCH_MODE})()", timeout=15000)
    assert not page.errors, page.errors


def test_finishing_a_brand_new_empty_sketch_just_leaves_the_mode(page, server,
                                                                 fresh_doc):
    page.evaluate("async () => (await import('/static/js/sketcher.js'))"
                  ".openSketchEditor('XY')")
    page.wait_for_function(IN_SKETCH_MODE, timeout=15000)
    page.wait_for_timeout(600)
    page.evaluate(FINISH)
    page.wait_for_function(f"() => !({IN_SKETCH_MODE})()", timeout=15000)
    assert page.locator("#tabstrip .tab").count() > 1
    assert ids(server) == []                      # nothing drawn, nothing made
    assert not page.errors, page.errors
