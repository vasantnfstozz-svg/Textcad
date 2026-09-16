"""Section 12 ROUND TWO — the cost and the ceiling of "restore EVERY tab".

Round one removed the [:MAX_TABS] slice from _restore_session and claimed
"restoring costs nothing per tab because only the active one is rebuilt".
Rebuilding is not the only per-tab cost: _new_tab hashes the document and
_restored_baseline opens the design's history AND re-loads the file from disk.

Measured here with a session file holding N tabs of the user's HEAVIEST saved
designs, with rebuild=False (so the rebuild is excluded) and with rebuild=True.

Run: C:\\Python314\\python.exe probes/section12_round2_restore_probe.py
"""
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      tempfile.mkdtemp(prefix="s12r2-hist-"))

import studio                                            # noqa: E402

DESIGNS = ROOT / "designs"


def main():
    files = sorted(DESIGNS.glob("*.tcad.json"),
                   key=lambda p: p.stat().st_size, reverse=True)
    print("heaviest designs:", [(p.stem, p.stat().st_size // 1024)
                                for p in files[:5]], "KB")
    tmp = Path(tempfile.mkdtemp(prefix="s12r2-sess-"))
    for n in (12, 40):
        tabs = []
        for i in range(n):
            p = files[i % len(files)]
            data = json.loads(p.read_text(encoding="utf-8"))
            stem = p.name[:-len(".tcad.json")]
            tabs.append({"doc": data, "source": f"file:{stem}",
                         "active": i == n - 1})
        sess = tmp / f"session-{n}.json"
        sess.write_text(json.dumps({"tabs": tabs}), encoding="utf-8")
        print(f"\n  session file with {n} tabs: "
              f"{sess.stat().st_size // 1024} KB")
        old = studio.SESSION_PATH
        studio.SESSION_PATH = sess
        try:
            studio.STATE["docs"], studio.STATE["active"] = {}, None
            t0 = time.perf_counter()
            back = studio._restore_session(rebuild=False)
            dt = time.perf_counter() - t0
        finally:
            studio.SESSION_PATH = old
        print(f"    restored {back} tabs in {dt * 1000:.0f} ms "
              f"(no rebuild) -> {dt * 1000 / max(back, 1):.0f} ms/tab")
        print(f"    active resolves to a real tab: "
              f"{studio.STATE['active'] in studio.STATE['docs']}")
        # /api/tabs cost: _dirty per tab on every document reply
        t0 = time.perf_counter()
        studio._tabs_json()
        print(f"    first _tabs_json() over {back} tabs: "
              f"{(time.perf_counter() - t0) * 1000:.0f} ms")

    # a tab whose design file has since been deleted
    print("\n  a tab whose design file is gone:")
    data = json.loads(files[-1].read_text(encoding="utf-8"))
    sess = tmp / "session-gone.json"
    sess.write_text(json.dumps({"tabs": [
        {"doc": data, "source": "file:_no-such-design-anywhere",
         "active": True}]}), encoding="utf-8")
    old = studio.SESSION_PATH
    studio.SESSION_PATH = sess
    try:
        studio.STATE["docs"], studio.STATE["active"] = {}, None
        back = studio._restore_session(rebuild=False)
    finally:
        studio.SESSION_PATH = old
    e = next(iter(studio.STATE["docs"].values()))
    print(f"    restored {back}; clean_hash={e['clean_hash']!r} "
          f"dirty={studio._dirty(e)}  active ok="
          f"{studio.STATE['active'] in studio.STATE['docs']}")

    # MAX_TABS still caps OPENING
    print("\n  MAX_TABS still caps /api/new:")
    from fastapi.testclient import TestClient
    studio.STATE["docs"], studio.STATE["active"] = {}, None
    c = TestClient(studio.app)
    codes = [c.post("/api/new", json={"name": f"_probe-cap-{i}"}).status_code
             for i in range(studio.MAX_TABS + 2)]
    print(f"    /api/new x{len(codes)} -> {codes} "
          f"(tabs now {len(studio.STATE['docs'])}, MAX_TABS={studio.MAX_TABS})")


if __name__ == "__main__":
    main()
