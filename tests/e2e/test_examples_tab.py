"""E2E: File > Examples shows the user's own designs, and one click opens them.

User request (2026-08-26): "collect all those design put it under in the example
tab". Before this, that group held three code samples and the real work was
buried in File > Open beside t-washer and my-part-3.
"""
import httpx
import pytest

pytest.importorskip("playwright.sync_api")


def open_gallery(page):
    page.click("#tabstrip >> text=File")
    page.wait_for_timeout(250)
    page.click("#ribbon >> text=Examples")
    page.wait_for_selector("#exDialog[open]", timeout=15000)
    page.wait_for_selector(".excard", timeout=15000)


def test_the_gallery_lists_the_real_designs_in_groups(page, server, fresh_doc):
    open_gallery(page)
    groups = page.locator(".exgroup b").all_text_contents()
    assert len(groups) >= 5, groups
    cards = page.locator(".excard").count()
    assert cards >= 20, f"only {cards} designs in the gallery"
    # the ones the user named
    for f in ("esp32-remote", "pump-impeller", "autonomiq-sat-panel"):
        assert page.locator(f".excard[data-file='{f}']").count() == 1, f
    # every tile carries a real thumbnail, a description and a feature count
    assert page.locator(".exthumb img").count() == cards
    esp = page.locator(".excard[data-file='esp32-remote']")
    assert "ESP32" in esp.locator(".extitle").inner_text()
    assert esp.locator(".exdesc").inner_text().strip()
    # the count must track the design, not a literal that dies every revision
    n = next(d["features"] for g in httpx.get(f"{server}/api/examples",
                                              timeout=10).json()["groups"]
             for d in g["designs"] if d["file"] == "esp32-remote")
    assert f"{n} features" in esp.locator(".exmeta").inner_text().lower()
    assert not page.errors, page.errors


def test_thumbnails_actually_load(page, server, fresh_doc):
    open_gallery(page)
    page.wait_for_timeout(1500)
    broken = page.evaluate("""
      () => [...document.querySelectorAll('.exthumb img')]
              .filter(i => !i.complete || i.naturalWidth === 0)
              .map(i => i.getAttribute('src'))""")
    assert not broken, f"thumbnails failed to load: {broken}"
    assert not page.errors, page.errors


def test_clicking_a_design_opens_it_in_a_new_tab(page, server, fresh_doc):
    open_gallery(page)
    before = len(httpx.get(f"{server}/api/tabs", timeout=10).json()["tabs"])
    page.locator(".excard[data-file='pump-impeller']").click()
    # a closed <dialog> is hidden, so waiting for it to be "visible" never
    # succeeds — check the attribute instead
    page.wait_for_function(
        "() => !document.getElementById('exDialog').open", timeout=10000)
    page.wait_for_function(
        "() => window.__vp.sceneCounts().bodies > 0 && "
        "document.getElementById('busy').style.display !== 'flex'",
        timeout=180000)
    doc = httpx.get(f"{server}/api/doc", timeout=30).json()
    assert doc["name"] == "pump-impeller" and doc["ok"]
    assert len(doc["tabs"]) == before + 1
    # inner_text is CSS-transformed ("10 FEATURES"), so compare case-insensitively
    assert "10 features" in page.locator("#featCount").inner_text().lower()
    # and the chat says what was opened, with its description
    log = page.locator("#chatLog").inner_text()
    assert "pump-impeller" in log and "blade" in log.lower()
    assert not page.errors, page.errors


def test_only_the_gallery_is_left_in_examples(page, server, fresh_doc):
    """The three code samples were deleted (user, 2026-09-24: "delete
    impeller, flange and compressor, we do not need them"); the gallery of
    the user's own designs stays."""
    page.click("#tabstrip >> text=File")
    page.wait_for_timeout(250)
    assert page.locator("#ribbon .rbtn[title='Examples']").count() == 1
    for name in ("Flange", "Impeller", "Compressor"):
        assert page.locator(f"#ribbon .rbtn[title='{name}']").count() == 0, name
    assert not page.errors, page.errors
