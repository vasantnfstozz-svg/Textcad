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


def _width(mm_value: float) -> str:
    """A blade width in the units a person would say it in.

    The clamped widths are 0.056719 mm and 0.000005 mm, and "0.00 mm" is not a
    sentence anyone can act on.
    """
    if mm_value >= 0.1:
        return f"{mm_value:.2f} mm"
    if mm_value >= 1e-3:
        return f"{mm_value * 1000.0:,.0f} micrometres"
    return "under a micrometre"


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
    # what continuity actually asked for, BEFORE the machinable floor below
    # clamped it. 0.0 on a design built by hand, which knows no ideal.
    exit_width_ideal: float = 0.0
    # the duty's own flow and the most any opening can pass in this gas state
    # (kg/s per mm2, the isentropic choked mass flux). `eye_problem` asks with
    # them whether the passage the blades leave can pass THIS duty, which a
    # fraction of the ring cannot answer. 0.0 on a hand-built design: the
    # question is then not asked, exactly as `exit_width_ideal` is not read.
    mass_flow: float = 0.0
    inlet_choke_flux: float = 0.0

    @property
    def notes(self) -> tuple[str, ...]:
        """Where these numbers are NOT the physics, said in plain sentences.

        `exit_width` is clamped to a machinable floor and nothing said so, so
        the design REPORTED a width the equations never asked for and the MCP
        tool handed it to an AI as `exit_width_mm`. Measured 2026-09-17
        (probes/meanline_exit_width_clamp.py): 0.5 kg/s at pressure ratio 3 and
        1,000 rpm wants 0.056719 mm and the design said 1.00 — 18x — and the
        1e-6 kg/s duty wants 0.000005 mm and said the same 1.00. The floor
        itself is right (nothing cuts a 57 micrometre channel); the silence is
        not, and it is also why `b2 >= r2` cannot catch a wheel enormously
        oversized for its flow — the number that rule reads has been clamped.
        (`_check_wheel`'s `b2 > L` rule, added the same day, does catch the
        clamped ones whose wheel is shallower than the floor.)
        """
        out: list[str] = []
        ideal = self.exit_width_ideal
        if ideal > 0.0 and self.exit_width > 1.01 * ideal:
            ratio = self.exit_width / ideal
            # "1 times wider than this flow needs" is what a 0.01 kg/s blower
            # at 90,000 rpm read (0.88 mm wanted, 1.00 mm floor) until round
            # four: every ratio from 1.01 to 1.49 rounded to "1 times", which
            # is not a sentence. Under half again, a percentage is the way a
            # person says it (measured, probes/meanline_round4_kernel.py).
            times = ("thousands of times" if ratio >= 1000.0
                     else f"{ratio:,.0f} times" if ratio >= 1.5
                     else f"{(ratio - 1.0) * 100:.0f}%")
            out.append(
                f"the exit blade width works out at {_width(ideal)}, thinner "
                f"than a cutter can make, so the wheel is built with the "
                f"{self.exit_width:.2f} mm floor instead — {times} wider than "
                f"this flow needs. It builds, but it is not the wheel the duty "
                f"describes: raise the speed or the mass flow, or lower the "
                f"pressure ratio, and the width becomes a real one")
        # ...and the same question for the INDUCER ANGLE, round four's. See
        # `built_blade_angle` for what was measured and how.
        eye_r = self.inducer_shroud_radius
        # a hand-built design with no hub nose has no camber to predict: the
        # blade root is 0.75 * r1h and the law starts there
        root = 0.75 * self.inducer_hub_radius
        if root > 0.0 and eye_r > root:
            built = built_blade_angle(self, eye_r)
            off = built - self.beta1_deg
            if abs(off) > _ANGLE_NOTE_DEG:
                out.append(
                    f"the inducer angle above, {self.beta1_deg:.1f} degrees, "
                    f"is not the angle the blade is cut with where the air "
                    f"meets it. The blade is drawn as one flat camber line "
                    f"from its root, buried in the hub, out to the rim, and at "
                    f"the {eye_r:,.2f} mm inlet eye the metal stands at "
                    f"{built:.1f} degrees — {abs(off):.1f} out. The wheel "
                    f"builds and is the right size; its inducer is not the one "
                    f"this angle describes, so the air meets the blade at the "
                    f"wrong angle. Lower the speed: the wheel grows, its eye "
                    f"is a smaller part of it, and the gap closes (measured, "
                    f"probes/meanline_round4_advice.py)")
        return tuple(out)

    def report(self) -> str:
        return "\n".join(self._lines() + [f"  NOTE: {n}" for n in self.notes])

    def _lines(self) -> list[str]:
        return [
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
        ]


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

