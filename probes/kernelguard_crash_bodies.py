"""The three bodies that killed the server, one after another, in ONE process.

my-part-8's sliver plate (fillet, 8 rims, radius 0.4), the oneplus case (shell
1.1 open bottom) and the pump impeller's three lumps (closed shell 1.9) each
died with 0xC0000005 in the overnight journey run. If kernelguard works, this
script prints a sentence for each one and REACHES THE END. Before it, the first
line would have been the last.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import blocks          # noqa: E402
import kernelguard     # noqa: E402
import sketch          # noqa: E402
from build123d import Part, import_brep      # noqa: E402

FX = ROOT / "tests" / "fixtures"


def body(name):
    return Part(import_brep(str(FX / f"{name}.brep")).wrapped)


def attempt(label, call):
    t0 = time.perf_counter()
    try:
        out = call()
        print(f"[{label}] BUILT {out.volume:.4g} mm3 in {time.perf_counter() - t0:.1f} s")
    except ValueError as e:
        kind = "CRASH-REFUSAL" if kernelguard.CRASH_PHRASE in str(e) else "refusal"
        print(f"[{label}] {kind} in {time.perf_counter() - t0:.1f} s")
        print(f"         {e}")
    except Exception as e:
        print(f"[{label}] !! {type(e).__name__}: {e}")


print("=== 1. my-part-8 sliver plate: fillet, the 8 horizontal rims, radius 0.4")
attempt("fillet", lambda: blocks.fillet_edges(body("sliver_intersect_plate"), 0.4, "horizontal"))

print("\n=== 2. oneplus case: shell 1.1 mm, open bottom")
attempt("shell-open", lambda: sketch.shell(body("oneplus_case_shell_body"), 1.1,
                                           None, "inside", "bottom"))

print("\n=== 3. pump impeller, 3 lumps: closed shell 1.9 mm")
attempt("shell-closed", lambda: sketch.shell(body("impeller_cut_shell_body"), 1.9,
                                             None, "inside", None))

print("\n=== 4. and the worker still works afterwards")
from build123d import Box                      # noqa: E402
attempt("plain box", lambda: blocks.fillet_edges(Part(Box(20, 10, 5).wrapped), 1.0, "top"))

kernelguard.shutdown()
print("\nREACHED THE END — the process survived all three.")
