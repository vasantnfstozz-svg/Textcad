"""The last live design whose depth the coverage fix RAISED: every wall it newly
permits on my-part-3 and my-part-9, put to the kernel."""
import json, os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT", str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))

def main() -> int:
    import inspector, sketch
    from document import Document
    real = sketch._barycentres
    def old(_k):
        return ((1 / 3, 1 / 3, 1 / 3),)
    n_ok = n_bad = 0
    for name in ("my-part-3", "my-part-9", "cam-cover-lower"):
        doc = Document.from_data(json.loads((ROOT / "designs" / f"{name}.tcad.json").read_text("utf-8")))
        doc.rebuild()
        part = [q for _f, q in doc._parts.items() if q is not None][-1]
        for label, faces in (("closed", None), ("top open", ["top"])):
            try:
                opens = sketch.shell_openings(part, faces, None) if faces else []
            except Exception:                              # noqa: BLE001
                continue
            got = []
            for fn in (old, real):
                sketch._barycentres = fn
                got.append(sketch.deepest_material(part, 1e9, opens)[0])
            sketch._barycentres = real
            was, now = got
            if now <= was * (1 + 1e-6):
                print(f"{name}/{label}: {was:.4f} unchanged", flush=True); continue
            print(f"{name}/{label}: depth {was:.4f} -> {now:.4f}  "
                  f"({len(part.faces())} faces, {part.volume:,.1f} mm3)", flush=True)
            for f in (0.2, 0.5, 0.8, 1.0):
                t = round(was + (now - was) * f, 4)
                t0 = time.perf_counter()
                try:
                    out = sketch.shell(part, t, faces)
                    h = inspector.health(out)
                    ok = bool(out.is_valid) and not h and out.volume > 0
                    n_ok += ok; n_bad += (not ok)
                    print(f"   t={t:<9g} BUILT cavity {part.volume - out.volume:12.3f} mm3 "
                          f"valid={out.is_valid} health={h} [{time.perf_counter()-t0:.1f}s]"
                          + ("" if ok else "   <<< NOT SOUND"), flush=True)
                except ValueError as e:
                    n_ok += 1
                    print(f"   t={t:<9g} refused in a sentence: {str(e)[:62]} "
                          f"[{time.perf_counter()-t0:.1f}s]", flush=True)
                except Exception as e:                     # noqa: BLE001
                    n_bad += 1
                    print(f"   t={t:<9g} {type(e).__name__}: {str(e)[:66]}   <<< NOT A SENTENCE",
                          flush=True)
    print(f"\n{n_ok} sound or refused in a sentence, {n_bad} NOT", flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
