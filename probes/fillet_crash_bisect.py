"""Which of the 8 "horizontal" edges makes fillet SEGFAULT? One subset per
child process. Also prints what each edge IS, so the class can be named."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BREP = ROOT / "tests" / "fixtures" / "sliver_intersect_plate.brep"


def load():
    import build123d as b3d
    import blocks
    part = b3d.Part(b3d.import_brep(str(BREP)).wrapped)
    return part, blocks.edges_for(part, "horizontal"), blocks


def describe():
    import build123d as b3d
    part, picked, _ = load()
    for i, e in enumerate(picked):
        faces = [f for f in part.faces() if any(
            _key(x) == _key(e) for x in f.edges())]
        print(f"  e{i}: {str(e.geom_type):22s} len {e.length:9.4f} "
              f"mid {tuple(round(c, 3) for c in e.center())} "
              f"faces {[str(f.geom_type).split('.')[-1] for f in faces]}", flush=True)
    _ = b3d


def _key(s):
    return s.wrapped.TShape(), tuple(s.wrapped.Location().Transformation().Transforms())


def one(idx: list[int], radius: float) -> None:
    part, picked, blocks = load()
    subset = [picked[i] for i in idx]
    out = blocks._b3d_fillet(subset, radius=radius) if hasattr(blocks, "_b3d_fillet") \
        else __import__("build123d").fillet(subset, radius=radius)
    print(f"OK {idx}: {out.volume:.3f}", flush=True)


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--describe":
        describe()
        return 0
    if len(sys.argv) > 1 and sys.argv[1] == "--idx":
        idx = [int(x) for x in sys.argv[2].split(",")]
        try:
            one(idx, float(sys.argv[3]))
        except Exception as e:                         # noqa: BLE001 — the point
            print(f"REFUSED {idx}: {type(e).__name__}: {str(e)[:120]}", flush=True)
        return 0
    p = subprocess.run([sys.executable, __file__, "--describe"], capture_output=True,
                       text=True, cwd=str(ROOT))
    print(p.stdout.rstrip(), flush=True)
    for i in range(8):
        run([i])
    for combo in ([0, 1], [0, 1, 2, 3], [4, 5, 6, 7], list(range(8))):
        run(combo)
    return 0


def run(idx):
    p = subprocess.run([sys.executable, __file__, "--idx", ",".join(map(str, idx)), "0.4"],
                       capture_output=True, text=True, cwd=str(ROOT))
    tail = [ln for ln in p.stdout.splitlines() if ln.startswith(("OK", "REFUSED"))]
    code = p.returncode & 0xFFFFFFFF
    print(f"edges {str(idx):16s} -> {tail[0] if tail else f'DIED 0x{code:08X}'}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
