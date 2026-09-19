"""Round three, attack 1: WHEN is `assert_the_deepest_point_was_hollowed` able
to speak at all?

The theorem's first gate is `point_is_inside(solid, at) is True`. Two questions
this answers by measurement, both cheap (no offset, no boolean):

  1. An OPEN shell's deep point. `deepest_material` gives every sample of an
     OPENING face a bound of `inf`, so those stations are measured FIRST and
     the loop breaks on the first one that is deep enough. Those points lie ON
     the opening face, so the solid classifier answers ON, not IN — and the
     theorem returns without judging anything. Measured here over boxes,
     plates and a drilled plate, closed and open.
  2. A MULTI-LUMP body. `_climb_to_the_deepest` accepts a candidate whenever
     `BRepClass3d_SolidClassifier` does not say OUT. If that classifier
     answers IN for a point in the AIR BETWEEN two lumps, the climb can read
     deeper than any material really is — the one direction that is dangerous.

    C:\\Python314\\python.exe probes/shell_r3_deep_point_reach.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))


def drilled(L, W, H, n, r, p):
    import build123d as b3d
    span = (n - 1) * p
    cut = b3d.Part()
    for i in range(n):
        for j in range(n):
            cut += b3d.Pos(-span / 2 + i * p, -span / 2 + j * p, 0) * \
                b3d.Cylinder(r, H * 2)
    return (b3d.Part() + b3d.Box(L, W, H)) - cut


def state_of(shape, at):
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_State
    cls = BRepClass3d_SolidClassifier(shape.wrapped)
    cls.Perform(gp_Pnt(*at), 1e-7)
    s = cls.State()
    return {TopAbs_State.TopAbs_IN: "IN", TopAbs_State.TopAbs_OUT: "OUT",
            TopAbs_State.TopAbs_ON: "ON"}.get(s, str(s))


def part_one() -> None:
    import build123d as b3d

    import sketch
    print("=== 1. the deep point an OPEN shell hands to the theorem ===")
    print(f"{'body':<26} {'t':>5} {'open':<7} {'depth':>9} {'margin':>8} "
          f"{'state in solid':>15}  verdict")
    bodies = [
        ("box 50", lambda: b3d.Part() + b3d.Box(50, 50, 50)),
        ("plate 60x60x12", lambda: b3d.Part() + b3d.Box(60, 60, 12)),
        ("plate 100x60x20", lambda: b3d.Part() + b3d.Box(100, 60, 20)),
        ("drilled 60x60x10 (100)", lambda: drilled(60, 60, 10, 10, 1.0, 6.0)),
    ]
    for name, make in bodies:
        solid = make()
        for t in (1.0, 2.5, 3.0):
            for opening in (None, "top"):
                walls = f"walls of {t:g} mm"
                openings = sketch.shell_openings(solid, None, opening or "none")
                try:
                    deep = sketch.assert_something_would_be_hollowed(
                        solid, t, openings, walls)
                except ValueError as e:
                    print(f"{name:<26} {t:>5g} {opening or 'closed':<7} "
                          f"{'-':>9} {'-':>8} {'-':>15}  guard refuses "
                          f"({str(e)[:40]})")
                    continue
                if deep is None:
                    print(f"{name:<26} {t:>5g} {opening or 'closed':<7} "
                          f"{'-':>9} {'-':>8} {'-':>15}  nothing measured")
                    continue
                depth, at, tol = deep
                st = state_of(solid, at)
                inert = (depth <= t + tol) or st != "IN"
                why = "INERT" if inert else "live"
                if depth <= t + tol:
                    why += " (no margin)"
                elif st != "IN":
                    why += f" (point is {st} the body)"
                print(f"{name:<26} {t:>5g} {opening or 'closed':<7} "
                      f"{depth:>9.4f} {depth - t - tol:>8.4f} {st:>15}  {why}")


def part_two() -> None:
    import build123d as b3d
    print("\n=== 2. the solid classifier on a MULTI-LUMP body ===")
    two = (b3d.Part() + b3d.Pos(-20, 0, 0) * b3d.Box(10, 10, 10)) \
        + b3d.Pos(20, 0, 0) * b3d.Box(10, 10, 10)
    print(f"two 10mm boxes at x=-20 and x=+20; lumps: {len(two.solids())}, "
          f"volume {two.volume:,.3f}")
    for at, what in (((-20, 0, 0), "inside lump 1"),
                     ((20, 0, 0), "inside lump 2"),
                     ((0, 0, 0), "AIR between them"),
                     ((0, 0, 40), "AIR far above")):
        print(f"  {what:<18} {str(at):<14} -> {state_of(two, at):<4}")

    # three lumps, the shape the pump impeller crash body has
    three = two + b3d.Pos(0, 25, 0) * b3d.Box(10, 10, 10)
    print(f"a third lump at y=+25; lumps: {len(three.solids())}")
    for at, what in (((-20, 0, 0), "inside lump 1"),
                     ((20, 0, 0), "inside lump 2"),
                     ((0, 25, 0), "inside lump 3"),
                     ((0, 12, 0), "AIR between all")):
        print(f"  {what:<18} {str(at):<14} -> {state_of(three, at):<4}")


def part_three() -> None:
    """What `deepest_material` answers on that two-lump body: if the climb can
    walk into the air, the answer is deeper than the 5.0 mm that 10 mm cubes
    really hold."""
    import build123d as b3d

    import sketch
    print("\n=== 3. deepest_material on the two-lump body (truth: 5.0) ===")
    two = (b3d.Part() + b3d.Pos(-20, 0, 0) * b3d.Box(10, 10, 10)) \
        + b3d.Pos(20, 0, 0) * b3d.Box(10, 10, 10)
    for t in (4.0, 6.0, 9.0, 20.0):
        got = sketch.deepest_material(two, t, ())
        if got is None:
            print(f"  t={t:<5g} nothing measured")
            continue
        depth, at, tol = got
        print(f"  t={t:<5g} depth {depth:9.4f} at "
              f"({at[0]:8.3f},{at[1]:8.3f},{at[2]:8.3f})  "
              f"state {state_of(two, at):<4}  "
              f"{'OVER-READ' if depth > 5.0 + 1e-3 else 'ok'}")
    # and a body whose lumps are FAR apart in one direction only
    far = (b3d.Part() + b3d.Pos(-60, 0, 0) * b3d.Box(8, 8, 8)) \
        + b3d.Pos(60, 0, 0) * b3d.Box(8, 8, 8)
    print("  --- two 8mm cubes 120mm apart (truth: 4.0) ---")
    for t in (5.0, 10.0, 30.0):
        got = sketch.deepest_material(far, t, ())
        if got is None:
            print(f"  t={t:<5g} nothing measured")
            continue
        depth, at, tol = got
        print(f"  t={t:<5g} depth {depth:9.4f} at "
              f"({at[0]:8.3f},{at[1]:8.3f},{at[2]:8.3f})  "
              f"state {state_of(far, at):<4}  "
              f"{'OVER-READ' if depth > 4.0 + 1e-3 else 'ok'}")


def main() -> int:
    part_one()
    part_two()
    part_three()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
