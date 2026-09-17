"""What do the extra seeds COST on a body with hundreds of faces?

The climb runs only when `assert_something_would_be_hollowed` is about to
refuse, so its cost lands on the refusal path — the path the user waits on to
be told "walls must be under N mm". LAUNCH-PLAN section 10 records that path at
7.2 s on the 675-face panel with three seeds and 13.0 s at thirty, and asks any
seeding change to measure itself there before it ships.

`_seeds_for_the_climb` draws up to three seeds from each of three rankings, so
the worst case is nine climbs where there were three. This times the WHOLE
refusal path (sampling included, since that is what the user waits for) against
the seeding as it shipped, on bodies from 6 faces to several hundred — the
drilled plates are synthetic so the face count can be dialled, and the three
committed crash fixtures are real.

    python probes/shell_depth_seed_cost_probe.py
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "probes"))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))

import sketch as sk  # noqa: E402


def depth_only(seen, deepest, tol):
    """the seeding as it shipped: the deepest stations, spread by their radius"""
    ranked = sorted(((d0, d0, q0) for d0, q0, _b in seen), key=lambda r: -r[0])
    return sk._spread_out(ranked, tol, sk._DEPTH_CLIMB_SEEDS)


def drilled(holes: int):
    import build123d as b3d
    part = b3d.Part() + b3d.Box(120.0, 120.0, 10.0)
    pitch = 110.0 / holes
    cut = b3d.Part()
    for i in range(holes):
        for j in range(holes):
            cut += b3d.Pos(-55 + (i + 0.5) * pitch, -55 + (j + 0.5) * pitch, 0) * \
                b3d.Cylinder(pitch * 0.25, 30)
    return part - cut


def fixture(name: str):
    import build123d as b3d
    p = ROOT / "tests" / "fixtures" / f"{name}.brep"
    return b3d.Part(b3d.import_brep(str(p)).wrapped)


CASES = (("box", lambda: __import__("build123d").Box(50, 50, 30)),
         ("drilled 6x6", lambda: drilled(6)),
         ("drilled 12x12", lambda: drilled(12)),
         ("drilled 18x18", lambda: drilled(18)),
         ("oneplus_case", lambda: fixture("oneplus_case_shell_body")),
         ("impeller_cut", lambda: fixture("impeller_cut_shell_body")),
         ("my_part_5_mirror", lambda: fixture("my_part_5_mirror_body")))


def main() -> int:
    real_seeds = sk._seeds_for_the_climb
    real_climb = sk._climb_to_the_deepest
    spent = [0]

    def counting_climb(solid, measure, seen, best, tol):
        """the real climb, with its distance calls counted — wall-clock on this
        box is noise (four agents share it), the call count is not"""
        def counted(q):
            spent[0] += 1
            return measure(q)
        return real_climb(solid, counted, seen, best, tol)

    sk._climb_to_the_deepest = counting_climb
    print(f"{'body':18s} {'faces':>6s} {'before':>9s} {'after':>9s} "
          f"{'calls was':>9s} {'calls now':>9s} {'was s':>7s} {'now s':>7s}   verdict",
          flush=True)
    for name, make in CASES:
        try:
            solid = make()
            nf = len(solid.faces())
        except Exception as e:                        # noqa: BLE001
            print(f"{name:18s} could not be built ({type(e).__name__}: {e})", flush=True)
            continue
        out = []
        for seeding in (depth_only, real_seeds):
            sk._seeds_for_the_climb = seeding
            spent[0] = 0
            t0 = time.perf_counter()
            got = sk.deepest_material(solid, 1e9)     # t = infinity: always climbs
            out.append((got[0] if got else 0.0, spent[0], time.perf_counter() - t0))
        sk._seeds_for_the_climb = real_seeds
        (d_was, c_was, s_was), (d_now, c_now, s_now) = out
        print(f"{name:18s} {nf:6d} {d_was:9.4f} {d_now:9.4f} {c_was:9d} {c_now:9d} "
              f"{s_was:7.2f} {s_now:7.2f}   "
              f"{'RAISED by ' + format(d_now - d_was, '.4f') if d_now > d_was + 1e-6 else 'same answer'}"
              f", {c_now - c_was:+d} calls", flush=True)
    print(f"\nthe climb's budget is {sk._DEPTH_CLIMB_CALLS} calls; no row may "
          f"exceed it", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
