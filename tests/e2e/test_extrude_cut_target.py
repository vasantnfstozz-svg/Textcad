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
    page.click("#vSelect")
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

    # finish the user's intent: a 1mm pocket
    page.select_option("#exOp", "cut")
    page.wait_for_timeout(1500)                      # live rewire + rebuild
    page.click("#exOk")
    page.wait_for_timeout(4000)

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
