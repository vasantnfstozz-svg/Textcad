"""probes/meanline_mcp_door.py -- what an AI actually reads at the MCP door.

`mcp_server._design_compressor` wraps `meanline.design` in a try and calls
`build_from_design` OUTSIDE it, so the gate in front of the kernel has to come
back as a REPORT, never as a raise. Both doors are exercised here, and no
duty below reaches OpenCASCADE (every one is refused first), so this probe is
seconds, not minutes.

    C:/Python314/python.exe probes/meanline_mcp_door.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import meanline     # noqa: E402
import mcp_server   # noqa: E402

print("--- door 1: design() raises, _design_compressor catches it ---")
for kw in (dict(mass_flow_kg_s=0.5, pressure_ratio=3.0, rpm=1),
           dict(mass_flow_kg_s=0.5, pressure_ratio=1.001, rpm=45000),
           dict(mass_flow_kg_s=0.5, pressure_ratio=1.2, rpm=45000)):
    rep = mcp_server._design_compressor(kw["mass_flow_kg_s"],
                                        kw["pressure_ratio"], kw["rpm"], 35.0)
    print(f"  {kw}\n    verified={rep['verified']}  {rep.get('error')}")

print("\n--- door 2: a hand-built design straight into build_from_design ---")
d = meanline.design(meanline.Duty(mass_flow=0.5, pressure_ratio=3.0,
                                  rpm=45000))
for field, value, why in (("tip_radius", 4221135.81, "the rpm-1 answer"),
                          ("bore_radius", 200.0, "a bore past the rim"),
                          ("exit_width", 500.0, "a drum, not an impeller")):
    hand = meanline.CompressorDesign(**{**d.__dict__, field: value})
    rep = meanline.build_from_design(hand)
    print(f"  {field}={value} ({why})")
    print(f"    ok={rep.ok}  part={rep.part}  {rep.all_problems()}")
