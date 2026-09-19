"""ROUND FOUR, job one: compare two runs of `shell_r4_library_verdict_probe.py`
cell by cell and name every cell of the user's own library whose verdict MOVED.

    python probes/shell_r4_compare_verdicts.py --old <old.jsonl> --new <new.jsonl>

A cell that was ALLOWED before the sweep and is REFUSED now is a saved design
that stopped building. Timeout refusals ("was stopped after") are listed apart,
because a wall-clock budget is not a guard.
"""
import argparse
import json
from pathlib import Path


def load(p: Path) -> dict:
    out = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:                                        # noqa: BLE001
            continue
        out[(r["design"], r["t"], r["mode"])] = r
    return out


def kind(r: dict) -> str:
    why = (r.get("why") or "").lower()
    if r["verdict"] == "ALLOWED":
        return "ALLOWED"
    for phrase, name in (
            ("was stopped after", "TIMEOUT"),
            ("crashed the geometry kernel", "CRASH"),
            ("came back as the body itself", "skin/coarea"),
            ("hollowed next to nothing", "deep-point"),
            ("nothing would be hollowed", "pre-kernel depth"),
            ("meet in the middle of", "half-extent"),
            ("nothing was hollowed", "identity"),
            ("do not fit this body", "kernel refused"),
            ("leave a broken solid", "broken result"),
            ("solid block", "lump block"),
            ("no face open", "lump opening")):
        if phrase in why:
            return name
    return "other"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    a = ap.parse_args()
    old, new = load(Path(a.old)), load(Path(a.new))
    out_of_play = ("SKIPPED", "PROBE-TIMEOUT")
    both = sorted(k for k in set(old) & set(new)
                  if old[k]["verdict"] not in out_of_play
                  and new[k]["verdict"] not in out_of_play)
    newly_refused, newly_allowed, moved_reason = [], [], []
    for k in both:
        o, n = old[k], new[k]
        ko, kn = kind(o), kind(n)
        if ko == "ALLOWED" and kn != "ALLOWED":
            (newly_refused if kn != "TIMEOUT" else moved_reason).append((k, ko, kn, n.get("why", "")))
        elif ko != "ALLOWED" and kn == "ALLOWED":
            newly_allowed.append((k, ko, kn, o.get("why", "")))
        elif ko != kn:
            moved_reason.append((k, ko, kn, n.get("why", "")))
    print(f"cells in both runs: {len(both)}  (old {len(old)}, new {len(new)})")
    print(f"\nNEWLY REFUSED (allowed before the sweep, refused now): {len(newly_refused)}")
    for k, ko, kn, why in newly_refused:
        print(f"   {k[0]:24s} t={k[1]:<7g} {k[2]:9s} {ko} -> {kn}: {why[:150]}")
    print(f"\nnewly allowed (refused before, allowed now): {len(newly_allowed)}")
    for k, ko, kn, why in newly_allowed:
        print(f"   {k[0]:24s} t={k[1]:<7g} {k[2]:9s} {ko} -> ALLOWED (old said: {why[:110]})")
    print(f"\nsame verdict, different reason / timeout noise: {len(moved_reason)}")
    for k, ko, kn, why in moved_reason:
        print(f"   {k[0]:24s} t={k[1]:<7g} {k[2]:9s} {ko} -> {kn}")
    missing = sorted(set(new) - set(old)) + sorted(set(old) - set(new))
    if missing:
        print(f"\ncells in only one run (not compared): {len(missing)}")
    return 1 if newly_refused else 0


if __name__ == "__main__":
    raise SystemExit(main())
