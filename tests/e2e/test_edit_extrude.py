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
    """Poll until the feature's param reaches value AND the rebuild finished.
    Sync endpoints run in a threadpool, so /api/doc can observe the param
    already written while the rebuild is still running (status 'stale',
    volume from the previous build) — trusting that snapshot is a race."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        f = feat(url, fid)
        if (abs(float(f["params"].get(param, 0)) - value) < 1e-9
                and f["status"] == "ok"):
            return f
        time.sleep(0.2)
    raise AssertionError(
        f"{fid}.{param} never became {value} with status ok; "
        f"last: {f['params']} status={f['status']}")


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


# --------------------------------------------------------------------------
# User 2026-09-07: "I am extruding a sketch to 12 mm, I change it to 0 and
# remove the 12, but it reloads 12 instead of 0 — for extrude and revolve."
# A 0 with a preview up used to be PUSHED: the kernel refused the
# zero-thickness solid and the framework's revert wrote the old value back
# into the box the user had just emptied. Honest zero now: in create mode the
# preview goes and the box keeps its 0; an edit keeps its feature and says why.

BUILD_SKETCH_ONLY = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'sk1', op: 'sketch',
      params: { plane: 'XY', offset: 0,
                entities: [{ kind: 'rectangle', w: 30, h: 20,
                             x: 0, y: 0, mode: 'add' }] },
      inputs: [] }, 'add');
  await loadMesh(true);
}
"""


def extrudes(url):
    doc = httpx.get(f"{url}/api/doc", timeout=5).json()
    return [f for f in doc["features"] if f["op"] == "extrude"]


def wait_extrudes(url, ok, timeout=15):
    """poll until `ok(list of extrude features)` holds; return that list"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        fs = extrudes(url)
        if ok(fs):
            return fs
        time.sleep(0.2)
    raise AssertionError(f"extrude features never reached the expected state: {fs}")


def test_typing_zero_removes_the_preview_and_keeps_the_box_at_zero(server, page, fresh_doc):
    page.evaluate(BUILD_SKETCH_ONLY)
    page.wait_for_selector("#tree .nrow >> text=sk1")
    row = page.locator("#tree .nrow", has_text="sk1")
    row.hover()
    row.locator("button[title^='extrude this sketch']").click()
    page.wait_for_selector("#extrudeDialog", state="visible")
    page.wait_for_function("() => window.__vp.gizmos().arrow", timeout=15000)   # the plan is in

    page.fill("#exDist", "12")
    wait_extrudes(server, lambda fs: len(fs) == 1 and fs[0]["status"] == "ok"
                  and float(fs[0]["params"]["amount"]) == 12)

    page.fill("#exDist", "0")                    # cleared to retype it
    wait_extrudes(server, lambda fs: fs == [])   # the preview is gone...
    page.wait_for_timeout(500)
    assert page.input_value("#exDist") == "0", "the box must keep the 0 the user typed"
    assert "Reverted" not in page.text_content("#chatLog"), "a 0 is not a broken solid"
    assert page.locator("#extrudeDialog").is_visible(), "the tool stays open"

    page.fill("#exDist", "8")                    # ...and a new value builds again
    fs = wait_extrudes(server, lambda fs: len(fs) == 1 and fs[0]["status"] == "ok"
                       and float(fs[0]["params"]["amount"]) == 8)
    assert abs(fs[0]["volume"] - 30 * 20 * 8) < 1.0

    page.click("#exOk")
    page.wait_for_selector("#extrudeDialog", state="hidden")
    fs = extrudes(server)
    assert len(fs) == 1 and float(fs[0]["params"]["amount"]) == 8, fs
    assert "Extrude created" in page.text_content("#chatLog")
    assert not page.errors, page.errors


def test_zero_in_edit_keeps_the_feature_and_says_why(server, page, fresh_doc):
    page.evaluate(BUILD_SKETCH_EXTRUDE)
    page.wait_for_selector("#tree .nrow >> text=ex1")
    open_edit(page, "ex1")
    page.wait_for_function("() => window.__vp.gizmos().arrow", timeout=15000)   # the plan is in

    page.fill("#exDist", "0")
    page.wait_for_timeout(1500)                  # the debounce and any rebuild it would start
    assert page.input_value("#exDist") == "0", "the box must keep the 0 the user typed"
    f = feat(server, "ex1")
    assert f["status"] == "ok" and float(f["params"]["amount"]) == 12,         "an edit at 0 keeps the feature as it was — nothing is pushed"
    chat = page.text_content("#chatLog")
    assert "nothing can be built" in chat and "12mm" in chat, chat
    assert "Reverted" not in chat

    page.click("#exCancel")
    page.wait_for_selector("#extrudeDialog", state="hidden")
    f = wait_param(server, "ex1", "amount", 12)
    assert abs(f["volume"] - 30 * 20 * 12) < 1.0
    assert not page.errors, page.errors
