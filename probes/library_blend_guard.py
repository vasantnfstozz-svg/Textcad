"""Does the blend guard (blocks._assert_is_a_blend) refuse anything the user
has already built? Rebuilds every saved design and every fixture and prints
each design's leaf volumes plus any feature that came back with an error.

    python probes/library_blend_guard.py > probes/_blend_after.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    from document import Document
    files = sorted((ROOT / "designs").glob("*.tcad.json")) + \
        sorted((ROOT / "tests" / "fixtures").glob("*.tcad.json"))
    out = {}
    bad = 0
    for f in files:
        name = f.name[:-len(".tcad.json")]
        try:
            doc = Document.from_data(json.loads(f.read_text(encoding="utf-8")))
            doc.rebuild()
        except Exception as e:                       # noqa: BLE001
            out[name] = {"open_failed": f"{type(e).__name__}: {e}"}
            bad += 1
            continue
        errs = {ft.id: str(getattr(ft, "error", None)) for ft in doc.features
                if getattr(ft, "error", None)}
        vols = {}
        for fid in doc.leaf_solid_ids():
            p = doc._parts.get(fid)
            try:
                vols[fid] = round(float(p.volume), 4)
            except Exception:                        # noqa: BLE001
                vols[fid] = None
        out[name] = {"errors": errs, "volumes": vols}
        bad += len(errs)
    print(json.dumps(out, indent=1, sort_keys=True))
    print(f"# {len(files)} designs, {bad} feature errors", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
