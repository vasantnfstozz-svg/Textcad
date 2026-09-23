"""E2E: Named parameters (Tier 2, specs/named-parameters.md). Real clicks and
keys; every volume is checked against area × height.
"""
import httpx
import pytest

pytest.importorskip("playwright.sync_api")

AREA = 20 * 10

BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 's', op: 'sketch', params: { plane: 'XY', offset: 0,
        entities: [{ kind: 'rectangle', w: 20, h: 10, mode: 'add' }] }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'e', op: 'extrude', params: { amount: 5 }, inputs: ['s'] }, 'add');
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
ROW_TEXT = """
([fid, label]) => {
  const n = document.querySelector(`#tree .node[data-fid="${fid}"]`);
  const row = [...n.querySelectorAll('.nbody > .prow')].find(r =>
    r.querySelector('.pname').textContent === label);
  return row ? row.querySelector('.pval').textContent : null;
}
"""
TYPE_IN = """
([fid, label, value]) => {
  const n = document.querySelector(`#tree .node[data-fid="${fid}"]`);
  const row = [...n.querySelectorAll('.nbody > .prow')].find(r =>
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


def open_params(page):
    page.locator("#tabstrip button", has_text="Modify").click()
    page.wait_for_timeout(200)
    page.locator("#ribbon button[title='Parameters']").click()
    page.wait_for_selector("#paramsDialog", state="visible", timeout=15000)


def add_param(page, name, expr):
    page.fill("#pmName", name)
    page.fill("#pmExpr", expr)
    page.click("#pmAdd")
    page.wait_for_timeout(800)


def rows(page):
    return page.eval_on_selector_all("#pmRows .pmrow", """els => els.map(r => ({
      name: r.querySelector('.pmname').textContent, expr: r.querySelector('.pmexpr').textContent,
      val: r.querySelector('.pmval').textContent, users: r.querySelector('.pmusers').textContent }))""")


def test_add_a_parameter_and_drive_an_extrude_from_the_tree(page, fresh_doc, server):
    page.evaluate(BUILD)
    page.wait_for_timeout(1200)
    open_params(page)
    assert page.is_visible("#pmEmpty")
    add_param(page, "wall", "3")
    assert rows(page) == [{"name": "wall", "expr": "3", "val": "= 3", "users": "unused"}]
    assert doc(server)["parameters"][0]["value"] == 3
    # the formula goes into the tree's number row
    page.evaluate(OPEN_CARD, "e")
    assert page.evaluate(ROW_TEXT, ["e", "amount"]) == "5"
    assert page.evaluate(TYPE_IN, ["e", "amount", "wall*2"]) == "ok"
    page.wait_for_timeout(1500)
    f = feature(server, "e")
    assert f["params"]["amount"] == "wall*2" and f["resolved"] == {"amount": 6.0}
    assert f["status"] == "ok" and f["volume"] == pytest.approx(AREA * 6)
    page.evaluate(OPEN_CARD, "e")
    assert page.evaluate(ROW_TEXT, ["e", "amount"]) == "wall*2 = 6"
    assert rows(page)[0]["users"] == "1 use"
    assert not page.errors, page.errors


def test_changing_the_parameter_moves_the_part_and_a_bad_formula_is_a_sentence(page, fresh_doc, server):
    page.evaluate(BUILD)
    page.wait_for_timeout(1200)
    open_params(page)
    add_param(page, "wall", "3")
    page.evaluate(OPEN_CARD, "e")
    page.evaluate(TYPE_IN, ["e", "amount", "wall*2"])
    page.wait_for_timeout(1500)
    # change the value in the panel: click the formula cell, type 4, Enter
    page.locator("#pmRows .pmrow .pmexpr").click()
    inp = page.locator("#pmRows .pmrow .pmexpr input")
    inp.fill("4")
    inp.press("Enter")
    page.wait_for_timeout(1500)
    f = feature(server, "e")
    assert f["volume"] == pytest.approx(AREA * 8) and f["resolved"] == {"amount": 8.0}
    assert rows(page)[0]["val"] == "= 4"
    # a typo in the tree is refused with the sentence, the feature keeps its formula
    page.evaluate(OPEN_CARD, "e")
    page.evaluate(TYPE_IN, ["e", "amount", "wal*2"])
    page.wait_for_timeout(1200)
    assert "did you mean 'wall'" in page.text_content("#chatLog")
    assert feature(server, "e")["params"]["amount"] == "wall*2"
    # deleting a used parameter is refused and says who uses it
    page.locator("#pmRows .pmrow .pmdel").click()
    page.wait_for_timeout(800)
    assert "used by feature 'e'" in page.text_content("#chatLog")
    assert len(rows(page)) == 1
    # the two refusals above answer 400 on purpose, and the browser logs each
    # as a "failed to load resource" console error — those are the refusals
    # working, not a page error
    real = [e for e in page.errors if "status of 400" not in e]
    assert not real, real


def test_renaming_a_parameter_rewrites_the_formula_in_the_tree(page, fresh_doc, server):
    page.evaluate(BUILD)
    page.wait_for_timeout(1200)
    open_params(page)
    add_param(page, "wall", "3")
    page.evaluate(OPEN_CARD, "e")
    page.evaluate(TYPE_IN, ["e", "amount", "wall*2"])
    page.wait_for_timeout(1500)
    page.locator("#pmRows .pmrow .pmname").click()
    inp = page.locator("#pmRows .pmrow .pmname input")
    inp.fill("thickness")
    inp.press("Enter")
    page.wait_for_timeout(1500)
    assert rows(page)[0]["name"] == "thickness"
    f = feature(server, "e")
    assert f["params"]["amount"] == "thickness*2" and f["volume"] == pytest.approx(AREA * 6)
    page.evaluate(OPEN_CARD, "e")
    assert page.evaluate(ROW_TEXT, ["e", "amount"]) == "thickness*2 = 6"
    # the design saves its parameters and reloads them (undo carries them too)
    d = doc(server)
    assert d["parameters"][0]["name"] == "thickness"
    page.click("#pmClose")
    assert not page.is_visible("#paramsDialog")
    assert not page.errors, page.errors


# ---------------------------------------------------------------------------
# The panel is non-modal ON PURPOSE — "a formula is typed INTO a tree row, with
# the panel open beside it" — so the document changes under it all the time,
# and `bus.on('doc-updated', render)` rebuilt #pmRows every time. A cell in the
# middle of an inline edit is an <input> inside those rows, so it went with
# them: measured 2026-09-19 with '3+ha' typed into a formula cell and a feature
# added from elsewhere, the input was simply gone, the typing lost and nothing
# said so. A redraw has to wait for the edit to finish (Enter, Escape or blur —
# each of which redraws anyway).
# ---------------------------------------------------------------------------

ADD_A_FEATURE = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  await postJSON('/api/feature/add',
    { id: 'z', op: 'disc', params: { radius: 5, thickness: 2 }, inputs: [] }, 'add');
}
"""