# The exit blade width has a machinable floor, and it should: continuity asks
# for 57 micrometres at 0.5 kg/s / PR 3 / 1,000 rpm and 0.005 micrometres at
# 1e-6 kg/s, and no cutter makes either. What was wrong was the SILENCE — the
# design reported 1.00 mm for both and the MCP tool passed that on as
# `exit_width_mm`. See `CompressorDesign.notes`.
_EXIT_WIDTH_FLOOR_MM = 1.0

# How much of its own shaft bore a finished wheel may contain before the build
# is called a failure, as a fraction of the bore cylinder's volume over the
# wheel's height. Round one's plugged micro-turbo held 67.21 mm3 of a 97.8 mm3
# bore — 69% — while every sound wheel measured exactly 0.000000 mm3, so the
# threshold sits three orders of magnitude clear of both
# (probes/compressor_bore_order_probe.py, probes/meanline_bore_check_cost.py).
_BORE_PLUG_FRACTION = 0.005

# How much of the inlet annulus has to be left OPEN once the blades stand in
# it. The eye is the other end of the wheel from the exit width: it is what the
# machine takes IN, `mcp_server` hands it to an AI as `inducer_shroud_radius_mm`
# beside `exit_width_mm`, and until 2026-09-17 nothing measured it against the
# metal. The blades are `max(0.02 * r2, 1.5)` mm thick — the third fixed
# millimetre on a small wheel, one file from the bore's 2 mm and the shroud
# offset's — and on a small wheel that floor fills the eye solid.
#
# MEASURED on nine built wheels (probes/meanline_eye_sweep2.py): the passage
# across the inlet plane, as a fraction of the annulus there to be blocked —
#
#     0.005 kg/s PR 1.8  250,000 rpm  60 deg   r2  14.87    3.21%
#     0.005 kg/s PR 1.1  100,000 rpm  35 deg   r2  11.55    3.36%
#     0.005 kg/s PR 1.8   90,000 rpm -20 deg   r2  28.25    6.55%
#     ------------------------------------------------- the rule cuts here ---
#     0.02  kg/s PR 2.5  150,000 rpm  35 deg   r2  25.35   16.06%
#     0.005 kg/s PR 4.0   90,000 rpm   0 deg   r2  48.28   26.50%
#     0.05  kg/s PR 1.8  180,000 rpm  35 deg   r2  16.51   31.37%  (micro turbo)
#     0.1   kg/s PR 4.0  250,000 rpm  25 deg   r2  18.64   37.43%
#     20    kg/s PR 2.5    5,000 rpm  35 deg   r2 760.55   68.96%
#     0.5   kg/s PR 3.0   45,000 rpm  35 deg   r2  93.80   70.71%  (the sample)
#
# so the line sits in a 2.5x gap with every wheel the corpus calls sound above
# it — the shipped sample at 70.71% and the module's own micro turbo at 31.37%
# — and the dead ones below. Below a tenth the wheel's own inlet velocity is
# supersonic several times over (3.51 mm2 for 5 g/s of air is 1,163 m/s), which
# is what "not an inlet" means in numbers.
_EYE_OPEN_FRACTION = 0.10

