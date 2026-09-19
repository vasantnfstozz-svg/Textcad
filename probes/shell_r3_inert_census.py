"""How often can `assert_the_deepest_point_was_hollowed` say anything at all?

The theorem has three gates before it ever looks at the result:

    depth > t + tol            — the point has margin over the wall
    point_is_inside(solid)     — the point is material of the body it judges
    v_in - v_out <= 1%         — the kernel removed next to nothing

The first two are decided BEFORE the kernel runs, so they can be censused
without a single offset. This walks the gauntlet corpus, the committed crash
fixtures and the three drilled blocks over the same ladder of thicknesses the
round-two corpus used, CLOSED and with the TOP OPEN, and prints why each cell
is live or inert.

    C:\\Python314\\python.exe probes/shell_r3_inert_census.py
    C:\\Python314\\python.exe probes/shell_r3_inert_census.py --open top

No offset, no boolean.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))

TS = (0.2, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 5.9, 8.0)
FIXTURES = ("oneplus_case_shell_body", "impeller_cut_shell_body",
            "sliver_intersect_plate", "my_part_5_mirror_body")


def drilled(L, W, H, n, r, p):
    import build123d as b3d
    span = (n - 1) * p
    cut = b3d.Part()
    for i in range(n):
        for j in range(n):
            cut += b3d.Pos(-span / 2 + i * p, -span / 2 + j * p, 0) * \
                b3d.Cylinder(r, H * 2)
    return (b3d.Part() + b3d.Box(L, W, H)) - cut


def bodies() -> dict:
    import build123d as b3d

    import gauntlet
    out = dict(gauntlet.BODIES)
    for name in FIXTURES:
        p = ROOT / "tests" / "fixtures" / f"{name}.brep"
        if p.exists():
            out[name] = (lambda p=p: b3d.Part(b3d.import_brep(str(p)).wrapped))
    out["drilled_100"] = lambda: drilled(60.0, 60.0, 10.0, 10, 1.0, 6.0)
    out["drilled_81"] = lambda: drilled(50.0, 50.0, 60.0, 9, 0.4, 5.0)
    out["drilled_49"] = lambda: drilled(60.0, 60.0, 40.0, 7, 0.5, 8.0)
    return out


def state_of(shape, at) -> str:
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_State
    cls = BRepClass3d_SolidClassifier(shape.wrapped)
    cls.Perform(gp_Pnt(*at), 1e-7)
    return {TopAbs_State.TopAbs_IN: "IN", TopAbs_State.TopAbs_OUT: "OUT",
            TopAbs_State.TopAbs_ON: "ON"}.get(cls.State(), "?")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", default=None, help="top | bottom (default: closed)")
    ap.add_argument("--only", default=None)
    a = ap.parse_args()
    import sketch
    names = a.only.split(",") if a.only else list(bodies())
    tally = {"live": 0, "no margin": 0, "point ON the body": 0,
             "point OUT of the body": 0, "guard refuses first": 0,
             "nothing measured": 0}
    print(f"openings: {a.open or 'none (closed)'}")
    print(f"{'body':<26} {'t':>5} {'depth':>9} {'margin':>9} {'state':>5}  why")
    for name in names:
        try:
            solid = bodies()[name]()
        except Exception as e:                       # noqa: BLE001
            print(f"{name:<26} could not build ({e})")
            continue
        try:
            openings = sketch.shell_openings(solid, None, a.open) if a.open else []
        except ValueError as e:
            print(f"{name:<26} no such opening ({str(e)[:60]})")
            continue
        for t in TS:
            walls = f"walls of {t:g} mm"
            try:
                deep = sketch.assert_something_would_be_hollowed(
                    solid, t, openings, walls)
            except ValueError:
                tally["guard refuses first"] += 1
                continue
            except Exception as e:                   # noqa: BLE001
                print(f"{name:<26} {t:>5g} guard raised {type(e).__name__}: "
                      f"{str(e)[:50]}")
                continue
            if deep is None:
                tally["nothing measured"] += 1
                continue
            depth, at, tol = deep
            st = state_of(solid, at)
            if depth <= t + tol:
                why = "no margin"
            elif st == "ON":
                why = "point ON the body"
            elif st != "IN":
                why = "point OUT of the body"
            else:
                why = "live"
            tally[why] += 1
            print(f"{name:<26} {t:>5g} {depth:>9.4f} {depth - t - tol:>+9.4f} "
                  f"{st:>5}  {why}", flush=True)
    total = sum(tally.values())
    print(f"\n{total} cells")
    for k, v in tally.items():
        print(f"  {k:<24} {v:4d}  {v / max(total, 1) * 100:5.1f}%")
    reached = tally["live"] + tally["no margin"] + tally["point ON the body"] \
        + tally["point OUT of the body"]
    print(f"  of the {reached} cells that reach the theorem, "
          f"{tally['live']} ({tally['live'] / max(reached, 1) * 100:.1f}%) are live")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