def test_a_document_change_does_not_wipe_a_half_typed_formula(page, fresh_doc,
                                                              server):
    page.evaluate(BUILD)
    page.wait_for_timeout(1200)
    open_params(page)
    add_param(page, "wall", "3")
    page.locator("#pmRows .pmrow .pmexpr").click()
    inp = page.locator("#pmRows .pmrow .pmexpr input")
    inp.fill("3+ha")                       # mid-word, not a formula yet

    page.evaluate(ADD_A_FEATURE)           # the document moves under the panel
    page.wait_for_timeout(1800)
    assert page.locator("#pmRows input").count() == 1, \
        "the redraw took the cell being edited away"
    assert page.input_value("#pmRows .pmrow .pmexpr input") == "3+ha", \
        "the redraw wiped what was typed"

    # ...and finishing it still lands, and the panel still catches up with the
    # document change it deferred
    inp = page.locator("#pmRows .pmrow .pmexpr input")
    inp.fill("4")
    inp.press("Enter")
    page.wait_for_timeout(1800)
    assert rows(page)[0]["expr"] == "4" and rows(page)[0]["val"] == "= 4"
    assert doc(server)["parameters"][0]["value"] == 4
    assert not page.errors, page.errors


# ---------------------------------------------------------------------------
# Round three's attack on the fix above. Deferring the redraw is right, but it
# makes the row a SNAPSHOT for as long as the cell is open — and a row was
# already a snapshot between two redraws, because the panel is non-modal.
# `/api/parameters` requires the formula, and the NOTE cell sent the formula
# its row remembered.
#
# Measured 2026-09-19: bore = 6, the note cell opened, the formula changed to
# 12.5 from elsewhere (the AI designer, MCP, an undo or a version restore all
# reach it), Enter on the note — and the document went back to bore = 6. Typing
# a comment silently undid a dimension, and every feature using `bore` rebuilt
# at the old size. The same snapshot re-created a parameter deleted under the
# edit, so a delete from elsewhere was quietly undone too.
# ---------------------------------------------------------------------------

SET_PARAM = """
async (a) => {
  const { postJSON } = await import('/static/js/api.js');
  return await postJSON('/api/parameters', a);
}
"""
DROP_PARAM = """
async (name) => {
  const { postJSON } = await import('/static/js/api.js');
  return await postJSON('/api/parameters/remove', { name });
}
"""


def test_a_parameter_with_no_note_yet_can_still_be_given_one(page, fresh_doc,
                                                             server):
    """The cell's own tooltip is "click to add a note", and an EMPTY one is a
    grid item with no content in a row that centres rather than stretches:
    measured 76.39 x 0.00 px at a 420 px column. There was nothing to click, so
    a note could only ever be typed in the Add row as the parameter was made."""
    page.evaluate(BUILD)
    page.wait_for_timeout(1200)
    open_params(page)
    add_param(page, "bore", "6")
    box = page.evaluate("""() => { const r = document.querySelector(
        '#pmRows .pmrow .pmcomment').getBoundingClientRect();
      return { w: r.width, h: r.height }; }""")
    assert box["h"] > 8 and box["w"] > 20, \
        f"the empty note cell has no box to click: {box}"
    page.locator("#pmRows .pmrow .pmcomment").click(timeout=8000)
    inp = page.locator("#pmRows .pmrow .pmcomment input")
    inp.fill("checked on the mill")
    inp.press("Enter")
    page.wait_for_timeout(1500)
    assert doc(server)["parameters"][0]["comment"] == "checked on the mill"
    assert not page.errors, page.errors


