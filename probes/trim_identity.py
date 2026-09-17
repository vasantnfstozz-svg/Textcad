r"""probes/trim_identity.py — the trim pieces did not move.

The speed fix in `sketch_trim._sample_wire` only takes work OUT of a loop, so
it must return the same points as the `wire.position_at(i / n)` it replaces.
"Must" is not a proof, so this probe puts the OLD loop back (monkeypatched)
and compares, over EVERY sketch in EVERY design in `designs/` (READ ONLY):

  * the same number of pieces, in the same order,
  * the same id / entity / whole flag on each,
  * the same points to FULL PRECISION (float bits, not rounded),
  * and the same decimated `trim_pieces` payload the browser receives.

A piece that appears, disappears or moves is a defect however fast it is.

    C:\Python314\python.exe probes/trim_identity.py
    C:\Python314\python.exe probes/trim_identity.py --apply   # + trim_apply
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np                                            # noqa: E402
import sketch_trim as tr                                      # noqa: E402

NEW = tr._sample_wire


def old_sample_wire(wire, n: int) -> np.ndarray:
    """`sketch_trim._outline` as it stood before the fix."""
    pts = np.empty((n, 2))
    for i in range(n):
        p = wire.position_at(i / n)
        pts[i] = (p.X, p.Y)
    return pts


def fingerprint(entities: list) -> tuple:
    """Everything Trim promises about a sketch, to full precision."""
    raw, _, crossing = tr._pieces_raw(entities)
    thin = tr.trim_pieces(entities)
    return (
        tuple((p["id"], p["ent"], p["whole"],
               p["_pts"].shape, p["_pts"].tobytes()) for p in raw),
        tuple(sorted(crossing)),
        json.dumps(thin, sort_keys=True),
    )


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


def main(do_apply: bool, sweep: bool = True) -> int:
    rows = list(sketches())
    print(f"{len(rows)} sketches in "
          f"{len({r[0] for r in rows})} designs, "
          f"{sum(len(r[2]) for r in rows)} entities\n")
    same = diff = err = 0
    t_old = t_new = 0.0
    for design, sid, ents in (rows if sweep else []):
        tr._sample_wire = old_sample_wire
        t = time.perf_counter()
        try:
            before = fingerprint(ents)
            ok_before, why = True, ""
        except Exception as ex:                               # noqa: BLE001
            before, ok_before, why = None, False, f"{type(ex).__name__}: {ex}"
        t_old += time.perf_counter() - t

        tr._sample_wire = NEW
        t = time.perf_counter()
        try:
            after = fingerprint(ents)
            ok_after, why2 = True, ""
        except Exception as ex:                               # noqa: BLE001
            after, ok_after, why2 = None, False, f"{type(ex).__name__}: {ex}"
        t_new += time.perf_counter() - t

        if not ok_before or not ok_after:
            if why == why2:
                err += 1                    # refused the same way before/after
                continue
            diff += 1
            print(f"  DIFFERS {design}/{sid}: before {why or 'ok'} "
                  f"-> after {why2 or 'ok'}")
            continue
        if before == after:
            same += 1
        else:
            diff += 1
            b, a = before[0], after[0]
            print(f"  DIFFERS {design}/{sid} ({len(ents)} entities): "
                  f"{len(b)} pieces -> {len(a)}")
            for pb, pa in zip(b, a):
                if pb != pa:
                    print(f"     first bad piece {pb[0]} shape {pb[3]}->{pa[3]}")
                    break
    print(f"\n{same} sketches IDENTICAL, {diff} differ, "
          f"{err} refused identically before and after")
    print(f"old sampler {t_old:6.1f} s total   "
          f"new sampler {t_new:6.1f} s total   "
          f"{t_old / max(t_new, 1e-9):.1f}x")

    if do_apply:
        print("\ntrim_apply, both samplers, on a spread of pieces:")
        want = [("rocky-balboa", "field_sketch"),
                ("esp32-remote", "sketch28"),
                ("rocky-keychain", "words_sketch"),
                ("my-part-8", "sketch4"),
                ("autonomiq-panel", "lockup_sketch_0"),
                ("bit-tray", None), ("hole-box", None)]
        todo = []
        for design, sid in want:
            for d, s, e in rows:
                if d == design and (sid is None or s == sid):
                    todo.append((d, s, e))
                    if sid is None:
                        break
        for design, sid, ents in todo:
            tr._sample_wire = NEW
            ids = [p["id"] for p in tr.trim_pieces(ents)]
            step = max(1, len(ids) // 8)            # a spread, not all 45
            ids = ids[::step][:8]
            bad = 0
            for pid in ids:
                out = []
                for sampler in (old_sample_wire, NEW):
                    tr._sample_wire = sampler
                    try:
                        r = tr.trim_apply(ents, pid)
                        out.append(json.dumps(r, sort_keys=True))
                    except Exception as ex:                   # noqa: BLE001
                        out.append(f"REFUSED {ex}")
                if out[0] != out[1]:
                    bad += 1
                    print(f"  DIFFERS {design}/{sid} piece {pid}")
                    print(f"    before: {out[0][:160]}")
                    print(f"    after : {out[1][:160]}")
            print(f"  {design}/{sid} ({len(ents)} entities): {len(ids)} "
                  f"pieces clicked, {len(ids) - bad} identical, {bad} differ")
            diff += bad
    tr._sample_wire = NEW
    print("\nRESULT: " + ("IDENTICAL EVERYWHERE" if diff == 0
                          else f"{diff} DIFFERENCES — do not ship"))
    return 0 if diff == 0 else 1


if __name__ == "__main__":
    np.seterr(all="ignore")
    sys.exit(main("--apply" in sys.argv or "--apply-only" in sys.argv,
                  sweep="--apply-only" not in sys.argv))
