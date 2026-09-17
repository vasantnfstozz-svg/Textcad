"""The gear-case segfault the 2026-09-17 library sweep reported, measured.

That sweep ran `shell_after_guards` DIRECTLY — no pre-kernel guards, no worker
— so "gear-case SEGFAULTED" says only that OpenCASCADE dies somewhere in there.
Three questions it does not answer, and this probe does:

  1. WHICH thickness, and is the window one band or several (the oneplus case's
     is not: 0.2 builds, 0.5-1.5 dies, 2.0 refuses politely).
  2. Do the PRE-kernel guards already refuse it, in which case the kernel is
     never asked and there is nothing to guard.
  3. What does the USER see — the whole point of kernelguard.py is that a
     segfault costs one feature and not the app, so the shipped door has to be
     measured, not the raw call.

    python probes/shell_gear_case_crash_probe.py --raw      (crashes on purpose)
    python probes/shell_gear_case_crash_probe.py            (the shipped door)

One child per run: an access violation is not catchable, so `--raw` ends the
process and the caller reads the exit code.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))


def the_body(design: str, which: int):
    from document import Document
    doc = Document.from_data(json.loads(
        (ROOT / "designs" / f"{design}.tcad.json").read_text("utf-8")))
    doc.rebuild()
    parts = [(fid, p) for fid, p in doc._parts.items() if p is not None]
    fid, part = parts[which]
    print(f"{design}/{fid}: {len(part.faces())} faces, {len(part.solids())} lump(s), "
          f"{part.volume:,.3f} mm3, area {part.area:,.3f} mm2, "
          f"bbox {part.bounding_box().size}", flush=True)
    return part


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--design", default="gear-case")
    ap.add_argument("--which", type=int, default=-1)
    ap.add_argument("--t", type=float, nargs="+",
                    default=[0.5, 1.0, 1.5, 1.8, 2.0, 2.5, 3.0, 4.0])
    ap.add_argument("--raw", action="store_true",
                    help="skip every guard and call the kernel in THIS process")
    a = ap.parse_args()
    import sketch
    part = the_body(a.design, a.which)
    for t in a.t:
        t0 = time.perf_counter()
        try:
            if a.raw:
                out = sketch.shell_after_guards(part, t, "inside", [],
                                                f"walls of {t:g} mm")
            else:
                out = sketch.shell(part, t)
            print(f"  t={t:<5g} BUILT {out.volume:,.3f} mm3 "
                  f"[{time.perf_counter() - t0:.0f}s]", flush=True)
        except Exception as e:                                # noqa: BLE001 — the point
            print(f"  t={t:<5g} {type(e).__name__}: {str(e)[:150]} "
                  f"[{time.perf_counter() - t0:.0f}s]", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
