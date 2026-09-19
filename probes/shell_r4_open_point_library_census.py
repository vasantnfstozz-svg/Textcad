"""ROUND FOUR, attack two: round three's opening nudge was proved to change no
verdict over SIXTEEN bodies. The user has fifty designs, and they are the
corpus that matters.

The theorem `assert_the_deepest_point_was_hollowed` has two gates it can decide
BEFORE the kernel runs — `depth > t + tol`, and `point_is_inside(solid, at) is
True` — so the whole question "is the theorem live or mute on this body?" can
be censused with no offset and no boolean at all. That is what round three did
over its corpus (probes/shell_r3_inert_census.py); this asks the same of the
user's own bodies, closed and with the top open.

    C:\\Python314\\python.exe probes/shell_r4_open_point_library_census.py
    C:\\Python314\\python.exe probes/shell_r4_open_point_library_census.py --design bit-tray

One child per design (the parent restarts after a segfault), one JSON line per
cell, flushed as it lands.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-r4-hist"))

TS = (0.5, 1.0, 2.0, 3.0)
CHILD_S = 900.0


def state_of(solid, at) -> str:
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_State
    try:
        cls = BRepClass3d_SolidClassifier(solid.wrapped)
        cls.Perform(gp_Pnt(*at), 1e-7)
        return {TopAbs_State.TopAbs_IN: "IN", TopAbs_State.TopAbs_OUT: "OUT",
                TopAbs_State.TopAbs_ON: "ON"}.get(cls.State(), "UNKNOWN")
    except Exception as e:                                       # noqa: BLE001
        return "ERR:" + str(e)[:40]


def one(stem: str, out_path: Path, done: set) -> None:
    import sketch as sk
    from document import Document
    doc = Document.from_data(json.loads(
        (ROOT / "designs" / f"{stem}.tcad.json").read_text(encoding="utf-8")))
    doc.rebuild()
    best = None
    for fid in doc.leaf_solid_ids():
        part = doc._parts.get(fid)
        if part is None:
            continue
        v = float(part.volume)
        if best is None or v > best[2]:
            best = (fid, part, v)
    if best is None:
        return
    fid, part, _v = best
    fh = out_path.open("a", encoding="utf-8")
    for mode in ("closed", "top-open"):
        try:
            openings = sk.shell_openings(part, ["top"] if mode == "top-open" else None)
        except Exception:                                        # noqa: BLE001
            continue
        for t in TS:
            key = f"{stem}|{t}|{mode}"
            if key in done:
                continue
            rec = {"design": stem, "fid": fid, "t": t, "mode": mode,
                   "faces": len(part.faces()), "lumps": len(part.solids())}
            t0 = time.perf_counter()
            try:
                got = sk.deepest_material(part, t, openings)
            except Exception as e:                               # noqa: BLE001
                rec["err"] = str(e)[:120]
                got = None
            if got is None:
                rec["depth"] = None
            else:
                depth, at, tol = got
                rec.update(depth=depth, at=list(at), tol=tol,
                           margin=bool(depth > t + tol), state=state_of(part, at),
                           allows=bool(depth >= t - tol))
            rec["s"] = round(time.perf_counter() - t0, 2)
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
    fh.close()


def load_done(out_path: Path) -> set:
    done = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:                                    # noqa: BLE001
                continue
            done.add(f"{r['design']}|{r['t']}|{r['mode']}")
    return done


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--design")
    ap.add_argument("--out", default=str(ROOT / "probes" / "_r4_open_point_census.jsonl"))
    a = ap.parse_args()
    out_path = Path(a.out)
    if a.design:
        one(a.design, out_path, load_done(out_path))
        return 0
    stems = sorted(p.name[:-len(".tcad.json")] for p in (ROOT / "designs").glob("*.tcad.json"))
    for stem in stems:
        for _attempt in range(3):
            before = len(load_done(out_path))
            try:
                p = subprocess.run(
                    [sys.executable, __file__, "--design", stem, "--out", str(out_path)],
                    capture_output=True, text=True, cwd=str(ROOT), timeout=CHILD_S,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8"})
                code = p.returncode & 0xFFFFFFFF
            except subprocess.TimeoutExpired:
                code = 0xDEAD
            after = len(load_done(out_path))
            print(f"{stem}: 0x{code:08X}, +{after - before} (total {after})", flush=True)
            if code == 0 or after == before:
                break
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
