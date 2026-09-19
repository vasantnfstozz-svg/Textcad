"""ROUND FOUR, job one: put the USER'S OWN 50 designs to the shell guard and
ask the one question three rounds never asked — is any body of theirs NEWLY
REFUSED by this sweep?

No design in `designs/` carries a `shell` feature (census 2026-09-19: extrude,
sketch, cut, move, fuse, ... and no shell at all), so "the thicknesses the
design actually uses" is an empty set. The honest substitute is the one a user
would hit: take each design's finished body and shell it at a ladder, closed
and with the top open, and record ALLOWED / REFUSED / CRASH for every cell.

Run the SAME file against a checkout of the pre-sweep commit (0670f58) and
compare cell by cell. A cell that was ALLOWED before and is REFUSED now is a
saved design that stopped building, which this project calls P0.

    python probes/shell_r4_library_verdict_probe.py --out <file.jsonl>
    python probes/shell_r4_library_verdict_probe.py --design esp32-remote

Each design runs in its OWN child and every cell is appended to the .jsonl and
flushed, so a segfault or a stall costs that one cell and the run resumes.
`kernelguard` already turns a kernel crash and a kernel stall into a sentence,
so a refusal here is either a guard or the kernel, and the record says which.
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-r4-hist"))

FIXED_TS = (0.5, 1.0, 2.0, 3.0)
CELL_S = 150.0                # one cell's whole budget, watchdogged inside the child
CHILD_S = 10 * CELL_S + 300.0


def designs_dir() -> Path:
    return Path(os.environ.get("TEXTCAD_DESIGNS_DIR") or (ROOT / "designs"))


def ladder(part) -> list:
    """The thicknesses this body is asked at: four a person types, plus one just
    under the closed-hollow limit of its own thinnest lump. Derived from the
    BODY, so the two checkouts ask exactly the same questions."""
    dmin = min(min(lump.bounding_box().size.X, lump.bounding_box().size.Y,
                   lump.bounding_box().size.Z) for lump in part.solids())
    ts = set(FIXED_TS)
    ts.add(round(0.45 * dmin, 4))
    return sorted(t for t in ts if t > 0)


def biggest_body(doc):
    """the finished body a user would shell: the largest leaf solid"""
    best = None
    for fid in doc.leaf_solid_ids():
        f = doc.get(fid)
        if f.suppressed or f.status != "ok":
            continue
        part = doc._parts.get(fid)
        if part is None:
            continue
        try:
            v = float(part.volume)
        except Exception:                                        # noqa: BLE001
            continue
        if v > 0 and (best is None or v > best[2]):
            best = (fid, part, v)
    return best


def one(stem: str, out_path: Path, done: set) -> None:
    """one design, in this child: every cell of the ladder, appended as it lands"""
    import sketch
    from document import Document
    doc = Document.from_data(json.loads(
        (designs_dir() / f"{stem}.tcad.json").read_text(encoding="utf-8")))
    doc.rebuild()
    got = biggest_body(doc)
    if got is None:
        return
    fid, part, v_in = got
    lumps = len(part.solids())
    nfaces = len(part.faces())
    top = None
    try:
        top = sketch.named_face(part, "top")
        sketch.assert_flat_opening(top)
    except Exception:                                            # noqa: BLE001
        top = None
    fh = out_path.open("a", encoding="utf-8")
    for t in ladder(part):
        for mode in ("closed", "top-open"):
            key = f"{stem}|{t}|{mode}"
            if key in done:
                continue
            if mode == "top-open" and top is None:
                continue
            t0 = time.perf_counter()
            rec = {"design": stem, "fid": fid, "t": t, "mode": mode,
                   "faces": nfaces, "lumps": lumps, "v_in": v_in}
            # the cell's OWN budget. `deepest_material` runs in this process and
            # has no budget of its own (the kernel half does, in the worker), so
            # one cell can outlive the run. The pre-record is what makes the
            # watchdog resumable: `load` keeps the LAST line for a cell, so a
            # cell that never came back stays PROBE-TIMEOUT and the next child
            # moves on to the next one instead of dying on this one again.
            fh.write(json.dumps({**rec, "verdict": "PROBE-TIMEOUT",
                                 "budget_s": CELL_S}) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
            bang = threading.Timer(CELL_S, lambda: os._exit(3))
            bang.daemon = True
            bang.start()
            try:
                res = sketch.shell(part, t, faces=(["top"] if mode == "top-open" else None),
                                   direction="inside")
                rec["verdict"] = "ALLOWED"
                rec["v_out"] = float(res.volume)
            except Exception as e:                               # noqa: BLE001
                rec["verdict"] = "REFUSED"
                rec["why"] = str(e)[:240]
            bang.cancel()
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
    ap.add_argument("--out", default=str(ROOT / "probes" / "_r4_library_verdicts.jsonl"))
    ap.add_argument("--only", help="comma-separated stems")
    a = ap.parse_args()
    out_path = Path(a.out)
    if a.design:
        one(a.design, out_path, load_done(out_path))
        return 0
    stems = sorted(p.name[:-len(".tcad.json")] for p in designs_dir().glob("*.tcad.json"))
    if a.only:
        want = set(a.only.split(","))
        stems = [s for s in stems if s in want]
    dead = []
    for stem in stems:
        for attempt in range(3):              # a segfault costs one cell, then on
            before = len(load_done(out_path))
            try:
                p = subprocess.run(
                    [sys.executable, __file__, "--design", stem, "--out", str(out_path)],
                    capture_output=True, text=True, cwd=str(ROOT), timeout=CHILD_S,
                    env={**os.environ, "PYTHONIOENCODING": "utf-8",
                         "TEXTCAD_KERNEL_SECONDS": os.environ.get("TEXTCAD_KERNEL_SECONDS", "120")})
                code = p.returncode & 0xFFFFFFFF
            except subprocess.TimeoutExpired:
                code, p = 0xDEAD, None
            after = len(load_done(out_path))
            print(f"{stem}: child {attempt} -> 0x{code:08X}, {after - before} cells "
                  f"(total {after})", flush=True)
            if code == 0:
                break
            if after == before:               # made no progress: stop retrying
                dead.append((stem, f"0x{code:08X}", "no progress"))
                if p is not None and p.stderr:
                    print("    " + p.stderr.strip().splitlines()[-1][:200], flush=True)
                break
        else:
            dead.append((stem, "retries exhausted", ""))
    print(f"\ncells recorded: {len(load_done(out_path))}", flush=True)
    if dead:
        print(f"children that died with no progress: {dead}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
