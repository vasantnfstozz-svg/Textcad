"""Pre-seed the PRE-SWEEP run so it only spends time on the cells that can
answer job one.

A cell the CURRENT code ALLOWS cannot be "newly refused" whatever the old code
said, so the old checkout never has to build it. This writes a SKIPPED row for
each such cell into the old run's .jsonl, which the probe's own resume logic
then walks past; the comparator ignores SKIPPED rows.

    python probes/shell_r4_preseed_old_run.py --new <new.jsonl> --old <old.jsonl>

Use it only when the clock is short: a full old run also names the cells this
sweep newly ALLOWED, which is a door newly opened to a kernel that segfaults.
"""
import argparse
import json
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", required=True)
    ap.add_argument("--old", required=True)
    a = ap.parse_args()
    rows = {}
    for line in Path(a.new).read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:                                        # noqa: BLE001
            continue
        rows[(r["design"], r["t"], r["mode"])] = r
    out = Path(a.old)
    n = 0
    with out.open("a", encoding="utf-8") as fh:
        for r in rows.values():
            if r["verdict"] != "ALLOWED":
                continue
            fh.write(json.dumps({"design": r["design"], "t": r["t"],
                                 "mode": r["mode"], "verdict": "SKIPPED",
                                 "why": "the current code ALLOWS this cell"}) + "\n")
            n += 1
    print(f"{n} allowed cells pre-seeded as SKIPPED into {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
