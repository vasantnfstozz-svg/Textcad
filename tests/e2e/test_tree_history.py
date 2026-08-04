"""E2E: the tree reads like a HISTORY (feature-tree workstream step 2).

Locks in, through the real UI:
  1. a consumed sketch nests as a CHILD row under the feature that used it
     (Fusion browser grouping), and renders after its consumer;
  2. double-clicking a feature's NAME renames it in place — references
     (the extrude's inputs) are rewritten, nothing breaks;
  3. a feature that fails to build SPEAKS: a human chat message appears,
     not just the red status dot;
  4. the Add Feature dialog suggests an id (fillet1 style) so the user
     never has to invent one.
"""
import time

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


def test_sketch_nests_under_its_consumer(server, page, fresh_doc):
    page.evaluate(BUILD)
    page.wait_for_selector("#tree .nrow >> text=ex1")
    sk_node = page.locator("#tree .node", has=page.locator(".nname", has_text="sk1"))
    assert "child" in sk_node.get_attribute("class"), \
        "consumed sketch must nest as a child of its extrude"
    # display order: the consumer first, its sketch nested after it
    names = page.locator("#tree .nname").all_text_contents()
    assert names.index("ex1") < names.index("sk1")
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
