"""REVIEW-QUEUE section 9 round THREE — do round two's 9 new test cases go
RED against the module they were written for?

Round two claims its tests were "measured red first". This imports
tests/test_trace.py with `imgtrace` bound to the ROUND ONE module and runs
only round two's own test cases, so a test that passes both ways is a guard,
not a regression test, and must be named as one.

Run:  C:\\Python314\\python.exe probes/imgtrace_r3_redcheck.py
"""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)

NEW = [("test_a_thin_dark_edge_is_not_a_dark_background", (1,)),
       ("test_a_thin_dark_edge_is_not_a_dark_background", (5,)),
       ("test_a_thin_dark_edge_is_not_a_dark_background", (12,)),
       ("test_a_dark_ground_that_is_not_a_frame_still_wins", ()),
       ("test_uncross_keeps_both_halves_of_a_pinched_outline", ()),
       ("test_a_pinched_outline_still_builds_a_healthy_solid", ()),
       ("test_a_speck_cannot_raise_the_speckle_floor", ()),
       ("test_a_speck_cannot_drop_the_dot_of_an_i", ()),
       ("test_art_too_fine_for_the_target_size_still_refuses", ())]


def load_tests(which):
    """import tests/test_trace.py with `imgtrace` bound to `which`"""
    for name in ("imgtrace", "tests.test_trace", "test_trace"):
        sys.modules.pop(name, None)
    if which == "r2":
        import imgtrace as mod                                  # noqa: F401
    else:
        spec = importlib.util.spec_from_file_location(
            "imgtrace", os.path.join(HERE, f"_imgtrace_{which}.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules["imgtrace"] = mod
        spec.loader.exec_module(mod)
    spec = importlib.util.spec_from_file_location(
        "test_trace_probe", os.path.join(ROOT, "tests", "test_trace.py"))
    tt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tt)
    return tt


def main():
    results = {}
    for which in ("old", "r1", "r2"):
        tt = load_tests(which)
        for name, args in NEW:
            fn = getattr(tt, name)
            try:
                fn(*args)
                ok = "PASS"
            except AssertionError:
                ok = "FAIL"
            except Exception as exc:                            # noqa: BLE001
                ok = f"ERR {type(exc).__name__}"
            results.setdefault((name, args), {})[which] = ok
    print(f"{'test case':58s} {'old':6s} {'r1':6s} {'r2':6s}  verdict")
    print("-" * 96)
    red = 0
    for (name, args), r in results.items():
        label = name[5:] + (f"[{args[0]}]" if args else "")
        verdict = ("guard - green on round one too" if r["r1"] == "PASS"
                   else "RED on round one")
        red += r["r1"] != "PASS"
        print(f"{label:58s} {r['old']:6s} {r['r1']:6s} {r['r2']:6s}  "
              f"{verdict}")
    print("-" * 96)
    print(f"{red} of {len(results)} go red against the module they replaced")


if __name__ == "__main__":
    main()
