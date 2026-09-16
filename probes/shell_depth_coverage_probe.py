"""A/B the face-coverage fix: `_barycentres` forced back to the single centroid
is exactly cc78019..3bbfcca's sampling, so the two columns are before/after."""
import json, os, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT", str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))
import build123d as b3d

def main() -> int:
    import sketch
    from document import Document
    real = sketch._barycentres
    def old(_k):
        return ((1 / 3, 1 / 3, 1 / 3),)

    cases = []
    cases.append(("thick_L", b3d.Part() + b3d.Box(60, 60, 30) + b3d.Pos(55, -26, 0) * b3d.Box(50, 8, 30), []))
    cases.append(("T plate", b3d.Part() + (b3d.Box(120, 20, 24) + b3d.Pos(0, 40, 0) * b3d.Box(20, 60, 24)), []))
    cases.append(("step block", b3d.Part() + (b3d.Box(100, 60, 10) + b3d.Pos(-20, 0, 5) * b3d.Box(60, 60, 30)), []))
    w = b3d.Part() + b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-40, 0), (40, 0), (40, 30), (-40, 2), close=True)), 40)
    cases.append(("wedge alone", w, []))
    cases.append(("wedge-in-a-slab", b3d.Part() + (w + b3d.Pos(0, -30, 12) * b3d.Box(80, 80, 24)), []))
    for name, mode in (("my-part-3", "closed"), ("cam-cover-lower", "closed"), ("bit-tray", "closed"),
                       ("my-part", "closed"), ("fan-disk", "closed"), ("my-part-2", "closed"),
                       ("hole-box", "top"), ("my-part-8", "closed"), ("my-part-9", "closed"),
                       ("pump-housing", "closed")):
        p = ROOT / "designs" / f"{name}.tcad.json"
        if not p.exists():
            continue
        doc = Document.from_data(json.loads(p.read_text("utf-8")))
        doc.rebuild()
        part = [q for _f, q in doc._parts.items() if q is not None][-1]
        opens = sketch.shell_openings(part, None, "top") if mode == "top" else []
        cases.append((name, part, opens))
    print(f"{'body':22s} {'BEFORE':>18s} {'AFTER':>18s}   faces")
    for label, part, opens in cases:
        out = []
        for fn in (old, real):
            sketch._barycentres = fn
            t0 = time.perf_counter()
            d = sketch.deepest_material(part, 1e9, opens)[0]
            out.append(f"{d:9.4f}/{time.perf_counter()-t0:5.1f}s")
        sketch._barycentres = real
        print(f"{label:22s} {out[0]:>18s} {out[1]:>18s}   {len(part.faces())}", flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
