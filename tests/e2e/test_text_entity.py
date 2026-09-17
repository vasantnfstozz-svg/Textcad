"""E2E: the Text sketch entity (Tier 2, specs/text-entity.md). Real clicks
and keys; every geometric claim checked against the kernel's own figures
(Arial on this box: 'AB' at 10 mm is 35.921 mm2).
"""
import httpx
import pytest

pytest.importorskip("playwright.sync_api")

AB = 35.921          # mm2, 'AB' at 10 mm in Arial (probes/text_api_probe.py)
PLATE = 60 * 40 * 12

OPEN_SKETCH = """
async () => {
  const sk = await import('/static/js/sketcher.js');
  sk.openSketchEditor('XY');
  await new Promise(r => setTimeout(r, 900));
  sk.setSketchTool('text');
}
"""
CLICK = """
async (args) => {
  const [x, y] = args;
  const { bus } = await import('/static/js/bus.js');
  bus.emit('sk3d-move', { x, y, tol: 1, down: false });
  bus.emit('sk3d-down', { x, y, tol: 1 }); bus.emit('sk3d-up', {});
  await new Promise(r => setTimeout(r, 200));
}
"""
ENTS = "async () => (await import('/static/js/sketcher.js')).sketchEntities()"
FINISH = "async () => (await import('/static/js/sketcher.js')).finishSketch()"

# a plate with 'AB' written on its top face, cut 2 mm deep: an engraving
BUILD_ENGRAVING = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 60, depth: 40, thickness: 12 }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 's', op: 'sketch_on_face',
      params: { face: 'top', offset: 0,
                entities: [{ kind: 'text', text: 'AB', size: 10, x: 0, y: 0, mode: 'add' }] },
      inputs: ['b'] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'e', op: 'extrude', params: { amount: -2 }, inputs: ['s'] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'cut1', op: 'cut', params: {}, inputs: ['b', 'e'] }, 'add');
  await loadMesh(true);
}
"""


OPEN_CARD = """
async (fid) => {
  const { S } = await import('/static/js/state.js');
  const { renderDoc } = await import('/static/js/tree.js');
  S.openNodes.add(fid);
  renderDoc(S.lastDoc);
  await new Promise(r => setTimeout(r, 250));
}
"""
CARD_ROWS = """
(fid) => {
  const n = document.querySelector(`#tree .node[data-fid="${fid}"]`);
  return [...n.querySelectorAll('.shape .prow')].map(r =>
    [r.querySelector('.pname').textContent, (r.querySelector('.pval') || {}).textContent]);
}
"""
TYPE_IN = """
([fid, label, value]) => {
  const n = document.querySelector(`#tree .node[data-fid="${fid}"]`);
  const row = [...n.querySelectorAll('.prow')].find(r =>
    r.querySelector('.pname').textContent === label);
  if (!row) return 'no row ' + label;
  row.querySelector('.pval').click();
  const inp = row.querySelector('input');
  if (!inp) return 'no input';
  inp.value = String(value);
  inp.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
  return 'ok';
}
"""


def doc(server):
    return httpx.get(f"{server}/api/doc", timeout=30).json()


def feature(server, fid):
    return next((f for f in doc(server)["features"] if f["id"] == fid), None)


def row(page, fid):
    return page.locator("#tree .nrow", has=page.locator(".nname", has_text=fid))


def test_the_text_tool_places_a_typed_word_and_it_extrudes(page, fresh_doc, server):
    page.evaluate(OPEN_SKETCH)
    page.evaluate(CLICK, [0, 0])
    box = page.locator("#skDimDraw")
    assert box.is_visible(), "the word box appears at the click"
    word = box.locator("input[data-dim='text']")
    assert word.count() == 1 and page.evaluate("() => document.activeElement.dataset.dim") == "text"
    page.keyboard.type("HI")                    # replaces the selected default
    page.keyboard.press("Tab")
    page.keyboard.type("12")
    page.keyboard.press("Enter")
    page.wait_for_timeout(300)
    ents = page.evaluate(ENTS)
    assert ents == [{"kind": "text", "mode": "add", "x": 0, "y": 0, "rotation": 0,
                     "text": "HI", "size": 12}], ents
    assert not box.is_visible(), "the box hides on commit"
    page.wait_for_timeout(1500)                 # the glyph loops arrive from the server
    page.evaluate(FINISH)
    page.wait_for_timeout(1500)
    sk = [f for f in doc(server)["features"] if f["op"] == "sketch"]
    assert len(sk) == 1 and sk[0]["status"] == "ok", sk
    page.evaluate("""async () => {
      const { postJSON } = await import('/static/js/api.js');
      await postJSON('/api/feature/add',
        { id: 'e1', op: 'extrude', params: { amount: 3 }, inputs: ['%s'] }, 'add');
    }""" % sk[0]["id"])
    page.wait_for_timeout(1500)
    e = feature(server, "e1")
    assert e["status"] == "ok" and e["pieces"] == 2 and e["volume"] > 50, e
    assert not page.errors, page.errors


def test_an_engraving_and_the_word_edited_in_the_tree(page, fresh_doc, server):
    page.evaluate(BUILD_ENGRAVING)
    page.wait_for_timeout(1500)
    c = feature(server, "cut1")
    assert c["status"] == "ok", c["problems"]
    assert c["volume"] == pytest.approx(PLATE - 2 * AB, abs=0.2)
    # the tree shows the word as a text row on the sketch's card (the card
    # opens the way test_tree_shape_edit opens one: the node joins openNodes)
    page.evaluate(OPEN_CARD, "s")
    rows = page.evaluate(CARD_ROWS, "s")
    assert ["word", "AB"] in rows and any(r[0] == "height" for r in rows), rows
    assert page.evaluate(TYPE_IN, ["s", "word", "ABC"]) == "ok"
    page.wait_for_timeout(2500)
    s = feature(server, "s")
    assert s["params"]["entities"][0]["text"] == "ABC", s["params"]
    c2 = feature(server, "cut1")
    assert c2["status"] == "ok" and c2["volume"] < c["volume"] - 10, (c["volume"], c2["volume"])
    assert not page.errors, page.errors


def test_editing_the_sketch_draws_the_glyphs_from_the_server(page, fresh_doc, server):
    page.evaluate(BUILD_ENGRAVING)
    page.wait_for_timeout(1500)
    with page.expect_response(lambda r: r.url.endswith("/api/sketch/outline")) as got:
        page.evaluate("""async () => {
          const { bus } = await import('/static/js/bus.js');
          const doc = await (await fetch('/api/doc')).json();
          bus.emit('edit-sketch', doc.features.find(f => f.id === 's'));
        }""")
    res = got.value.json()
    assert len(res["outlines"]) == 1 and len(res["outlines"][0]) == 5, \
        "A: outer + hole, B: outer + 2 holes"
    assert res["errors"] == {}
    page.wait_for_timeout(800)
    active = page.evaluate("async () => (await import('/static/js/sketch3d.js')).sketch3DActive()")
    assert active
    ents = page.evaluate(ENTS)
    assert ents[0]["kind"] == "text" and ents[0]["text"] == "AB"
    assert not page.errors, page.errors
