"""probes/samples_bore_probe.py -- is the shaft bore of the OTHER shipped
sample a hole? `sample_impeller` drills `hub` and fuses the blades afterwards,
exactly like `sample_compressor` does, so the same question has to be asked of
it before its ordering is left alone or changed.

    C:/Python314/python.exe probes/samples_bore_probe.py [impeller|compressor]
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import inspector   # noqa: E402
import samples     # noqa: E402
from build123d import Cylinder  # noqa: E402

which = sys.argv[1] if len(sys.argv) > 1 else "impeller"
doc = samples.SAMPLES[which]()
bore = {"impeller": 6.0, "compressor": 4.92}[which]
t0 = time.perf_counter()
ok = doc.rebuild()
res = doc.result()
m = inspector.measure(res)
print(f"{which}: rebuild {time.perf_counter() - t0:.1f} s ok={ok} "
      f"spec_problems={doc.spec_problems}")
print(f"  volume={m['volume']!r} faces={m['n_faces']} solids={m['n_solids']} "
      f"manifold={m['is_manifold']} size={m['size']}")
print(f"  cylinder_radii={m.get('cylinder_radii')}")
zmax = m["size"][2]
plug = res & Cylinder(radius=bore, height=4.0 * (zmax + 1.0))
vol = float(plug.volume) if plug is not None else 0.0
print(f"  MATERIAL INSIDE THE {bore} mm BORE: {vol:.6f} mm3")
