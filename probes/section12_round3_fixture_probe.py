r"""Section 12 ROUND THREE - what the export tests DELETE from the library.

Round two's P3 was "a round-one test leaves designs/flange-100.step behind",
and its cure was an unconditional

    (studio.DESIGNS / "flange-100.step").unlink(missing_ok=True)

in tests/test_server_layer.py's fixture - the same line tests/test_export_guard
.py has carried all along. flange-100 is a LIBRARY design (designs/flange-100
.tcad.json, a gallery tile with a preview), so designs/flange-100.step is a
file the user can make themselves: open the design, press Export. Neither
fixture asks whether the test created it.

This runs both test files against a THROWAWAY copy of the library with a
sentinel flange-100.step already in it - the user's export - and reports
whether it is still there afterwards. designs/ is never touched.

Run: C:\Python314\python.exe probes/section12_round3_fixture_probe.py
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      tempfile.mkdtemp(prefix="s12r3f-hist-"))

SENTINEL = b"ISO-10303-21; the user's own export, made by pressing Export\n"


def main() -> None:
    import studio

    lib = Path(tempfile.mkdtemp(prefix="s12r3f-lib-"))
    for p in (ROOT / "designs").glob("*.tcad.json"):
        shutil.copy2(p, lib / p.name)
    shutil.copy2(ROOT / "designs" / "examples.json", lib / "examples.json")
    studio.DESIGNS = lib

    step = lib / "flange-100.step"
    step.write_bytes(SENTINEL)
    print("=" * 74)
    print("The user's designs/flange-100.step, and the export test files")
    print("=" * 74)
    print(f"   throwaway library     : {lib}")
    print(f"   before the test run   : exists={step.exists()} "
          f"{step.stat().st_size} bytes")

    import pytest
    code = pytest.main(["tests/test_export_guard.py",
                        "tests/test_server_layer.py",
                        "-q", "-p", "no:randomly", "-p", "no:cacheprovider"])

    print(f"\n   pytest exit           : {code}")
    print(f"   after the test run    : exists={step.exists()}")
    if step.exists():
        same = step.read_bytes() == SENTINEL
        print(f"   still the user's file : {same}")
    else:
        print("   -> the fast tier DELETED a file it did not create.")


if __name__ == "__main__":
    main()