def test_typing_a_note_never_writes_back_the_formula_the_row_remembers(
        page, fresh_doc, server):
    page.evaluate(BUILD)
    page.wait_for_timeout(1200)
    open_params(page)
    add_param(page, "bore", "6")
    page.locator("#pmRows .pmrow .pmcomment").click()
    inp = page.locator("#pmRows .pmrow .pmcomment input")
    inp.fill("checked on the mill")

    page.evaluate(SET_PARAM, {"name": "bore", "expr": "12.5"})   # from elsewhere
    page.wait_for_timeout(1500)
    assert doc(server)["parameters"][0]["expr"] == "12.5"

    inp.press("Enter")
    page.wait_for_timeout(1800)
    p = doc(server)["parameters"][0]
    assert p["expr"] == "12.5" and p["value"] == pytest.approx(12.5), \
        f"typing a note put the formula back to what the row remembered: {p}"
    assert p["comment"] == "checked on the mill", f"the note was not saved: {p}"
    assert not page.errors, page.errors


def test_a_parameter_deleted_under_an_edit_is_not_re_created_by_it(
        page, fresh_doc, server):
    page.evaluate(BUILD)
    page.wait_for_timeout(1200)
    open_params(page)
    add_param(page, "bore", "6")
    page.locator("#pmRows .pmrow .pmexpr").click()
    inp = page.locator("#pmRows .pmrow .pmexpr input")
    inp.fill("9")

    page.evaluate(DROP_PARAM, "bore")           # deleted from elsewhere
    page.wait_for_timeout(1500)
    assert doc(server)["parameters"] == []

    inp.press("Enter")
    page.wait_for_timeout(1500)
    assert doc(server)["parameters"] == [], \
        "the edit brought a deleted parameter back"
    assert "not in this design any more" in page.text_content("#chatLog")
    assert rows(page) == [], "the table still shows a parameter that is gone"
    assert not page.errors, page.errors


BUILD_TAPERED = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/parameters', { name: 't', expr: '3' }, 'add');
  await postJSON('/api/feature/add',
    { id: 's', op: 'sketch', params: { plane: 'XY', offset: 0,
        entities: [{ kind: 'rectangle', w: 20, h: 10, mode: 'add' }] }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'e', op: 'extrude', params: { amount: 5, taper: 't' }, inputs: ['s'] }, 'add');
  await loadMesh(true);
}
"""
EDIT = """
async (fid) => {
  const { editFeature } = await import('/static/js/tool.js');
  editFeature(fid);
}
"""


def test_reopening_a_feature_in_its_tool_keeps_its_formulas(page, fresh_doc, server):
    """Review of Named parameters (2026-09-23): every tool's snapshot read
    `Number("t") || 0`, so the panel showed a formula as 0 — and OK in an edit
    pushes every box, so an extrude of 5 with taper `t` came back with taper
    0: the solid changed and the formula was gone, from OK alone."""
    page.evaluate(BUILD_TAPERED)
    page.wait_for_timeout(1200)
    before = feature(server, "e")
    assert before["params"]["taper"] == "t" and before["status"] == "ok"
    # open, look, OK: the box shows the formula's VALUE and the formula stays
    page.evaluate(EDIT, "e")
    page.wait_for_selector("#extrudeDialog", state="visible", timeout=15000)
    page.wait_for_timeout(1500)
    assert float(page.input_value("#exTaper")) == pytest.approx(3)
    page.click("#exOk")
    page.wait_for_timeout(1500)
    f = feature(server, "e")
    assert f["params"]["taper"] == "t", f["params"]
    assert f["volume"] == pytest.approx(before["volume"])
    # a box the user DOES change is theirs: the distance goes to 8, the taper
    # they left alone still follows t
    page.evaluate(EDIT, "e")
    page.wait_for_selector("#extrudeDialog", state="visible", timeout=15000)
    page.wait_for_timeout(1500)
    page.fill("#exDist", "8")
    page.wait_for_timeout(1500)
    page.click("#exOk")
    page.wait_for_timeout(1500)
    f = feature(server, "e")
    assert f["params"]["amount"] == 8 and f["params"]["taper"] == "t", f["params"]
    r = httpx.post(f"{server}/api/parameters", json={"name": "t", "expr": "1"}, timeout=60)
    assert r.status_code == 200
    assert feature(server, "e")["resolved"] == {"taper": 1.0}
    assert not page.errors, page.errors
