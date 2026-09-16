"""Section 12 round SIX — the SERVER half of round five, put to the test.

Round five folded two middlewares onto one _addressed_tab() rule and made
every answer name the tab it is ABOUT. Both are cheap to assert and expensive
to get wrong, so this probe walks the full matrix instead of reading it:

  F. the one-writer-per-tab guard, with and without a header, with a stale
     header, and with a header naming the busy tab
  G. the consequences of "two windows now hold independent tabs": the session
     checkpoint, MAX_TABS, and two tabs on one design file
  H. every response label a page reads back

Writes nothing outside a temp history root and starts no server.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

import studio  # noqa: E402

EDIT = {"feature_id": "base", "param": "thickness", "value": 77}
PLATE = {"id": "base", "op": "plate", "inputs": [],
         "params": {"width": 20, "depth": 20, "thickness": 5}}


def fresh():
    studio.STATE["docs"].clear()
    studio.STATE["active"] = None
    studio.STATE["seq"] = 0
    studio.JOBS.clear()
    c = TestClient(studio.app)
    a = c.post("/api/new", json={}).json()["active_tab"]
    c.post("/api/feature/add", json=PLATE)
    b = c.post("/api/new", json={}).json()["active_tab"]
    c.post("/api/feature/add", json=PLATE)
    return c, a, b


def thick(tid):
    return studio.STATE["docs"][tid]["doc"].features[0].params["thickness"]


def main():
    print("=" * 74)
    print("F. one writer per tab — the AI is building in the tab the server")
    print("   calls active; who may still write?")
    print("=" * 74)
    rows = [
        ("no header at all", None),
        ("header = the QUIET tab (the page's own)", "quiet"),
        ("header = the BUSY tab", "busy"),
        ("header = a tab that is NOT open (stale / post-restart)", "t-gone"),
    ]
    for label, which in rows:
        c, quiet, busy = fresh()
        studio.STATE["active"] = busy
        studio.JOBS["j"] = {"id": "j", "tab": busy, "done": False}
        h = {}
        if which == "quiet":
            h = {"X-TextCAD-Tab": quiet}
        elif which == "busy":
            h = {"X-TextCAD-Tab": busy}
        elif which == "t-gone":
            h = {"X-TextCAD-Tab": "t-gone"}
        r = c.post("/api/edit", json=EDIT, headers=h)
        verdict = "REFUSED" if r.status_code == 400 else f"ALLOWED -> {r.status_code}"
        print(f"  {label:54s} {verdict:16s} "
              f"quiet={thick(quiet)} busy={thick(busy)}")
        studio.JOBS.clear()

    print()
    print("  the same four while NOTHING is building (nothing may be refused):")
    for label, which in rows:
        c, quiet, busy = fresh()
        studio.STATE["active"] = busy
        h = {}
        if which == "quiet":
            h = {"X-TextCAD-Tab": quiet}
        elif which == "busy":
            h = {"X-TextCAD-Tab": busy}
        elif which == "t-gone":
            h = {"X-TextCAD-Tab": "t-gone"}
        r = c.post("/api/edit", json=EDIT, headers=h)
        print(f"  {label:54s} {r.status_code:<16} "
              f"quiet={thick(quiet)} busy={thick(busy)}")

    print()
    print("=" * 74)
    print("G. two windows, independent tabs — what the shared server still owes")
    print("=" * 74)
    c, w1, w2 = fresh()
    studio.STATE["active"] = w2                 # window 2 switched last
    # the session checkpoint is the SERVER's, not a window's
    tabs = [{"id": tid, "active": tid == studio.STATE["active"]}
            for tid in studio.STATE["docs"]]
    print(f"  checkpoint would record active={[t['id'] for t in tabs if t['active']]}"
          f" out of {[t['id'] for t in tabs]} — one and only one: "
          f"{sum(t['active'] for t in tabs) == 1}")
    # window 1 polls: does its poll MOVE the server's active tab?
    before = studio.STATE["active"]
    c.get("/api/doc", headers={"X-TextCAD-Tab": w1})
    print(f"  window 1's poll moved STATE['active']: "
          f"{studio.STATE['active'] != before} (must be False)")
    # MAX_TABS still counts every tab, whoever opened it
    n = len(studio.STATE["docs"])
    for _ in range(studio.MAX_TABS + 2):
        r = c.post("/api/new", json={}, headers={"X-TextCAD-Tab": w1})
        if r.json().get("error") or "too many" in str(r.json().get("reply", "")):
            break
    print(f"  MAX_TABS={studio.MAX_TABS}; opened from {n} tabs, ended at "
          f"{len(studio.STATE['docs'])} — capped: "
          f"{len(studio.STATE['docs']) <= studio.MAX_TABS}")
    # two tabs on ONE design file is still a single tab, from either window
    fresh_c, w1, w2 = fresh()
    studio.STATE["docs"][w1]["source"] = "file:round6-demo"
    got = fresh_c.post("/api/open/round6-demo", json={},
                       headers={"X-TextCAD-Tab": w2})
    owners = [t for t, e in studio.STATE["docs"].items()
              if (e.get("source") or "") == "file:round6-demo"]
    print(f"  /api/open of a design window 1 already holds -> tabs owning "
          f"that file: {owners} (must be exactly one)  [{got.status_code}]")

    print()
    print("=" * 74)
    print("H. every label a page reads back names the tab it is ABOUT")
    print("=" * 74)
    c, mine, other = fresh()
    studio.STATE["active"] = other
    d = c.get("/api/doc", headers={"X-TextCAD-Tab": mine}).json()
    t = c.get("/api/tabs", headers={"X-TextCAD-Tab": mine}).json()
    print(f"  /api/doc  active_tab={d['active_tab']} (want {mine}), "
          f"strip active={[x['id'] for x in d['tabs'] if x['active']]}")
    print(f"  /api/tabs active_tab={t['active_tab']} (want {mine}), "
          f"strip active={[x['id'] for x in t['tabs'] if x['active']]}")
    import tempfile  # noqa: PLC0415
    with tempfile.TemporaryDirectory() as td:
        studio.BUGS = pathlib.Path(td)           # never litter the real bugs/
        c.post("/api/bug", json={"note": "r6", "requests": [], "console": [],
                                 "ui_build": "r6"},
               headers={"X-TextCAD-Tab": mine})
        saved = sorted(pathlib.Path(td).iterdir())
        rec = json.loads((saved[0] / "state.json").read_text(encoding="utf-8"))
    print(f"  /api/bug recorded active_tab={rec['doc']['active_tab']} "
          f"(want {mine}: the reporting window's design, not the active one)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