# THE BLADE ANGLES ARE PUBLISHED AND NOTHING MEASURED THEM. `mcp_server` hands
# an AI `beta1_deg` and `beta2_deg` beside the radii, and round four measured
# the blade the kernel actually cuts (probes/meanline_blade_angle_spline.py,
# and with real booleans on the metal, probes/meanline_blade_angle_metal.py):
#
#   * at the RIM the metal is 1.1 to 3.1 degrees steeper than `beta2_deg`;
#   * at the blade's ROOT it is 6.4 to 28.2 degrees steeper than `beta1_deg`,
#     on every wheel, the shipped sample included (49.4 published, 64.1 built);
#   * and at the INLET EYE — the station `beta1_deg` is defined at, "inducer
#     blade angle at shroud" — the metal is 0.1 to 77.7 degrees AWAY from it:
#         the shipped sample   49.4 published   47.99 built    -1.4
#         a big turbo          46.8             46.68          -0.1
#         a small turbo        63.3             49.60         -13.7
#         a micro turbo        67.4             46.89         -20.5
#         backsweep -60        65.9            -11.80         -77.7  (the
#             blade leans the OTHER WAY from the angle published)
#
# Two causes compound, and neither is in this file: `blocks.curved_blade`
# integrates the camber law in 16 forward-Euler steps, and the first step
# advances the radius by 73% of itself, which over-wraps the blade by 18-23%;
# and the law runs beta1 at the blade ROOT (0.75 * r1h, deep inside the hub)
# and ramps it linearly in radius, so an inlet eye at 0.72 of the tip radius
# is nowhere near its own published angle. A wheel is not refused for this —
# the geometry is sound and the kernel builds it — but the design SAYS so now.
_ANGLE_NOTE_DEG = 2.0            # the prediction is good to 0.07 degrees

# `blocks.curved_blade` walks the camber law in this many forward-Euler steps.
# It is read here to say what the blade will BE, and
# tests/test_meanline_gate.py::test_the_predicted_blade_angle_is_the_one_in_the_metal
# measures a real blade with booleans, so this goes red if that ever changes.
_CAMBER_STEPS = 16

