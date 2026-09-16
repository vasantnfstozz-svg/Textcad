"""Does the pre-kernel guard (sketch.assert_something_would_be_hollowed) ever
refuse a shell the kernel would have built SOUND?  The one question a
pre-kernel guard has to answer (round two and three of the first shell review
were both guards refusing correct geometry).

For every corpus body x thickness x {closed, top open} the guard is asked
first; where it REFUSES, the kernel is asked too (in the kernel worker, so a
segfault is a row, not the end) and the verdict is compared. Where the guard
allows, nothing changes from today and the kernel is not run.

  python probes/memcap.py --gb 6 --timeout 3600 -- python probes/shell_thin_wall_corpus.py
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT", str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))

import build123d as b3d  # noqa: E402

TS = (0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 5.0)
BUDGET = 45.0
BREPS = {
    "oneplus_case": ROOT / "tests/fixtures/oneplus_case_shell_body.brep",
    "impeller_cut": ROOT / "tests/fixtures/impeller_cut_shell_body.brep",
    "sliver_plate": ROOT / "tests/fixtures/sliver_intersect_plate.brep",
    "my_part_5_mirror": ROOT / "tests/fixtures/my_part_5_mirror_body.brep",
    "finding_mypart": ROOT / "probes/_thin_mypart.brep",
    "finding_mypart9": ROOT / "probes/_thin_mypart9.brep",
}


def plate_with_rib():
    """a 4 mm rib fused on a 12 mm plate: is a rib the wall does not fit a
    refusal, or does the kernel leave it solid and hollow the plate?"""
    return b3d.Part() + b3d.Box(60, 40, 12) + b3d.Pos(0, 0, 10) * b3d.Box(4, 40, 8)


def plate_with_pin():
    return b3d.Part() + b3d.Box(60, 40, 12) + b3d.Pos(10, 0, 8.5) * b3d.Cylinder(2, 5)


def two_pockets():
    """two 8 mm-deep pockets in a 12 mm plate with a 4 mm web between them —
    the my-part-9 pattern on a body with nothing else going on"""
    plate = b3d.Box(60, 40, 12)
    a = b3d.Pos(-12, 0, 6) * b3d.Box(20, 30, 8)
    b = b3d.Pos(12, 0, 6) * b3d.Box(20, 30, 8)
    return b3d.Part() + (plate - a - b)


def bodies() -> dict:
    import gauntlet
    out = dict(gauntlet.BODIES)
    out.update(plate_with_rib=plate_with_rib, plate_with_pin=plate_with_pin, two_pockets=two_pockets)
    for name, path in BREPS.items():
        if path.exists():
            out[name] = (lambda path=path: b3d.Part(b3d.import_brep(str(path)).wrapped))
    return out


def main() -> int:
    import inspector
    import kernelguard
    import sketch
    only = sys.argv[1].split(",") if len(sys.argv) > 1 else None
    false_refusals, caught, rows = [], 0, 0
    for name, mk in bodies().items():
        if only and name not in only:
            continue
        try:
            solid = mk()
        except Exception as e:  # noqa: BLE001
            print(f"{name}: could not build ({e})", flush=True)
            continue
        n_faces = len(solid.faces())
        t0 = time.perf_counter()
        closed = sketch.deepest_material(solid, 1e9)
        try:
            top = sketch.shell_openings(solid, None, "top")
        except ValueError:                       # no flat top (the clipped ball): closed only
            top = None
        opened = sketch.deepest_material(solid, 1e9, top) if top else None
        dt = time.perf_counter() - t0
        print(f"== {name}: {n_faces} faces, deepest material closed {closed[0]:.3f} "
              + (f"open {opened[0]:.3f}" if opened else "(no flat top)")
              + f", measured in {dt:.2f} s", flush=True)
        modes = [("closed", [])] + ([("top open", top)] if top else [])
        for label, openings in modes:
            for t in TS:
                walls = f"walls of {t:g} mm"
                rows += 1
                try:
                    if not openings:
                        sketch.assert_wall_fits_every_lump(solid, t, walls)
                except ValueError:
                    print(f"   {label:8s} t={t:<4g} bbox guard refuses (as before)", flush=True)
                    continue
                try:
                    sketch.assert_something_would_be_hollowed(solid, t, openings, walls)
                except ValueError as e:
                    said = str(e)
                else:
                    continue                       # allowed: nothing changes today
                # the guard refused: what would the kernel have done?
                t1 = time.perf_counter()
                try:
                    out = kernelguard.guarded("shell", solid, {
                        "thickness": t, "direction": "inside", "walls": walls,
                        "picks": kernelguard.indices(solid.faces(), openings),
                        "marks": kernelguard._marks(openings),
                        "crashed": "CRASHED", "stopped": "STOPPED <minutes>"},
                        lambda: sketch.shell_after_guards(solid, t, "inside", openings, walls),
                        budget=BUDGET)
                    sound = (bool(out.is_valid) and not inspector.health(out)
                             and inspector.closed_shell(out) and 0 < out.volume < solid.volume)
                    verdict = "SOUND" if sound else "unsound"
                    if sound:
                        false_refusals.append((name, label, t, said))
                except ValueError as e:
                    verdict = "kernel " + ("CRASHED" if "CRASHED" in str(e) else
                                           "STOPPED" if "STOPPED" in str(e) else f"refused ({str(e)[7:60]})")
                    caught += 1
                print(f"   {label:8s} t={t:<4g} GUARD REFUSES ({said[said.find(':', 8) + 2:said.find('(near')]}) "
                      f"-> {verdict} in {time.perf_counter() - t1:.1f} s", flush=True)
    kernelguard.shutdown()
    print()
    print(f"{rows} cases; guard refusals that the kernel would have failed/crashed/stalled: {caught}")
    print(f"FALSE REFUSALS (kernel would have built a sound shell): {len(false_refusals)}")
    for r in false_refusals:
        print("   ", r)
    return 1 if false_refusals else 0


if __name__ == "__main__":
    raise SystemExit(main())
