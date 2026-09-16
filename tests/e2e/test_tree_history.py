"""E2E: the tree reads like a HISTORY (feature-tree workstream step 2).

Locks in, through the real UI:
  1. a consumed sketch and the feature that used it are one nested pair
     (Fusion browser grouping): the sketch owns the row, its consumer is the
     CHILD, and the sketch is drawn first;
  2. double-clicking a feature's NAME renames it in place — references
     (the extrude's inputs) are rewritten, nothing breaks;
  3. a feature that fails to build SPEAKS: a human chat message appears,
     not just the red status dot;
  4. the Add Feature dialog suggests an id (fillet1 style) so the user
     never has to invent one.
"""

import httpx
import pytest

pytest.importorskip("playwright.sync_api")

BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'sk1', op: 'sketch',
      params: { plane: 'XY', offset: 0,
                entities: [{ kind: 'rectangle', w: 30, h: 20,
                             x: 0, y: 0, mode: 'add' }] }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'ex1', op: 'extrude', params: { amount: 12 }, inputs: ['sk1'] }, 'add');
  await loadMesh(true);
}
"""

BUILD_FAILING_FILLET = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'base1', op: 'plate',
      params: { width: 40, depth: 30, thickness: 10 }, inputs: [] }, 'add');
  await loadMesh(true);
  await postJSON('/api/feature/add',
    { id: 'fillet1', op: 'fillet',
      params: { radius: 200, edges: 'all' }, inputs: ['base1'] }, 'add');
}
"""


def feats(url):
    return httpx.get(f"{url}/api/doc", timeout=5).json()["features"]


def test_sketch_nests_with_its_consumer(server, page, fresh_doc):
    page.evaluate(BUILD)
    page.wait_for_selector("#tree .nrow >> text=ex1")
    # the SKETCH owns the row and its consumer is the indented one (tree.js
    # renderDoc). It used to be the other way round; the pair must stay
    # together either way, which is what this locks in.
    ex_node = page.locator("#tree .node[data-fid='ex1']")
    assert "child" in ex_node.get_attribute("class"), \
        "an extrude must nest as a child of the sketch it consumed"
    sk_node = page.locator("#tree .node[data-fid='sk1']")
    assert "child" not in sk_node.get_attribute("class")
    # creation order (user mandate R4): the sketch FIRST, its consumer below
    names = page.locator("#tree .nname").all_text_contents()
    assert names.index("sk1") < names.index("ex1")
    assert not page.errors, page.errors


def test_no_suppress_or_rollback_actions(server, page, fresh_doc):
    """User mandate R5: suppress + rollback are gone from the tree UI."""
    page.evaluate(BUILD)
    page.wait_for_selector("#tree .nrow >> text=ex1")
    page.locator("#tree .nrow", has_text="ex1").hover()
    assert page.locator("#tree button[title*='suppress']").count() == 0
    assert page.locator("#tree button[title*='roll back']").count() == 0
    assert page.locator("#tree .rollbar").count() == 0
    assert not page.errors, page.errors


def test_edit_sketch_isolates_model(server, page, fresh_doc):
    """User mandate R3 (Fusion): editing a sketch rolls the model back to it —
    the consuming extrude's body vanishes while editing, and returns after
    Finish Sketch."""
    page.evaluate(BUILD)
    page.wait_for_selector("#tree .nrow >> text=ex1")
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)

    row = page.locator("#tree .nrow",
                       has=page.locator(".nname", has_text="sk1"))
    row.hover()
    row.locator("button[title^='edit this sketch']").click()
    page.wait_for_function("() => window.__vp.bodyCount() === 0", timeout=20000)
    doc = httpx.get(f"{server}/api/doc", timeout=5).json()
    assert doc["rollback"] == "sk1", "edit must roll back to the sketch"

    page.click("#ribbon .rbtn[title='Finish Sketch']")
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    doc = httpx.get(f"{server}/api/doc", timeout=5).json()
    assert doc["rollback"] is None, "finish must release the rollback"
    f = next(x for x in doc["features"] if x["id"] == "ex1")
    assert f["status"] == "ok"
    assert not page.errors, page.errors


def test_selected_sketch_highlights(server, page, fresh_doc):
    """User mandate R3a: clicking a consumed sketch row colors it in the
    viewport (needs the per-sketch mesh endpoint — STL can't do sketches)."""
    page.evaluate(BUILD)
    page.wait_for_selector("#tree .nrow >> text=sk1")
    m = httpx.get(f"{server}/api/sketch-mesh/sk1", timeout=10).json()
    assert m.get("outlines"), "consumed sketch must still tessellate"
    page.locator("#tree .nrow",
                 has=page.locator(".nname", has_text="sk1")).click()
    page.wait_for_timeout(600)
    assert not page.errors, page.errors


def test_rename_via_name_dblclick(server, page, fresh_doc):
    page.evaluate(BUILD)
    page.wait_for_selector("#tree .nrow >> text=ex1")
    name = page.locator("#tree .nname", has_text="sk1")
    name.dblclick()
    box = page.locator("#tree .nname input")
    box.fill("base_profile")
    box.press("Enter")
    page.wait_for_selector("#tree .nname >> text=base_profile")
    fs = {f["id"]: f for f in feats(server)}
    assert "base_profile" in fs and "sk1" not in fs
    assert fs["ex1"]["inputs"] == ["base_profile"], "references must follow"
    assert fs["ex1"]["status"] == "ok"
    assert not page.errors, page.errors


def test_failed_feature_speaks_in_chat(server, page, fresh_doc):
    page.evaluate(BUILD_FAILING_FILLET)
    page.wait_for_selector("#tree .ndot.failed")
    log = page.text_content("#chatLog")
    assert 'Feature "fillet1"' in log and "failed to build" in log, \
        f"failure must produce a human chat message, got: {log[-400:]}"
    assert not page.errors, page.errors


def test_add_feature_dialog_suggests_id(server, page, fresh_doc):
    page.evaluate(BUILD_FAILING_FILLET)      # existing fillet1 forces fillet2
    page.wait_for_selector("#tree .ndot.failed")
    page.evaluate("""async () => {
      const { openFeatDialog } = await import('/static/js/dialogs.js');
      await openFeatDialog('fillet');
    }""")
    assert page.input_value("#featId") == "fillet2", \
        "dialog must auto-suggest the next free op-numbered id"
    assert not page.errors, page.errors
