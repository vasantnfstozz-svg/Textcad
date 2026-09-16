"""ONE solid this time: tapered rib genuinely fused into a uniform slab."""
import os, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT", str(Path(os.environ.get("TEMP", ".")) / "tcad-probe-hist"))
import build123d as b3d
import sketch as sk
from shell_depth_oracle_probe import oracle_depth

def body(slab_t, slab_y0):
    w = b3d.Part() + b3d.extrude(b3d.Plane.XZ * b3d.make_face(
        b3d.Polyline((-40, 0), (40, 0), (40, 30), (-40, 2), close=True)), 40)
    print("   wedge bbox", w.bounding_box().min, w.bounding_box().max)
    slab = b3d.Pos(0, slab_y0, slab_t / 2) * b3d.Box(80, 80, slab_t)
    return b3d.Part() + (w + slab)

for slab_t, slab_y0 in ((24.0, -30.0), (26.0, -30.0)):
    print(f"--- slab {slab_t} mm")
    s = body(slab_t, slab_y0)
    print(f"    n_solids={len(s.solids())} vol={s.volume:.1f} bbox={s.bounding_box().size}")
    if len(s.solids()) != 1:
        continue
    guard = sk.deepest_material(s, 1e9)[0]
    truth, at = oracle_depth(s, coarse=20, refine=4)
    print(f"    guard deepest = {guard:.4f} ; oracle = {truth:.4f} at {at}")
    for t in (12.0, 12.2, 12.4):
        try:
            sk.assert_wall_fits_every_lump(s, t, f"walls of {t} mm")
            sk.assert_something_would_be_hollowed(s, t, [], f"walls of {t} mm")
            out = sk.shell(s, t)
            print(f"    t={t}: BUILT  cavity={s.volume-out.volume:.2f} mm3 "
                  f"valid={out.is_valid} watertight={len(out.faces())>0}")
        except ValueError as e:
            print(f"    t={t}: REFUSED: {str(e)[:130]}")
