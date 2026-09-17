"""If the three rankings share ONE budget, in what order should they spend it?

`_seeds_for_the_climb` draws three seeds from each of three rankings and
`_climb_to_the_deepest` gives the whole climb 120 distance measurements, of
which one seed can spend 41. The shipped order is all three DEEPEST seeds
first, so on a body whose deep seeds each run their forty steps the two new
rankings are never reached — measured, that is exactly what happens to the slab
with a post (probes/shell_depth_seed_starvation_probe.py: 17.0000 shipped,
17.2160 with the budget lifted, and the lifted climb spends only 157).

Two orders, same budget, same bodies, and the ANSWER and the SPEND for each:

  A. shipped:     deep1 deep2 deep3 | room1 both1 room2 both2 ...
  B. round-robin: deep1 room1 both1 | deep2 room2 both2 | deep3 room3 both3

An order may only ever be adopted if NO body's answer goes down: the climb's
answer is what the guard allows, so a smaller answer is a wall refused that the
kernel would have built.

    python probes/shell_depth_seed_order_probe.py
"""
import itertools
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


def rankings(seen, deepest, tol):
    """the three `_spread_out` lists, before they are put in an order"""
    deep, room = [], []
    for d0, q0, bound in seen:
        deep.append((d0, d0, q0))
        if bound != float("inf") and d0 >= 0.1 * deepest:
            room.append((bound / max(d0, 1e-9), d0, q0))
    both = [r for r in room if r[1] >= 0.5 * deepest]
    return [sk._spread_out(sorted(r, key=lambda x: -x[0]), tol, sk._DEPTH_CLIMB_SEEDS)
            for r in (deep, room, both)]


def dedupe(order, tol):
    seeds, at = [], []
    for d0, q0 in order:
        if all((q0 - p).length > tol for p in at):
            seeds.append((d0, q0))
            at.append(q0)
    return seeds


def shipped(seen, deepest, tol):
    p = rankings(seen, deepest, tol)
    order = p[0] + [s for pair in zip(p[1], p[2]) for s in pair] \
        + p[1][len(p[2]):] + p[2][len(p[1]):]
    return dedupe(order, tol)


def round_robin(seen, deepest, tol):
    p = rankings(seen, deepest, tol)
    order = [s for trio in itertools.zip_longest(*p) for s in trio if s is not None]
    return dedupe(order, tol)


def bodies():
    import build123d as b3d

    from shell_depth_plateau_seeds_probe import BODIES
    out = dict(BODIES)
    sys.path.insert(0, str(ROOT / "tests"))
    import gauntlet
    out.update(gauntlet.BODIES)
    for name in ("oneplus_case_shell_body", "impeller_cut_shell_body",
                 "sliver_intersect_plate", "my_part_5_mirror_body"):
        p = ROOT / "tests" / "fixtures" / f"{name}.brep"
        out[name] = (lambda p=p: b3d.Part(b3d.import_brep(str(p)).wrapped))
    return out


def main() -> int:
    real_climb = sk._climb_to_the_deepest
    real_seeds = sk._seeds_for_the_climb
    spent = [0]

    def counting(solid, measure, seen, best, tol):
        def counted(q):
            spent[0] += 1
            return measure(q)
        return real_climb(solid, counted, seen, best, tol)

    sk._climb_to_the_deepest = counting
    worse = 0
    for name, make in bodies().items():
        solid = make()
        got = {}
        for label, fn in (("shipped", shipped), ("round-robin", round_robin)):
            sk._seeds_for_the_climb = fn
            spent[0] = 0
            t0 = time.perf_counter()
            answer = sk.deepest_material(solid, 1e9)[0]
            got[label] = (answer, spent[0], time.perf_counter() - t0)
        sk._seeds_for_the_climb = real_seeds
        a, b = got["shipped"], got["round-robin"]
        flag = ""
        if b[0] < a[0] - 1e-9:
            flag, worse = "   <<< ROUND-ROBIN IS WORSE", worse + 1
        elif b[0] > a[0] + 1e-9:
            flag = "   <<< round-robin finds more"
        print(f"{name:26s} shipped {a[0]:9.4f} ({a[1]:3d} calls, {a[2]:5.1f}s)   "
              f"round-robin {b[0]:9.4f} ({b[1]:3d} calls, {b[2]:5.1f}s){flag}",
              flush=True)
    print(f"\nbodies where round-robin answers LESS: {worse}")
    return 1 if worse else 0


if __name__ == "__main__":
    raise SystemExit(main())
