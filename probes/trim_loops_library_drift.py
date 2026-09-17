r"""Does reading an entity as ALL its loops change ANY of the user's sketches?

Round two of the Trim review. The fix replaces `_outline` (one face, its outer
wire) with `_entity_loops` (every face, every wire). The seven parametric
kinds build exactly one face with one wire, so their arithmetic must come out
BYTE-IDENTICAL — same piece ids, same `whole` flags, same point arrays to the
last bit, same crossing pairs, same cluster order.

This runs the shipped module and the one at the given git revision side by
side, in one process, over every sketch in `designs/` (READ ONLY).

    C:\Python314\python.exe probes/trim_loops_library_drift.py [<rev>]
"""
from __future__ import annotations
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import sketch_trim as new                                     # noqa: E402

GIT = r"C:\Program Files\Git\cmd\git.exe"


def load_old(rev: str):
    blob = subprocess.run([GIT, "show", f"{rev}:sketch_trim.py"],
                          cwd=ROOT, capture_output=True, check=True).stdout
    tmp = Path(tempfile.gettempdir()) / "_sketch_trim_old.py"
    tmp.write_bytes(blob)
    spec = importlib.util.spec_from_file_location("sketch_trim_old", tmp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sketches():
    for path in sorted((ROOT / "designs").glob("*.tcad.json")):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except Exception:                                     # noqa: BLE001
            continue
        if not isinstance(d, dict) or "features" not in d:
            continue
        for f in d["features"]:
            ents = (f.get("params") or {}).get("entities")
            if isinstance(ents, list) and ents:
                yield path.name[:-len(".tcad.json")], f.get("id"), ents


def fingerprint(mod, ents):
    pieces, outlines, crossing = mod._pieces_raw(ents)
    fp = [(p["id"], p["ent"], p["whole"], p["_pts"].tobytes()) for p in pieces]
    clusters = []
    for seed in range(len(ents)):
        try:
            clusters.append(tuple(mod._cluster(ents, outlines, crossing, seed)))
        except Exception as ex:                               # noqa: BLE001
            clusters.append(("ERR", str(ex)[:40]))
    return fp, sorted(crossing), clusters


def main():
    rev = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
    old = load_old(rev)
    rows = list(sketches())
    same = drift = old_only = new_only = both_refused = 0
    details = []
    for design, sid, ents in rows:
        try:
            fo = fingerprint(old, ents)
            eo = None
        except Exception as ex:                               # noqa: BLE001
            fo, eo = None, f"{type(ex).__name__}: {str(ex)[:70]}"
        try:
            fn = fingerprint(new, ents)
            en = None
        except Exception as ex:                               # noqa: BLE001
            fn, en = None, f"{type(ex).__name__}: {str(ex)[:70]}"
        if eo and en:
            both_refused += 1
            continue
        if eo and not en:
            new_only += 1
            details.append(f"  NEWLY WORKS  {design}/{sid}: was {eo}")
            continue
        if en and not eo:
            old_only += 1
            details.append(f"  NEWLY BROKEN {design}/{sid}: {en}")
            continue
        if fo == fn:
            same += 1
        else:
            drift += 1
            pa = {p[0] for p in fo[0]}
            pb = {p[0] for p in fn[0]}
            details.append(
                f"  DRIFT        {design}/{sid}: pieces {len(fo[0])}->"
                f"{len(fn[0])} ids+{sorted(pb - pa)[:4]} -{sorted(pa - pb)[:4]}"
                f" crossings {'same' if fo[1] == fn[1] else 'DIFFER'}"
                f" clusters {'same' if fo[2] == fn[2] else 'DIFFER'}")
    print(f"revision compared against : {rev}")
    print(f"sketches in designs/      : {len(rows)}")
    print(f"byte-identical            : {same}")
    print(f"DRIFTED                   : {drift}")
    print(f"newly works (was refused) : {new_only}")
    print(f"NEWLY BROKEN              : {old_only}")
    print(f"refused by both           : {both_refused}")
    for line in details[:40]:
        print(line)


if __name__ == "__main__":
    main()
