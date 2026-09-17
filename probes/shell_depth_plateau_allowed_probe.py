"""Every wall the plateau seeding newly ALLOWS, put to the kernel.

THE RULE this exists for: the corpus behind a guard whose job is refusing only
tests its REFUSALS, so a fix that raises the guard's number proves nothing by
running that corpus. The walls between the old number and the new one are the
ones nobody has ever built. Each of them is built here, and the result is
measured — OCCT-valid, watertight, health clean, and a cavity whose volume is
printed rather than assumed.

The "before" number is produced by putting the seeding back to depth-only, so
the two columns come from the same code on the same body in the same process.

    python probes/shell_depth_plateau_allowed_probe.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "probes"))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))

import sketch as sk  # noqa: E402
from shell_depth_plateau_seeds_probe import BODIES  # noqa: E402


def depth_only(seen, deepest, tol):
    """the seeding as it shipped before this fix: the deepest stations, spread"""
    ranked = sorted(((d0, d0, q0) for d0, q0, _b in seen), key=lambda r: -r[0])
    return sk._spread_out(ranked, tol, sk._DEPTH_CLIMB_SEEDS)


def main() -> int:
    import inspector
    from shell_depth_oracle_probe import oracle_depth
    bad = 0
    for name, make in BODIES.items():
        solid = make()
        real = sk._seeds_for_the_climb
        sk._seeds_for_the_climb = depth_only
        before = sk.deepest_material(solid, 1e9)[0]
        sk._seeds_for_the_climb = real
        after = sk.deepest_material(solid, 1e9)[0]
        truth, _at = oracle_depth(solid, coarse=20, refine=4)
        print(f"\n{name}: {solid.volume:,.3f} mm3 — before {before:.4f}, "
              f"after {after:.4f}, grid oracle {truth:.4f}", flush=True)
        if after <= before + 1e-6:
            print("   nothing newly allowed", flush=True)
            continue
        band = [before + (after - before) * f for f in (0.1, 0.4, 0.7, 0.95)]
        for t in band:
            try:
                out = sk.shell(solid, t)
            except ValueError as e:
                # a POLITE refusal is a pass, whoever made it: the guard no
                # longer stands in the kernel's way, and the kernel's own no is
                # a sentence and not a corrupt body. Only the guard refusing
                # inside its own newly allowed band would be a contradiction.
                who = ("THE GUARD" if "nothing would be hollowed" in str(e)
                       else "the kernel")
                print(f"   t={t:<8.4f} refused by {who}: {str(e)[:90]}", flush=True)
                bad += who == "THE GUARD"
                continue
            ok = (bool(out.is_valid) and inspector.closed_shell(out)
                  and not inspector.health(out))
            print(f"   t={t:<8.4f} built  cavity {solid.volume - out.volume:10.3f} mm3  "
                  f"valid={bool(out.is_valid)} watertight={inspector.closed_shell(out)} "
                  f"health={inspector.health(out) or 'clean'}", flush=True)
            bad += not ok
        # and just past the new number it must still be refused
        try:
            sk.shell(solid, after * 1.05)
            print(f"   t={after * 1.05:<8.4f} BUILT — the guard let a wall past its "
                  f"own answer", flush=True)
            bad += 1
        except ValueError as e:
            print(f"   t={after * 1.05:<8.4f} refused, as it must: {str(e)[:80]}",
                  flush=True)
    print(f"\n{bad} newly allowed wall(s) that came back unsound, or that the "
          f"guard refused inside its own band")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
