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
from build123d import Cylinder, Pos


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

def _check(duty: Duty, flow_coeff: float = 0.28) -> None:
    """A duty the equations below cannot answer, refused in words.

    Every one of these was measured reaching the caller as a Python traceback
    (section 13 review, 2026-09-16): `rpm` 0 and a pressure ratio of exactly 1
    divide by zero (omega, and a zero work input that makes the tip speed 0),
    a ratio under 1 asks for the square root of a negative work input, and a
    backsweep of 90 degrees or more does the same through cos(beta2) — all of
    them out of the MCP `design_compressor` tool, which is an AI's door."""
    if duty.rpm <= 0:
        raise ValueError("rpm must be greater than 0 — a compressor that does "
                         "not turn has no tip speed and no size")
    if duty.pressure_ratio <= 1.0:
        raise ValueError(f"pressure ratio must be greater than 1 (got "
                         f"{duty.pressure_ratio:g}) — at 1 the stage does no "
                         f"work, and below 1 it would be a turbine")
    if duty.mass_flow <= 0:
        raise ValueError("mass flow must be greater than 0 kg/s — with no "
                         "flow the exit width and inducer have no area")
    # The window is not -90..90: the Euler relation with backsweep is
    #   U2 = sqrt(dh0 / (sigma * (1 - phi*tan(beta2))))
    # and that denominator reaches zero at atan(1/phi) — 74.36 degrees at the
    # default flow coefficient — where the blade turns the flow back as fast
    # as the through-flow pushes it and no positive tip speed exists. Past it
    # the square root failed with math's own "expected a nonnegative input,
    # got -1037485500.38", straight out to the MCP caller, from the guard
    # that exists to stop exactly that (measured 2026-09-17, round two).
    limit = math.degrees(math.atan(1.0 / flow_coeff)) if flow_coeff > 0 else 90.0
    if not -90.0 < duty.backsweep_deg < min(90.0, limit):
        raise ValueError(f"backsweep must be between -90 and {limit:.1f} "
                         f"degrees from radial (got {duty.backsweep_deg:g}) — "
                         f"at {limit:.1f} the blade turns the flow back as "
                         f"fast as it is pushed through and there is no tip "
                         f"speed that does the work; 25 to 45 is the usual "
                         f"range")
    if duty.eta <= 0 or duty.T01 <= 0:
        raise ValueError("efficiency and inlet temperature must be above 0")


# The bounds below are MEASURED, not chosen by taste
# (probes/meanline_size_probe.py, probes/meanline_backsweep_sweep.py,
# 2026-09-17). Eight sound duties spanning a 0.05 kg/s micro-turbo at 180,000
# rpm to a 50 kg/s industrial machine at 3,000 rpm answered:
#     tip radius r2       16.51 .. 1084.39 mm
#     exit width / r2      0.018 ..    0.180
#     inducer r1s / r2     0.319 ..    0.722
# so every gate sits far outside all of them.
_R2_MIN_MM = 1.0        # 16x below the smallest sound wheel measured
# The upper bound was 2000 mm ("1.8x the largest duty I happened to test") and
# that refused wheels OpenCASCADE builds perfectly. Each of these was put to
# the kernel on its own, 6 GB capped (probes/meanline_review_kernel.py,
# review round 2026-09-17), and every one came back a single watertight solid,
# health [], 13-fold symmetric, max_radius equal to the design's:
#     50 kg/s PR 2.0 @ 1500 rpm   r2 2168.78 mm   78.9 s   1.21 GB
#     0.5 kg/s PR 3.0 @ 1000 rpm  r2 4221.14 mm   86.2 s   1.20 GB
#     50 kg/s PR 2.0 @  325 rpm   r2 9998.67 mm   69.6 s   1.27 GB
# The first is the corpus's OWN largest duty at half its speed — a 1500 rpm
# machine is a 4-pole motor — so the old bound refused a real one. The kernel
# is not the constraint anywhere near here; the bound is a sanity bound, and
# it is set where it was MEASURED sound. The answer that actually failed (rpm
# 1: 4,221,135 mm, 110 s to an open shell) is still 422x outside it.
_R2_MAX_MM = 10000.0    # a wheel 20 metres across, measured sound at 9998.67


def _across(radius_mm: float) -> str:
    """A wheel's diameter in the units a person would say it in.

    The rpm-1 answer is 4,221,135.81 mm of RADIUS, so "mm" stops meaning
    anything: it is 8.4 kilometres across.
    """
    dia = 2.0 * radius_mm
    if dia >= 1e6:
        return f"{dia / 1e6:,.1f} kilometres"
    if dia >= 1000.0:
        return f"{dia / 1000.0:,.1f} metres"
    return f"{dia:,.2f} mm"


