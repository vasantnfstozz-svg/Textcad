"""E2E: Extrude on a FACE sketch picks Fusion's default operation from the
drag direction - out of the body = Join, into the body = Cut - and a session
never deletes the sketch it was opened on.

Reported 2026-09-08: a design with two bosses drawn on pocket floors and pulled
up was exported to STEP, and the other program said "3 solid bodies" and would
not edit it. The bosses had been left at "New body" (the Operation box opened
on 'new' for every sketch profile), so they were separate solids the user
never asked for. Fusion joins a profile that lies on a body when it is pulled
away and cuts when it is pushed in; "New body" is only for a free plane
sketch. Locked in here: the boss JOINS, the pocket CUTS, and a hand-picked
operation is kept.

Found while locking that in: the framework removed a session's combiner with
the DEFAULT delete mode, which repairs the tree by sweeping a cut's tool prism
and that prism's sketch. Switching Cut to anything else, or Cancel in a Cut
session, deleted the user's sketch and the extrude itself. Both go through
'strict' (that one node) now; the second test is the Cancel case.
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

TYPE_DIST = """(v) => {
  const d = document.getElementById('exDist');
  d.value = String(v);
  d.dispatchEvent(new Event('input', { bubbles: true }));
}"""


def _features(server):
    doc = httpx.get(f"{server}/api/doc", timeout=30).json()
    return [(f["id"], f["op"], f["inputs"], f["status"]) for f in doc["features"]]


def _combiners(server):
    return [f for f in _features(server) if f[1] in ("fuse", "cut", "intersect")]


def _wait_for(page, server, pred, what):
    for _ in range(80):
        combs = _combiners(server)
        if pred(combs):
            return combs
        page.wait_for_timeout(250)
    panel = page.evaluate("""() => ({ dist: document.getElementById('exDist').value,
        op: document.getElementById('exOp').value })""")
    raise AssertionError(f"{what}; features: {_features(server)}; panel: {panel}")


def _open_extrude_on_face_sketch(page, server):
    """A centred plate (top at z=5), a circle sketched on its top face, then
    the user flow: click the profile, press Extrude."""
    for fid, op, params, inputs in [
        ("base", "plate", {"width": 60, "depth": 40, "thickness": 10}, []),
        ("sk", "sketch_on_face",
         {"face_center": [0, 0, 5], "face_normal": [0, 0, 1],
          "entities": [{"kind": "circle", "r": 6}]}, ["base"]),
    ]:
        r = httpx.post(f"{server}/api/feature/add",
                       json={"id": fid, "op": op, "params": params,
                             "inputs": inputs}, timeout=120).json()
        assert not r.get("error"), r.get("error")
    page.reload(wait_until="domcontentloaded")
    page.wait_for_function("() => !!window.__vp", timeout=20000)
    page.wait_for_timeout(2000)
    page.evaluate("() => window.__vp.setPickMode(true)")
    page.wait_for_timeout(300)
    pt = page.evaluate(TO_SCREEN, [4, 1, 5])
    page.mouse.click(pt["x"], pt["y"])
    page.wait_for_timeout(600)
    page.click("#ribbon .rbtn[title='extrude']")
    page.wait_for_selector("#exOk", state="visible", timeout=15000)
    # the PROFILE was picked, not the plate's face (face mode has its own default)
    assert page.eval_on_selector("#exProfile", "el => el.value") == "sk"
    assert page.eval_on_selector("#exTarget", "el => el.value") == "base"


def test_face_sketch_extrude_joins_out_and_cuts_in(page, fresh_doc, server):
    _open_extrude_on_face_sketch(page, server)

    # 1. pulled OUT of the body (a boss): Join, on the body the sketch is on
    page.evaluate(TYPE_DIST, 5)
    combs = _wait_for(page, server, lambda c: any(f[1] == "fuse" and f[3] == "ok" for f in c),
                      "a boss pulled off a face must JOIN its body")
    assert page.eval_on_selector("#exOp", "el => el.value") == "join"
    fuse = next(f for f in combs if f[1] == "fuse")
    assert fuse[2][0] == "base" and fuse[3] == "ok", fuse
    assert [f[1] for f in combs] == ["fuse"], combs

    # 2. pushed INTO the body (a pocket): the Join is rewired to a Cut
    page.evaluate(TYPE_DIST, -2)
    combs = _wait_for(page, server, lambda c: [(f[1], f[3]) for f in c] == [("cut", "ok")],
                      "a profile pushed into its body must CUT it")
    assert page.eval_on_selector("#exOp", "el => el.value") == "cut"
    assert combs[0][2][0] == "base" and combs[0][3] == "ok", combs

    # 3. the user's own choice wins: New body stays New body whichever way -
    #    and leaving Cut must not take the extrude or the sketch with it
    page.select_option("#exOp", "new")
    _wait_for(page, server, lambda c: c == [], "New body chosen by hand must drop the cut")
    ids = [f[0] for f in _features(server)]
    assert "sk" in ids and "extrude1" in ids, ids
    page.evaluate(TYPE_DIST, 4)
    page.wait_for_timeout(2500)
    assert _combiners(server) == [], "a hand-picked operation must not be overridden"
    assert page.eval_on_selector("#exOp", "el => el.value") == "new"

    page.click("#exOk")
    page.wait_for_timeout(2500)
    doc = httpx.get(f"{server}/api/doc", timeout=30).json()
    ex = [f for f in doc["features"] if f["op"] == "extrude"]
    assert len(ex) == 1 and ex[0]["status"] == "ok", ex
    assert ex[0]["params"]["amount"] == 4, ex[0]["params"]
    assert doc["bodies"] == 2, doc["bodies"]           # the New body the user asked for
    assert page.errors == []


def test_cancel_of_a_cut_session_keeps_the_sketch(page, fresh_doc, server):
    _open_extrude_on_face_sketch(page, server)
    page.evaluate(TYPE_DIST, -3)                       # into the body: a Cut
    _wait_for(page, server, lambda c: [(f[1], f[3]) for f in c] == [("cut", "ok")],
              "a profile pushed into its body must CUT it")
    page.click("#exCancel")
    page.wait_for_timeout(2500)
    feats = _features(server)
    assert [f[0] for f in feats] == ["base", "sk"], feats     # the sketch survives Cancel
    assert all(f[3] == "ok" for f in feats), feats
    assert page.errors == []
