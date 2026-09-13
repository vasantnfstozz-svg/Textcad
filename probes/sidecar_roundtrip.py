"""Can a body cross a process boundary without its edges/faces changing identity?

The overnight run's crash fixes hang on ONE question: if we run the dangerous
kernel call (fillet on picked edges, shell with picked openings) in a CHILD
process, the child has to pick THE SAME edges and faces the parent picked. The
cheapest way to send a body is a .brep file. So:

  1. how long does export_brep + import_brep cost, per body size?
  2. does part.edges() come back in the SAME ORDER, with the same geometry?
  3. same for part.faces()?
  4. what does a cold child cost just to import build123d?

Nothing here is assumed: order is compared element by element by length and
centre, not by count.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from build123d import Box, Part, export_brep, import_brep   # noqa: E402

SCRATCH = ROOT / "probes" / "_sidecar_tmp"
SCRATCH.mkdir(exist_ok=True)


def _size(s):
    """An edge measures by length, a face by area; build123d gives BOTH
    attributes on every Shape and returns None for the wrong one."""
    for attr in ("length", "area"):
        v = getattr(s, attr, None)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def fingerprint(shapes):
    out = []
    for s in shapes:
        c = s.center()
        out.append((round(_size(s), 9),
                    round(c.X, 9), round(c.Y, 9), round(c.Z, 9)))
    return out


def report(name, part):
    t0 = time.perf_counter()
    before_e = fingerprint(part.edges())
    before_f = fingerprint(part.faces())
    t_fp = time.perf_counter() - t0

    path = SCRATCH / f"{name}.brep"
    t0 = time.perf_counter()
    export_brep(part, str(path))
    t_w = time.perf_counter() - t0

    t0 = time.perf_counter()
    back = Part(import_brep(str(path)).wrapped)
    t_r = time.perf_counter() - t0

    after_e = fingerprint(back.edges())
    after_f = fingerprint(back.faces())

    e_ok = before_e == after_e
    f_ok = before_f == after_f
    e_same_set = sorted(before_e) == sorted(after_e)
    f_same_set = sorted(before_f) == sorted(after_f)

    print(f"\n=== {name}")
    print(f"  faces {len(before_f):4d}  edges {len(before_e):4d}  "
          f"volume {part.volume:.6g} -> {back.volume:.6g}")
    print(f"  brep {path.stat().st_size / 1024:.1f} kB   "
          f"write {t_w * 1000:.1f} ms   read {t_r * 1000:.1f} ms   "
          f"(fingerprint {t_fp * 1000:.1f} ms)")
    print(f"  edge ORDER preserved: {e_ok}      edge SET preserved: {e_same_set}")
    print(f"  face ORDER preserved: {f_ok}      face SET preserved: {f_same_set}")
    if not e_ok and e_same_set:
        moved = sum(1 for a, b in zip(before_e, after_e) if a != b)
        print(f"  !! {moved} of {len(before_e)} edges are at a different INDEX")
    return dict(name=name, faces=len(before_f), edges=len(before_e),
                kb=round(path.stat().st_size / 1024, 1),
                write_ms=round(t_w * 1000, 2), read_ms=round(t_r * 1000, 2),
                edge_order=e_ok, face_order=f_ok,
                edge_set=e_same_set, face_set=f_same_set,
                vol_before=part.volume, vol_after=back.volume)


rows = []
rows.append(report("plain_box", Box(20, 10, 5)))

for fx in ("sliver_intersect_plate", "oneplus_case_shell_body", "impeller_cut_shell_body"):
    p = ROOT / "tests" / "fixtures" / f"{fx}.brep"
    if p.exists():
        rows.append(report(fx, Part(import_brep(str(p)).wrapped)))
    else:
        print(f"\n=== {fx}: MISSING at {p}")

(SCRATCH / "roundtrip.json").write_text(json.dumps(rows, indent=1))
print("\nwrote", SCRATCH / "roundtrip.json")