def _rpm_for(d: CompressorDesign, radius_mm: float) -> float:
    """The speed that would put THIS duty's tip radius at `radius_mm`.

    r2 = U2 / omega and omega = 2*pi*rpm/60, and the tip speed does not depend
    on the speed at all — so this is arithmetic, not advice.
    """
    return d.tip_speed * 60.0 / (2.0 * math.pi * radius_mm / 1000.0)


def _check_wheel(d: CompressorDesign, duty: Duty | None = None) -> None:
    """The equations answered; is the ANSWER a wheel? Refused in words.

    `_check` above guards the equations' own DOMAIN — whether the meanline
    relations have an answer at all. Whether that answer is a machinable object
    is a different question, and until 2026-09-17 nothing asked it: rpm 1
    answered a tip radius of 4,221,135 mm (a wheel 8.4 metres across) whose
    inducer shroud equalled its hub, a pressure ratio of 1.001 answered blades
    7,217 mm tall at the rim of a 2.61 mm wheel, and `build_from_design` handed
    every one of them to OpenCASCADE, which spent two minutes on the 8.4 metre
    one and came back with an open shell.

    The sentence names the duty to change, because an AI or a user reads it out
    of the MCP `design_compressor` tool.
    """
    r2, b2 = d.tip_radius, d.exit_width
    r1s = d.inducer_shroud_radius
    if not all(math.isfinite(v) for v in (r2, b2, r1s, d.tip_speed)):
        raise ValueError("this duty has no finite answer — check the mass "
                         "flow, the pressure ratio and the speed")
    speed = f"at {duty.rpm:,.0f} rpm " if duty is not None else ""
    # The exit width and the inlet eye are driven by the FLOW and the pressure
    # ratio together (b2 ~ mdot / (rho2 * Cm2 * r2), and the eye's annulus area
    # is mdot / (rho01 * Cx)) — and by the backsweep through the tip speed. The
    # first draft of these two opened with "a pressure ratio of 3" for a
    # 10,000 kg/s duty and for a -80 degree forward sweep, which named the one
    # dial that was not the problem.
    lead = (f"at {duty.mass_flow:g} kg/s and pressure ratio "
            f"{duty.pressure_ratio:g}, " if duty is not None else "")
    # The SPEED belongs in this list and was missing from it. Both of these
    # rules compare something flow-driven against the rim, and the rim is
    # r2 = U2 / omega — so a slower wheel always has a bigger one, while the
    # exit width and the inlet eye grow more slowly or not at all. Measured
    # (probes/meanline_gate_boundary_probe.py): 0.5 kg/s at pressure ratio 1.2
    # is refused at 45,000 rpm (eye 50.86 against a 35.72 mm rim) and is a
    # well-proportioned wheel at 10,000 rpm (eye 53.45, rim 160.74) — with the
    # duty, the one thing the sentence told them to change, untouched.
    fix = ("raise the pressure ratio, lower the mass flow, or lower the "
           "speed — the rim grows as the wheel turns slower")
    if duty is not None and not 25.0 <= duty.backsweep_deg <= 45.0:
        fix += (f"; a backsweep of {duty.backsweep_deg:g} degrees is outside "
                f"the usual 25 to 45 and is part of why the wheel comes out "
                f"this shape")
    if r2 > _R2_MAX_MM:
        raise ValueError(
            f"{speed}the wheel would come out {_across(r2)} across — raise "
            f"the speed to at least about {_rpm_for(d, _R2_MAX_MM):,.0f} rpm; "
            f"less pressure or less backsweep would shrink it too")
    if r2 < _R2_MIN_MM:
        raise ValueError(
            f"{speed}the wheel would come out {_across(r2)} across, too small "
            f"to machine — lower the speed to at most about "
            f"{_rpm_for(d, _R2_MIN_MM):,.0f} rpm")
    if b2 >= r2:
        raise ValueError(
            f"{lead}the blades would come out {b2:,.2f} mm tall at the rim of "
            f"a wheel only {r2:,.2f} mm in radius — that is a drum, not an "
            f"impeller; {fix}")
    if r1s >= r2:
        raise ValueError(
            f"{lead}the inlet eye would come out beyond the rim of the wheel "
            f"itself ({r1s:,.2f} mm against a tip radius of {r2:,.2f} mm), so "
            f"the air would have nowhere to turn; {fix}")
    # `bore_radius` has a 2 mm floor, and the blade is cut back to clear the
    # bore (see `one_blade`); a bore at or past the rim would cut the blade
    # away entirely and leave an empty component instead of a sentence
    if d.bore_radius >= r2:
        raise ValueError(
            f"{lead}the shaft bore would come out {d.bore_radius:,.2f} mm, at "
            f"or past the rim of a wheel only {r2:,.2f} mm in radius — there "
            f"would be no impeller left around it; {fix}")


