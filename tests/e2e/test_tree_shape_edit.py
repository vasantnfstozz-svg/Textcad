"""E2E: edit a shape's dimensions in the FEATURE TREE, no sketch editor needed.

User request (2026-08-25): "when click the feature, we dont need see to
entities, and all, also if i am having sketch of square, i have to see lenth, in
the feature tree, if i want change it i can do it in the feature tree itself
[...] lets say we have piller, i can able to change outer diameter and inner
diameter as well, all parameter [...] so it should be robust."

Locked in through the browser:
  1. a sketch shows one card per shape with named dimension rows — and NEVER
     the raw entities JSON that used to fill the panel;
  2. typing a new width in the tree rebuilds the solid;
  3. round things offer a diameter, and editing Ø writes radius = Ø / 2;
  4. a pillar (tube) exposes outer/inner diameter next to its radii;
  5. a traced PATH shows a summary + a way into the sketch editor, because a
     coordinate list has no dimensions to type.
"""
import httpx
import pytest

pytest.importorskip("playwright.sync_api")

BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  const add = (id, op, params, inputs) =>
    postJSON('/api/feature/add', { id, op, params, inputs }, 'add');
  await add('sq', 'sketch', { plane: 'XY', offset: 0, entities: [
    { kind: 'rectangle', w: 40, h: 25, x: 0, y: 0, mode: 'add' },
    { kind: 'circle', r: 6, x: 12, y: 0, mode: 'subtract' }] }, []);
  await add('block', 'extrude', { amount: 10 }, ['sq']);
  await add('post', 'tube', { outer_radius: 20, inner_radius: 8, height: 40 },
            []);
  await add('trace', 'sketch', { plane: 'XY', offset: 2, entities: [
    { kind: 'path', mode: 'add', start: [0, 0], segments: [
      { type: 'line', to: [0, 8] },
      { type: 'arc', via: [1.2, 10.8], to: [4, 12] },
      { type: 'line', to: [10, 12] },
      { type: 'line', to: [10, 0] },
      { type: 'line', to: [0, 0] }] }] }, []);
  await loadMesh(true);
}
"""

OPEN = """
async (fid) => {
  const { S } = await import('/static/js/state.js');
  const { renderDoc } = await import('/static/js/tree.js');
  S.openNodes.add(fid);
  renderDoc(S.lastDoc);
  await new Promise(r => setTimeout(r, 250));
}
"""

ROWS = """
(fid) => {
  const n = document.querySelector(`#tree .node[data-fid="${fid}"]`);
  if (!n) return null;
  const body = n.querySelector('.nbody');
  return {
    raw: (body ? body.innerText : '').includes('"kind"'),
    rows: [...n.querySelectorAll('.prow')].map(r =>
      r.querySelector('.pname').textContent),
    shapes: [...n.querySelectorAll('.shape')].map(s => ({
      kind: (s.querySelector('.skind') || {}).textContent,
      mode: (() => { const m = s.querySelector('.smode');
        return !m ? null : (m.tagName === 'SELECT' ? m.value : m.textContent); })(),
      rows: [...s.querySelectorAll('.prow')].map(r =>
        [r.querySelector('.pname').textContent,
         (r.querySelector('.pval') || {}).textContent]),
      geom: (s.querySelector('.shgeom') || {}).textContent || null,
      hasEditBtn: !!s.querySelector('.shbtn'),
    })),
  };
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


def feats(server):
    return {f["id"]: f for f in
            httpx.get(f"{server}/api/doc", timeout=10).json()["features"]}


def build(page, server):
    page.evaluate(BUILD)
    page.wait_for_selector("#tree .nrow >> text=trace")
    page.wait_for_timeout(1200)


def test_a_sketch_lists_its_shapes_with_named_dimensions(page, server,
                                                         fresh_doc):
    build(page, server)
    page.evaluate(OPEN, "sq")
    d = page.evaluate(ROWS, "sq")
    assert d and d["raw"] is False, "the raw entities JSON is still showing"
    # textContent is the raw kind; the capital letter is CSS (text-transform)
    assert [s["kind"] for s in d["shapes"]] == ["rectangle", "circle"]
    rect = d["shapes"][0]
    assert [r[0] for r in rect["rows"]][:2] == ["width", "height"]
    assert dict(rect["rows"])["width"] == "40"
    assert dict(rect["rows"])["height"] == "25"
    assert rect["mode"] == "add"
    circ = d["shapes"][1]
    assert dict(circ["rows"])["radius"] == "6"
    assert dict(circ["rows"])["Ø diameter"] == "12"      # Ø offered
    assert circ["mode"] == "subtract"
    assert not page.errors, page.errors


def test_typing_a_width_in_the_tree_rebuilds_the_solid(page, server,
                                                       fresh_doc):
    build(page, server)
    page.evaluate(OPEN, "sq")
    v0 = feats(server)["block"]["volume"]
    assert page.evaluate(TYPE_IN, ["sq", "width", 80]) == "ok"
    page.wait_for_timeout(2200)
    v1 = feats(server)["block"]["volume"]
    assert v1 > v0 * 1.9, f"{v0} -> {v1}"          # 40 -> 80 wide
    assert feats(server)["sq"]["params"]["entities"][0]["w"] == 80
    assert not page.errors, page.errors


def test_editing_a_diameter_stores_half_of_it_as_the_radius(page, server,
                                                            fresh_doc):
    build(page, server)
    page.evaluate(OPEN, "sq")
    assert page.evaluate(TYPE_IN, ["sq", "Ø diameter", 20]) == "ok"
    page.wait_for_timeout(2200)
    assert feats(server)["sq"]["params"]["entities"][1]["r"] == 10
    assert not page.errors, page.errors


def test_a_pillar_exposes_outer_and_inner_diameter(page, server, fresh_doc):
    build(page, server)
    page.evaluate(OPEN, "post")
    d = page.evaluate(ROWS, "post")
    assert "Ø outer" in d["rows"] and "Ø inner" in d["rows"], d["rows"]
    assert page.evaluate(TYPE_IN, ["post", "Ø outer", 60]) == "ok"
    page.wait_for_timeout(2200)
    assert feats(server)["post"]["params"]["outer_radius"] == 30
    assert not page.errors, page.errors


def test_a_traced_path_shows_a_summary_not_a_json_dump(page, server,
                                                       fresh_doc):
    build(page, server)
    page.evaluate(OPEN, "trace")
    d = page.evaluate(ROWS, "trace")
    assert d["raw"] is False
    path = d["shapes"][0]
    assert "segments" in (path["geom"] or "")
    assert "mm" in (path["geom"] or "")            # its overall size
    assert path["hasEditBtn"]                      # ...and a way to reshape it
    assert not page.errors, page.errors


ISLANDS = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add', { id: 'isl', op: 'sketch', inputs: [],
    params: { plane: 'XY', offset: 0, entities: [
      { kind: 'circle', r: 5, x: -20, y: 0, mode: 'add' },
      { kind: 'circle', r: 5, x: 0, y: 0, mode: 'add' },
      { kind: 'circle', r: 5, x: 20, y: 0, mode: 'add' }] } }, 'add');
  await postJSON('/api/feature/add', { id: 'pins', op: 'extrude',
    params: { amount: 8 }, inputs: ['isl'] }, 'add');
  await loadMesh(true);
}
"""

MODE_KIND = """
([fid, idx]) => {
  const n = document.querySelector(`#tree .node[data-fid="${fid}"]`);
  const card = [...n.querySelectorAll('.shape')][idx];
  const el = card.querySelector('.smode');
  return { tag: el ? el.tagName : null, text: el ? el.textContent : null,
           title: el ? el.title : null };
}
"""

SET_MODE = """
([fid, idx, val]) => {
  const n = document.querySelector(`#tree .node[data-fid="${fid}"]`);
  const sel = [...n.querySelectorAll('.shape')][idx]
                .querySelector('select.smode');
  if (!sel) return 'no dropdown';
  sel.value = val;
  sel.dispatchEvent(new Event('change', { bubbles: true }));
  return 'ok';
}
"""


def islands(page, server):
    page.evaluate(ISLANDS)
    page.wait_for_selector("#tree .nrow >> text=pins")
    page.wait_for_timeout(1000)
    page.evaluate(OPEN, "isl")


def test_the_first_shape_cannot_be_set_to_subtract(page, server, fresh_doc):
    """sketch._compose refuses a leading subtraction, so offering it on the
    first card was a guaranteed red feature. It is a fixed badge now, and it
    explains why."""
    islands(page, server)
    first = page.evaluate(MODE_KIND, ["isl", 0])
    assert first["tag"] != "SELECT", "the first shape must not offer subtract"
    assert first["text"] == "add"
    assert "cut into" in (first["title"] or "")      # it explains itself
    assert page.evaluate(SET_MODE, ["isl", 0, "subtract"]) == "no dropdown"
    page.wait_for_timeout(800)
    assert feats(server)["isl"]["status"] == "ok"    # nothing got broken
    assert not page.errors, page.errors


def test_subtracting_a_later_shape_removes_that_island(page, server,
                                                       fresh_doc):
    """The control is not decoration: on separate circles, subtract drops that
    circle out of the profile (3 pins -> 2)."""
    islands(page, server)
    v0 = feats(server)["pins"]["volume"]
    assert page.evaluate(MODE_KIND, ["isl", 1])["tag"] == "SELECT"
    assert page.evaluate(SET_MODE, ["isl", 1, "subtract"]) == "ok"
    page.wait_for_timeout(2200)
    v1 = feats(server)["pins"]["volume"]
    assert abs(v1 - v0 * 2 / 3) < 1e-3, f"{v0} -> {v1}"
    assert feats(server)["isl"]["params"]["entities"][1]["mode"] == "subtract"
    assert not page.errors, page.errors


def test_dimensions_still_show_when_the_kinds_endpoint_is_missing(
        page, server, fresh_doc):
    """A server older than this page has no /api/sketch/kinds. The cards used to
    render EMPTY except the dropdown, which reads as "the tree is broken" (the
    user hit exactly this). Raw key names are an acceptable degradation;
    nothing is not."""
    page.route("**/api/sketch/kinds",
               lambda route: route.fulfill(status=404, body="{}"))
    page.reload()
    page.wait_for_function("() => !!window.__vp", timeout=25000)
    page.wait_for_timeout(1500)
    islands(page, server)
    d = page.evaluate(ROWS, "isl")
    labels = [r[0] for r in d["shapes"][0]["rows"]]
    assert "r" in labels, labels             # raw key, but editable
    assert "Ø diameter" in labels            # Ø still offered
    assert d["raw"] is False                 # and never the JSON dump
    stale = page.evaluate(
        "() => !!document.querySelector('#tree .shstale')")
    assert stale, "the stale-server note must explain the raw labels"
    # the blocked /api/sketch/kinds request is this test's own doing
    unexpected = [e for e in page.errors if "404" not in e]
    assert not unexpected, unexpected
