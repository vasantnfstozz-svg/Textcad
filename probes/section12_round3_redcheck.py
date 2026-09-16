r"""Section 12 ROUND THREE - the red check on round two's own tests.

Reverts ONE of round two's fixes in studio.py so `pytest tests/test_server_layer
.py` can be run against it, then restores the file from a backup. A test that
stays green under the revert of the fix it is named for is not a test of that
fix.

    C:\Python314\python.exe probes/section12_round3_redcheck.py backup
    C:\Python314\python.exe probes/section12_round3_redcheck.py export
    C:\Python314\python.exe probes/section12_round3_redcheck.py spec
    C:\Python314\python.exe probes/section12_round3_redcheck.py restore
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = ROOT / "studio.py"
BACKUP = ROOT / "probes" / "_studio_redcheck_backup.txt"

EXPORT_FIXED = "    slug = _slug_of_active() or _design_slug(doc.name)\n"
EXPORT_ROUND_ONE = "    slug = _design_slug(doc.name)\n"

NUM_FIXED = """    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    try:
        return math.isfinite(v)
    except (OverflowError, TypeError):   # int too large to convert to float
        return False
"""
NUM_ROUND_ONE = \
    "    return isinstance(v, (int, float)) and not isinstance(v, bool)\n"

HOLES_FIXED = """            try:
                if not math.isfinite(float(r)):
                    raise ValueError
                if int(n) != float(n):
                    raise ValueError
            except (TypeError, ValueError, OverflowError):
"""
HOLES_ROUND_ONE = """            try:
                float(r)
                if int(n) != float(n):
                    raise ValueError
            except (TypeError, ValueError):
"""


def main() -> None:
    what = sys.argv[1] if len(sys.argv) > 1 else "backup"
    src = TARGET.read_text(encoding="utf-8")
    if what == "backup":
        BACKUP.write_text(src, encoding="utf-8")
        print(f"backed up {len(src)} chars")
        return
    if what == "restore":
        TARGET.write_text(BACKUP.read_text(encoding="utf-8"), encoding="utf-8")
        BACKUP.unlink()
        print("studio.py restored")
        return
    if what == "export":
        out = src.replace(EXPORT_FIXED, EXPORT_ROUND_ONE)
    elif what == "spec":
        out = src.replace(NUM_FIXED, NUM_ROUND_ONE).replace(
            HOLES_FIXED, HOLES_ROUND_ONE)
    else:
        raise SystemExit(f"unknown: {what}")
    assert out != src, f"{what}: the revert did not apply"
    TARGET.write_text(out, encoding="utf-8")
    print(f"{what}: round two's fix reverted")


if __name__ == "__main__":
    main()
