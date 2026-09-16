"""REVIEW of 275eeab: does `_SHELL_SKIN_FACTOR = 2.0` ever refuse a CORRECT
hollow of one of the user's own designs?

275eeab calibrated the ceiling over the gauntlet corpus and the committed crash
bodies (0.61-1.056 measured, ceiling 2.0).  It did not run it over `designs/`,
and the ratio `wall_volume / (area * t)` rises with CONCAVE detail -- a hole of
radius r shelled at t is `1 + t/2r` of its own skin -- so a body whose surface
is mostly small concave features is where a correct result could cross 2.0.
The user's library has exactly those parts (isogrid-panel, thread-case, the
hole boxes).

Each design's finished body is shelled in its OWN CHILD, with the skin check
itself monkeypatched off and EVERY OTHER check left in place, so a result the
ceiling would have refused is still measured and still has to be sound.  A
segfault or a stall costs that one design.

    python probes/shell_skin_library_probe.py
    python probes/shell_skin_library_probe.py --design isogrid-panel
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT", str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))

TS = (1.0, 2.0, 3.0)
CHILD_S = 40.0


def one(stem: str) -> None:
    """one design, in this child: shell the finished body at each thickness and
    print the ratio every SOUND result reached"""
    import inspector
    import sketch
    from document import Document
    sketch.assert_walls_could_be_a_skin = lambda *a, **k: None   # the thing under test
    doc = Document.from_data(json.loads((ROOT / "designs" / f"{stem}.tcad.json").read_text("utf-8")))
    doc.rebuild()
    parts = [(fid, p) for fid, p in doc._parts.items() if p is not None]
    if not parts:
        print(f"{stem}: no body", flush=True)
        return
    fid, part = parts[-1]
    area, v_in = float(part.area), float(part.volume)
    if area <= 0 or v_in <= 0:
        return
    print(f"{stem}/{fid}: {len(part.faces())} faces, {v_in:,.0f} mm3, area {area:,.0f} mm2", flush=True)
    for t in TS:
        t0 = time.perf_counter()
        try:
            out = sketch.shell_after_guards(part, t, "inside", [], f"walls of {t:g} mm")
        except Exception as e:                                   # noqa: BLE001
            print(f"   t={t:<4g} refused ({str(e)[7:70]}) [{time.perf_counter() - t0:.0f} s]",
                  flush=True)
            continue
        sound = (bool(out.is_valid) and not inspector.health(out)
                 and inspector.closed_shell(out) and 0 < out.volume < v_in)
        ratio = float(out.volume) / (area * t)
        print(f"   t={t:<4g} {'SOUND' if sound else 'unsound'} ratio {ratio:.4f} "
              f"[{time.perf_counter() - t0:.0f} s]"
              + ("   <<< OVER THE 2.0 CEILING" if sound and ratio > 2.0 else ""), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--design")
    a = ap.parse_args()
    if a.design:
        one(a.design)
        return 0
    stems = sorted(p.stem.replace(".tcad", "") for p in (ROOT / "designs").glob("*.tcad.json"))
    over, sound, dead = [], 0, []
    for stem in stems:
        try:
            p = subprocess.run([sys.executable, __file__, "--design", stem],
                               capture_output=True, text=True, cwd=str(ROOT),
                               timeout=CHILD_S * 3 + 60,
                               env={**os.environ, "PYTHONIOENCODING": "utf-8",
                                    "TEXTCAD_KERNEL_SECONDS": str(int(CHILD_S))})
        except subprocess.TimeoutExpired:
            # a body whose own shell outlives the ladder -- said out loud, never
            # counted as covered (the autonomiq-panel body alone takes 692 s)
            dead.append((stem, "timed out"))
            print(f"{stem}: CHILD TIMED OUT -- not covered", flush=True)
            continue
        code = p.returncode & 0xFFFFFFFF
        if code not in (0,):
            dead.append((stem, f"0x{code:08X}"))
            print(f"{stem}: CHILD DIED 0x{code:08X}", flush=True)
        for line in p.stdout.splitlines():
            print(line, flush=True)
            if "ratio" in line and "SOUND" in line:
                sound += 1
                if "OVER THE 2.0 CEILING" in line:
                    over.append((stem, line.strip()))
    print(f"\n{len(stems)} designs; {sound} sound hollows measured; "
          f"sound results OVER the 2.0 ceiling: {len(over)}", flush=True)
    for r in over:
        print("   ", r, flush=True)
    if dead:
        print(f"children that died or timed out (NOT covered): {len(dead)} -> {dead}", flush=True)
    return 1 if over else 0


if __name__ == "__main__":
    raise SystemExit(main())
