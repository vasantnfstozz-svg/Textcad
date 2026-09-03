"""E2E: Extrude's Combine-with target defaults to the body the sketch is ON.

Reported 2026-08-24 on the sat-side-panel design: the user sketched on their
part's face and extrude-CUT it, but the cut landed on 'blank' (the raw stock,
FIRST body in the tree) instead of the panel — so a "new body" appeared and
the part was untouched. Locked in: for a sketch_on_face profile the target
must default to the sketch's parent body, walked to its CURRENT state
(latest solid descendant), never to whatever body happens to be first.
"""
import httpx
import pytest

pytest.importorskip("playwright.sync_api")

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


def test_cut_targets_the_sketched_body(page, fresh_doc, server):
    # the user's situation in miniature: stock plate FIRST in the tree, the
    # actual part later, a sketch on the part's top face — and the part has
    # been modified since (with_center_hole), so the walk must land on the
    # part's CURRENT state, not the feature the sketch names.
    for fid, op, params, inputs in [
        ("blank", "plate", {"width": 100, "depth": 60, "thickness": 5}, []),
        ("part", "disc", {"radius": 15, "thickness": 10}, []),
        ("sk", "sketch_on_face",
         {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
          "entities": [{"kind": "circle", "r": 6}]}, ["part"]),
        ("part2", "with_center_hole", {"radius": 2}, ["part"]),
    ]:
        r = httpx.post(f"{server}/api/feature/add",
                       json={"id": fid, "op": op, "params": params,
                             "inputs": inputs}, timeout=120).json()
        assert not r.get("error"), r.get("error")
    page.reload(wait_until="domcontentloaded")
    page.wait_for_function("() => !!window.__vp", timeout=20000)
    page.wait_for_timeout(2000)

    # user flow: Select, click the sketch profile, Extrude
    page.evaluate("() => window.__vp.setPickMode(true)")     # picking on (default; explicit so the test cannot flip it off)
    page.wait_for_timeout(300)
    # on the circle profile — away from the center-hole rim (r=2) and the
    # sketch outline (r=6), both of which grab line-picks
    pt = page.evaluate(TO_SCREEN, [4, 1, 5])
    page.mouse.click(pt["x"], pt["y"])
    page.wait_for_timeout(600)
    page.click("#ribbon .rbtn[title='extrude']")
    page.wait_for_selector("#exOk", state="visible", timeout=15000)

    # THE FIX: target defaults to the sketched body's current state — not
    # 'blank', not the stale 'part'
    assert page.eval_on_selector("#exTarget", "el => el.value") == "part2"

    # finish the user's intent: a 1mm pocket (the box starts at 0 now, so a
    # depth must be typed; apply flips the positive value INTO the body)
    page.select_option("#exOp", "cut")
    page.wait_for_timeout(400)
    # R3 (P2): the typed depth creates the extrude AND its cut — two document
    # changes, ONE viewport refresh (holdViewport). The half-done state (a
    # floating tool prism) is never even fetched.
    model_fetches = []
    page.on("request", lambda r: model_fetches.append(r.url)
            if "/api/model" in r.url else None)
    page.evaluate("""() => {
      const d = document.getElementById('exDist');
      d.value = '1';
      d.dispatchEvent(new Event('input', { bubbles: true }));
    }""")
    # wait for the cut to EXIST (the tree folds it into the extrude's row, so
    # there is no row to wait for); the one model fetch follows the moment the
    # browser has both answers — a fixed wait raced a slow first rebuild
    for _ in range(80):
        if any(f["op"] == "cut" for f in
               httpx.get(f"{server}/api/doc", timeout=30).json()["features"]):
            break
        page.wait_for_timeout(250)
    page.wait_for_timeout(1500)
    assert len(model_fetches) == 1, model_fetches
    model_fetches.clear()
    page.click("#exOk")
    page.wait_for_timeout(4000)
    assert model_fetches == [], "OK with nothing left to apply must not refetch"

    doc = httpx.get(f"{server}/api/doc", timeout=30).json()
    cuts = [f for f in doc["features"]
            if f["op"] == "cut" and f["id"].startswith("extrude")]
    assert cuts, [(f["id"], f["op"]) for f in doc["features"]]
    assert cuts[0]["inputs"][0] == "part2", cuts[0]
    assert cuts[0]["status"] == "ok"
    # the pocket really removed material from the part (disc minus center
    # hole minus pocket < disc minus center hole)
    part2 = next(f for f in doc["features"] if f["id"] == "part2")
    assert cuts[0]["volume"] < part2["volume"]
    assert page.errors == []
