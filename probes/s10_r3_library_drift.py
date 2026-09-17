"""probes/s10_r3_library_drift.py — READ-ONLY: every saved design rebuilt, so a
new refusal that takes away correct work cannot hide.

Round three added guards in `blocks` (pick points, edge picks, revolve_profile
points, rotate's axis, curved_blade) and put the CREATORS through the numeric
door, and it changed what `plain_cause` does with a ValueError. A gate must
never refuse correct work, so every `designs/*.tcad.json` is loaded and rebuilt
and its per-feature status, volume, pieces and problems written out. Run it on
master and on the branch and diff the two files.

    C:\\Python314\\python.exe probes\\s10_r3_library_drift.py <out.json>

Nothing is saved back; `designs/` is only read.
"""
import json
import pathlib
import sys
import traceback

sys.path.insert(0, ".")

from document import Document                        # noqa: E402

ROOT = pathlib.Path("designs")


def snapshot(path):
    try:
        d = Document.load(str(path))
    except Exception as e:
        return {"open": f"{type(e).__name__}: {e}"}
    try:
        d.rebuild()
    except Exception:
        return {"rebuild_raised": traceback.format_exc(limit=3)}
    return {"features": [
        {"id": f.id, "op": f.op, "status": f.status, "volume": f.volume,
         "pieces": f.pieces, "problems": list(f.problems or []),
         "notes": list(f.notes or [])}
        for f in d.features],
        "warnings": list(d.warnings or []),
        "spec": list(d.spec_problems or [])}


if __name__ == "__main__":
    out_path = sys.argv[1] if len(sys.argv) > 1 else "_r3_drift.json"
    out = {}
    for p in sorted(ROOT.glob("*.tcad.json")):
        out[p.name] = snapshot(p)
        n = out[p.name].get("features")
        bad = sum(1 for f in (n or []) if f["status"] != "ok")
        print(f"{p.name:44s} {len(n or [])} features, {bad} not ok")
    pathlib.Path(out_path).write_text(json.dumps(out, indent=1, sort_keys=True),
                                      encoding="utf-8")
    print("written", out_path)