# How far past its own choking limit a wheel's measured inlet may be before the
# build is refused. `_EYE_OPEN_FRACTION` above asks what FRACTION of the ring
# the blades leave open; it cannot ask whether the air FITS, because that
# depends on the duty and not on the wheel alone. The same tenth is an easy
# inlet on a 5,000 rpm industrial stage and an impossible one on a 250,000 rpm
# micro turbo. Measured over a 6,273-design grid (probes/meanline_eye_choke.py,
# probes/meanline_choke_bands.py): the tenth passes 3,178 wheels whose passage
# cannot pass their own mass flow even at the speed of sound — up to 9.4x over
# — and refuses NOT ONE that could.
#
# ROUND THREE's own nine kernel-measured wheels, each one's passage against the
# flow its duty asks for (probes/meanline_round4_numbers.py):
#     3.21%    21.54x     6.55%     6.19x    31.37%   1.52x
#     3.36%     5.91x    16.06%     3.78x    37.43%   1.99x
#     26.50%    2.63x     68.96%    0.88x    70.71%   0.95x  (the sample)
#
# THE LINE IS NOT WHERE SOUNDNESS BEGINS. Everything past 1.0x is a wheel that
# cannot pass its duty's flow, and the module's own inlet sizing puts it there:
# `design()` sizes the eye ring for Cx = 0.30 * U2 with NO allowance for the
# blades that then stand in it, so its whole corpus lands between 0.75x and
# 2.0x (the shipped sample at 0.95x) and a rule at 1.0 would refuse the module
# rather than the wheel. That is named for the plan, not fixed here: it moves
# every eye radius, including the user's shipped sample. What this line does
# refuse is the wheels that cannot pass HALF their own flow — 2.6x on a
# perfectly ordinary 0.01 kg/s blower at 90,000 rpm that the tenth passed at
# 11.91% open (built, probes/meanline_round4_kernel.py) — while the most
# blocked wheel the corpus calls sound (the micro turbo, 1.52x measured on a
# real 16.0 s build) keeps building. The nearest wheel on the allowed side is
# 1.99x and it cannot pass its own flow either; it is 0.1 kg/s at pressure
# ratio 4 and 250,000 rpm, and it is the plan's problem, not this rule's.
_EYE_CHOKE_MARGIN = 2.0


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
    # THE INLET EYE IS A RING, AND A RING NEEDS TWO RADII. `r1s` is
    # sqrt(area/pi + r1h**2), so a duty whose continuity area vanishes beside
    # the hub answers r1s == r1h: an eye of ZERO area, published to an AI as
    # `inducer_shroud_radius_mm` and built by the kernel as a wheel with no
    # inlet at all. 289 of 4,424 designs in a 7,040-duty grid land there
    # (probes/meanline_round3_gaps.py) — 0.0001 kg/s at 200 rpm answers a
    # 3.5 metre wheel whose eye and hub are both 187.23 mm. The shaft bore is
    # the other floor: on a wheel under about 6 mm of tip radius the 2 mm bore
    # swallows the eye whole. Both say the same thing — there is no ring.
    inner = max(d.inducer_hub_radius, d.bore_radius)
    if r1s <= inner:
        what = ("the shaft bore" if d.bore_radius >= d.inducer_hub_radius
                else "the hub nose it sits on")
        raise ValueError(
            f"{lead}the inlet eye would come out {r1s:,.2f} mm, no wider than "
            f"{what} ({inner:,.2f} mm) — the air has no ring to come in "
            f"through, so this is a disc, not an impeller; raise the mass flow "
            f"or raise the speed, which shrinks the hub without shrinking the "
            f"eye")
    # `bore_radius` has a 2 mm floor, and the blade is cut back to clear the
    # bore (see `one_blade`); a bore at or past the rim would cut the blade
    # away entirely and leave an empty component instead of a sentence
    if d.bore_radius >= r2:
        raise ValueError(
            f"{lead}the shaft bore would come out {d.bore_radius:,.2f} mm, at "
            f"or past the rim of a wheel only {r2:,.2f} mm in radius — there "
            f"would be no impeller left around it; {fix}")
    # THE EXIT WIDTH HAS TO FIT IN THE WHEEL. `build_from_design`'s shroud
    # cutter runs from (r1s, t+L) DOWN to (r2, t+b2); if b2 is taller than the
    # wheel is deep the line runs UP instead, the cut takes nothing off the
    # rim, and the blades stand full height there — so the wheel's exit width
    # is L, not the b2 the design published, and NOTHING could see it: not
    # `to_spec` (symmetry, solid count, tip radius, overall height all still
    # pass), not health, not the symmetry proof. MEASURED 2026-09-17
    # (probes/meanline_rim_height_probe.py): 0.05 kg/s at pressure ratio 1.01
    # and 10,000 rpm published exit_width 17.29 mm and built a wheel 12.480 mm
    # tall at the rim — ok=True, one watertight solid, health [], 14-fold
    # symmetric, 39% wrong on the one number that sets what the machine flows.
    # 43 duties in a 12,320-duty grid land here with an UNCLAMPED width
    # (probes/meanline_shroud_scan.py); every one has b2/r2 >= 0.35, where a
    # real centrifugal wheel is 0.02 to 0.10, so this refuses no machine
    # anyone would build — it refuses the answers the model cannot draw.
    if b2 > d.axial_length:
        raise ValueError(
            f"{lead}the blades would have to be {b2:,.2f} mm tall where they "
            f"leave the rim, but the wheel comes out only "
            f"{d.axial_length:,.2f} mm deep — they would run full height "
            f"there and the wheel would not be the one these numbers "
            f"describe; {fix}")


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


