"""E2E: the Extrude dialog's OK COMMITS the panel values.

Reported 2026-08-21: "i have rocky logo sketch but i can[not] extrude it" —
the user traced a PNG into a sketch, picked the profile, opened Extrude and
pressed OK. The feature was only ever created by dragging the arrow or
editing an input, so an untouched panel closed with 'Nothing extruded'.
Locked in: pick profile -> Extrude -> OK (touch NOTHING) must produce a
real extrude feature at the panel's default distance.
"""
import base64

import httpx
import pytest

pytest.importorskip("playwright.sync_api")
cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

TO_SCREEN = """
(w) => {
  const vp = window.__vp;
  const cv = document.querySelector('#viewer canvas');
  const r = cv.getBoundingClientRect();
  const V3 = vp.camera.position.constructor;
  const v = new V3(w[0], w[1], w[2]).project(vp.camera);
  return { x: r.left + (v.x + 1) / 2 * r.width,
           y: r.top + (1 - (v.y + 1) / 2) * r.height };
}
"""


def _donut_b64():
    img = np.zeros((400, 400, 4), np.uint8)
    cv2.circle(img, (200, 200), 150, (10, 10, 10, 255), -1)
    cv2.circle(img, (200, 200), 60, (0, 0, 0, 0), -1)
    ok, buf = cv2.imencode(".png", img)
    assert ok
    return base64.b64encode(buf.tobytes()).decode()


def test_ok_with_untouched_defaults_extrudes(page, fresh_doc, server):
    # a traced sketch, exactly as the Trace PNG button makes one
    r = httpx.post(f"{server}/api/trace-png",
                   json={"png_base64": _donut_b64(), "feature_id": "logo",
                         "height_mm": 50}, timeout=120).json()
    assert not r.get("error"), r.get("error")
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(2500)

    # the user flow: Select mode, click the ring of the profile, Extrude, OK
    page.click("#vSelect")
    page.wait_for_timeout(300)
    pt = page.evaluate(TO_SCREEN, [0, -17, 0])       # inside the donut ring
    page.mouse.click(pt["x"], pt["y"])
    page.wait_for_timeout(600)
    page.click("#ribbon .rbtn[title='extrude']")
    page.wait_for_selector("#exOk", state="visible", timeout=15000)
    page.click("#exOk")                              # touch NOTHING else
    page.wait_for_timeout(4000)

    doc = httpx.get(f"{server}/api/doc", timeout=30).json()
    ext = [f for f in doc["features"] if f["op"] == "extrude"]
    assert ext, ("OK closed the dialog without creating an extrude feature: "
                 f"{[(f['id'], f['op']) for f in doc['features']]}")
    assert ext[0]["status"] == "ok"
    assert float(ext[0]["params"]["amount"]) == pytest.approx(1.0)
    assert page.errors == []
