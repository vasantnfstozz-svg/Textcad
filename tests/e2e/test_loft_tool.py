"""E2E: Loft — the second Tier 2 tool and the framework's first multi-input
tool (LAUNCH-PLAN.md §4, specs/loft.md). Real clicks; the built volume is
checked against the kernel's own exact figures for a cylinder.
"""
import math

import httpx
import pytest

pytest.importorskip("playwright.sync_api")

R = 5.0
CYL = math.pi * R * R * 20          # a: circle r5 at z 6, c: circle r5 at z 26

# a plate, a circle on its top face (z 6), a circle 20 above it (z 26) and a
# small circle between them (z 16)
BUILD = """
async () => {
  const { postJSON } = await import('/static/js/api.js');
  const { loadMesh, setView } = await import('/static/js/viewport.js');
  await postJSON('/api/feature/add',
    { id: 'b', op: 'plate', params: { width: 60, depth: 40, thickness: 12 }, inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'a', op: 'sketch_on_face',
      params: { face: 'top', offset: 0, entities: [{ kind: 'circle', r: 5, mode: 'add' }] },
      inputs: ['b'] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'c', op: 'sketch',
      params: { plane: 'XY', offset: 26, entities: [{ kind: 'circle', r: 5, mode: 'add' }] },
      inputs: [] }, 'add');
  await postJSON('/api/feature/add',
    { id: 'm', op: 'sketch',
      params: { plane: 'XY', offset: 16, entities: [{ kind: 'circle', r: 2, mode: 'add' }] },
      inputs: [] }, 'add');
  await loadMesh(true);
  setView('iso');
}
"""


def row(page, fid):
    return page.locator("#tree .nrow", has=page.locator(".nname", has_text=fid))


def open_loft(page, fid):
    r = row(page, fid)
    r.hover()
    r.locator("button[title^='loft this sketch']").click()
    page.wait_for_selector("#loftDialog", state="visible", timeout=15000)
    page.wait_for_timeout(800)


def feature(server, fid):
    doc = httpx.get(f"{server}/api/doc", timeout=30).json()
    return next((f for f in doc["features"] if f["id"] == fid), None)


def wait_feature(page, server, fid, timeout_ms=15000):
    for _ in range(timeout_ms // 200):
        f = feature(server, fid)
        if f and f["status"] in ("ok", "failed"):
            return f
        page.wait_for_timeout(200)
    raise AssertionError(f"{fid} never built")


def listed(page):
    return page.eval_on_selector_all("#lfList .lfrow span", "els => els.map(e => e.textContent)")


def setup(page, build):
    page.evaluate(build)
    page.wait_for_timeout(1500)


def test_open_from_the_row_and_add_a_second_profile_from_the_tree(page, fresh_doc, server):
    """One profile: a ring, nothing built. A tree row click adds the second
    and the verified cylinder appears at exactly pi r^2 h."""
    setup(page, BUILD)
    open_loft(page, "a")
    assert listed(page) == ["a"]
    g = page.evaluate("() => window.__vp.gizmos()")
    assert g["loft"], g
    info = page.evaluate("async () => (await import('/static/js/viewport.js')).loftGhostInfo()")
    assert info["rings"] == 1 and info["triangles"] == 0, info
    assert page.evaluate("() => window.__vp.bodyCount()") == 1, "one profile builds nothing"
    assert feature(server, "loft1") is None
    assert page.eval_on_selector_all("#lfAdd option", "els => els.map(e => e.value)") == ["", "m", "c"]

    row(page, "c").locator(".nname").click()                 # the tree is a selection surface
    f = wait_feature(page, server, "loft1")
    assert f["status"] == "ok", f["problems"]
    assert f["inputs"] == ["a", "c"] and f["params"] == {"ruled": False}
    assert f["volume"] == pytest.approx(CYL, rel=1e-4)
    assert listed(page) == ["a", "c"]
    assert not page.evaluate("() => window.__vp.gizmos()")["loft"], "the solid replaced the ghost"
    assert not page.errors, page.errors


def test_add_list_ruled_ok_then_edit_and_cancel(page, fresh_doc, server):
    setup(page, BUILD)
    open_loft(page, "a")
    page.select_option("#lfAdd", "c")
    f = wait_feature(page, server, "loft1")
    assert f["status"] == "ok" and f["volume"] == pytest.approx(CYL, rel=1e-4)
    page.check("#lfRuled")
    page.wait_for_timeout(1200)
    f = feature(server, "loft1")
    assert f["params"]["ruled"] is True and f["status"] == "ok"
    page.click("#lfOk")
    page.wait_for_selector("#loftDialog", state="hidden", timeout=15000)
    page.wait_for_timeout(500)
    assert "Loft created" in page.text_content("#chatLog")
    doc = httpx.get(f"{server}/api/doc", timeout=30).json()
    assert doc["bodies"] == 2, "New body: the plate and the loft"

    row(page, "loft1").dblclick()
    page.wait_for_selector("#loftDialog", state="visible", timeout=15000)
    page.wait_for_timeout(800)
    assert listed(page) == ["a", "c"] and page.is_checked("#lfRuled")
    assert page.locator("#lfList button").count() == 0, "an edit does not rewire the sections"
    page.uncheck("#lfRuled")
    page.wait_for_timeout(1200)
    page.click("#lfCancel")
    page.wait_for_selector("#loftDialog", state="hidden", timeout=15000)
    page.wait_for_timeout(500)
    f2 = feature(server, "loft1")
    assert f2["params"]["ruled"] is True and f2["volume"] == f["volume"]
    assert not page.errors, page.errors


def test_out_of_order_picks_are_put_in_order_and_said(page, fresh_doc, server):
    """a (z 6), then c (z 26), then m (z 16): the kernel would fold that
    through itself and call it valid; the tool orders them a, m, c."""
    setup(page, BUILD)
    open_loft(page, "a")
    page.select_option("#lfAdd", "c")
    wait_feature(page, server, "loft1")
    page.select_option("#lfAdd", "m")
    page.wait_for_timeout(1500)
    f = feature(server, "loft1")
    assert f["inputs"] == ["a", "m", "c"], f["inputs"]
    assert f["status"] == "ok", f["problems"]
    assert listed(page) == ["a", "m", "c"]
    assert "order they lie" in page.text_content("#chatLog")
    # honest volume: two frusta, not the folded 1.98x
    frustum = lambda r1, r2, h: math.pi * h / 3 * (r1 * r1 + r1 * r2 + r2 * r2)
    assert f["volume"] < 2 * frustum(5, 2, 10) * 1.05
    # ✕ takes the middle one out again: back to the cylinder
    page.locator("#lfList .lfrow", has_text="m").locator("button").click()
    page.wait_for_timeout(1500)
    f = feature(server, "loft1")
    assert f["inputs"] == ["a", "c"] and f["volume"] == pytest.approx(CYL, rel=1e-4)
    assert not page.errors, page.errors
