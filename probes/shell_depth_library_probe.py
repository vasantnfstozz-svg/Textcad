"""REVIEW of cc78019: which of the user's OWN designs sat in the false-refusal
band?

`deepest_material` samples along rays through face sample points; the review's
fix walks the best of them uphill to the real maximum.  The band between the
two numbers is exactly the set of wall thicknesses cc78019 refused BEFORE the
kernel on a body the kernel can hollow.  So: measure every body of every live
design both ways and print the band.

    python probes/shell_depth_library_probe.py
"""
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT", str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))


def main() -> int:
    import sketch
    from document import Document
    real = sketch._climb_to_the_deepest
    final_only = "--final" in sys.argv        # only the body the design ENDS on
    bands, bodies, designs = [], 0, 0
    for path in sorted((ROOT / "designs").glob("*.tcad.json")):
        try:
            doc = Document.from_data(json.loads(path.read_text("utf-8")))
            doc.rebuild()
        except Exception as e:                            # noqa: BLE001
            print(f"{path.stem}: did not build ({str(e)[:70]})", flush=True)
            continue
        designs += 1
        t0 = time.perf_counter()
        hits = []
        parts = list(doc._parts.items())
        if final_only:
            parts = [(fid, p) for fid, p in parts if p is not None][-1:]
        for fid, part in parts:
            if part is None:
                continue
            try:
                if not part.solids() or part.volume <= 0:
                    continue
            except Exception:                             # noqa: BLE001
                continue
            bodies += 1
            try:
                opens = [("closed", [])]
                try:
                    top = sketch.shell_openings(part, None, "top")
                    if top:
                        opens.append(("top open", top))
                except Exception:                         # noqa: BLE001
                    pass
                for label, openings in opens:
                    sketch._climb_to_the_deepest = lambda s, m, sn, b, tl: b
                    was = sketch.deepest_material(part, 1e9, openings)
                    sketch._climb_to_the_deepest = real
                    now = sketch.deepest_material(part, 1e9, openings)
                    if was and now and now[0] - was[0] > max(1e-3, 1e-3 * now[0]):
                        hits.append((fid, label, was[0], now[0]))
            except Exception as e:                        # noqa: BLE001
                print(f"  {fid}: RAISED {type(e).__name__}: {str(e)[:70]}", flush=True)
            finally:
                sketch._climb_to_the_deepest = real
        print(f"{path.stem}: {len(doc.features)} features, {time.perf_counter() - t0:.1f} s"
              + (f"  -- {len(hits)} body/mode(s) with a band" if hits else ""), flush=True)
        for fid, label, was, now in hits:
            print(f"    {fid:28s} {label:9s} refused walls from {was:.4g} to {now:.4g} mm",
                  flush=True)
            bands.append((path.stem, fid, label, was, now))
    print(f"\n{designs} designs, {bodies} bodies; "
          f"{len(bands)} body/mode(s) where cc78019 refused a wall the kernel can build",
          flush=True)
    widest = sorted(bands, key=lambda r: -(r[4] - r[3]))[:12]
    for r in widest:
        print(f"   {r[0]}/{r[1]} {r[2]}: {r[3]:.4g} -> {r[4]:.4g} mm "
              f"(a {r[4] - r[3]:.4g} mm band)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
