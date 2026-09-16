r"""Section 12 ROUND THREE - every saved design, opened and EXPORTED for real.

Round two measured its export fix by calling _design_slug / _name_clash
directly ("0 of 50 refused, 0 of 50 moved"). This puts all 50 through the REAL
endpoints - POST /api/open/<stem> then POST /api/export - and then reads the
file back with inspector, so the answer covers the whole path: the refusal
guard, the file name, and whether what landed on disk is a solid a CAM tool
can use.

designs/ is never touched: the library is COPIED to a throwaway folder and
studio.DESIGNS is pointed at the copy, so the .step files land there.

Run: C:\Python314\python.exe probes/section12_round3_export_sweep.py
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      tempfile.mkdtemp(prefix="s12r3-sweep-hist-"))


def main() -> None:
    import studio
    from fastapi.testclient import TestClient
    import inspector

    lib = Path(tempfile.mkdtemp(prefix="s12r3-sweep-lib-"))
    stems = []
    for p in sorted((ROOT / "designs").glob("*.tcad.json")):
        shutil.copy2(p, lib / p.name)
        stems.append(p.name[:-len(".tcad.json")])
    shutil.copy2(ROOT / "designs" / "examples.json", lib / "examples.json")
    studio.DESIGNS = lib

    print("=" * 78)
    print(f"{len(stems)} designs, opened from the library and EXPORTED for real")
    print(f"library copy: {lib}")
    print("=" * 78)

    refused, moved, bad, ok = [], [], [], []
    t_all = time.time()
    for i, stem in enumerate(stems, 1):
        studio.STATE["docs"].clear()
        studio.STATE["active"] = None
        studio.STATE["seq"] = 0
        c = TestClient(studio.app)
        t0 = time.time()
        o = c.post(f"/api/open/{stem}").json()
        if o.get("error"):
            bad.append((stem, f"open: {o['error']}"))
            print(f"[{i:2}/{len(stems)}] {stem:<34} OPEN FAILED: {o['error']}",
                  flush=True)
            continue
        r = c.post("/api/export")
        d = r.json()
        dt = time.time() - t0
        if r.status_code != 200 or d.get("error"):
            refused.append((stem, d.get("error")))
            print(f"[{i:2}/{len(stems)}] {stem:<34} REFUSED {r.status_code}: "
                  f"{str(d.get('error'))[:60]}  {dt:.1f}s", flush=True)
            continue
        got = Path(d["path"]).name
        if got != f"{stem}.step":
            moved.append((stem, got))
        m = inspector.measure(d["path"])
        valid = bool(m.get("is_valid")) and bool(m.get("is_manifold"))
        if not valid:
            bad.append((stem, f"is_valid={m.get('is_valid')} "
                              f"is_manifold={m.get('is_manifold')}"))
        ok.append(stem)
        print(f"[{i:2}/{len(stems)}] {stem:<34} -> {got:<36} "
              f"n={m.get('n_solids')} vol={m.get('volume')} "
              f"valid={m.get('is_valid')} manifold={m.get('is_manifold')} "
              f"{dt:.1f}s", flush=True)

    print("\n" + "=" * 78)
    print(f"exported     : {len(ok)} of {len(stems)}   "
          f"({time.time() - t_all:.0f}s total)")
    print(f"REFUSED      : {len(refused)}  {refused}")
    print(f"MOVED off its own stem: {len(moved)}  {moved}")
    print(f"NOT a clean solid     : {len(bad)}  {bad}")


if __name__ == "__main__":
    main()
