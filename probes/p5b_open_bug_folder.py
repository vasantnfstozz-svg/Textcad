"""P5b review: what a finding made by the OPENING check leaves behind.

Journey.run() asks check_bodies() and check_roundtrip() before it plays any
move — "this saved design is already broken" is the cheapest finding there is.
But run_one() only remembers a `before` document for a MUTATING request, and
no request has been sent yet, so write_bug gets before=None. The folder then
holds the design as after.tcad.json, and replay() looks only for
before.tcad.json / doc.tcad.json.

Run:  C:\\Python314\\python.exe probes/p5b_open_bug_folder.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import journeys  # noqa: E402


def main():
    bugs = Path(tempfile.mkdtemp(prefix="p5b-openbug-"))
    path = dict(journeys.sources())["pump-impeller"]

    import inspector
    orig = inspector.health
    inspector.health = lambda part, **k: ["staged: non-manifold shell"]
    try:
        out = journeys.run_one("pump-impeller", path, seed=1, steps=5,
                               log_path=None, bugs_dir=bugs, verbose=False)
    finally:
        inspector.health = orig

    print(f"exit={out['exit']}  folder={out.get('folder')}")
    folder = Path(out["folder"])
    print("files in the folder:", sorted(p.name for p in folder.iterdir()))
    print()
    print("report.md's Reproduce line:")
    for line in (folder / "report.md").read_text(encoding="utf-8").splitlines():
        if "--replay" in line:
            print("   ", line.strip())
    print()
    try:
        res = journeys.replay(folder, verbose=False)
        print("replay ->", res["result"])
    except SystemExit as e:
        print(f"replay REFUSED: SystemExit({e})")


if __name__ == "__main__":
    main()
