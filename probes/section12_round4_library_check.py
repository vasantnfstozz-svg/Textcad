"""Does the section-12 test run leave designs/ exactly as it found it?

Round four's item 4: every fast-tier door into the user's library. Snapshot
name + size + sha256 of every file under designs/ (the version histories
included), run the server-layer test files, snapshot again, and print the
difference.

Run:  C:\\Python314\\python.exe probes/section12_round4_library_check.py
"""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DESIGNS = ROOT / "designs"
FILES = ["tests/test_server_layer.py", "tests/test_api.py",
         "tests/test_export_guard.py", "tests/test_tab_reuse.py",
         "tests/test_session_restore.py", "tests/test_examples_gallery.py",
         "tests/test_supervisor.py", "tests/test_version_api.py",
         "tests/test_launch_rules.py", "tests/test_import_step.py",
         "tests/test_mcp_arrival.py", "tests/test_mcp_server.py"]


def snap():
    out = {}
    for p in sorted(DESIGNS.rglob("*")):
        if p.is_file():
            out[str(p.relative_to(DESIGNS))] = (
                p.stat().st_size,
                hashlib.sha256(p.read_bytes()).hexdigest()[:16])
    return out


before = snap()
print(f"designs/ before: {len(before)} files")
r = subprocess.run([sys.executable, "-m", "pytest", *FILES, "-q",
                    "--no-header", "-p", "no:cacheprovider"],
                   cwd=ROOT, capture_output=True, text=True)
tail = [ln for ln in r.stdout.splitlines()
        if " passed" in ln or " failed" in ln or " error" in ln]
print("pytest:", tail[-1] if tail else r.stdout[-500:])
after = snap()
print(f"designs/ after:  {len(after)} files")

added = sorted(set(after) - set(before))
gone = sorted(set(before) - set(after))
changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
print("ADDED  :", added or "none")
print("REMOVED:", gone or "none")
print("CHANGED:", changed or "none")
print()
print("designs/ is byte-identical:", not (added or gone or changed))
