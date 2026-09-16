"""REVIEW of 3bbfcca: on the FINISHED body of every live design, does the
shipped guard (climb included) still read BELOW an independent grid oracle?
That is the residual of F1 the brief asked the reviewer to hunt for."""
import json, os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT", str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))
from shell_depth_oracle_probe import oracle_depth   # noqa: E402

MAX_FACES = int(os.environ.get("RV_MAX_FACES", "400"))

def main() -> int:
    import sketch
    from document import Document
    gaps = []
    for path in sorted((ROOT / "designs").glob("*.tcad.json")):
        try:
            doc = Document.from_data(json.loads(path.read_text("utf-8")))
            doc.rebuild()
        except Exception as e:                            # noqa: BLE001
            print(f"{path.stem}: did not build ({str(e)[:60]})", flush=True); continue
        parts = [(f, p) for f, p in doc._parts.items() if p is not None]
        if not parts:
            print(f"{path.stem}: no body", flush=True); continue
        fid, part = parts[-1]
        try:
            if not part.solids() or part.volume <= 0:
                print(f"{path.stem}: empty body", flush=True); continue
        except Exception:                                 # noqa: BLE001
            continue
        nf = len(part.faces())
        if nf > MAX_FACES:
            print(f"{path.stem}/{fid}: {nf} faces -- skipped (oracle too slow)", flush=True); continue
        opens = [("closed", [])]
        try:
            top = sketch.shell_openings(part, None, "top")
            if top:
                opens.append(("top open", top))
        except Exception:                                 # noqa: BLE001
            pass
        for label, openings in opens:
            t0 = time.perf_counter()
            try:
                g = sketch.deepest_material(part, 1e9, openings)
                guard = g[0] if g else 0.0
                o, at = oracle_depth(part, openings)
            except Exception as e:                        # noqa: BLE001
                print(f"{path.stem}/{fid} {label}: RAISED {type(e).__name__} {str(e)[:60]}", flush=True)
                continue
            gap = o - guard
            flag = "   <<< GUARD STILL UNDERSTATES" if gap > max(0.05, 0.02 * o) else ""
            print(f"{path.stem}/{fid} [{nf}f] {label:9s} guard {guard:8.4f} oracle {o:8.4f} "
                  f"gap {gap:+7.4f}  [{time.perf_counter()-t0:.0f}s]{flag}", flush=True)
            if flag:
                gaps.append((path.stem, fid, label, guard, o, at))
    print(f"\n{len(gaps)} finished body/mode(s) where the SHIPPED guard still reads low:", flush=True)
    for r in gaps:
        print(f"   {r[0]}/{r[1]} {r[2]}: guard {r[3]:.4g} vs oracle {r[4]:.4g} "
              f"(a {r[4]-r[3]:.4g} mm band) at {r[5]}", flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
