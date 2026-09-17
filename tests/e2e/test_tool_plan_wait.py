"""E2E: a value typed before the plan lands is not lost (LAUNCH-PLAN.md R2).

Every geometric fact a new feature needs comes from POST /api/tool/plan — the
point Hole drills at, the edges Fillet rounds, Mirror's plane, Pattern's seed —
so nothing can be built in the moment between pressing the tool and the plan
coming back. Seven tools each wrote that rule into their own `isEmpty` as
`!st.plan ||` and each re-applied by hand in their `gizmos.begin`; the
framework owns it now (tool.js): applyOnce refuses to CREATE without a plan,
adoptPlan applies whatever is in the boxes the moment one lands, and OK waits
for a plan that is still in flight.

The last of those is new behaviour, and it is what these journeys pin down: a
user who presses the tool, types a number and hits OK straight away — faster
than the round trip — used to be told "Nothing hollowed" about a value they
had typed. Everything happens in ONE JavaScript turn here, so the plan cannot
possibly have arrived: the race is certain, not lucky.
"""
import time

import httpx
import pytest

pytest.importorskip("playwright.sync_api")

BUILD_BOX = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh, setView } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 60, depth: 40, thickness: 12 }, inputs: [] }, 'add');
  await loadMesh(true);
  setView('iso');
}
"""
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
TOP_PICKED = """
async () => {
  const { S } = await import('/static/js/state.js');
  return !!(S.pickedFace && S.pickedFace.normal && S.pickedFace.normal[2] > 0.9);
}
"""
# ONE JavaScript turn: press the ribbon button, type into the box, press OK.
# The plan is a network round trip, so it cannot have come back yet — whatever
# the machine's speed.
IN_ONE_TURN = """
([button, box, value, ok]) => {
  document.querySelector(button).click();
  const inp = document.getElementById(box);
  inp.value = value;
  inp.dispatchEvent(new Event('input', { bubbles: true }));
  if (ok) document.getElementById(ok).click();
  return !!inp.offsetParent;            // the panel opened synchronously
}
"""
PT = [10.0, 5.0, 6.0]                              # a point on the plate's top face


def features(server):
    return httpx.get(f"{server}/api/doc", timeout=30).json()["features"]


def feature(server, fid):
    return next((f for f in features(server) if f["id"] == fid), None)


def wait_param(server, fid, key, want, timeout=60, tol=1e-6):
    t0 = time.time()
    got = f = None
    while time.time() - t0 < timeout:
        f = feature(server, fid)
        got = f and f["params"].get(key)
        if (got is not None and abs(float(got) - want) <= tol
                and f["status"] in ("ok", "failed")):
            return f
        time.sleep(0.25)
    raise AssertionError(f"{fid}.{key} is {got!r}, not {want} ({f})")


def setup(page):
    page.evaluate(BUILD_BOX)
    page.wait_for_function("() => window.__vp.bodyCount() === 1", timeout=20000)
    page.wait_for_timeout(600)
    sp = page.evaluate(TO_SCREEN, PT)
    page.mouse.click(sp["x"], sp["y"])
    page.wait_for_function(TOP_PICKED, timeout=15000)


def test_ok_pressed_before_the_plan_lands_still_builds(page, fresh_doc, server):
    """Shell: press, type 3, OK — all before the plan can answer. The wall is
    3 mm, and OK says it was built rather than that nothing was."""
    setup(page)
    page.locator("button.tab", has_text="Modify").click()
    page.wait_for_timeout(150)
    assert page.evaluate(IN_ONE_TURN,
                         ["#ribbon .rbtn[title='shell']", "shThickness", "3", "shOk"])
    f = wait_param(server, "shell1", "thickness", 3)
    assert f["status"] == "ok", f
    assert f["volume"] == pytest.approx(60 * 40 * 12 - 54 * 34 * 9, rel=1e-4)
    page.wait_for_selector("#shellDialog", state="hidden", timeout=15000)
    log = page.text_content("#chatLog")
    assert "Nothing hollowed" not in log, "OK blamed the user for a value they typed"
    assert "Shell created" in log, log
    assert page.errors == []


def test_a_value_typed_before_the_plan_lands_builds_when_it_arrives(page, fresh_doc, server):
    """Hole: the same race without OK — the depth is typed in the tool's first
    turn, and the plan's arrival is what applies it (the hole's point on the
    face is the plan's, so there is nothing to build from until then)."""
    setup(page)
    assert page.evaluate(IN_ONE_TURN,
                         ["#ribbon .rbtn[title='hole']", "hoDepth", "4", None])
    f = wait_param(server, "hole1", "depth", 4)
    assert f["status"] == "ok" and f["params"]["at"], f
    assert page.is_visible("#holeDialog"), "the panel is still open: nothing was pressed"
    page.click("#hoOk")
    page.wait_for_selector("#holeDialog", state="hidden", timeout=15000)
    assert page.errors == []
