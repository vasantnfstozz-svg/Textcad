"""THE RULE, applied to the ridge climb: a guard whose job is REFUSING proves
nothing by reading a bigger number. Every wall it newly ALLOWS has to be put to
the kernel.

`probes/shell_depth_ridge_climb_probe.py` raises the depth the guard measures
(the ramped plate 12.2987 -> 12.7125, whose exact inscribed radius is 12.713).
That opens a band of wall thicknesses on every body whose answer moved, and
this walks each band through `sketch.shell` itself — the crash guard in the
way, so a segfault is a row and not the end of the run — and says which of
three things happened:

    BUILT sound     the refusal really was costing the user a correct shell
    kernel refused  a residual and nothing more
    CRASHED         a regression: the pre-kernel guard exists so that the
                    kernel is never asked this question

    python probes/memcap.py --gb 6 --timeout 2400 -- \\
        C:\\Python314\\python.exe probes/shell_depth_ridge_allowed_probe.py
"""
import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "probes"))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))
os.environ.setdefault("TEXTCAD_KERNEL_SECONDS", "90")

FIXTURES = ("oneplus_case_shell_body", "impeller_cut_shell_body",
            "sliver_intersect_plate", "my_part_5_mirror_body")


def bodies() -> dict:
    import build123d as b3d

    import gauntlet
    from shell_depth_plateau_seeds_probe import BODIES
    out = dict(BODIES)
    out.update(gauntlet.BODIES)
    for name in FIXTURES:
        p = ROOT / "tests" / "fixtures" / f"{name}.brep"
        if p.exists():
            out[name] = (lambda p=p: b3d.Part(b3d.import_brep(str(p)).wrapped))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=4)
    ap.add_argument("--open-face", default=None)
    a = ap.parse_args()
    import inspector
    import kernelguard
    import sketch as sk
    from shell_depth_ridge_climb_probe import ridge_climb
    real = sk._climb_to_the_deepest

    for name, make in bodies().items():
        try:
            solid = make()
        except Exception as e:                            # noqa: BLE001
            print(f"{name:24s} could not build ({type(e).__name__})", flush=True)
            continue
        openings = sk.shell_openings(solid, None, a.open_face) if a.open_face else []
        t0 = time.perf_counter()
        sk._climb_to_the_deepest = real
        now = sk.deepest_material(solid, 1e9, openings)
        sk._climb_to_the_deepest = ridge_climb
        new = sk.deepest_material(solid, 1e9, openings)
        if now is None or new is None:
            print(f"{name:24s} nothing measured", flush=True)
            sk._climb_to_the_deepest = real
            continue
        print(f"{name:24s} today {now[0]:9.4f} -> ridge {new[0]:9.4f}"
              f"   [{time.perf_counter() - t0:.0f}s]", flush=True)
        if new[0] <= now[0] + 1e-6:
            sk._climb_to_the_deepest = real
            continue
        for k in range(1, a.steps + 1):
            t = now[0] + (new[0] - now[0]) * k / a.steps
            t1 = time.perf_counter()
            try:
                out = sk.shell(solid, t, None, "inside", a.open_face)
            except kernelguard.KernelGone as e:
                print(f"    t={t:<9.4f} CRASHED OR STOPPED: {str(e)[:80]}", flush=True)
                continue
            except ValueError as e:
                who = ("the guard" if "nothing would be hollowed" in str(e)
                       else "the kernel")
                print(f"    t={t:<9.4f} refused by {who}: {str(e)[:70]}", flush=True)
                continue
            ok = (bool(out.is_valid) and inspector.closed_shell(out)
                  and not inspector.health(out))
            print(f"    t={t:<9.4f} BUILT cavity {solid.volume - out.volume:10.3f} mm3 "
                  f"{'SOUND' if ok else 'UNSOUND'}  [{time.perf_counter() - t1:.0f}s]",
                  flush=True)
        sk._climb_to_the_deepest = real
    kernelguard.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
