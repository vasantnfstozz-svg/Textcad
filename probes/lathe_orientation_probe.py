"""Run probes/lathe_orientation.html in headless Chromium and print what
three.js LatheGeometry does (rule 1: never call a three.js API from memory).

Result 2026-09-03 (three 0.160.0):
    quarter_from_0:   first [0, -1, 10] (on +Z), last [10, -1, 0] (on +X)
    quarter_negative: first [-10, -1, 0] (on -X), last [0, -1, 10] (on +Z)
    axis_is_local_y:  true
So a lathe sweeps from local +Z toward local +X about local +Y, i.e.
right-handed about +Y — the ghost's frame in viewport.beginRevolveGhost maps
local Y = the spin axis, local Z = the ring's x (radial, toward the material),
local X = the ring's y; a positive angle therefore turns the way the kernel's
positive revolution_arc does (probes/revolve_axis_probe.py, step 4).

Run: C:\\Python314\\python.exe probes\\lathe_orientation_probe.py
"""
import json
import pathlib

from playwright.sync_api import sync_playwright

page_path = pathlib.Path(__file__).with_name("lathe_orientation.html").resolve()
with sync_playwright() as pw:
    b = pw.chromium.launch()
    pg = b.new_page()
    pg.goto(page_path.as_uri())
    pg.wait_for_function("() => !document.getElementById('out').textContent.startsWith('probing')",
                         timeout=30000)
    out = json.loads(pg.text_content("#out"))
    b.close()
for k, v in out.items():
    print(f"{k}: {v}")
q = out["quarter_from_0"]
assert q["first"][2] > 9 and abs(q["first"][0]) < 1e-6, "φ=0 must start on local +Z"
assert q["last"][0] > 9 and abs(q["last"][2]) < 1e-6, "φ grows toward local +X"
assert out["axis_is_local_y"], "the lathe axis must be local Y"
print("LatheGeometry: +Z -> +X about +Y (right-handed), as the ghost assumes")
