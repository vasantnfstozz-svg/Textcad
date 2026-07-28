---
name: ui-verify
description: Visually verify a Studio UI change with Playwright — launch the app in a real browser, click the actual feature, screenshot it, and LOOK at the result. Run after ANY frontend change before claiming it works; also the tool for dogfooding sessions.
---

# UI-verify — see it before you say it works

Numeric tests can pass while the UI is broken. This routine makes the change
visible. It complements ship-check (which covers tests/API); this covers eyes.

## Prereqs (already installed)

- Python Playwright: `C:\Python314\python.exe -m playwright --version`
  (if missing: `pip install playwright` + `python -m playwright install chromium`)
- Studio running: FIRST check if one already answers
  (`Invoke-RestMethod http://127.0.0.1:8123/api/doc`) — launching a second
  `python studio.py` fails with a port-bind error (exit 3). If the running server
  is the user's and backend code changed, ask before killing it; if backend is
  unchanged, just reuse it (but remember your POSTs are visible in their open tab).
  Otherwise launch `C:\Python314\python.exe studio.py` in background, wait ~15s.
- Cache-buster bumped (`main.js?v=N` in static/index.html) if JS/CSS changed.
  A fresh Playwright context has no cache, but the USER's browser does — the bump
  is for them, not for the test.

## The routine

1. Write a probe script in the scratchpad (template below). Drive the REAL flow a
   user would: click the ribbon button, fill the dialog, hit Create — not just load
   the page.
2. Screenshot at each meaningful step into the scratchpad.
3. **Read every screenshot with the Read tool and actually look at it.** Check the
   thing you changed, and also: busy overlay gone? status bar sane? tree populated?
4. Capture `page.on("console")` — any `error` message = failure even if the page
   "looks" fine.
5. Anything off that you are not fixing right now → add to BACKLOG.md immediately.

## Template

```python
from playwright.sync_api import sync_playwright

SHOT = r"<scratchpad>\shot_{}.png"
errors = []
with sync_playwright() as p:
    b = p.chromium.launch()  # headless
    page = b.new_page(viewport={"width": 1600, "height": 900})
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto("http://127.0.0.1:8123", wait_until="networkidle")
    page.wait_for_timeout(2500)          # let three.js render the model
    page.screenshot(path=SHOT.format(1), full_page=True)
    # ... click ribbon buttons / dialogs here (ids in static/index.html) ...
    b.close()
print("console errors:", errors or "none")
```

## Selector notes (probe static/index.html when unsure)

- Ribbon tool tabs: `#tabstrip` items; ribbon buttons live in `#ribbon`.
- Feature tree rows: `.prow`; inline-editable values are the blue spans.
- Dialogs: `#featDialog`, `#sketchDialog`, `#specDialog`; sketch canvas `#skCanvas`.
- Busy overlay blocks clicks while rebuilding — wait for it to disappear before
  the next action.
- The viewport is WebGL (three.js): headless Chromium renders it fine, but give it
  ~2s after load/rebuild before screenshotting or it may be blank.

## Dogfooding mode

Same tooling, different goal: build a real part start-to-finish using ONLY UI
clicks (no API shortcuts). Every hesitation, missing tool, or confusing moment is
a BACKLOG.md entry — the point is to find friction, not to succeed quickly.
