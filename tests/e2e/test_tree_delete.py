"""E2E: deleting a feature out of the middle of the tree, through the real UI.

The user's report: "the AI designs it with a perfect feature tree, but if I want
to delete a sketch or an extrude it's not working". Every AI-authored tree is a
chain (sketch -> extrude tool -> cut, repeated), and the ✕ button used to answer
"cannot remove 'x': used by [...]" for every feature except the last one.

Locks in, through the browser:
  1. ✕ on a consumed SKETCH deletes it (with the features that cannot live
     without it) after a confirm that NAMES them;
  2. ✕ on a mid-chain cut reconnects the features below it — the design keeps
     building, one body, no orphan tool prism;
  3. cancelling the confirm changes nothing;
  4. the Del key deletes the selected feature;
  5. one Ctrl+Z brings the whole group back.
"""
import httpx
import pytest

from conftest import ask_cancel, ask_ok

pytest.importorskip("playwright.sync_api")

# a base body plus two pockets — the shape author.py emits for every design
BUILD_POCKETS = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  const add = (id, op, params, inputs) =>
    postJSON('/api/feature/add', { id, op, params, inputs }, 'add');
  await add('outline', 'sketch', { plane: 'XY', offset: 0, entities: [
    { kind: 'rectangle', w: 80, h: 60, x: 0, y: 0, mode: 'add' }] }, []);
  await add('body', 'extrude', { amount: 12 }, ['outline']);
  let prev = 'body';
  for (const [tag, x] of [['p0', -20], ['p1', 20]]) {
    await add(tag + '_sketch', 'sketch', { plane: 'XY', offset: 12, entities: [
      { kind: 'circle', r: 8, x, y: 0, mode: 'add' }] }, []);
    await add(tag + '_tool', 'extrude', { amount: -5 }, [tag + '_sketch']);
    await add(tag, 'cut', {}, [prev, tag + '_tool']);
    prev = tag;
  }
  await loadMesh(true);
}
"""


def doc(url):
    return httpx.get(f"{url}/api/doc", timeout=5).json()


def ids(url):
    return [f["id"] for f in doc(url)["features"]]


def build(page, server):
    page.evaluate(BUILD_POCKETS)
    page.wait_for_selector("#tree .nrow >> text=p1")
    assert len(ids(server)) == 8
    return page.locator("#tree")


def click_delete(page, fid):
    """Hover the row, then press its ✕ (the row actions appear on hover)."""
    row = page.locator("#tree .node", has=page.locator(
        ".nname", has_text=fid)).first.locator(".nrow").first
    row.hover()
    row.locator("button[title^='delete']").click()


def test_deleting_a_consumed_sketch_asks_then_deletes_the_group(page, server,
                                                                fresh_doc):
    build(page, server)
    seen = []
    click_delete(page, "p0_sketch")
    seen.append(ask_ok(page))
    page.wait_for_function(
        "() => !document.querySelector('#tree .nname[data-x], #tree') || "
        "![...document.querySelectorAll('#tree .nname')]"
        ".some(e => e.textContent === 'p0_sketch')", timeout=15000)

    assert seen, "deleting a feature others depend on must ask FIRST"
    # the confirm has to name what else goes, not just say 'are you sure'
    assert "p0_tool" in seen[0] and "p0" in seen[0]
    assert ids(server) == ["outline", "body", "p1_sketch", "p1_tool", "p1"]
    assert doc(server)["ok"]                      # and it still verifies
    assert not page.errors, page.errors


def test_deleting_a_mid_chain_cut_reconnects_the_rest(page, server, fresh_doc):
    build(page, server)
    click_delete(page, "p0")
    ask_ok(page)
    page.wait_for_function(
        "() => ![...document.querySelectorAll('#tree .node')]"
        ".some(n => n.dataset.fid === 'p0_tool')", timeout=15000)

    d = doc(server)
    p1 = next(f for f in d["features"] if f["id"] == "p1")
    assert p1["inputs"] == ["body", "p1_tool"]    # history repaired
    assert d["ok"] and not d["warnings"]          # one body, no orphan prism
    assert page.locator("#verifyBadge").inner_text().startswith("✓")
    assert not page.errors, page.errors


def test_cancelling_the_confirm_changes_nothing(page, server, fresh_doc):
    build(page, server)
    click_delete(page, "p0_sketch")
    ask_cancel(page)
    page.wait_for_timeout(1200)
    assert len(ids(server)) == 8
    assert not page.errors, page.errors


def test_del_key_deletes_the_selected_feature(page, server, fresh_doc):
    build(page, server)
    page.locator("#tree .node", has=page.locator(
        ".nname", has_text="p1")).first.locator(".nrow").first.click()
    page.keyboard.press("Delete")
    ask_ok(page)
    page.wait_for_function(
        "() => ![...document.querySelectorAll('#tree .nname')]"
        ".some(e => e.textContent === 'p1')", timeout=15000)
    assert ids(server) == ["outline", "body", "p0_sketch", "p0_tool", "p0"]
    assert not page.errors, page.errors


def test_one_undo_restores_the_whole_group(page, server, fresh_doc):
    build(page, server)
    click_delete(page, "p0")
    ask_ok(page)
    page.wait_for_function(
        "() => ![...document.querySelectorAll('#tree .node')]"
        ".some(n => n.dataset.fid === 'p0_tool')", timeout=15000)
    page.keyboard.press("Control+z")
    page.wait_for_function(
        "() => [...document.querySelectorAll('#tree .node')]"
        ".some(n => n.dataset.fid === 'p0_tool')", timeout=15000)
    assert ids(server) == ["outline", "body", "p0_sketch", "p0_tool", "p0",
                           "p1_sketch", "p1_tool", "p1"]
    assert doc(server)["ok"]
    assert not page.errors, page.errors