def built_blade_angle(d: CompressorDesign, radius: float) -> float:
    """The angle from radial the blade is ACTUALLY CUT with at `radius`.

    Not the design's camber law — the curve `blocks.curved_blade` draws. It
    integrates d(theta) = tan(beta)/r * dr in `_CAMBER_STEPS` forward-Euler
    steps and splines the points, and the steps are coarse where it matters
    most: the blade root is 0.75 * 0.105 * r2 by construction, so the FIRST
    step advances the radius by 73% of itself on every wheel ever designed
    here, whatever its size.

    Each step is the arc of a logarithmic spiral — the curve of constant blade
    angle — so the angle that joins two nodes is atan(dtheta / ln(r2/r1)); the
    curve's angle AT a node is the average of the two either side, which is
    what the spline's tangent does, and in between it runs linearly in radius.

    This is arithmetic because `design()` has no geometry. It was checked
    against the OCCT curve's own tangent on twelve duties — worst 0.07 degrees
    at the inlet eye (probes/meanline_camber_predict.py) — and against the
    METAL with real booleans: the shipped sample's blade reads 48.3 degrees at
    its eye radius against the 48.03 predicted here
    (probes/meanline_blade_angle_metal.py).
    """
    ri, ro = 0.75 * d.inducer_hub_radius, d.tip_radius
    n = _CAMBER_STEPS
    if not (ro > ri > 0) or n < 2:
        return d.beta2_deg
    rs, ths, theta = [], [], 0.0
    for i in range(n + 1):
        t = i / n
        rs.append(ri + (ro - ri) * t)
        ths.append(theta)
        if i < n:
            beta = math.radians(d.beta1_deg
                                + (d.beta2_deg - d.beta1_deg) * t)
            theta += math.tan(beta) / rs[-1] * ((ro - ri) / n)
    seg = [math.degrees(math.atan2(ths[i + 1] - ths[i],
                                   math.log(rs[i + 1] / rs[i])))
           for i in range(n)]
    node = ([seg[0]] + [0.5 * (seg[i - 1] + seg[i]) for i in range(1, n)]
            + [seg[-1]])
    x = min(max((radius - ri) / ((ro - ri) / n), 0.0), float(n))
    i = min(int(x), n - 1)
    return node[i] + (node[i + 1] - node[i]) * (x - i)


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


def _choke_flux(duty: Duty) -> float:
    """kg/s per mm2: the most any opening can pass in this gas state.

    The isentropic choked mass flux, P0/sqrt(T0) * sqrt(g/R) * (2/(g+1)) **
    ((g+1)/(2(g-1))) — 241.3 kg/s per m2 for air at 288.15 K and 101,325 Pa,
    the textbook figure. It is a hard ceiling: no casing, no speed and no
    amount of suction moves more air than that through a given area, so a
    passage narrower than mdot / this cannot pass the duty at all.
    """
    g, R = duty.gamma, duty.R
    if duty.T01 <= 0 or R <= 0 or g <= 1.0:
        return 0.0
    return (duty.P01 / math.sqrt(duty.T01) * math.sqrt(g / R)
            * (2.0 / (g + 1.0)) ** ((g + 1.0) / (2.0 * (g - 1.0)))) * 1e-6


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
        # the clamp is right — nothing cuts a 57 micrometre channel — but it
        # is no longer SILENT: `exit_width_ideal` carries what continuity
        # asked for, and `CompressorDesign.notes` says so in a sentence
        exit_width=round(max(b2 * mm, _EXIT_WIDTH_FLOOR_MM), 2),
        exit_width_ideal=b2 * mm,
        blade_count=Z,
        beta2_deg=duty.backsweep_deg,
        beta1_deg=round(beta1, 1),
        inducer_shroud_radius=round(r1s * mm, 2),
        inducer_hub_radius=round(r1h * mm, 2),
        axial_length=round(L * mm, 2),
        backplate_thk=round(max(0.03 * r2 * mm, 2.0), 2),
        bore_radius=round(max(0.5 * r1h * mm, 2.0), 2),
        mass_flow=duty.mass_flow,
        inlet_choke_flux=_choke_flux(duty),
    )
    # the answer is arithmetic; this asks whether it is a WHEEL, on the
    # ROUNDED numbers, because those are the ones the geometry is built from
    _check_wheel(out, duty)
    return out


# ---------------------------------------------------------------------------
# Design -> geometry (via the verified blocks) and -> Spec (ground truth)
# ---------------------------------------------------------------------------

