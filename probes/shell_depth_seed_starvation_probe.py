"""Does the climb's BUDGET starve the very seeds the three rankings added?

`_seeds_for_the_climb`'s docstring records what the new seeding measured:

    the wedge in a slab 12.0000 -> 12.4461 (oracle 12.4300), the slab with a
    post 17.0000 -> 17.2160 (17.2047), the 180 mm draft prism unchanged at
    15.3405, the ramped plate unchanged at 12.2987

The shipped code answers 12.4156 for the wedge and **17.0000** for the slab
with a post — no change at all on the body the THIRD ranking exists for. The
suspect is `_DEPTH_CLIMB_CALLS`, added in the same commit: it is a SHARED
budget of 120 distance measurements, a single seed can spend 41 of them, and
the three DEEPEST seeds are ordered first — so on a body whose deep seeds all
run their full forty steps there is nothing left for the rankings that were
added, and the seeding is exactly the old one wearing a new coat.

This probe measures that rather than arguing it: the same body, the same
seeding, three budgets, and the seed each answer came from.

    python probes/shell_depth_seed_starvation_probe.py
    python probes/shell_depth_seed_starvation_probe.py --body plateau_pair
"""
import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "probes"))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--body")
    ap.add_argument("--costly", action="store_true",
                    help="the bodies the budget was added FOR: hundreds of "
                         "faces, where one distance measurement costs 0.12 s")
    a = ap.parse_args()
    import sketch as sk
    from shell_depth_plateau_seeds_probe import BODIES
    if a.costly:
        from shell_depth_seed_cost_probe import CASES
        BODIES = dict(CASES)
    names = [a.body] if a.body else list(BODIES)
    shipped = sk._DEPTH_CLIMB_CALLS
    for name in names:
        solid = BODIES[name]()
        print(f"\n{name}: {solid.volume:,.3f} mm3", flush=True)
        for calls in (shipped, 200, 10_000):
            spent = [0]
            real = sk._climb_to_the_deepest

            def counting(solid, measure, seen, best, tol, _real=real, _n=spent):
                def counted(q):
                    _n[0] += 1
                    return measure(q)
                return _real(solid, counted, seen, best, tol)

            sk._DEPTH_CLIMB_CALLS = calls
            sk._climb_to_the_deepest = counting
            t0 = time.perf_counter()
            got = sk.deepest_material(solid, 1e9)
            took = time.perf_counter() - t0
            sk._climb_to_the_deepest = real
            sk._DEPTH_CLIMB_CALLS = shipped
            print(f"   budget {calls:>6}  answer {got[0]:9.4f}  "
                  f"measurements spent {spent[0]:>4}  whole refusal path {took:6.1f}s"
                  + ("   <-- SHIPPED" if calls == shipped else ""), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
