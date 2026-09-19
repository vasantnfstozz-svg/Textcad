"""ROUND FOUR, job one: put the USER'S OWN designs to the shell guard and ask
the one question three rounds never asked — is any body of theirs NEWLY
REFUSED by this sweep?

No design in `designs/` carries a `shell` feature (census 2026-09-19: extrude,
sketch, cut, move, fuse, ... and no shell at all), so "the thicknesses the
design actually uses" is an empty set. The honest substitute is the one a user
would hit: take each design's finished body and shell it at a ladder, closed
and with the top open, and record ALLOWED / REFUSED for every cell.

Run the SAME file against a checkout of the pre-sweep commit (0670f58) and
compare cell by cell (`shell_r4_compare_verdicts.py`). A cell that was ALLOWED
before the sweep and is REFUSED now is a saved design that stopped building,
which this project calls P0.

    python probes/shell_r4_library_verdict_probe.py --out <file.jsonl>
    python probes/shell_r4_library_verdict_probe.py --cell bit-tray 2.0 closed

THREE processes deep on purpose. The bodies are built ONCE and cached as .brep
(`--export`), then every CELL runs in its own child with an OS-enforced
timeout, and the kernel half of that child runs in `kernelguard`'s worker with
its own. A thread watchdog was tried first and is not enough: a long
OpenCASCADE call holds the GIL, so a `threading.Timer` never fires — the
timeout has to belong to the operating system. `deepest_material` runs in the
LISTENER process and has no budget of its own, which is exactly why one cell
can otherwise outlive the whole run.
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

FIXED_TS = (0.5, 1.0, 2.0, 3.0)
CELL_S = 130.0                 # one cell alone (--cell), enforced by the OS
DESIGN_S = 420.0               # one attempt at a design's remaining cells
BUILD_S = 900.0                # one design's rebuild + export


def designs_dir() -> Path:
    return Path(os.environ.get("TEXTCAD_DESIGNS_DIR") or (ROOT / "designs"))


def bodies_dir() -> Path:
    d = Path(os.environ.get("TEXTCAD_R4_BODIES") or (ROOT / "probes" / "_r4_bodies"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_body(stem: str):
    import build123d as b3d
    return b3d.Part(b3d.import_brep(str(bodies_dir() / f"{stem}.brep")).wrapped)


def ladder(part) -> list:
    """The thicknesses this body is asked at: four a person types, plus one just
    under the closed-hollow limit of its own thinnest lump. Derived from the
    BODY, so the two checkouts ask exactly the same questions."""
    dmin = min(min(lump.bounding_box().size.X, lump.bounding_box().size.Y,
                   lump.bounding_box().size.Z) for lump in part.solids())
    ts = set(FIXED_TS)
    ts.add(round(0.45 * dmin, 4))
    return sorted(t for t in ts if t > 0)


def export_one(stem: str) -> None:
    """build the design ONCE and cache its largest leaf body.

    A cached .brep is REUSED, and that is what lets the pre-sweep checkout be
    asked about exactly the same bodies without rebuilding a single design —
    point both runs at one `TEXTCAD_R4_BODIES` and the two answers differ only
    by the code under test."""
    import build123d as b3d
    from document import Document
    cached = bodies_dir() / f"{stem}.brep"
    if cached.exists():
        part = load_body(stem)
        print(json.dumps({"design": stem, "fid": "(cached)",
                          "v_in": float(part.volume), "faces": len(part.faces()),
                          "lumps": len(part.solids()), "ts": ladder(part)}), flush=True)
        return
    doc = Document.from_data(json.loads(
        (designs_dir() / f"{stem}.tcad.json").read_text(encoding="utf-8")))
    doc.rebuild()
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
    if best is None:
        print(json.dumps({"design": stem, "body": None}), flush=True)
        return
    fid, part, v = best
    b3d.export_brep(part, str(bodies_dir() / f"{stem}.brep"))
    print(json.dumps({"design": stem, "fid": fid, "v_in": v,
                      "faces": len(part.faces()), "lumps": len(part.solids()),
                      "ts": ladder(part)}), flush=True)


def one_cell(sketch, part, stem: str, t: float, mode: str) -> dict:
    rec = {"design": stem, "t": t, "mode": mode}
    t0 = time.perf_counter()
    try:
        res = sketch.shell(part, t, faces=(["top"] if mode == "top-open" else None),
                           direction="inside")
        rec["verdict"] = "ALLOWED"
        rec["v_out"] = float(res.volume)
    except Exception as e:                                       # noqa: BLE001
        rec["verdict"] = "REFUSED"
        rec["why"] = str(e)[:240]
    rec["s"] = round(time.perf_counter() - t0, 2)
    return rec


def cell(stem: str, t: float, mode: str) -> None:
    """ONE cell, in its own child: the whole of `sketch.shell`, verdict on stdout"""
    import sketch
    print(json.dumps(one_cell(sketch, load_body(stem), stem, t, mode)), flush=True)


def design_cells(stem: str, out_path: Path) -> None:
    """every cell of one design still missing from `out_path`, in THIS child,
    each appended and fsynced the moment it lands.

    One child per design and not one per cell, because a cell child costs about
    twelve seconds of interpreter and worker start-up and most cells are shorter
    than that. The OS timeout belongs to the parent's `subprocess.run`, so a cell
    that will not end costs this child and the parent resumes at the next one."""
    import sketch
    part = load_body(stem)
    done = load_done(out_path)
    with out_path.open("a", encoding="utf-8") as fh:
        for t in ladder(part):
            for mode in ("closed", "top-open"):
                if (stem, t, mode) in done:
                    continue
                rec = one_cell(sketch, part, stem, t, mode)
                fh.write(json.dumps(rec) + "\n")
                fh.flush()
                os.fsync(fh.fileno())
                print(f"   t={t:<7g} {mode:9s} {rec['verdict']:9s} {rec['s']:7.1f}s  "
                      f"{(rec.get('why') or '')[:80]}", flush=True)
    print(json.dumps({"design": stem, "finished": True}), flush=True)


def load_done(out_path: Path) -> dict:
    done = {}
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:                                    # noqa: BLE001
                continue
            done[(r["design"], r["t"], r["mode"])] = r
    return done


def run_child(args: list, timeout: float) -> tuple:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8",
           "TEXTCAD_KERNEL_SECONDS": os.environ.get("TEXTCAD_KERNEL_SECONDS", "60")}
    try:
        p = subprocess.run([sys.executable, __file__, *args], capture_output=True,
                           text=True, cwd=str(ROOT), timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return None, "PROBE-TIMEOUT", ""
    code = p.returncode & 0xFFFFFFFF
    for line in reversed(p.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line), None, ""
            except Exception:                                    # noqa: BLE001
                pass
    errs = (p.stderr or "").strip().splitlines()
    return None, f"CHILD-0x{code:08X}", errs[-1][:160] if errs else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--export")
    ap.add_argument("--cell", nargs=3, metavar=("DESIGN", "T", "MODE"))
    ap.add_argument("--design")
    ap.add_argument("--out", default=str(ROOT / "probes" / "_r4_library_verdicts.jsonl"))
    ap.add_argument("--only", help="comma-separated stems")
    a = ap.parse_args()
    out_path = Path(a.out)
    if a.export:
        export_one(a.export)
        return 0
    if a.cell:
        cell(a.cell[0], float(a.cell[1]), a.cell[2])
        return 0
    if a.design:
        design_cells(a.design, out_path)
        return 0

    stems = sorted(p.name[:-len(".tcad.json")] for p in designs_dir().glob("*.tcad.json"))
    if a.only:
        want = set(a.only.split(","))
        stems = [s for s in stems if s in want]
    for stem in stems:
        info, err, tail = run_child(["--export", stem], BUILD_S)
        if info is None or not info.get("ts"):
            print(f"{stem}: NO BODY ({err or 'empty'}) {tail}", flush=True)
            continue
        want_n = 2 * len(info["ts"])
        print(f"{stem}: {info['faces']} faces, {info['lumps']} lumps, "
              f"ts {info['ts']}", flush=True)
        for attempt in range(5):
            here = [k for k in load_done(out_path) if k[0] == stem]
            if len(here) >= want_n:
                break
            t0 = time.perf_counter()
            _got, err, tail = run_child(["--design", stem, "--out", str(out_path)],
                                        DESIGN_S)
            after = [k for k in load_done(out_path) if k[0] == stem]
            print(f"   [attempt {attempt}: {err or 'ok'} "
                  f"{len(after)}/{want_n} cells, "
                  f"{time.perf_counter() - t0:.0f}s] {tail}", flush=True)
            if len(after) == len(here):
                # this attempt landed nothing: the cell it died on would kill
                # every retry the same way, so it is written off and named
                missing = [(t, m) for t in info["ts"] for m in ("closed", "top-open")
                           if (stem, t, m) not in load_done(out_path)]
                if missing:
                    t, m = missing[0]
                    with out_path.open("a", encoding="utf-8") as fh:
                        fh.write(json.dumps({"design": stem, "t": t, "mode": m,
                                             "verdict": err or "PROBE-TIMEOUT",
                                             "why": tail}) + "\n")
                    print(f"   t={t:<7g} {m:9s} {err or 'PROBE-TIMEOUT'} "
                          f"(written off)", flush=True)
    print(f"\ncells recorded: {len(load_done(out_path))}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
