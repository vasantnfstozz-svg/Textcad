"""The two residuals the plateau-seeding fix declared, put to the kernel.

`_seeds_for_the_climb`'s docstring says the ramped plate is "the climb's own
limit and not the seeding's": the guard answers 12.2987 where a grid oracle
says 12.6900, and climbing ALL 160 of its stations reaches 12.2987 too. That is
an UNDER-estimate, which is the safe direction for a crash and the unsafe one
for the user — every wall in the gap is refused before the kernel is asked.

Whether that costs the user anything is not a matter of opinion: build them.
A wall the kernel builds SOUND inside the gap is the same defect the wedge-in-
slab fix closed, still open on another shape; a wall the kernel refuses or
crashes on is a residual and nothing more.

    python probes/shell_depth_residual_band_probe.py
    python probes/shell_depth_residual_band_probe.py --body plateau_pair

Through `sketch.shell`, so the crash guard is in the way and one segfault does
not end the ladder.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "probes"))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--body", default="ramped_plate")
    ap.add_argument("--steps", type=int, default=5)
    ap.add_argument("--ask-the-kernel", action="store_true",
                    help="patch the depth guard off, so the band reaches the "
                         "kernel and the question is what IT says (the crash "
                         "guard is still in the way, so a segfault costs one row)")
    a = ap.parse_args()
    import inspector
    import sketch as sk
    if a.ask_the_kernel:
        sk.assert_something_would_be_hollowed = lambda *x, **k: None
    from shell_depth_oracle_probe import oracle_depth
    from shell_depth_plateau_seeds_probe import BODIES
    solid = BODIES[a.body]()
    said = sk.deepest_material(solid, 1e9)[0]
    truth, _at = oracle_depth(solid, coarse=20, refine=4)
    print(f"{a.body}: {solid.volume:,.3f} mm3 — the guard answers {said:.4f}, "
          f"the grid oracle {truth:.4f}", flush=True)
    if truth <= said:
        print("   no gap: the guard is not under the oracle", flush=True)
        return 0
    for k in range(1, a.steps + 1):
        t = said + (truth - said) * k / (a.steps + 1)
        try:
            out = sk.shell(solid, t)
        except ValueError as e:
            who = ("THE GUARD" if "nothing would be hollowed" in str(e)
                   else "the kernel")
            print(f"   t={t:<8.4f} refused by {who}: {str(e)[:90]}", flush=True)
            continue
        ok = (bool(out.is_valid) and inspector.closed_shell(out)
              and not inspector.health(out))
        print(f"   t={t:<8.4f} BUILT cavity {solid.volume - out.volume:10.3f} mm3  "
              f"{'sound' if ok else 'UNSOUND'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