def bore_material(part, d: CompressorDesign) -> float:
    """mm3 of a finished wheel sitting INSIDE its own shaft bore.

    The one question `to_spec` cannot ask. A Spec can pin symmetry, solid
    count, tip radius and height, and round one measured a wheel that passed
    all four with 67.27 mm3 of blade in its 2 mm bore. `Spec.holes` does not
    reach it either: the plugged micro-turbo still reported
    `cylinder_radii={2.0: 1, 16.51: 5}` — the bore's wall is still a
    cylindrical face, it is just filled in behind
    (probes/compressor_bore_order_probe.py, 2026-09-17). Only a boolean
    answers, and on the shipped wheel it costs 0.14 s against a 73 s build
    (probes/meanline_bore_check_cost.py).
    """
    try:
        plug = part & Cylinder(radius=d.bore_radius,
                               height=4.0 * (d.backplate_thk + d.axial_length))
    except Exception:
        # build123d raises on an EMPTY operand rather than returning nothing;
        # a wheel that is not there is somebody else's failure, not this one
        return 0.0
    return float(plug.volume) if plug is not None else 0.0


def bore_problem(part, d: CompressorDesign) -> str | None:
    """The sentence a wheel with a filled-in shaft bore earns, or None."""
    room = math.pi * d.bore_radius ** 2 * (d.backplate_thk + d.axial_length)
    plug = bore_material(part, d)
    if room <= 0 or plug <= _BORE_PLUG_FRACTION * room:
        return None
    return (f"the shaft bore is not a hole: {plug:,.2f} mm3 of the wheel "
            f"stands inside the {2 * d.bore_radius:,.2f} mm bore, so no shaft "
            f"would go through it")


def eye_passage(part, d: CompressorDesign) -> tuple[float, float]:
    """(open mm2, available mm2) across the wheel's INLET, both measured.

    The station is the top of the wheel, z = t + L, where the hub is exactly
    `inducer_hub_radius` and the shroud cut has not started coming down yet.
    A slab there, inside the published eye radius, holds the whole inlet; what
    is not wheel in it is passage. The shaft bore is open too and is taken off
    both sides, because no air goes down the shaft.

    The denominator is measured at the same station rather than taken from
    `pi*(r1s**2 - r1h**2)`, so the hub's own growth across the slab cancels
    instead of counting as blockage: the first version of this read a slab 2%
    of the wheel's depth lower and called a sound 26.50% wheel 0.00%, because
    on a 0.86 mm annulus the cone had already closed it
    (probes/meanline_eye_sweep.py, then meanline_eye_sweep2.py).

    Cost, measured on the same nine wheels: 0.56 s to 3.47 s, against builds of
    14 s to 168 s.
    """
    t, L = d.backplate_thk, d.axial_length
    r1s = d.inducer_shroud_radius
    if L <= 0 or r1s <= 0:
        return 0.0, 0.0
    h = min(0.02, L / 500.0)
    z_mid = t + L - h / 2.0
    hub_r = d.tip_radius - (d.tip_radius - d.inducer_hub_radius) \
        * ((z_mid - t) / L)
    inner = max(hub_r, d.bore_radius)
    available = math.pi * (r1s ** 2 - inner ** 2)
    if available <= 0.0:
        return 0.0, 0.0
    try:
        free = (Pos(0, 0, z_mid) * Cylinder(radius=r1s, height=h)) - part
    except Exception:
        # build123d raises when the difference is EMPTY — which here means the
        # wheel fills the whole eye, the very thing this measures
        return 0.0, available
    if free is None:
        return 0.0, available
    open_mm2 = float(free.volume) / h - math.pi * d.bore_radius ** 2
    return max(open_mm2, 0.0), available


