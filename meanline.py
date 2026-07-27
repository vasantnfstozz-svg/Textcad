"""
meanline.py — the design calculator (our mini "Vista CCD").

THE POINT: in a robust text-to-CAD system, the geometry of an engineering part
must come from CALCTULATED ground truth, not from anyone's imagination — not the
user's, and certainly not the LLM's. This module turns a DUTY ("compress 0.5
kg/s of air to pressure ratio 3 at 45,000 rpm") into a full geometric parameter
set via first-order centrifugal-compressor meanline design, and hands the
pipeline a Spec whose numbers are physics, not guesses.

    Duty (flow, PR, rpm)  ->  design()  ->  CompressorDesign (r2, b2, Z, betas..)
                                             |-> build_from_design()  (geometry)
                                             |-> to_spec()            (ground truth)

The methods are standard textbook first-order (Euler work equation, Wiesner
slip, velocity triangles, continuity). HONEST LIMITS, stated plainly:
  * no loss models, no choke/surge margins, no diffusion limits — sizes are
    plausible, not optimized. (That's what full tools like Vista CCD add.)
  * the 3D blade is a first-order geometric approximation: the camber curve
    beta1->beta2 is applied in plan view; the true 3D inducer wrap (blade angle
    varying hub-to-shroud along the axial inlet) is not modeled yet.
"""

from __future__ import annotations
from dataclasses import dataclass
import math

import blocks
import inspector
import assembly
from build123d import Pos


# ---------------------------------------------------------------------------
# Inputs and outputs
# ---------------------------------------------------------------------------

@dataclass
class Duty:
    """What the compressor must DO (the engineering requirement)."""
    mass_flow: float            # kg/s
    pressure_ratio: float       # total-to-total
    rpm: float
    T01: float = 288.15         # inlet stagnation temperature, K
    P01: float = 101325.0       # inlet stagnation pressure, Pa
    eta: float = 0.80           # assumed stage isentropic efficiency
    backsweep_deg: float = 35.0  # chosen exit blade angle (from radial)
    # gas properties (air)
    cp: float = 1005.0
    gamma: float = 1.4
    R: float = 287.0


@dataclass
class CompressorDesign:
    """Everything geometry needs, all in mm/deg except where noted."""
    # thermo / kinematics (SI, for the report)
    work_input: float           # J/kg
    tip_speed: float            # m/s
    slip_factor: float
    power_kw: float
    # geometry (mm / deg)
    tip_radius: float           # r2
    exit_width: float           # b2 (blade height at exit)
    blade_count: int            # Z
    beta2_deg: float            # exit blade angle (backsweep)
    beta1_deg: float            # inducer blade angle at shroud
    inducer_shroud_radius: float  # r1s
    inducer_hub_radius: float     # r1h
    axial_length: float         # impeller axial length L
    backplate_thk: float        # backplate disc thickness
    bore_radius: float

    def report(self) -> str:
        return "\n".join([
            f"  tip radius r2          : {self.tip_radius:8.2f} mm",
            f"  tip speed U2           : {self.tip_speed:8.1f} m/s",
            f"  exit blade width b2    : {self.exit_width:8.2f} mm",
            f"  blade count Z          : {self.blade_count:8d}",
            f"  exit blade angle b2*   : {self.beta2_deg:8.1f} deg (backsweep)",
            f"  inducer blade angle b1 : {self.beta1_deg:8.1f} deg",
            f"  inducer shroud radius  : {self.inducer_shroud_radius:8.2f} mm",
            f"  inducer hub radius     : {self.inducer_hub_radius:8.2f} mm",
            f"  axial length L         : {self.axial_length:8.2f} mm",
            f"  slip factor (Wiesner)  : {self.slip_factor:8.3f}",
            f"  shaft power            : {self.power_kw:8.1f} kW",
        ])


# ---------------------------------------------------------------------------
# The meanline design calculation
# ---------------------------------------------------------------------------

