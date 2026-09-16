"""Is the isogrid-panel s9016 segfault — LAUNCH-PLAN section 10's last open P1
shell row — still reachable at HEAD?  The row says ac5c11d fenced it, and three
newer guards have landed since (cc78019, 3bbfcca, b9a8f8f); this measures the
answer instead of reading it.

The journey's step 25 is `shell {thickness 1.8, open_face "none"}` on
`j13_scale` = scale 0.8 of intersect(extrude(YZ rect 6 x 10.4, 8.9),
rotate(ball 3.2, Z, 180)).  Every thickness runs in its OWN child, because the
red answer is a dead process (0xC0000005) that no in-process assert can catch,
and the child reports which guard spoke and whether the kernel was reached at
all (kernelguard.guarded is wrapped to leave a mark on stdout).

  python probes/memcap.py --gb 4 --timeout 600 -- python probes/shell_scaled_ball_head_probe.py

Measured 2026-09-16 at 6586579 — see the table this prints.
"""
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))

# the journey's own thickness first, then the bound either side of it
# (dmin/2 = 1.28 on the 2.56 x 4.8 x 5.12 body) and the two the 2026-09-12
# sweep recorded as "refuses cleanly" / "crashes"
THICKNESSES = (1.8, 1.29, 1.28, 1.27, 2.0, 3.0)

CHILD = textwrap.dedent("""
    import sys, time
    import sketch as sk
    import kernelguard
    from tests.test_shell_tool import clipped_ball

    reached = []
    real = kernelguard.guarded
    def spy(kind, solid, info, fn):
        reached.append(kind)
        return real(kind, solid, info, fn)
    kernelguard.guarded = spy

    body = clipped_ball()
    bb = body.bounding_box().size
    print(f"BODY vol={body.volume:.6g} faces={len(body.faces())} lumps={len(body.solids())} "
          f"box={bb.X:.4g}x{bb.Y:.4g}x{bb.Z:.4g}")
    t = float(sys.argv[1])
    t0 = time.perf_counter()
    try:
        out = sk.shell(body, t, open_face="none")
        print(f"BUILT vol={out.volume:.6g}")
    except ValueError as e:
        print(f"REFUSED {e}")
    except Exception as e:
        print(f"RAISED {type(e).__name__}: {str(e)[:200]}")
    print(f"KERNEL_REACHED={bool(reached)} SECONDS={time.perf_counter() - t0:.2f}")
    """)


def run(t):
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8")
    t0 = time.perf_counter()
    p = subprocess.run([sys.executable, "-c", CHILD, str(t)], capture_output=True,
                       text=True, timeout=600, env=env, cwd=str(ROOT))
    return p, time.perf_counter() - t0


if __name__ == "__main__":
    for t in THICKNESSES:
        p, wall = run(t)
        code = p.returncode & 0xFFFFFFFF
        if p.returncode != 0:
            print(f"t={t:<5g} CHILD DIED {code:#x} after {wall:.1f} s :: {p.stderr[-200:]}")
            continue
        lines = [ln for ln in p.stdout.splitlines() if ln.strip()]
        body = next((ln for ln in lines if ln.startswith("BODY")), "")
        verdict = next((ln for ln in lines if ln.split("=")[0].split()[0] in
                        ("REFUSED", "BUILT", "RAISED")), "?")
        mark = next((ln for ln in lines if ln.startswith("KERNEL_REACHED")), "?")
        if t == THICKNESSES[0]:
            print(body)
        print(f"t={t:<5g} {mark}  {verdict[:180]}")
