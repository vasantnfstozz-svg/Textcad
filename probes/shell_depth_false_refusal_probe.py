"""REVIEW of cc78019: the two bodies where `deepest_material` reads LOW
(probes/shell_depth_oracle_probe.py) -- does the guard refuse a shell the
kernel builds SOUND?  That is the question the commit's own corpus asked and
answered zero for; these bodies were not in it.

    python probes/shell_depth_false_refusal_probe.py           # the verdicts
    python probes/shell_depth_false_refusal_probe.py --why     # where the sampling loses it
"""
import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT", str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))

import build123d as b3d  # noqa: E402


def wedge():
    """a plain draft/taper: 2 mm at one end, 30 mm at the other, 40 mm deep"""
    return b3d.Part() + b3d.extrude(
        b3d.Plane.XZ * b3d.make_face(b3d.Polyline((-40, 0), (40, 0), (40, 30), (-40, 2), close=True)), 40)


def thick_L():
    return b3d.Part() + b3d.Box(60, 60, 30) + b3d.Pos(55, -26, 0) * b3d.Box(50, 8, 30)


def cone():
    return b3d.Part() + b3d.Cone(25, 0, 40)


def pyramid():
    return b3d.Part() + b3d.loft([b3d.Plane.XY * b3d.Rectangle(60, 60),
                                  b3d.Plane.XY.offset(40) * b3d.Rectangle(4, 4)])


BODIES = {"wedge": wedge, "thick_L": thick_L, "cone": cone, "pyramid": pyramid}
TS = (2.0, 4.0, 6.0, 8.0, 10.0, 11.0, 11.5, 12.0, 14.0, 16.0, 20.0, 24.0, 26.0, 28.0)


def why(name, solid, openings):
    """re-run the guard's own sampling, then say what the oracle's winning point
    would have scored -- the point exists in the body, the sample set misses it"""
    import sketch
    from probes.shell_depth_oracle_probe import oracle_depth
    got = sketch.deepest_material(solid, 1e9, openings)
    od, op = oracle_depth(solid, openings)
    print(f"{name}: guard samples reach {got[0]:.4f} mm; the grid finds "
          f"{od:.4f} mm at {tuple(round(v, 2) for v in op)}", flush=True)
    print(f"   -> every wall between {got[0]:.3f} and {od:.3f} mm is refused "
          f"before the kernel is asked", flush=True)


def main() -> int:
    import inspector
    import kernelguard
    import sketch
    ap = argparse.ArgumentParser()
    ap.add_argument("--why", action="store_true")
    ap.add_argument("--budget", type=float, default=60.0)
    a = ap.parse_args()
    false_refusals = []
    for name, mk in BODIES.items():
        solid = mk()
        bb = solid.bounding_box().size
        print(f"\n== {name}: {len(solid.faces())} faces, {solid.volume:,.0f} mm3, "
              f"bbox {bb.X:.1f} x {bb.Y:.1f} x {bb.Z:.1f}", flush=True)
        try:
            top = sketch.shell_openings(solid, None, "top")
        except Exception:                                   # noqa: BLE001
            top = None
        modes = [("closed", [])] + ([("top open", top)] if top else [])
        for label, openings in modes:
            if a.why:
                why(f"{name} {label}", solid, openings)
                continue
            for t in TS:
                walls = f"walls of {t:g} mm"
                try:
                    if not openings:
                        sketch.assert_wall_fits_every_lump(solid, t, walls)
                except ValueError:
                    continue                                # the old bbox guard: as before
                try:
                    sketch.assert_something_would_be_hollowed(solid, t, openings, walls)
                except ValueError as e:
                    said = str(e)
                else:
                    continue
                t1 = time.perf_counter()
                try:
                    out = kernelguard.guarded("shell", solid, {
                        "thickness": t, "direction": "inside", "walls": walls,
                        "picks": kernelguard.indices(solid.faces(), openings),
                        "marks": kernelguard._marks(openings),
                        "crashed": "CRASHED", "stopped": "STOPPED <minutes>"},
                        lambda: sketch.shell_after_guards(solid, t, "inside", openings, walls),
                        budget=a.budget)
                    sound = (bool(out.is_valid) and not inspector.health(out)
                             and inspector.closed_shell(out) and 0 < out.volume < solid.volume)
                    verdict = (f"SOUND {out.volume:,.1f} mm3 of {solid.volume:,.1f}"
                               if sound else "unsound")
                    if sound:
                        false_refusals.append((name, label, t, out.volume, solid.volume))
                except ValueError as e:
                    s = str(e)
                    verdict = "kernel " + ("CRASHED" if "CRASHED" in s else
                                           "STOPPED" if "STOPPED" in s else f"refused ({s[7:60]})")
                print(f"   {label:9s} t={t:<5g} GUARD REFUSES -> {verdict} "
                      f"[{time.perf_counter() - t1:.1f} s]", flush=True)
                print(f"      said: {said[:150]}", flush=True)
    kernelguard.shutdown()
    print(f"\nFALSE REFUSALS (the kernel builds a sound hollow): {len(false_refusals)}", flush=True)
    for r in false_refusals:
        print("   ", r, flush=True)
    return 1 if false_refusals else 0


if __name__ == "__main__":
    raise SystemExit(main())