def eye_problem(part, d: CompressorDesign) -> str | None:
    """The sentence a wheel whose inlet is solid blade metal earns, or None.

    Round two proved a wheel can publish an exit width 39% larger than the one
    it has. This is the same question at the inlet, and the answer was worse:
    0.005 kg/s at pressure ratio 1.1 and 100,000 rpm publishes an eye radius of
    6.10 mm — a 112.30 mm2 ring — and builds a wheel with 3.51 mm2 of passage
    in it, 3% of what it says. ok=True, ONE watertight solid, health [],
    13-fold symmetric, the right tip radius, the right overall height, and the
    STEP file exported as `verified: true` (probes/meanline_eye_kernel.py).

    TWO questions, because a fraction of the ring cannot answer the second.
    Round three asked whether enough of the ring is open; round four asks
    whether the air FITS THROUGH WHAT IS OPEN, which depends on the duty and
    not on the wheel alone. The same 10% is an easy inlet on a 5,000 rpm
    industrial stage and an impossible one on a 250,000 rpm micro turbo. See
    `_EYE_CHOKE_MARGIN`: the tenth passes 3,178 wheels in a 6,273-design grid
    that cannot pass their own mass flow at the speed of sound.
    """
    open_mm2, available = eye_passage(part, d)
    thk = max(0.02 * d.tip_radius, 1.5)
    if available <= 0.0:
        return ("the inlet eye is not an opening: there is no ring between "
                "the hub and the shroud for the air to come in through")
    # "raise the mass flow, which makes the wheel bigger" was half wrong and
    # measured so in round four: r2 is U2/omega and U2 has no mass flow in it,
    # so at 0.005 -> 0.01 kg/s (PR 1.1, 100,000 rpm) the wheel stays 11.55 mm
    # and it is the EYE that grows — one step, and the next is refused by the
    # eye-beyond-rim rule. Lowering the speed is the dial that grows the wheel,
    # and it was measured over five speeds on three duties
    # (probes/meanline_round4_advice.py).
    fix = ("lower the speed: the wheel grows while the blades stay as thick "
           "as a cutter can make them, so they take up less of its inlet")
    if open_mm2 < _EYE_OPEN_FRACTION * available:
        return (f"the inlet eye is not an opening: the {d.blade_count} blades "
                f"at {thk:,.2f} mm thick leave {open_mm2:,.2f} mm2 of the "
                f"{available:,.2f} mm2 ring the design asked for, so almost "
                f"none of the air it is sized for can get in — {fix}")
    # ...and the fraction cannot ask whether the air FITS. That depends on the
    # duty, and this is the ceiling physics puts on it. See `_EYE_CHOKE_MARGIN`.
    most = d.inlet_choke_flux * open_mm2
    if d.mass_flow > 0.0 and most > 0.0 \
            and d.mass_flow > _EYE_CHOKE_MARGIN * most:
        return (f"the inlet the blades leave cannot pass this flow: "
                f"{open_mm2:,.2f} mm2 of passage takes {most:.4g} kg/s at the "
                f"very most — that is air moving through it at the speed of "
                f"sound — and the duty asks for {d.mass_flow:g} kg/s, "
                f"{d.mass_flow / most:,.1f} times what fits. The "
                f"{d.blade_count} blades at {thk:,.2f} mm thick are what is "
                f"standing in it — {fix}; or lower the pressure ratio, which "
                f"slows the air the eye has to swallow")
    return None


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

    rep = assembly.build_and_verify(
        [assembly.Component("hub", hub),
         assembly.Component("blades", bladeset)],
        mode="fuse", assembly_spec=to_spec(d))
    # ...and then the questions the Spec cannot ask, MEASURED. Round one's P0
    # was a wheel that passed every line of `to_spec` with its bore filled in;
    # `one_blade` is why it cannot happen now, and this is the proof rather
    # than the promise. Round three's was the same wheel's INLET, filled with
    # blade metal by the 1.5 mm thickness floor. 0.14 s and 0.5-3.5 s against
    # builds of 14 to 168 s.
    if rep.part is not None:
        for problem in (bore_problem(rep.part, d), eye_problem(rep.part, d)):
            if problem:
                rep.assembly_problems.append(problem)
                rep.ok = False
    return rep


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
