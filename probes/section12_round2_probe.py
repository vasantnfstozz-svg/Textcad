"""Section 12 ROUND TWO — measuring round one's own new guards (b88d870).

Part 1: the 50 saved designs against _design_slug and _spec_problem.
  - does every design's name still slug to its own file stem (so no saved
    design's export path moved)?
  - does every saved spec block still pass _spec_problem (so opening and
    re-saving a design is not refused)?

Run: C:\\Python314\\python.exe probes/section12_round2_probe.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      tempfile.mkdtemp(prefix="s12r2-hist-"))

import studio                                            # noqa: E402
import document                                          # noqa: E402

DESIGNS = ROOT / "designs"


def part1():
    print("=" * 72)
    print("PART 1 — the saved library against _design_slug / _spec_problem")
    print("=" * 72)
    files = sorted(DESIGNS.glob("*.tcad.json"))
    print(f"{len(files)} design files")
    moved, spec_refused, name_missing = [], [], []
    for p in files:
        stem = p.name[:-len(".tcad.json")]
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  UNREADABLE {p.name}: {e}")
            continue
        name = data.get("name")
        if not name:
            name_missing.append(stem)
            continue
        slug = studio._design_slug(name)
        if slug != stem:
            moved.append((stem, name, slug, slug.lower() == stem.lower()))
        spec = data.get("spec") or {}
        for k, v in spec.items():
            if v is None:
                continue
            if k not in {"size", "volume", "holes", "n_solids", "symmetry",
                         "tip_radius", "com", "require_manifold", "tol",
                         "vol_tol"}:
                continue
            problem = studio._spec_problem(k, v)
            if problem:
                spec_refused.append((stem, k, v, problem))

    print(f"\n  designs whose name does NOT slug to its own file stem: "
          f"{len(moved)}")
    for stem, name, slug, ci in moved:
        print(f"    {stem!r}: name={name!r} -> slug={slug!r} "
              f"(same file on a case-insensitive FS: {ci})")
    print(f"  designs with no 'name' field: {len(name_missing)} {name_missing}")
    print(f"\n  saved spec values REFUSED by _spec_problem: {len(spec_refused)}")
    for stem, k, v, why in spec_refused:
        print(f"    {stem}: {k}={v!r} -> {why}")
    return moved, spec_refused


def part2():
    """Every saved spec, through the real /api/spec door, on its own design."""
    print()
    print("=" * 72)
    print("PART 2 — every saved spec re-sent through POST /api/spec")
    print("=" * 72)
    from fastapi.testclient import TestClient
    refused = []
    files = sorted(DESIGNS.glob("*.tcad.json"))
    for p in files:
        stem = p.name[:-len(".tcad.json")]
        data = json.loads(p.read_text(encoding="utf-8"))
        spec = data.get("spec") or {}
        if not spec:
            continue
        studio.STATE["docs"], studio.STATE["active"] = {}, None
        doc = document.Document.from_data(data)
        studio._new_tab(doc, source=f"file:{stem}")
        c = TestClient(studio.app)
        r = c.post("/api/spec", json={"spec": spec})
        if r.status_code != 200:
            refused.append((stem, spec, r.json().get("error")))
        else:
            back = r.json().get("spec")
            if back != {k: v for k, v in spec.items() if v is not None}:
                print(f"    {stem}: spec came back DIFFERENT: {back!r} "
                      f"vs sent {spec!r}")
    print(f"  saved designs whose own spec is now REFUSED: {len(refused)}")
    for stem, spec, why in refused:
        print(f"    {stem}: {spec!r} -> {why}")
    return refused


if __name__ == "__main__":
    moved, spec_refused = part1()
    refused = part2()
    print()
    print("=" * 72)
    print(f"VERDICT: {len(moved)} export paths moved, "
          f"{len(spec_refused)} spec values refused by the helper, "
          f"{len(refused)} designs refused through /api/spec")
