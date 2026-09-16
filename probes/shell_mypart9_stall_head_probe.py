"""Does the my-part-9 s96223 stall — bugs/20260916-011919-my-part-9-s96223-step19,
LAUNCH-PLAN section 10 P2 — still stall at HEAD, now that the depth guard has
landed (cc78019) and been amended twice (3bbfcca, b9a8f8f)?

The filed step is `shell {thickness 2.5, open_face "top"}` on `j1_chamfer`.
Each thickness runs in its OWN child with a SHORT kernel budget
(TEXTCAD_KERNEL_SECONDS), so a stall costs the budget instead of 15 minutes,
and the child says which of the three answers it got:

  * a PRE-KERNEL refusal (the guards saw it; kernel never asked)
  * the kernel's own refusal, and how long it took
  * the worker's "was stopped after" — the stall, still there

The body is rebuilt from the folder's before.tcad.json and exported to
probes/_thin_mypart9.brep, so the numbers below are the filed body's own.

  python probes/memcap.py --gb 4 --timeout 900 -- python probes/shell_mypart9_stall_head_probe.py [budget_s]

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

FOLDER = "bugs/20260916-011919-my-part-9-s96223-step19"
FID = "j1_chamfer"
# the filed thickness, the two the 2026-09-16 triage saw refused quickly, and
# one more from the stall band
THICKNESSES = (2.5, 1.5, 1.7, 1.6)

CHILD = textwrap.dedent("""
    import json, sys, time
    from pathlib import Path
    import sketch as sk
    import kernelguard
    from document import Document

    ROOT = Path.cwd()
    doc = Document.from_data(json.loads(
        (ROOT / sys.argv[1] / "before.tcad.json").read_text(encoding="utf-8")))
    doc.rebuild()
    body = doc._parts[sys.argv[2]]
    bb = body.bounding_box().size
    print(f"BODY vol={body.volume:.6g} faces={len(body.faces())} lumps={len(body.solids())} "
          f"box={bb.X:.4g}x{bb.Y:.4g}x{bb.Z:.4g}")
    from build123d import export_brep
    export_brep(body, str(ROOT / "probes" / "_thin_mypart9.brep"))

    reached = []
    real = kernelguard.guarded
    def spy(kind, solid, info, fn):
        reached.append(time.perf_counter())
        return real(kind, solid, info, fn)
    kernelguard.guarded = spy

    t = float(sys.argv[3])
    t0 = time.perf_counter()
    try:
        out = sk.shell(body, t, open_face="top")
        verdict = f"BUILT vol={out.volume:.6g}"
    except ValueError as e:
        verdict = f"REFUSED {e}"
    except Exception as e:
        verdict = f"RAISED {type(e).__name__}: {str(e)[:200]}"
    done = time.perf_counter()
    guard_s = (reached[0] - t0) if reached else (done - t0)
    print(f"KERNEL_REACHED={bool(reached)} GUARD_S={guard_s:.2f} TOTAL_S={done - t0:.2f}")
    print(verdict)
    """)


if __name__ == "__main__":
    budget = sys.argv[1] if len(sys.argv) > 1 else "60"
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8",
               TEXTCAD_KERNEL_SECONDS=budget,
               TEXTCAD_HISTORY_ROOT=str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))
    print(f"kernel budget {budget} s")
    for t in THICKNESSES:
        t0 = time.perf_counter()
        p = subprocess.run([sys.executable, "-c", CHILD, FOLDER, FID, str(t)],
                           capture_output=True, text=True, timeout=1800, env=env, cwd=str(ROOT))
        wall = time.perf_counter() - t0
        if p.returncode != 0:
            print(f"t={t:<5g} CHILD DIED {p.returncode & 0xFFFFFFFF:#x} after {wall:.1f} s "
                  f":: {p.stderr[-200:]}")
            continue
        lines = [ln for ln in p.stdout.splitlines() if ln.strip()]
        if t == THICKNESSES[0]:
            print(next((ln for ln in lines if ln.startswith("BODY")), "?"))
        mark = next((ln for ln in lines if ln.startswith("KERNEL_REACHED")), "?")
        verdict = next((ln for ln in lines if ln.split()[0] in ("REFUSED", "BUILT", "RAISED")), "?")
        print(f"t={t:<5g} wall={wall:6.1f}s {mark}")
        print(f"        {verdict[:240]}")
