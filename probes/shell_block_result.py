"""my-part-5 seed 18800 (bugs/20260913-193839-my-part-5-s18800-step25): the
folder was filed as a shell SEGFAULT, and the segfault is real — but the
thickness sweep beside it (probes/shell_mirror_crash.py) found two CLOSED
shells on the same body that came back "successful":

    t = 1.5   413262.875 -> 137707.973 mm3 (33.3%)   is_valid FALSE
    t = 3.0   413262.875 -> 413260.165 mm3 (100.0%)  is_valid True

The second is the whole body handed back as a hollow: 2.71 mm3 of 413262 is
nothing, and `shell_after_guards`' "nothing was hollowed" test is an IDENTITY
test with a 1e-6 floor, so 2.71 clears it. This probe asks what separates that
block from a REAL hollow, and whether the separator can fire on correct work.

    python probes/shell_block_result.py

Every case runs in its own child (an access violation kills the process).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BREP = ROOT / "probes" / "_mirror_shell_body.brep"


def facts(part) -> dict:
    """Everything a guard could read, measured rather than assumed."""
    import build123d as b3d
    from OCP.TopAbs import TopAbs_SHELL
    from OCP.TopExp import TopExp_Explorer

    import inspector
    shells, exp = 0, TopExp_Explorer(part.wrapped, TopAbs_SHELL)
    while exp.More():
        shells += 1
        exp.Next()
    bb = part.bounding_box()
    return {"volume": round(part.volume, 3), "faces": len(part.faces()),
            "lumps": len(part.solids()), "shells": shells,
            "area": round(part.area, 3),
            "valid": bool(part.is_valid),
            "closed_shell": bool(inspector.closed_shell(part)),
            "health": inspector.health(part),
            "box": [round(v, 3) for v in (bb.min.X, bb.min.Y, bb.min.Z,
                                          bb.max.X, bb.max.Y, bb.max.Z)],
            "_b3d": b3d.__name__}


def body_of(case: str):
    import build123d as b3d
    if case == "mirror":
        return b3d.Part(b3d.import_brep(str(BREP)).wrapped)
    if case == "box":                    # a shell that is known to be correct
        return b3d.Box(44, 44, 24)
    if case == "plate":
        return b3d.Box(80, 50, 12)
    raise SystemExit(f"no such body {case!r}")


def one(case: str, t: float) -> None:
    """The kernel call `shell_after_guards` makes for a CLOSED inside hollow,
    with the intermediate `off` kept, so the cavity can be measured on its
    own."""
    import build123d as b3d
    solid = body_of(case)
    off = b3d.offset(solid, amount=-t, kind=b3d.Kind.INTERSECTION)
    out = solid - off
    print("FACTS " + json.dumps({
        "case": case, "t": t,
        "in": facts(solid), "cavity": facts(off), "out": facts(out),
    }, default=str), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case")
    ap.add_argument("--t", type=float)
    a = ap.parse_args()
    if a.case:
        try:
            one(a.case, a.t)
        except Exception as e:                        # noqa: BLE001 -- the point
            print(f"REFUSED {a.case} t {a.t}: {type(e).__name__}: {str(e)[:160]}", flush=True)
        return 0
    for case, t in (("mirror", 3.0), ("mirror", 1.5), ("mirror", 1.2),
                    ("box", 3.0), ("box", 5.0), ("plate", 3.0), ("plate", 5.9)):
        p = subprocess.run([sys.executable, __file__, "--case", case, "--t", str(t)],
                           capture_output=True, text=True, cwd=str(ROOT))
        line = next((ln for ln in p.stdout.splitlines()
                     if ln.startswith(("FACTS", "REFUSED"))), None)
        if line is None:
            print(f"{case} t={t} -> DIED 0x{p.returncode & 0xFFFFFFFF:08X}", flush=True)
            continue
        if line.startswith("REFUSED"):
            print(f"{case} t={t} -> {line}", flush=True)
            continue
        d = json.loads(line[6:])
        i, c, o = d["in"], d["cavity"], d["out"]
        print(f"{case:7s} t={t:<4g} in {i['volume']:>12.3f} ({i['shells']} shell) "
              f"cavity {c['volume']:>12.3f} valid {str(c['valid']):5s} "
              f"-> out {o['volume']:>12.3f} = {100 * o['volume'] / i['volume']:6.2f}% "
              f"{o['shells']} shell(s) valid {str(o['valid']):5s} "
              f"closed {str(o['closed_shell']):5s} health {o['health']} "
              f"| wall<=area*t? {o['volume']:.0f} vs {i['area'] * t:.0f}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
