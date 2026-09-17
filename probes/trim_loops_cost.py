r"""What does reading every loop COST, on the sketch Trim is slowest on?

Round two of the Trim review. The pair loop now walks loop pairs instead of
entity pairs, and `_entity_loops` samples every wire of every face. For the
seven one-loop kinds both are one iteration, so the price must be zero; a
word pays for the loops it really has.

    C:\Python314\python.exe probes/trim_loops_cost.py
"""
from __future__ import annotations
import importlib.util
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sketch_trim as new                                     # noqa: E402

GIT = r"C:\Program Files\Git\cmd\git.exe"
REV = sys.argv[1] if len(sys.argv) > 1 else "ee7fdad"


def load_old(rev):
    blob = subprocess.run([GIT, "show", f"{rev}:sketch_trim.py"], cwd=ROOT,
                          capture_output=True, check=True).stdout
    tmp = Path(tempfile.gettempdir()) / "_sketch_trim_old_cost.py"
    tmp.write_bytes(blob)
    spec = importlib.util.spec_from_file_location("sketch_trim_old_cost", tmp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def biggest(design):
    d = json.loads((ROOT / "designs" / f"{design}.tcad.json")
                   .read_text(encoding="utf-8"))
    best = None
    for f in d["features"]:
        ents = (f.get("params") or {}).get("entities")
        if isinstance(ents, list) and (best is None or len(ents) > len(best[1])):
            best = (f.get("id"), ents)
    return best


def timed(fn, *a):
    runs = [0.0, 0.0]
    for k in range(2):
        t = time.perf_counter()
        out = fn(*a)
        runs[k] = time.perf_counter() - t
    return min(runs) * 1000, out


def main():
    old = load_old(REV)
    for design in ("rocky-balboa", "esp32-remote", "rocky-keychain"):
        try:
            sid, ents = biggest(design)
        except Exception as ex:                               # noqa: BLE001
            print(f"{design}: {ex}")
            continue
        a, pa = timed(old._pieces_raw, ents)
        b, pb = timed(new._pieces_raw, ents)
        print(f"{design}/{sid}  {len(ents)} entities   "
              f"old {a:8.1f} ms -> new {b:8.1f} ms   "
              f"pieces {len(pa[0])} -> {len(pb[0])}")
    word = [{"kind": "rectangle", "mode": "add", "x": 0, "y": 0,
             "w": 120, "h": 40},
            {"kind": "text", "mode": "subtract", "x": 0, "y": 0,
             "text": "AUTONOMIQ", "size": 20}]
    b, pb = timed(new._pieces_raw, word)
    print(f"plate + 9-letter word (13 loops)      new {b:8.1f} ms   "
          f"pieces {len(pb[0])}")


if __name__ == "__main__":
    main()