def design(duty: Duty, flow_coeff: float = 0.28,
           inlet_flow_coeff: float = 0.30) -> CompressorDesign:
    """First-order centrifugal compressor meanline design."""
    g, cp = duty.gamma, duty.cp
    beta2 = math.radians(duty.backsweep_deg)

    # 1) required work input (Euler head) from the pressure ratio
    dh0s = cp * duty.T01 * (duty.pressure_ratio ** ((g - 1) / g) - 1.0)
    dh0 = dh0s / duty.eta                                   # J/kg

    # 2) blade count from Wiesner slip at a target slip factor ~0.85,
    #    then the consistent slip factor for that (integer) count
    sigma_target = 0.85
    z_exact = (math.sqrt(math.cos(beta2)) / (1.0 - sigma_target)) ** (1.0 / 0.7)
    Z = max(5, round(z_exact))
    sigma = 1.0 - math.sqrt(math.cos(beta2)) / Z ** 0.7      # Wiesner

    # 3) tip speed from Euler with backsweep:  dh0 = sigma*U2^2*(1 - phi*tan(b2))
    U2 = math.sqrt(dh0 / (sigma * (1.0 - flow_coeff * math.tan(beta2))))
    omega = 2.0 * math.pi * duty.rpm / 60.0
    r2 = U2 / omega                                          # m

    # 4) exit width b2 from continuity (crude isentropic exit density)
    rho01 = duty.P01 / (duty.R * duty.T01)
    rho2 = rho01 * duty.pressure_ratio ** (1.0 / g)          # first-order
    Cm2 = flow_coeff * U2
    b2 = duty.mass_flow / (rho2 * Cm2 * 2.0 * math.pi * r2)  # m

    # 5) inducer: axial inflow Cx, annulus area from continuity,
    #    hub radius as a fraction, shroud blade angle from the velocity triangle
    Cx = inlet_flow_coeff * U2
    r1h = 0.30 * r2 * 0.35                                   # small hub nose
    area = duty.mass_flow / (rho01 * Cx)
    r1s = math.sqrt(area / math.pi + r1h ** 2)
    U1s = omega * r1s
    beta1 = math.degrees(math.atan(U1s / Cx))

    # 6) axial length (Jansen-style rule of thumb) and mechanical bits
    L = 0.35 * r2
    mm = 1000.0
    return CompressorDesign(
        work_input=dh0, tip_speed=U2, slip_factor=sigma,
        power_kw=duty.mass_flow * dh0 / 1000.0,
        tip_radius=round(r2 * mm, 2),
        exit_width=round(max(b2 * mm, 1.0), 2),   # clamp: machinable minimum
        blade_count=Z,
        beta2_deg=duty.backsweep_deg,
        beta1_deg=round(beta1, 1),
        inducer_shroud_radius=round(r1s * mm, 2),
        inducer_hub_radius=round(r1h * mm, 2),
        axial_length=round(L * mm, 2),
        backplate_thk=round(max(0.03 * r2 * mm, 2.0), 2),
        bore_radius=round(max(0.5 * r1h * mm, 2.0), 2),
    )


# ---------------------------------------------------------------------------
# Design -> geometry (via the verified blocks) and -> Spec (ground truth)
# ---------------------------------------------------------------------------

def to_spec(d: CompressorDesign) -> inspector.Spec:
    """The Spec IS the calculation — ground truth the build must hit."""
    return inspector.Spec(
        symmetry=d.blade_count,
        n_solids=1,
        tip_radius=d.tip_radius,
        size=(None, None, d.backplate_thk + d.axial_length),
        tol=1.0,
    )


def build_from_design(d: CompressorDesign) -> assembly.AssemblyReport:
    """Build the impeller geometry the design describes, fully verified."""
    t, L = d.backplate_thk, d.axial_length
    r_in = 0.75 * d.inducer_hub_radius     # blade root buried in the hub nose

    def hub():
        prof = [(0, 0), (d.tip_radius, 0), (d.tip_radius, t),
                (d.inducer_hub_radius, t + L), (0, t + L)]
        return blocks.with_center_hole(blocks.revolve_profile(prof),
                                       d.bore_radius)

    def bladeset():
        one = blocks.curved_blade(
            inner_radius=r_in, outer_radius=d.tip_radius,
            inlet_angle_deg=d.beta1_deg, exit_angle_deg=d.beta2_deg,
            height=L, thickness=max(0.02 * d.tip_radius, 1.5))
        allb = blocks.polar_pattern(Pos(0, 0, t) * one, d.blade_count)
        # shroud cut: full height at the inducer, tapering to b2 at the tip
        big = t + L + 50.0
        cutter = blocks.revolve_profile([
            (r_in - 2.0, t + L),
            (d.inducer_shroud_radius, t + L),
            (d.tip_radius, t + d.exit_width),
            (d.tip_radius + 15.0, t + d.exit_width),
            (d.tip_radius + 15.0, big),
            (r_in - 2.0, big),
        ])
        return allb - cutter

    return assembly.build_and_verify(
        [assembly.Component("hub", hub),
         assembly.Component("blades", bladeset)],
        mode="fuse", assembly_spec=to_spec(d))


# ---------------------------------------------------------------------------
# Demo: duty -> design -> geometry -> verify -> STEP.  python meanline.py
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import build123d as b3d

    duty = Duty(mass_flow=0.5, pressure_ratio=3.0, rpm=45000)
    print(f"DUTY: {duty.mass_flow} kg/s air, PR {duty.pressure_ratio}, "
          f"{duty.rpm:.0f} rpm\n")

    d = design(duty)
    print("=== meanline design (the calculated ground truth) ===")
    print(d.report())

    print("\n=== building the geometry the calculation demands ===")
    rep = build_from_design(d)
    print(rep.summary())

    if rep.ok and rep.part is not None:
        m = inspector.measure(rep.part)
        sym_ok = inspector.is_rotationally_symmetric(rep.part, d.blade_count)
        print("\n--- independent verification vs the calculation ---")
        print(f"  {d.blade_count}-fold symmetry (measured): {sym_ok}")
        print(f"  tip radius (measured max reach): {m['max_radius']} "
              f"(calculated: {d.tip_radius})")
        print(f"  single watertight solid: "
              f"{m['n_solids'] == 1 and m['is_manifold']}")
        b3d.export_step(rep.part, "compressor_designed.step")
        print("\n  wrote compressor_designed.step")
        try:
            from ocp_vscode import show
            show(rep.part)
            print("  (sent to OCP CAD Viewer)")
        except Exception as e:
            print(f"  (viewer not shown: {e})")
    else:
        print("\nFAILED — see problems above")
