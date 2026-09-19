"""ROUND FOUR, attack on round three's fix: a station that is AIR still enters
`seen` unclassified — where does that matter?

Round three classifies a station only when it is "about to change the answer"
(become the best, or end the loop). Every other measured station is appended to
`seen` with no classification at all, and `seen` is exactly the list
`_climb_to_the_deepest` seeds from. The climb does classify each seed
(`if outside(q0): continue`), so an air seed cannot be BELIEVED — but it is
picked FIRST, and `_spread_out` then blackballs every later station within
`max(d0, tol)` of it. An air seed therefore costs a seed slot AND a sphere of
real candidates around a point that is not in the body at all.

That direction of harm is UNDER-reading, so it does not hand a crash to the
kernel — it refuses walls the kernel would build.

This measures it: for each body and thickness, run `deepest_material` twice —
once as shipped, and once with `seen` filtered to stations the classifier calls
material — and print the two answers and how many seeds were air.

    C:\\Python314\\python.exe probes/shell_r4_air_seed_probe.py
    C:\\Python314\\python.exe probes/shell_r4_air_seed_probe.py --library
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-r4-hist"))

TS = (0.2, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0)


def instrument():
    """wrap `_climb_to_the_deepest` so every call reports its seeds, and can be
    asked to run on a `seen` with the air taken out"""
    import sketch as sk
    real_climb = sk._climb_to_the_deepest
    log = []

    def wrapper(solid, measure, seen, best, tol):
        seeds = sk._seeds_for_the_climb(seen, best[0], tol) or [best]
        air_seeds = sum(1 for _d, q in seeds
                        if sk.point_is_inside(solid, (q.X, q.Y, q.Z)) is not True)
        air_seen = sum(1 for d, q, _b in seen
                       if sk.point_is_inside(solid, (q.X, q.Y, q.Z)) is not True)
        shipped = real_climb(solid, measure, seen, best, tol)
        clean = [s for s in seen
                 if sk.point_is_inside(solid, (s[1].X, s[1].Y, s[1].Z)) is True]
        filtered = real_climb(solid, measure, clean, best, tol)
        log.append({"seeds": len(seeds), "air_seeds": air_seeds,
                    "seen": len(seen), "air_seen": air_seen,
                    "shipped": shipped[0], "filtered": filtered[0]})
        return shipped

    sk._climb_to_the_deepest = wrapper
    return log


def bodies(library: bool):
    import build123d as b3d
    import gauntlet
    for name, make in sorted(gauntlet.BODIES.items()):
        try:
            yield name, make()
        except Exception as e:                                   # noqa: BLE001
            print(f"  (corpus {name}: {e})", flush=True)
    for p in sorted((ROOT / "tests" / "fixtures").glob("*.brep")):
        try:
            yield p.stem, b3d.Part(b3d.import_brep(str(p)).wrapped)
        except Exception as e:                                   # noqa: BLE001
            print(f"  (fixture {p.stem}: {e})", flush=True)
    if library:
        from document import Document
        for p in sorted((ROOT / "designs").glob("*.tcad.json")):
            doc = Document.from_data(json.loads(p.read_text(encoding="utf-8")))
            doc.rebuild()
            best = None
            for fid in doc.leaf_solid_ids():
                part = doc._parts.get(fid)
                if part is None:
                    continue
                v = float(part.volume)
                if best is None or v > best[1]:
                    best = (part, v)
            if best:
                yield p.name[:-len(".tcad.json")], best[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--library", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    import sketch as sk
    log = instrument()
    moved = []
    for name, solid in bodies(a.library):
        if a.only and a.only != name:
            continue
        for t in TS:
            del log[:]
            try:
                got = sk.deepest_material(solid, t)
            except Exception as e:                               # noqa: BLE001
                print(f"{name} t={t}: {e}", flush=True)
                continue
            if got is None or not log:
                continue                    # no climb ran: the guard allowed at once
            r = log[-1]
            flag = ""
            if abs(r["shipped"] - r["filtered"]) > 1e-9:
                flag = "   <<< THE AIR IN `seen` CHANGES THE ANSWER"
                moved.append((name, t, r["shipped"], r["filtered"]))
            print(f"{name:28s} t={t:<5g} depth {got[0]:9.4f}  seeds {r['seeds']} "
                  f"({r['air_seeds']} air)  seen {r['seen']} ({r['air_seen']} air)  "
                  f"climb shipped {r['shipped']:.4f} / filtered {r['filtered']:.4f}{flag}",
                  flush=True)
    print(f"\ncells where the air in `seen` changed the climb's answer: {len(moved)}",
          flush=True)
    for m in moved:
        print("   ", m, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
