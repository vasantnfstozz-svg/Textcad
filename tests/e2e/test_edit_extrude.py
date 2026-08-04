"""E2E: Edit Feature for extrude — the tree's ✎ reopens the REAL Extrude tool
on an existing feature (feature-tree workstream, R2a north star: every feature
re-openable with the tool that created it).

Locks in, through the real UI entry point:
  1. ✎ on an extrude row opens the dialog SEEDED with the feature's params
     (not the create-mode defaults), profile/operation rows locked;
  2. typing a new distance edits the feature in place (verified rebuild —
     the feature's params and volume actually change);
  3. OK keeps the change;
  4. Cancel restores the ORIGINAL params exactly — including params the
     session added (a taper typed mid-edit must reset to 0, not linger).
"""
import time

import httpx
import pytest

pytest.importorskip("playwright.sync_api")

BUILD_SKETCH_EXTRUDE = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'sk1', op: 'sketch',
      params: { plane: 'XY', offset: 0,
                entities: [{ kind: 'rectangle', w: 30, h: 20,
                             x: 0, y: 0, mode: 'add' }] },
      inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'ex1', op: 'extrude', params: { amount: 12 }, inputs: ['sk1'] },
    'add');
  await loadMesh(true);
}
"""

BUILD_FACE_EXTRUDE = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'base', op: 'plate',
      params: { width: 60, depth: 40, thickness: 20 }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'boss', op: 'extrude_face',
      params: { face_center: [0, 0, 10], face_normal: [0, 0, 1], amount: 8 },
      inputs: ['base'] }, 'add');
  await loadMesh(true);
}
"""


def feat(url, fid):
    doc = httpx.get(f"{url}/api/doc", timeout=5).json()
    return next(f for f in doc["features"] if f["id"] == fid)


def wait_param(url, fid, param, value, timeout=15):
    """Poll until the feature's param reaches value (debounce + rebuild)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        f = feat(url, fid)
        if abs(float(f["params"].get(param, 0)) - value) < 1e-9:
            return f
        time.sleep(0.2)
    raise AssertionError(
        f"{fid}.{param} never became {value}; last: {f['params']}")


def open_edit(page, fid):
    row = page.locator("#tree .nrow", has_text=fid)
    row.hover()                        # row actions only show on :hover
    row.locator("button[title^='edit this extrude']").click()
    page.wait_for_selector("#extrudeDialog", state="visible")


def test_edit_seeds_and_applies(server, page, fresh_doc):
    page.evaluate(BUILD_SKETCH_EXTRUDE)
    page.wait_for_selector("#tree .nrow >> text=ex1")

    open_edit(page, "ex1")
    # seeded with the FEATURE's values, not create-mode defaults
    assert page.input_value("#exDist") == "12"
    assert "Edit ex1" in page.text_content("#extrudeDialog .exhead")
    assert page.locator("#exProfile").is_disabled(), "profile must be locked"
    assert page.locator("#exOp").is_disabled(), "operation must be locked"

    page.fill("#exDist", "25")
    f = wait_param(server, "ex1", "amount", 25)
    assert abs(f["volume"] - 30 * 20 * 25) < 1.0, "edit did not rebuild"

    page.click("#exOk")
    page.wait_for_selector("#extrudeDialog", state="hidden")
    assert float(feat(server, "ex1")["params"]["amount"]) == 25, \
        "OK must keep the edit"
    assert not page.errors, page.errors


def test_cancel_restores_original(server, page, fresh_doc):
    page.evaluate(BUILD_SKETCH_EXTRUDE)
    page.wait_for_selector("#tree .nrow >> text=ex1")

    open_edit(page, "ex1")
    page.fill("#exDist", "40")
    page.fill("#exTaper", "5")             # a param the feature did NOT have
    wait_param(server, "ex1", "amount", 40)

    page.click("#exCancel")
    page.wait_for_selector("#extrudeDialog", state="hidden")
    f = wait_param(server, "ex1", "amount", 12)   # original restored
    assert float(f["params"].get("taper", 0)) == 0, \
        "cancel must reset params the session added"
    assert abs(f["volume"] - 30 * 20 * 12) < 1.0
    assert not page.errors, page.errors


def test_edit_face_extrude(server, page, fresh_doc):
    page.evaluate(BUILD_FACE_EXTRUDE)
    page.wait_for_selector("#tree .nrow >> text=boss")

    open_edit(page, "boss")
    assert page.input_value("#exDist") == "8"
    assert page.locator("#exDir").is_disabled(), \
        "face extrude is one-directional"

    page.fill("#exDist", "15")
    f = wait_param(server, "boss", "amount", 15)
    assert abs(f["volume"] - 60 * 40 * 15) < 1.0

    page.click("#exCancel")
    page.wait_for_selector("#extrudeDialog", state="hidden")
    f = wait_param(server, "boss", "amount", 8)
    assert abs(f["volume"] - 60 * 40 * 8) < 1.0
    assert not page.errors, page.errors
