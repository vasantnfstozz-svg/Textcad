"""Section 11 round three — do round two's 12 tests actually GO RED if round
two's fix is taken back out?  (Step 2, item 5 of the round-three brief.)

A test that stays green on the reverted code is not pinning anything.  This
puts each of the three files back to its round-ONE state (a3d6b03), runs
tests/test_tool_framework_round2.py, and restores the file.

Usage:  C:\\Python314\\python.exe probes/round2_tests_go_red_probe.py
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GIT = r"C:\Program Files\Git\cmd\git.exe"
PY = sys.executable
BASE = "a3d6b03"                      # the round-ONE fix commit
FILES = ["static/js/tool.js", "static/js/dialogs.js", "static/js/api.js"]


def _run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", cwd=str(ROOT), **kw)


def _failed(out: str) -> list[str]:
    names = set()
    for ln in out.splitlines():
        if ln.startswith("FAILED ") and "::" in ln:
            names.add(ln[len("FAILED "):].split("::")[-1].split(" ")[0])
    return sorted(names)


def main() -> int:
    keep = Path(tempfile.mkdtemp(prefix="round2_revert_"))
    for rel in FILES:
        shutil.copy(ROOT / rel, keep / Path(rel).name)
    try:
        for rel in FILES:
            old = _run([GIT, "show", f"{BASE}:{rel}"])
            if old.returncode != 0:
                print(old.stderr)
                return 1
            (ROOT / rel).write_text(old.stdout, encoding="utf-8", newline="")
            r = _run([PY, "-m", "pytest", "tests/test_tool_framework_round2.py",
                      "-q", "--no-header", "-p", "no:cacheprovider"])
            print(f"\n--- {rel} reverted to {BASE} ---")
            print(r.stdout.strip().splitlines()[-1])
            for name in _failed(r.stdout):
                print(f"    RED  {name}")
            shutil.copy(keep / Path(rel).name, ROOT / rel)
    finally:
        for rel in FILES:                       # belt and braces
            shutil.copy(keep / Path(rel).name, ROOT / rel)
    r = _run([PY, "-m", "pytest", "tests/test_tool_framework_round2.py", "-q",
              "--no-header", "-p", "no:cacheprovider"])
    print("\n--- restored ---")
    print(r.stdout.strip().splitlines()[-1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