def shroud_root_radius(blade_root_radius: float) -> float:
    """Where the shroud cutter's inner wall stands, given the blade root.

    It used to be `blade_root - 2.0` in two places, and that fixed 2 mm is more
    than the WHOLE hub nose on any wheel under about 25 mm radius. So a sound
    micro-turbo duty (0.05 kg/s, PR 1.8, 180,000 rpm — a 16.51 mm wheel) handed
    `blocks.revolve_profile` a radius of -0.7025 and the user read
    `builder crashed: ValueError('revolve_profile: point 1 has radius
    -0.7025 ...')`, an internal function's name for a duty nothing was wrong
    with (measured 2026-09-17, probes/meanline_kernel_repro.py).

    The cutter only ever meets the blades, and they start at the root, so the
    axis is a perfectly good inner wall: clamp at 0. Every wheel big enough for
    the old expression keeps the cutter it had, to the micron.
    """
    return max(blade_root_radius - 2.0, 0.0)


def one_blade(d: CompressorDesign):
    """The single blade `build_from_design` patterns around the hub.

    THE SHAFT BORE IS TAKEN OUT OF IT HERE. `build_from_design` drills the
    bore into the hub with `blocks.with_center_hole` and fuses the blades on
    afterwards, so any blade material reaching inside the bore fills the hole
    back in — and nothing notices: `to_spec` measures symmetry, solid count
    and tip radius, all of which a wheel with a plugged bore still passes.
    Measured 2026-09-17 (probes/meanline_review_kernel.py): the 0.05 kg/s
    micro-turbo duty came back ok=True, ONE watertight solid, health [],
    13-fold symmetric — with 67.27 mm3 of blade sitting in its 2 mm bore.

    It is the SECOND fixed 2 mm on a small wheel, one function from the first:
    `bore_radius` is `max(0.5 * r1h, 2.0)` and the blade root is `0.75 * r1h`,
    so without that floor the root clears the bore by construction.

    The cut is not conditional, because the blade's inner end cannot be
    predicted: `blocks.curved_blade` traces a ribbon and the cap overshoots
    `inner_radius` by an amount that follows the blade ANGLE, not just the
    thickness — 0.74 mm on the micro turbo against 1.66 mm on a PR 1.3 blower,
    both 1.5 mm thick (bisected with real booleans,
    probes/meanline_bore_reach.py). On a wheel whose blades already clear the
    bore the cut removes nothing and the volume is identical to the last digit.
    """
    blade = blocks.curved_blade(
        inner_radius=0.75 * d.inducer_hub_radius, outer_radius=d.tip_radius,
        inlet_angle_deg=d.beta1_deg, exit_angle_deg=d.beta2_deg,
        height=d.axial_length, thickness=max(0.02 * d.tip_radius, 1.5))
    return blade - Cylinder(radius=d.bore_radius,
                            height=8.0 * d.axial_length)


def design(duty: Duty, flow_coeff: float = 0.28,
           inlet_flow_coeff: float = 0.30) -> CompressorDesign:
    """First-order centrifugal compressor meanline design."""
    _check(duty, flow_coeff)
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
    out = CompressorDesign(
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
    # the answer is arithmetic; this asks whether it is a WHEEL, on the
    # ROUNDED numbers, because those are the ones the geometry is built from
    _check_wheel(out, duty)
    return out


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
    # `design()` gates its own answer, but a CompressorDesign can also be built
    # by hand (an editor, a repair loop, a saved file), and NOTHING that is not
    # a wheel may reach OpenCASCADE: the rpm-1 answer took 110 s in the kernel
    # and came back an open shell. A failed report, never a raise —
    # `mcp_server._design_compressor` calls this outside its try.
    try:
        _check_wheel(d)
    except ValueError as e:
        return assembly.AssemblyReport(ok=False, mode="fuse", components=[],
                                       assembly_problems=[str(e)])
    t, L = d.backplate_thk, d.axial_length
    r_in = 0.75 * d.inducer_hub_radius     # blade root buried in the hub nose

    def hub():
        prof = [(0, 0), (d.tip_radius, 0), (d.tip_radius, t),
                (d.inducer_hub_radius, t + L), (0, t + L)]
        return blocks.with_center_hole(blocks.revolve_profile(prof),
                                       d.bore_radius)

    def bladeset():
        one = one_blade(d)      # the shaft bore already taken out of it
        allb = blocks.polar_pattern(Pos(0, 0, t) * one, d.blade_count)
        # shroud cut: full height at the inducer, tapering to b2 at the tip
        big = t + L + 50.0
        root = shroud_root_radius(r_in)
        cutter = blocks.revolve_profile([
            (root, t + L),
            (d.inducer_shroud_radius, t + L),
            (d.tip_radius, t + d.exit_width),
            (d.tip_radius + 15.0, t + d.exit_width),
            (d.tip_radius + 15.0, big),
            (root, big),
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
