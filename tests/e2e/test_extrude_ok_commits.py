"""E2E: the Extrude panel opens HONEST and works from the feature tree.

2026-08-21: "i have rocky logo sketch but i can[not] extrude it" — OK on an
untouched panel silently created nothing while the box claimed 1mm.
2026-09-01: the same traced-logo flow, three fixes locked in here:
  1. selecting the sketch IN THE TREE and pressing ribbon-Extrude must open
     the tool ON that sketch ("when I touch the sketch in the feature tree,
     it should also work");
  2. the distance box STARTS AT 0 — the truth: nothing is extruded until the
     user drags or types ("it should [start] from 0, even I am not
     extruding");
  3. OK at 0 creates nothing and SAYS so; typing a distance then OK creates
     the real extrude at that distance.
"""
import base64

import httpx
import pytest

pytest.importorskip("playwright.sync_api")
cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")


def _donut_b64():
    img = np.zeros((400, 400, 4), np.uint8)
    cv2.circle(img, (200, 200), 150, (10, 10, 10, 255), -1)
    cv2.circle(img, (200, 200), 60, (0, 0, 0, 0), -1)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return base64.b64encode(buf.tobytes()).decode()


def _row(page, fid):
    return page.locator("#tree .nrow",
                        has=page.locator(".nname", has_text=fid))


def test_tree_select_then_extrude_and_honest_zero(page, fresh_doc, server):
    # a traced sketch, exactly as the Trace Image button makes one
    r = httpx.post(f"{server}/api/trace-png",
                   json={"png_base64": _donut_b64(), "feature_id": "logo",
                         "height_mm": 50}, timeout=120).json()
    assert not r.get("error"), r.get("error")
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(2500)

    # 1. the user's flow: click the sketch ROW in the tree, press Extrude
    _row(page, "logo").click()
    page.wait_for_timeout(300)
    page.click("#ribbon .rbtn[title='extrude']")
    page.wait_for_selector("#exOk", state="visible", timeout=15000)
    assert page.evaluate("document.getElementById('exProfile').value") \
        == "logo", "tree-selected sketch must become the Extrude profile"

    # 2. the box tells the truth: nothing extruded yet -> 0
    assert page.evaluate("document.getElementById('exDist').value") == "0"

    # 3a. OK untouched: NO feature, and the chat says why
    page.click("#exOk")
    page.wait_for_timeout(2000)
    doc = httpx.get(f"{server}/api/doc", timeout=30).json()
    assert not [f for f in doc["features"] if f["op"] == "extrude"], \
        "OK at distance 0 must not invent geometry"
    assert "Nothing extruded" in page.text_content("#chatLog")

    # 3b. the tree's ⬆ also opens the tool; a typed distance + OK commits
    row = _row(page, "logo")
    row.hover()
    row.locator("button[title^='extrude this sketch']").click()
    page.wait_for_selector("#exOk", state="visible", timeout=15000)
    page.evaluate("""() => {
      const d = document.getElementById('exDist');
      d.value = '2';
      d.dispatchEvent(new Event('input', { bubbles: true }));
    }""")
    page.wait_for_timeout(1500)
    page.click("#exOk")
    page.wait_for_timeout(4000)

    doc = httpx.get(f"{server}/api/doc", timeout=30).json()
    ext = [f for f in doc["features"] if f["op"] == "extrude"]
    assert ext, ("OK closed the dialog without creating an extrude feature: "
                 f"{[(f['id'], f['op']) for f in doc['features']]}")
    assert ext[0]["status"] == "ok"
    assert float(ext[0]["params"]["amount"]) == pytest.approx(2.0)
    assert page.errors == []
