"""E2E: deleting a feature out of the middle of the tree, through the real UI.

The user's report: "the AI designs it with a perfect feature tree, but if I want
to delete a sketch or an extrude it's not working". Every AI-authored tree is a
chain (sketch -> extrude tool -> cut, repeated), and the ✕ button used to answer
"cannot remove 'x': used by [...]" for every feature except the last one.

THE GESTURE IS TWO STEPS, and these tests drove the old one. Since the
strike-out mandate (2026-08-31, eb9f42e) the row's ✕ STRIKES the feature out —
the geometry goes, the row stays, no confirm, one click to take back — and the
struck row's ✕ is the permanent delete, which still asks first and still names
whatever must go with it. The five tests below asked for the one-step ✕ and had
been red from that day until 2026-09-16; the engine underneath never changed,
which `probes/tree_delete_e2e_probe.py` measures without a browser — the group,
the history repair and the undo are all still there.

Locks in, through the browser:
  1. strike then delete on a consumed SKETCH takes it away (with the features
     that cannot live without it) after a confirm that NAMES them;
  2. the same on a mid-chain cut reconnects the features below it — the design
     keeps building, one body, no orphan tool prism;
  3. cancelling the confirm leaves every row in place, and the strike is still
     one click from coming back;
  4. the Del key does the same two steps on the selected feature;
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


def row_of(page, fid):
    """One feature's row, BY ID. Never by name text: 'p0' is a substring of
    'p0_sketch', so a `has_text` locator answers with whichever of them the
    tree happens to draw first."""
    return page.locator(f"#tree .node[data-fid='{fid}'] .nrow").first


def click_strike(page, fid):
    """The row's ✕: the soft delete. The row actions appear on hover."""
    row = row_of(page, fid)
    row.hover()
    row.locator("button[title^='strike out']").click()
    page.wait_for_selector(f"#tree .node[data-fid='{fid}'].suppressed",
                           timeout=15000)


def click_delete(page, fid):
    """The whole gesture: strike it out, then delete the struck row for good.
    The caller answers the confirm."""
    click_strike(page, fid)
    row = row_of(page, fid)
    row.hover()
    row.locator("button[title^='delete permanently']").click()


def gone(fid):
    return ("() => ![...document.querySelectorAll('#tree .node')]"
            f".some(n => n.dataset.fid === '{fid}')")


def not_struck(fid):
    return ('() => !document.querySelector("#tree .node[data-fid=\'' + fid +
            '\']").classList.contains("suppressed")')


def test_deleting_a_consumed_sketch_asks_then_deletes_the_group(page, server,
                                                                fresh_doc):
    build(page, server)
    click_delete(page, "p0_sketch")
    seen = ask_ok(page)
    page.wait_for_function(gone("p0_sketch"), timeout=15000)

    assert seen, "deleting a feature others depend on must ask FIRST"
    # the confirm has to name what else goes, not just say 'are you sure'
    assert "p0_tool" in seen and "p0" in seen
    assert ids(server) == ["outline", "body", "p1_sketch", "p1_tool", "p1"]
    assert doc(server)["ok"]                      # and it still verifies
    assert not page.errors, page.errors


def test_deleting_a_mid_chain_cut_reconnects_the_rest(page, server, fresh_doc):
    # a boolean is FOLDED onto its tool's row, so the row a user can press for
    # the p0 pocket is p0_tool - there is no node with fid 'p0' at all, and
    # deleting that row takes the cut with it (measured in
    # probes/tree_delete_e2e_probe.py)
    build(page, server)
    click_delete(page, "p0_tool")
    ask_ok(page)
    page.wait_for_function(gone("p0_tool"), timeout=15000)

    d = doc(server)
    left = [f["id"] for f in d["features"] if f["id"].startswith("p0")]
    assert left == ["p0_sketch"]                  # the cut went with its prism
    p1 = next(f for f in d["features"] if f["id"] == "p1")
    assert p1["inputs"] == ["body", "p1_tool"]    # history repaired
    assert d["ok"]                                # one body, no orphan prism
    assert page.locator("#verifyBadge").inner_text().startswith("✓")
    assert not page.errors, page.errors


def test_cancelling_the_confirm_changes_nothing(page, server, fresh_doc):
    build(page, server)
    click_strike(page, "p0_sketch")
    row = row_of(page, "p0_sketch")
    row.hover()
    row.locator("button[title^='delete permanently']").click()
    ask_cancel(page)
    page.wait_for_timeout(1200)
    assert len(ids(server)) == 8

    # and the strike itself is still one click from coming back
    row = row_of(page, "p0_sketch")
    row.hover()
    row.locator("button[title^='restore']").click()
    page.wait_for_function(not_struck("p0_sketch"), timeout=15000)
    assert doc(server)["ok"]
    assert not page.errors, page.errors


def test_del_key_deletes_the_selected_feature(page, server, fresh_doc):
    build(page, server)
    row_of(page, "p1_sketch").click()
    page.keyboard.press("Delete")                 # first Del strikes it out
    page.wait_for_selector("#tree .node[data-fid='p1_sketch'].suppressed",
                           timeout=15000)
    # the selection SURVIVES the strike, so the same key deletes for good
    page.keyboard.press("Delete")
    ask_ok(page)
    page.wait_for_function(gone("p1_sketch"), timeout=15000)
    assert ids(server) == ["outline", "body", "p0_sketch", "p0_tool", "p0"]
    assert not page.errors, page.errors


def test_one_undo_restores_the_whole_group(page, server, fresh_doc):
    build(page, server)
    click_delete(page, "p0_sketch")
    ask_ok(page)
    page.wait_for_function(gone("p0_tool"), timeout=15000)
    page.keyboard.press("Control+z")
    page.wait_for_function(
        "() => [...document.querySelectorAll('#tree .node')]"
        ".some(n => n.dataset.fid === 'p0_tool')", timeout=15000)
    assert ids(server) == ["outline", "body", "p0_sketch", "p0_tool", "p0",
                           "p1_sketch", "p1_tool", "p1"]
    # one undo takes back the DELETE; the strike under it is its own step, so a
    # second one brings the geometry back
    page.keyboard.press("Control+z")
    page.wait_for_function(not_struck("p0_sketch"), timeout=15000)
    assert doc(server)["ok"]
    assert not page.errors, page.errors
