"""The size gate: a duty whose ANSWER is not a wheel never reaches the kernel.

LAUNCH-PLAN §10 (P2, section 13 round two, 2026-09-17):

    `meanline.design` answers duties whose GEOMETRY is impossible, and hands
    them to OCCT. rpm 1 gives a tip radius of 4,221,135 mm with the inducer
    shroud equal to the hub; a pressure ratio of 1.001 gives an exit width of
    3207 mm on a 5.87 mm wheel; and `build_from_design` passes all of it on
    with no size gate — a NEGATIVE radius reaches the shroud cutter's revolve
    profile.

`_check` guards the EQUATIONS' domain — whether the meanline relations have an
answer at all. Whether that answer is a machinable object is a different
question, and nothing asked it.

Both margins are pinned here, as the plan asks: the sound designs that must
still pass, and the impossible duties that must now be refused. The bounds come
from `probes/meanline_size_probe.py` (ten duties from a 0.05 kg/s micro-turbo
at 180,000 rpm to a 50 kg/s industrial machine at 3,000 rpm) and
`probes/meanline_backsweep_sweep.py`, never from taste.
"""
import dataclasses
import math

import pytest
from build123d import Box, Cylinder, Pos

import assembly
import blocks
import inspector
import meanline


def duty(**kw):
    base = dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000)
    base.update(kw)
    return meanline.Duty(**base)


# --------------------------------------------- the sound band must survive ---

# name, duty, (r2 mm, exit_width/r2, r1s/r2) as measured at HEAD
SOUND = [
    ("the shipped sample",  dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000),
     (93.80, 0.027, 0.350)),
    ("the MCP test duty",   dict(mass_flow=1.0, pressure_ratio=3.0, rpm=40000),
     (105.53, 0.043, 0.432)),
    ("a small turbo",       dict(mass_flow=0.1, pressure_ratio=2.0, rpm=120000),
     (27.11, 0.113, 0.598)),
    ("a micro turbo",       dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000),
     (16.51, 0.180, 0.722)),
    ("a big turbo",         dict(mass_flow=2.0, pressure_ratio=4.0, rpm=25000),
     (193.84, 0.018, 0.319)),
    ("an industrial stage", dict(mass_flow=5.0, pressure_ratio=2.5, rpm=15000),
     (253.52, 0.047, 0.425)),
    ("a big industrial",    dict(mass_flow=20.0, pressure_ratio=3.5, rpm=8000),
     (570.03, 0.024, 0.350)),
    ("the largest measured", dict(mass_flow=50.0, pressure_ratio=2.0, rpm=3000),
     (1084.39, 0.035, 0.345)),
]


@pytest.mark.parametrize("name,kw,expect", SOUND,
                         ids=[s[0].replace(" ", "_") for s in SOUND])
def test_every_sound_duty_still_designs_and_its_margin_is_pinned(name, kw,
                                                                 expect):
    """The gate may not refuse one of these, today or after any later tuning.

    The third number is the tightest margin in the whole gate: a micro-turbo's
    inlet eye is 0.722 of its tip radius, and the gate refuses at 1.0.
    """
    d = meanline.design(duty(**kw))
    r2, b2_over, eye_over = expect
    assert d.tip_radius == pytest.approx(r2, rel=1e-3), name
    assert d.exit_width / d.tip_radius == pytest.approx(b2_over, abs=1e-3)
    assert (d.inducer_shroud_radius / d.tip_radius
            == pytest.approx(eye_over, abs=1e-3))
    # ...and each one is inside the gate with room to spare
    assert meanline._R2_MIN_MM < d.tip_radius < meanline._R2_MAX_MM
    assert d.exit_width < d.tip_radius
    assert d.inducer_shroud_radius < d.tip_radius


def test_the_backsweeps_the_mcp_tests_bless_are_all_still_answered():
    """tests/test_mcp_server.py asserts every backsweep from -60 to 74 designs.
    Measured (probes/meanline_backsweep_sweep.py): 74 degrees already gives a
    2583 m/s tip speed and an inlet eye 1.039x the hub nose, so a gate on the
    EYE-to-NOSE ratio would refuse it. It was measured out instead of guessed
    at: the 1e-6 kg/s duty, whose eye EQUALS its nose, builds a sound single
    watertight solid (probes/meanline_kernel_repro.py tinyflow, 19.4 s,
    ok=True). A gate that refuses geometry the kernel gets right is the one
    mistake this file exists to avoid, so there is no such gate."""
    for beta in (-60.0, 0.0, 25.0, 35.0, 45.0, 60.0, 70.0, 74.0):
        meanline.design(duty(mass_flow=1.0, rpm=40000, backsweep_deg=beta))


# ------------------------------------- the impossible answers are refused ----

IMPOSSIBLE = [
    # name, duty, a word the sentence must contain
    ("1 rpm: an 8.4 metre wheel", dict(rpm=1), "metres"),
    ("10 rpm", dict(rpm=10), "metres"),
    # this row was "1000 rpm" until the review round of 2026-09-17 measured
    # that wheel: 4221.14 mm, and the kernel builds it as ONE watertight solid,
    # health [], 13-fold symmetric, in 86.2 s. Refusing it was refusing
    # geometry OpenCASCADE gets right. 100 rpm is 84 metres across and stays.
    ("100 rpm", dict(rpm=100), "metres"),
    ("1e9 rpm: a wheel of nothing", dict(rpm=1e9), "small"),
    ("PR 1.001: a 7217 mm blade on a 2.6 mm wheel",
     dict(pressure_ratio=1.001), "rim"),
    ("PR 1.01", dict(pressure_ratio=1.01), "rim"),
    ("PR 1.05", dict(pressure_ratio=1.05), "rim"),
    ("PR 1.2: the eye outside the wheel", dict(pressure_ratio=1.2), "inlet"),
    ("10,000 kg/s", dict(mass_flow=1e4), "rim"),
    ("a forward sweep of -80", dict(mass_flow=1.0, rpm=40000,
                                    backsweep_deg=-80.0), "inlet"),
]


@pytest.mark.parametrize("name,kw,word", IMPOSSIBLE,
                         ids=[s[0].split(":")[0].replace(" ", "_")
                              for s in IMPOSSIBLE])
def test_an_impossible_duty_is_refused_in_a_sentence(name, kw, word):
    with pytest.raises(ValueError) as e:
        meanline.design(duty(**kw))
    msg = str(e.value)
    assert word in msg, (name, msg)
    # a SENTENCE naming what to change, not a number and not a traceback
    assert len(msg.split()) >= 8, (name, msg)
    assert any(verb in msg for verb in ("raise", "lower", "reduce")), (name,
                                                                       msg)
    assert "Traceback" not in msg and "Error" not in msg, (name, msg)


def test_the_rpm_1_refusal_says_the_size_and_the_speed_to_reach():
    """The plan's own example of what the user should read. Its "8.4 metres"
    was an order of magnitude kind: a tip RADIUS of 4,221,135.81 mm is 8.4
    KILOMETRES across, and the sentence says the measured number."""
    with pytest.raises(ValueError) as e:
        meanline.design(duty(rpm=1))
    msg = str(e.value)
    assert "at 1 rpm" in msg and "8.4 kilometres" in msg, msg
    assert "raise the speed" in msg, msg
    # the speed it names is arithmetic, not advice: r2 = U2 / omega — so it
    # moved with the bound (2,111 rpm when the bound was 2000 mm, 422 now
    # that it is the measured 10,000 mm)
    assert "422 rpm" in msg, msg


def test_the_pressure_ratio_1_001_refusal_quotes_both_numbers():
    with pytest.raises(ValueError) as e:
        meanline.design(duty(pressure_ratio=1.001))
    msg = str(e.value)
    assert "7,217.26 mm" in msg and "2.61 mm" in msg, msg
    assert "at 0.5 kg/s and pressure ratio 1.001" in msg, msg


def test_the_two_flow_refusals_name_the_speed_as_well():
    """The exit-width and inlet-eye sentences named the pressure ratio and the
    mass flow — the DUTY, the thing the user is not free to change — and never
    the speed, which is free and always works: the rim is r2 = U2 / omega.
    Measured (probes/meanline_gate_boundary_probe.py): 0.5 kg/s at pressure
    ratio 1.2 is refused at 45,000 rpm with an inlet eye of 50.86 mm against a
    35.72 mm rim, and at 10,000 rpm the same duty gives eye 53.45 against a
    160.74 mm rim and passes every rule."""
    for kw in (dict(pressure_ratio=1.001), dict(pressure_ratio=1.2)):
        with pytest.raises(ValueError) as e:
            meanline.design(duty(**kw))
        assert "lower the speed" in str(e.value), str(e.value)
    # ...and the duty it names as refusable at speed really does design
    d = meanline.design(duty(pressure_ratio=1.2, rpm=10000))
    assert d.inducer_shroud_radius < d.tip_radius
    assert d.exit_width < d.tip_radius


def test_a_refusal_names_the_dial_that_is_actually_wrong():
    """The first draft opened both flow-driven refusals with "a pressure ratio
    of 3" — for a 10,000 kg/s duty and for a -80 degree forward sweep, naming
    the one dial that was not the problem."""
    with pytest.raises(ValueError) as e:
        meanline.design(duty(mass_flow=1e4))
    assert "at 10000 kg/s" in str(e.value), str(e.value)
    with pytest.raises(ValueError) as e:
        meanline.design(duty(mass_flow=1.0, rpm=40000, backsweep_deg=-80.0))
    assert "backsweep of -80 degrees" in str(e.value), str(e.value)


# ------------------------------- the negative radius cannot reach the kernel --

def test_the_shroud_cutter_never_stands_at_a_negative_radius():
    """THE REPRO. `build_from_design` put the shroud cutter's inner wall 2 mm
    inside the blade root — a FIXED 2 mm, which is more than the whole hub nose
    on any wheel under about 25 mm radius. Measured at HEAD 2026-09-17
    (probes/meanline_kernel_repro.py tiny): the micro-turbo duty (0.05 kg/s,
    PR 1.8, 180,000 rpm) is a perfectly sound 16.51 mm wheel, and its cutter
    profile opened at radius **-0.7025**, so the user read
    `builder crashed: ValueError('revolve_profile: point 1 has radius -0.7025
    ...')` — an internal function's name, for a duty nothing is wrong with."""
    for kw in [s[1] for s in SOUND] + [dict(mass_flow=0.05,
                                            pressure_ratio=1.8, rpm=180000)]:
        d = meanline.design(duty(**kw))
        root = meanline.shroud_root_radius(0.75 * d.inducer_hub_radius)
        assert root >= 0.0, (kw, root)
        assert root < 0.75 * d.inducer_hub_radius or root == 0.0


def test_the_shipped_sample_keeps_the_exact_cutter_it_had():
    """The clamp may not move one micron of the design the user opens."""
    d = meanline.design(duty())
    assert meanline.shroud_root_radius(0.75 * d.inducer_hub_radius) \
        == pytest.approx(0.75 * 9.85 - 2.0)
    assert meanline.shroud_root_radius(round(0.75 * d.inducer_hub_radius, 2)) \
        == pytest.approx(round(0.75 * 9.85, 2) - 2.0)


def test_the_micro_turbo_cutter_is_a_solid_the_kernel_accepts():
    """Not inferred from the arithmetic: the profile that used to be refused is
    put to `blocks.revolve_profile` and measured."""
    d = meanline.design(duty(mass_flow=0.05, pressure_ratio=1.8, rpm=180000))
    t, L = d.backplate_thk, d.axial_length
    root = meanline.shroud_root_radius(0.75 * d.inducer_hub_radius)
    big = t + L + 50.0
    cutter = blocks.revolve_profile([
        (root, t + L), (d.inducer_shroud_radius, t + L),
        (d.tip_radius, t + d.exit_width),
        (d.tip_radius + 15.0, t + d.exit_width),
        (d.tip_radius + 15.0, big), (root, big)])
    assert cutter.volume > 0
    assert len(cutter.solids()) == 1


def test_build_from_design_refuses_an_impossible_wheel_without_the_kernel():
    """The gate sits in front of the kernel as well as behind the solve: a
    CompressorDesign built by hand (an editor, a repair loop, a saved file)
    must not reach OpenCASCADE either. It comes back as a failed report, the
    way every other assembly failure does — `build_from_design` never raises,
    because `mcp_server._design_compressor` calls it outside its try."""
    d = meanline.design(duty())
    d.tip_radius = 4221135.81          # the rpm-1 answer, forced in
    rep = meanline.build_from_design(d)
    assert rep.ok is False and rep.part is None
    problems = " ".join(rep.all_problems())
    assert "metres" in problems and "raise the speed" in problems, problems


def test_the_samples_drill_their_shaft_bore_after_the_blades_are_on():
    """ROUND TWO. `sample_compressor` drilled the bore into `hub` and fused the
    blades on afterwards — the exact ordering that made round one's P0. Its own
    wheel is large enough to be clear (blade reach 6.5578 against a 4.92 mm
    bore), but a user editing the tree down to a small wheel plugged the bore
    with no warning and nothing could see it. MEASURED on that same tree at the
    micro-turbo duty (probes/compressor_bore_order_probe.py, 2026-09-17):

        bore drilled first   67.210 mm3 inside a 2 mm bore, ok=True,
                             spec_problems=[], health [], ONE watertight solid
        bore drilled last     0.000 mm3, same bbox, same max_radius

    and on the SHIPPED duty the two orderings are identical to the last digit
    (volume 428259.878, 69 faces, 187.6 x 187.6 x 35.64, max_radius 93.8), so
    the tree that teaches the right shape costs the example nothing.
    """
    import samples

    for maker in (samples.sample_compressor, samples.sample_impeller):
        doc = maker()
        ops = [(f.id, f.op) for f in doc.features]
        drills = [i for i, (_, op) in enumerate(ops)
                  if op == "with_center_hole"]
        fuses = [i for i, (_, op) in enumerate(ops) if op == "fuse"]
        assert drills and fuses, ops
        assert min(drills) > max(fuses), (maker.__name__, ops)
        # ...and the drilled body is the one the user ends up with
        assert ops[-1][1] == "with_center_hole", ops


def test_the_shipped_compressor_example_is_pinned_feature_by_feature():
    """Nothing in the fast tier rebuilds `compressor` — it is the most
    expensive example there is (29.5 s on an idle box, 91.6 s with other
    OpenCASCADE work beside it, probes/compressor_rebuild_cost.py), so a 13-
    blade build cannot live here. What CAN live here is every number meanline
    hands the tree, which costs nothing and is what a change to this module
    would move. The solid those numbers build was measured alongside them:
    volume 428259.878 mm3, 69 faces, ONE solid, health [] — the figures any
    later speed-up has to reproduce exactly
    (probes/meanline_gate_sentences.py)."""
    import samples

    doc = samples.sample_compressor()
    p = {f.id: f.params for f in doc.features}
    assert doc.name == "compressor-PR3-13blades"
    assert p["hub_body"]["points"] == [[0, 0], [93.8, 0], [93.8, 2.81],
                                       [9.85, 35.64], [0, 35.64]]
    assert p["blade"] == {"inner_radius": 7.39, "outer_radius": 93.8,
                          "inlet_angle_deg": 49.4, "exit_angle_deg": 35.0,
                          "height": 32.83, "thickness": 1.88}
    assert p["blades_raw"]["count"] == 13
    assert p["shroud_cutter"]["points"] == [
        [5.39, 35.64], [32.81, 35.64], [93.8, 5.359999999999999],
        [108.8, 5.359999999999999], [108.8, 85.64], [5.39, 85.64]]
    assert p["impeller"]["radius"] == 4.92      # the bore, drilled LAST
    assert doc.spec == {"symmetry": 13, "n_solids": 1, "tip_radius": 93.8,
                        "tol": 1.0}


# ------------------------------ the shaft bore is a hole, not a promise ------

# Every duty whose wheel is under about 35 mm of tip radius. The blades are
# fused on AFTER `with_center_hole` drills the hub, so blade material that
# reaches inside the bore fills the hole back in — and nothing measures it:
# `to_spec` checks symmetry, solid count and tip radius, all of which a wheel
# with a plugged bore still passes. Measured at HEAD 2026-09-17
# (probes/meanline_review_kernel.py, probes/meanline_bore_reach.py):
#
#   a micro turbo  r2 16.51  bore 2.00   blade reaches in to 0.556  67.27 mm3
#   a small turbo  r2 27.11  bore 2.00   blade reaches in to 1.392   5.63 mm3
#
# and the micro turbo came back ok=True, ONE watertight solid, health [],
# 13-fold symmetric, max_radius 16.51 — a "verified" impeller no shaft fits.
BORE_BLOCKED = [
    ("a small turbo", dict(mass_flow=0.1, pressure_ratio=2.0, rpm=120000)),
    ("a micro turbo", dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000)),
    ("a blower",      dict(mass_flow=0.5, pressure_ratio=1.5, rpm=45000)),
]


def _bore_plug(d):
    return Cylinder(radius=d.bore_radius, height=8.0 * d.axial_length)


@pytest.mark.parametrize("name,kw", BORE_BLOCKED,
                         ids=[s[0].replace(" ", "_") for s in BORE_BLOCKED])
def test_the_blades_leave_the_shaft_bore_open(name, kw):
    """THE SECOND FIXED 2 mm. `bore_radius` is `max(0.5 * r1h, 2.0)` and the
    blade root is `0.75 * r1h`, so without the 2 mm floor the root is always
    outside the bore by construction — the floor is what breaks it, exactly as
    the fixed 2 mm shroud offset broke the cutter one function away.

    The blade's inner end is NOT at its `inner_radius`: `blocks.curved_blade`
    traces a ribbon and the cap overshoots inwards by an amount that follows
    the blade ANGLE, not just the thickness — 0.74 mm on the micro turbo and
    1.66 mm on a PR 1.3 blower, both 1.5 mm thick (bisected with real
    booleans, probes/meanline_bore_reach.py). So the bore cannot be predicted
    clear; it is cut out of the blade the pattern copies."""
    d = meanline.design(duty(**kw))
    blade = meanline.one_blade(d)
    assert blade.volume > 0, "the bore cut may not eat the blade"
    left = blade & _bore_plug(d)
    vol = left.volume if left is not None else 0.0
    assert vol < 1e-9, f"{name}: {vol:.3f} mm3 of blade inside the shaft bore"


def _raw_blade(d):
    return blocks.curved_blade(
        inner_radius=0.75 * d.inducer_hub_radius, outer_radius=d.tip_radius,
        inlet_angle_deg=d.beta1_deg, exit_angle_deg=d.beta2_deg,
        height=d.axial_length, thickness=max(0.02 * d.tip_radius, 1.5))


# ROUND TWO. Round one proved the bore cut on three duties, all of them the
# same 25-45 degree traced kind. A bore that is clear on the corpus and plugged
# on a shape nobody tried is the same defect, so the BACKSWEEP — the one dial
# that changes the blade's shape rather than its size, and which
# tests/test_mcp_server.py blesses from -60 to 74 — is swept here as well,
# thick blades and thin. Measured over 30 shapes
# (probes/meanline_bore_sweep.py, 2026-09-17): every one came back with an
# empty bore, ONE solid, health [], and every blade that already cleared the
# bore came back byte-identical in volume.
BLADE_SHAPES = [
    ("forward swept -30", dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000,
                               backsweep_deg=-30.0)),
    ("radial 0", dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000,
                      backsweep_deg=0.0)),
    ("heavy 60", dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000,
                      backsweep_deg=60.0)),
    ("the last blessed 74", dict(mass_flow=0.05, pressure_ratio=1.8,
                                 rpm=180000, backsweep_deg=74.0)),
    # was 1e-6 kg/s at 500,000 rpm until the eye rule (round three) refused it:
    # that wheel's inlet eye is 0.51 mm inside a 2.00 mm shaft bore. This is
    # the smallest wheel left — r2 3.21 mm (probes/meanline_eye_rule_blast.py)
    ("the smallest wheel", dict(mass_flow=1e-3, pressure_ratio=1.2,
                                rpm=500000)),
    ("a thick blade", dict(mass_flow=20.0, pressure_ratio=3.5, rpm=8000)),
]


@pytest.mark.parametrize("name,kw", BLADE_SHAPES,
                         ids=[s[0].replace(" ", "_") for s in BLADE_SHAPES])
def test_the_bore_cut_holds_on_every_blade_shape_the_dials_reach(name, kw):
    d = meanline.design(duty(**kw))
    blade = meanline.one_blade(d)
    assert blade.volume > 0, f"{name}: the cut emptied the blade"
    # a blade the cut SEVERS still patterns into a watertight wheel — silent
    assert len(blade.solids()) == 1, f"{name}: the cut severed the blade"
    assert inspector.health(blade) == [], name
    left = blade & _bore_plug(d)
    vol = left.volume if left is not None else 0.0
    assert vol < 1e-9, f"{name}: {vol:.3f} mm3 of blade inside the shaft bore"


# every one of these has a blade root outside its bore already, so the cut has
# to remove NOTHING — round one claimed "identical to the last digit" and
# measured the shipped duty only
BORE_CLEAR = [s for s in SOUND
              if s[0] not in ("a micro turbo", "a small turbo")]


@pytest.mark.parametrize("name,kw,_e", BORE_CLEAR,
                         ids=[s[0].replace(" ", "_") for s in BORE_CLEAR])
def test_a_wheel_whose_blades_already_clear_the_bore_is_untouched(name, kw, _e):
    """The shipped duty's blade reaches in to 6.5578 mm against a 4.92 mm bore
    (probes/meanline_bore_reach.py), so the cut must remove nothing at all —
    not a micron, not a face — and that has to hold for every clear wheel, not
    just the one the fix was written against."""
    d = meanline.design(duty(**kw))
    raw = _raw_blade(d)
    left = raw & _bore_plug(d)
    assert (left.volume if left is not None else 0.0) < 1e-9, \
        f"{name} is not a bore-clear wheel; this test proves nothing on it"
    assert meanline.one_blade(d).volume == pytest.approx(raw.volume, rel=1e-12)


def test_a_bore_wider_than_the_wheel_is_refused_in_words():
    """The cut must never be able to eat the whole blade. A hand-built design
    (an editor, a repair loop) can say so; the gate answers in a sentence, not
    with an empty component."""
    d = meanline.design(duty())
    d.bore_radius = d.tip_radius + 1.0
    rep = meanline.build_from_design(d)
    assert rep.ok is False and rep.part is None
    problems = " ".join(rep.all_problems())
    assert "shaft bore" in problems and "crashed" not in problems, problems


# ------------------------------- the big end of the gate is not a kernel limit

# Every one of these was REFUSED by `_R2_MAX_MM = 2000.0` and every one builds
# a sound solid — measured one at a time, 6 GB capped
# (probes/meanline_review_kernel.py, 2026-09-17):
#
#   50 kg/s PR 2.0 @ 1500 rpm    r2 2168.78   ok in 78.9 s, 1 solid, health []
#   0.5 kg/s PR 3.0 @ 1000 rpm   r2 4221.14   ok in 86.2 s, 1 solid, health []
#   50 kg/s PR 2.0 @  325 rpm    r2 9998.67   ok in 69.6 s, 1 solid, health []
#
# all watertight, all 13-fold symmetric, all with max_radius equal to the
# design's to the last digit and peak memory under 1.3 GB. The kernel is
# nowhere near its limit at 2000 mm, so a bound there is a size opinion, and
# the first row is the author's OWN largest duty at half its speed.
BIG_BUT_SOUND = [
    ("half the speed of the largest duty",
     dict(mass_flow=50.0, pressure_ratio=2.0, rpm=1500), 2168.78),
    ("a 1000 rpm wheel", dict(pressure_ratio=3.0, rpm=1000), 4221.14),
    ("a 20 metre wheel",
     dict(mass_flow=50.0, pressure_ratio=2.0, rpm=325.3597), 9998.67),
]


@pytest.mark.parametrize("name,kw,r2", BIG_BUT_SOUND,
                         ids=[s[0].replace(" ", "_") for s in BIG_BUT_SOUND])
def test_a_wheel_the_kernel_builds_sound_is_not_refused_for_being_big(name, kw,
                                                                      r2):
    d = meanline.design(duty(**kw))
    assert d.tip_radius == pytest.approx(r2, rel=1e-4), name


def test_the_bound_still_refuses_the_answers_that_are_not_machines():
    """...and it has to still catch the ones that are. 100 rpm is a 84 metre
    wheel and 1 rpm is 8.4 kilometres — the one the kernel actually failed on,
    110 s to an open shell."""
    for rpm in (100, 10, 1):
        with pytest.raises(ValueError) as e:
            meanline.design(duty(rpm=rpm))
        assert "across" in str(e.value), (rpm, str(e.value))


def test_the_lower_bound_refuses_nothing_that_could_be_machined():
    """Attacked and cleared, by arithmetic over 1080 duties
    (probes/meanline_gate_min_scan.py): the smallest wheel that survives the
    other two rules is 1.08 mm, and it needs 3,000,000 rpm at a microgram per
    second. Its blade would be 1.5 mm thick — THICKER than the whole wheel is
    round — which is the real reason nothing lives down there.

    ROUND THREE moved the floor up without touching `_R2_MIN_MM`: the wheels
    that small have their inlet eye INSIDE the shaft bore, and the eye rule
    refuses them first. The smallest wheel any duty still designs is 3.21 mm
    of tip radius, and a search 100x finer bottoms out at 2.90 mm — nearly 3x
    the bound (probes/meanline_eye_rule_blast.py). The 4.87 mm wheel this test
    used to name is one of the refused ones: its eye is 0.78 mm, the bore
    2.00."""
    d = meanline.design(duty(mass_flow=1e-3, pressure_ratio=1.2, rpm=500000))
    assert d.tip_radius == pytest.approx(3.21, abs=0.01)   # 3x the bound
    assert d.tip_radius > 2.9 > meanline._R2_MIN_MM
    assert max(0.02 * d.tip_radius, 1.5) > meanline._R2_MIN_MM
    with pytest.raises(ValueError, match="inlet eye"):
        meanline.design(duty(mass_flow=1e-4, pressure_ratio=1.5, rpm=500000))


def test_the_gate_reads_the_geometry_it_will_actually_build():
    """`exit_width` is CLAMPED to a machinable 1.0 mm minimum, so the gate has
    to judge the clamped number — that is the blade the kernel will cut.

    (The 1e-6 kg/s duty this used to ask is refused by the eye rule now: its
    eye and its hub nose are both 9.85 mm, a ring of nothing.)"""
    d = meanline.design(duty(mass_flow=1e-5, pressure_ratio=2.0, rpm=60000))
    assert d.exit_width == 1.0                      # the clamp bit
    assert d.exit_width < d.tip_radius              # and it is still a wheel
    assert all(math.isfinite(v) for v in
               (d.tip_radius, d.exit_width, d.inducer_shroud_radius))


# ------------------------- the machinable floor no longer keeps its mouth shut

# name, duty, the width continuity ASKED for (mm), and the overstatement
# (probes/meanline_exit_width_clamp.py, 2026-09-17)
# The second and third rows named 1e-6 kg/s and 1e-4 kg/s at 500,000 rpm until
# round three's eye rule refused both (an eye of zero area, and an eye inside
# the shaft bore). These two clamp just as hard, keep a real ring, and exercise
# the same two branches of the sentence — "under a micrometre" with "thousands
# of times", and "N micrometres" with a count
# (probes/meanline_eye_rule_replacements.py).
CLAMPED = [
    ("PR 3 at 1,000 rpm", dict(pressure_ratio=3.0, rpm=1000), 0.056719, 17.6),
    ("1e-5 kg/s at PR 5",
     dict(mass_flow=1e-5, pressure_ratio=5.0, rpm=20000), 0.0000099486,
     100516.2),
    ("1e-4 kg/s at 50,000 rpm",
     dict(mass_flow=1e-4, pressure_ratio=1.5, rpm=50000), 0.0027937, 357.9),
]


@pytest.mark.parametrize("name,kw,ideal,ratio", CLAMPED,
                         ids=[s[0].replace(" ", "_") for s in CLAMPED])
def test_the_exit_width_floor_says_so_when_it_fires(name, kw, ideal, ratio):
    """THE REPRO. `exit_width` is clamped to a machinable 1.0 mm and NOTHING
    said so, so a design whose physics wanted 57 micrometres reported 1.00 mm —
    18 times wider — and `mcp_server.design_compressor` handed that number to
    an AI as `exit_width_mm`. It is also why `b2 >= r2` cannot catch a wheel
    enormously oversized for its flow: the number that rule reads is the
    clamped one. The floor stays (nothing cuts a 57 micrometre channel); the
    silence does not."""
    d = meanline.design(duty(**kw))
    assert d.exit_width == 1.0
    assert d.exit_width_ideal == pytest.approx(ideal, rel=1e-3), name
    assert d.exit_width / d.exit_width_ideal == pytest.approx(ratio, rel=1e-2)
    note = " ".join(d.notes)
    assert note, f"{name}: the clamp fired and the design said nothing"
    # a SENTENCE a person can act on, naming the dials that are free
    assert "exit blade width" in note and "floor" in note, note
    assert "raise the speed" in note, note
    assert len(note.split()) >= 20, note
    # ...and it reaches whoever reads the design
    assert "NOTE:" in d.report() and "exit blade width" in d.report()


@pytest.mark.parametrize("name,kw,expect", SOUND,
                         ids=[s[0].replace(" ", "_") for s in SOUND])
def test_a_wheel_whose_width_is_real_says_nothing(name, kw, expect):
    """The note may not cry wolf on the eight duties the corpus calls sound —
    every one of them has a true b2 between 2.55 and 38.27 mm, well clear of
    the floor (probes/meanline_exit_width_clamp.py).

    ROUND FOUR: this used to assert `d.notes == ()`, which quietly made it the
    test of EVERY note rather than of the width one. Four of these eight wheels
    now carry the inducer-angle note — measured, and true of them — so the
    guard is written as what it always meant: the WIDTH says nothing."""
    d = meanline.design(duty(**kw))
    assert d.exit_width_ideal > 1.0, name
    assert d.exit_width == pytest.approx(d.exit_width_ideal, abs=0.005)
    assert "exit blade width" not in " ".join(d.notes), (name, d.notes)
    assert "floor instead" not in d.report(), name


# ---------------------------- the bore is MEASURED now, not taken on trust ---

def test_a_filled_in_bore_is_measured_and_refused_in_words():
    """`to_spec` checks symmetry, solid count, tip radius and height, and round
    one measured a wheel that passed all four with 67.27 mm3 of blade in its
    2 mm bore. `Spec.holes` cannot reach it either: the plugged micro-turbo
    still measured `cylinder_radii={2.0: 1, 16.51: 5}` — the bore's wall is
    still a cylindrical face, just filled in behind
    (probes/compressor_bore_order_probe.py). Only a boolean answers, and it
    costs 0.14 s against a 73 s build."""
    d = meanline.design(duty())
    solid = Cylinder(radius=d.tip_radius, height=d.backplate_thk)
    assert meanline.bore_material(solid, d) > 0
    problem = meanline.bore_problem(solid, d)
    assert problem and "shaft bore is not a hole" in problem, problem
    assert "9.84 mm bore" in problem, problem       # the DIAMETER, in words
    drilled = blocks.with_center_hole(solid, d.bore_radius)
    assert meanline.bore_material(drilled, d) < 1e-9
    assert meanline.bore_problem(drilled, d) is None


def test_the_bore_check_does_not_fire_on_a_hair_of_boolean_noise():
    """A guard that refuses correct geometry is the worse sin. The threshold is
    0.5% of the bore's own volume: round one's plug filled 69% of it, and every
    sound wheel measured exactly 0.000000 mm3 — three orders of magnitude of
    daylight on both sides."""
    d = meanline.design(duty())
    room = math.pi * d.bore_radius ** 2 * (d.backplate_thk + d.axial_length)
    drilled = blocks.with_center_hole(
        Cylinder(radius=d.tip_radius, height=d.backplate_thk + d.axial_length),
        d.bore_radius)
    # a wisp one thousandth of the bore: not a plug, and not refused
    wisp = Cylinder(radius=d.bore_radius, height=0.0005 * (d.backplate_thk
                                                           + d.axial_length))
    assert meanline.bore_problem(drilled + wisp, d) is None
    # a real plug — a quarter of the bore — is
    plug = Cylinder(radius=d.bore_radius,
                    height=0.25 * (d.backplate_thk + d.axial_length))
    assert meanline.bore_problem(drilled + plug, d) is not None
    assert room > 0


def test_a_blade_that_crosses_the_bore_without_filling_it_is_still_caught():
    """ROUND THREE attacking round two's own fix: the measurement is an
    INTERSECTION with the bore cylinder, so a blade that enters the bore and
    leaves it on the other side — never filling the cylinder — has to be
    counted just the same. Measured on the shipped wheel
    (probes/meanline_round3_attacks.py): a bar straight across the 9.84 mm
    bore is refused down to 0.10 mm thick (35.07 mm3, 1.29% of the bore). The
    only bar it misses is 0.02 mm — a twentieth of a millimetre, where
    `one_blade`'s own thickness floor is 1.5 mm."""
    d = meanline.design(duty())
    t, L = d.backplate_thk, d.axial_length
    drilled = blocks.with_center_hole(
        Cylinder(radius=d.tip_radius, height=t + L), d.bore_radius)
    for thk, caught in ((1.88, True), (0.5, True), (0.1, True)):
        bar = Box(4.0 * d.tip_radius, thk, t + L)
        crossing = bar & Cylinder(radius=d.tip_radius, height=8.0 * (t + L))
        problem = meanline.bore_problem(drilled + crossing, d)
        assert (problem is not None) is caught, (thk, problem)
        assert meanline.bore_material(drilled + crossing, d) > 30.0, thk


# --------------- the exit width has to fit in the wheel, or it is not built ---

# Every one of these designed cleanly at 4092242, built a sound watertight
# wheel, and published an exit width the wheel did not have. Measured
# (probes/meanline_rim_height_probe.py, probes/meanline_shroud_scan.py):
#
#   0.05 kg/s PR 1.01 @ 10,000 rpm, 25 deg   said b2 17.29, built 12.480 (= L)
#
# name, duty, (published b2, the wheel's depth L)
EXIT_TALLER_THAN_THE_WHEEL = [
    ("the measured one", dict(mass_flow=0.05, pressure_ratio=1.01, rpm=10000,
                              backsweep_deg=25.0), (17.29, 12.48)),
    ("a 124 mm blower", dict(mass_flow=0.5, pressure_ratio=1.01, rpm=3000,
                             backsweep_deg=35.0), (47.96, 43.27)),
    ("a small fast one", dict(mass_flow=0.01, pressure_ratio=1.2, rpm=300000,
                              backsweep_deg=60.0), (2.89, 2.35)),
]


@pytest.mark.parametrize("name,kw,expect", EXIT_TALLER_THAN_THE_WHEEL,
                         ids=[s[0].replace(" ", "_")
                              for s in EXIT_TALLER_THAN_THE_WHEEL])
def test_a_wheel_too_shallow_for_its_own_exit_width_is_refused(name, kw,
                                                               expect):
    """ROUND TWO, and the one the round-one question "what ELSE can `to_spec`
    not see?" turned up. `build_from_design`'s shroud cutter runs from
    (r1s, t+L) DOWN to (r2, t+b2). When b2 is taller than the wheel is deep the
    line runs UP, the cut takes nothing off the rim, and the blades stand full
    height there — so the wheel's exit width is L, not the b2 the design
    published, and every check passes: one watertight solid, health [], 14-fold
    symmetric, the right tip radius, the right overall height.

    MEASURED at 4092242 (probes/meanline_rim_height_probe.py): 0.05 kg/s at
    pressure ratio 1.01 and 10,000 rpm published `exit_width` 17.29 mm and
    built a wheel 12.480 mm tall at the rim, in both a 0.5 mm and a 1.0 mm rim
    band — 39% wrong on the one number that sets what the machine flows, and
    `mcp_server.design_compressor` hands it to an AI as `exit_width_mm`.

    The same probe on a sound duty reads the design's own number back
    (micro turbo: 2.97 published, 2.97 measured at the rim), so the
    measurement is not the suspect."""
    b2, L = expect
    with pytest.raises(ValueError) as e:
        meanline.design(duty(**kw))
    msg = str(e.value)
    assert f"{b2:,.2f} mm tall" in msg, (name, msg)
    assert f"{L:,.2f} mm deep" in msg, (name, msg)
    assert "lower the speed" in msg, (name, msg)
    assert "Traceback" not in msg and "Error" not in msg, msg


def test_no_duty_that_designs_can_make_the_shroud_cut_run_backwards():
    """The invariant behind the rule, over a grid rather than three rows: a
    design that passes the gate always has an exit width its wheel is deep
    enough for, so the shroud cutter's line never runs upward. 163 of 5,965
    duties in the full 12,320-duty grid were refused by it, every one with
    b2/r2 at or above 0.35 where a real centrifugal wheel is 0.02 to 0.10
    (probes/meanline_shroud_scan.py)."""
    seen = refused = 0
    for mdot in (1e-4, 0.01, 0.05, 0.5, 5.0, 50.0):
        for pr in (1.01, 1.2, 1.8, 3.0, 6.0):
            for rpm in (3000, 10000, 45000, 300000):
                for beta in (-30.0, 0.0, 35.0, 60.0):
                    try:
                        d = meanline.design(meanline.Duty(
                            mass_flow=mdot, pressure_ratio=pr, rpm=rpm,
                            backsweep_deg=beta))
                    except ValueError:
                        refused += 1
                        continue
                    seen += 1
                    assert d.exit_width <= d.axial_length, (mdot, pr, rpm,
                                                            beta, d.exit_width,
                                                            d.axial_length)
    assert seen > 100 and refused > 0, (seen, refused)


def test_the_corpus_is_nowhere_near_the_new_rule():
    """A guard that refuses correct geometry is the worse sin. Every sound duty
    keeps a wide margin: the tightest is the micro turbo at b2/L = 0.514."""
    worst = 0.0
    for _name, kw, _e in SOUND:
        d = meanline.design(duty(**kw))
        worst = max(worst, d.exit_width / d.axial_length)
    assert worst == pytest.approx(0.514, abs=0.01), worst


# ---------------- the inlet eye has to BE an opening, and that is measured ---

# ROUND THREE. `exit_width_mm` is what the machine flows; `inducer_shroud_
# radius_mm` is what it takes IN, and it leaves through the same MCP door.
# Nothing measured it against the metal. The blades are `max(0.02*r2, 1.5)` mm
# thick — the THIRD fixed millimetre on a small wheel, after the bore's 2 mm
# and the shroud offset's — and on a small wheel that floor fills the eye
# solid.
#
# MEASURED at 967963d (probes/meanline_eye_kernel.py, meanline_eye_sweep2.py):
#
#   0.005 kg/s PR 1.1 @ 100,000 rpm, 35 deg   r2 11.55, Z 13, eye r1s 6.10
#       published inlet ring   112.30 mm2
#       passage in the metal     3.51 mm2  = 3.4% of the 104.33 mm2 there to
#                                            be blocked
#       and ok=True, ONE watertight solid, health [], 13-fold symmetric, the
#       right tip radius, the right overall height, STEP exported "verified".
#
# A duty whose eye is no wider than the hub nose or the shaft bore never gets
# that far: 289 of 4,424 designs in a 7,040-duty grid answer r1s == r1h, an
# eye of ZERO area (probes/meanline_round3_gaps.py).

EYE_IS_NOT_A_RING = [
    ("no ring at all", dict(mass_flow=1e-4, pressure_ratio=1.01, rpm=200,
                            backsweep_deg=35.0), (194.73, 194.73)),
    ("the hub swallows it", dict(mass_flow=1e-4, pressure_ratio=1.05, rpm=200,
                                 backsweep_deg=0.0), (387.68, 387.68)),
]


@pytest.mark.parametrize("name,kw,expect", EYE_IS_NOT_A_RING,
                         ids=[s[0].replace(" ", "_")
                              for s in EYE_IS_NOT_A_RING])
def test_an_eye_no_wider_than_the_hub_is_refused_before_the_kernel(name, kw,
                                                                   expect):
    """`r1s` is sqrt(area/pi + r1h**2): a duty whose continuity area vanishes
    beside the hub answers an eye EQUAL to the hub — published to an AI as
    `inducer_shroud_radius_mm` and built as a wheel with no inlet. The old gate
    asked only whether the eye was inside the RIM."""
    r1s, r1h = expect
    with pytest.raises(ValueError) as e:
        meanline.design(duty(**kw))
    msg = str(e.value)
    assert "inlet eye" in msg, (name, msg)
    assert f"{r1s:,.2f} mm" in msg and f"{r1h:,.2f} mm" in msg, (name, msg)
    assert "raise the mass flow" in msg, (name, msg)
    assert "Traceback" not in msg and "Error" not in msg, msg


def test_the_sound_corpus_keeps_a_real_ring():
    """A guard that refuses correct geometry is the worse sin. The tightest
    sound wheel's eye is still more than 3x the radius it has to clear."""
    worst = None
    for _name, kw, _e in SOUND:
        d = meanline.design(duty(**kw))
        inner = max(d.inducer_hub_radius, d.bore_radius)
        ratio = d.inducer_shroud_radius / inner
        worst = ratio if worst is None else min(worst, ratio)
    assert worst is not None and worst > 3.0, worst


def _wheel_with_eye_blocked_to(d, fraction_left):
    """A hub with a ring standing in its inlet, leaving `fraction_left` of the
    published annulus open. Cheap: no blades, no pattern, no fuse."""
    t, L = d.backplate_thk, d.axial_length
    r1s, r1h = d.inducer_shroud_radius, d.inducer_hub_radius
    hub = blocks.with_center_hole(
        blocks.revolve_profile([(0, 0), (d.tip_radius, 0), (d.tip_radius, t),
                                (r1h, t + L), (0, t + L)]), d.bore_radius)
    if fraction_left >= 1.0:
        return hub
    cover = math.sqrt(r1s ** 2 - fraction_left * (r1s ** 2 - r1h ** 2))
    ring = Pos(0, 0, t + L / 2.0) * Cylinder(radius=cover, height=L)
    return hub + (ring - Cylinder(radius=d.bore_radius, height=8.0 * (t + L)))


def test_an_eye_the_blades_have_filled_is_measured_and_refused_in_words():
    """The wheel measured at 967963d, in the shape a test can afford: a ring
    standing where the blades stand. Nothing else in the module can see it —
    `to_spec` pins symmetry, solid count, tip radius and overall height, and
    the real wheel passed all four."""
    d = meanline.design(duty())
    wide_open = _wheel_with_eye_blocked_to(d, 1.0)
    open_mm2, available = meanline.eye_passage(wide_open, d)
    assert available > 3000.0, available          # the shipped wheel's ring
    assert open_mm2 == pytest.approx(available, rel=0.01)
    assert meanline.eye_problem(wide_open, d) is None

    sealed = _wheel_with_eye_blocked_to(d, 0.0)
    open_mm2, available = meanline.eye_passage(sealed, d)
    assert open_mm2 < 1e-6, open_mm2
    problem = meanline.eye_problem(sealed, d)
    assert problem and "inlet eye is not an opening" in problem, problem
    assert "13 blades" in problem, problem        # the count, in words
    assert "1.88 mm thick" in problem, problem    # and the thickness
    # ROUND FOUR corrected the second half of this advice: "raise the mass
    # flow, which makes the wheel bigger" does not make the wheel bigger —
    # r2 is U2/omega and U2 has no mass flow in it (measured over four flows
    # at PR 1.1 / 100,000 rpm, probes/meanline_round4_advice.py: r2 stays
    # 11.55 mm and the next step up is refused by the eye-beyond-rim rule).
    assert "lower the speed" in problem, problem
    assert "the wheel grows" in problem, problem


def test_the_eye_rule_cuts_where_the_measurements_put_it():
    """BOTH sides of the TENTH, on one wheel. The line is a tenth of the ring,
    and the nine wheels it was set from (probes/meanline_eye_sweep2.py) read
    3.21, 3.36 and 6.55 percent below it and 16.06, 26.50, 31.37, 37.43, 68.96
    and 70.71 above.

    ROUND FOUR re-pointed the duty and says why. On the shipped sample's duty
    the 12% wheel is no longer "alive": 369.25 mm2 of passage can pass 0.089
    kg/s of air at the speed of sound and that duty asks for 0.5, so the FLOW
    rule refuses it — and this test would have been pinning the wrong rule
    while reading as if it pinned the tenth. At pressure ratio 1.1 the air the
    eye has to swallow is slow enough that the tenth is the rule that bites
    (12% open is 1.5x under the choking limit, 8% is 2.3x over it —
    probes/meanline_round4_testduty.py), so the tenth keeps a test of its own
    and the old duty is kept below with the answer it now earns."""
    d = meanline.design(duty(mass_flow=0.5, pressure_ratio=1.1, rpm=12000))
    dead = _wheel_with_eye_blocked_to(d, 0.08)
    open_mm2, available = meanline.eye_passage(dead, d)
    assert 0.07 < open_mm2 / available < 0.09, open_mm2 / available
    problem = meanline.eye_problem(dead, d)
    assert problem and "inlet eye is not an opening" in problem, problem

    alive = _wheel_with_eye_blocked_to(d, 0.12)
    open_mm2, available = meanline.eye_passage(alive, d)
    assert 0.11 < open_mm2 / available < 0.13, open_mm2 / available
    assert meanline.eye_problem(alive, d) is None

    # the duty this test used to ask, with what it earns now
    sample = meanline.design(duty())
    still_choked = _wheel_with_eye_blocked_to(sample, 0.12)
    problem = meanline.eye_problem(still_choked, sample)
    assert problem and "cannot pass this flow" in problem, problem


def test_the_eye_is_read_at_the_top_of_the_wheel_not_below_it():
    """The first version of this measurement read a slab 2% of the wheel's
    depth below the top and called a SOUND 26.50% wheel 0.00% open: on a
    0.86 mm annulus the hub cone had already closed it (0.005 kg/s, PR 4,
    90,000 rpm — probes/meanline_eye_sweep.py against meanline_eye_sweep2.py).
    The station is the inlet plane, and the denominator is measured there too,
    so the cone's own growth cancels instead of counting as blockage."""
    d = meanline.design(duty(mass_flow=0.005, pressure_ratio=4.0, rpm=90000,
                             backsweep_deg=0.0))
    assert d.inducer_shroud_radius - d.inducer_hub_radius < 1.0, d
    hub_only = _wheel_with_eye_blocked_to(d, 1.0)
    open_mm2, available = meanline.eye_passage(hub_only, d)
    assert available > 20.0, available
    assert open_mm2 / available > 0.95, (open_mm2, available)
    assert meanline.eye_problem(hub_only, d) is None


def test_both_measured_questions_reach_the_report(monkeypatch):
    """The bore and the eye are asked of the BUILT wheel, and either one turns
    `ok` off — `mcp_server._design_compressor` reads `build.ok` and
    `build.all_problems()`. A 13-blade build is 14 to 168 s, so the wheel the
    kernel would hand back is handed back here instead."""
    d = meanline.design(duty())
    sealed = _wheel_with_eye_blocked_to(d, 0.0)

    def fake(components, mode="fuse", assembly_spec=None, clash_tol=1e-3):
        return assembly.AssemblyReport(ok=True, mode=mode, components=[],
                                       assembly_problems=[], part=sealed)

    monkeypatch.setattr(meanline.assembly, "build_and_verify", fake)
    rep = meanline.build_from_design(d)
    assert rep.ok is False
    joined = " ".join(rep.all_problems())
    assert "inlet eye is not an opening" in joined, joined
    # and the bore, which this wheel does have, is not falsely reported
    assert "shaft bore is not a hole" not in joined, joined


# ------ ROUND FOUR: the blade ANGLES are published, so they are measured ----

# `mcp_server._design_compressor` hands an AI `beta1_deg` and `beta2_deg` beside
# the radii, and until round four nothing compared them to the blade the kernel
# cuts. Measured three ways, all agreeing (probes/meanline_blade_angle_spline.py
# reads the OCCT curve's own tangent; probes/meanline_blade_angle_metal.py cuts
# thin annular shells out of the BUILT blade with real booleans and takes the
# centre of mass of each; probes/meanline_camber_predict.py checks the
# arithmetic `meanline.built_blade_angle` uses against both):
#
#   at the RIM the metal is 1.1 to 3.1 degrees steeper than `beta2_deg`;
#   at the blade ROOT it is 6.4 to 28.2 steeper than `beta1_deg` — the
#       shipped sample's blade leaves its root at 64.1 where 49.4 is published,
#       and two duties leave it past 90, which is a blade turning INWARD;
#   at the INLET EYE, the station `beta1_deg` is named for ("inducer blade
#       angle at shroud"), the metal is 0.05 to 77.6 degrees away from it.
#
# name, duty, r1s/r2, the angle IN THE METAL at the inlet eye
INDUCER_ANGLE = [
    ("the shipped sample", dict(), 0.350, 48.03),
    ("the MCP test duty", dict(mass_flow=1.0, rpm=40000), 0.432, 50.00),
    ("a small turbo", dict(mass_flow=0.1, pressure_ratio=2.0, rpm=120000),
     0.598, 49.63),
    ("a micro turbo", dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000),
     0.722, 46.94),
    ("a big turbo", dict(mass_flow=2.0, pressure_ratio=4.0, rpm=25000),
     0.319, 46.75),
    ("the largest measured", dict(mass_flow=50.0, pressure_ratio=2.0,
                                  rpm=3000), 0.345, 47.85),
    ("backsweep 0", dict(mass_flow=1.0, rpm=40000, backsweep_deg=0.0),
     0.505, 35.26),
    ("backsweep -60", dict(mass_flow=1.0, rpm=40000, backsweep_deg=-60.0),
     0.672, -11.69),
]


@pytest.mark.parametrize("name,kw,ratio,built", INDUCER_ANGLE,
                         ids=[s[0].replace(" ", "_") for s in INDUCER_ANGLE])
def test_the_inducer_angle_in_the_metal_is_not_the_one_published(name, kw,
                                                                 ratio, built):
    """THE ANGLE THE AIR MEETS, pinned wheel by wheel.

    This test pins a DEFECT, deliberately: the gap is not meanline's to close
    (`blocks.curved_blade` integrates the camber law in 16 forward-Euler steps
    and the first one advances the radius by 73% of itself), and the day it is
    closed this file must be read again rather than quietly kept green.

    The worst of these is a backsweep of -60: the design publishes an inducer
    angle of +65.9 degrees and the metal at the eye leans -11.7 — the other
    way. tests/test_mcp_server.py blesses that backsweep."""
    d = meanline.design(duty(**kw))
    assert d.inducer_shroud_radius / d.tip_radius == pytest.approx(ratio,
                                                                   abs=0.001)
    got = meanline.built_blade_angle(d, d.inducer_shroud_radius)
    assert got == pytest.approx(built, abs=0.05), name
    # the wheels whose eye sits far out have no chance of carrying beta1: the
    # camber runs beta1 at the ROOT and ramps it linearly in radius
    assert (abs(got - d.beta1_deg) > 4.0) == (ratio > 0.40), (name, got,
                                                              d.beta1_deg)


def test_the_predicted_blade_angle_is_the_one_in_the_metal():
    """The arithmetic above says what `blocks.curved_blade` WILL draw, so it
    has to be checked against what it DID draw — with booleans, on the built
    blade, not against itself. Thin annular shells at three radii; the centre
    of mass of each chunk is the camber there, and the angle between two of
    them is the blade angle.

    This is also the guard on `_CAMBER_STEPS`: change the integration in
    `blocks` and this test goes red instead of the design quietly publishing a
    sentence about a blade that no longer exists."""
    d = meanline.design(duty())
    blade = meanline.one_blade(d)
    ri, ro = 0.75 * d.inducer_hub_radius, d.tip_radius
    thk = max(0.02 * ro, 1.5)
    band, step = (ro - ri) / 200.0, 0.01 * (ro - ri)

    def theta_at(r):
        shell = (Cylinder(radius=r + band / 2.0, height=d.axial_length)
                 - Cylinder(radius=r - band / 2.0, height=d.axial_length))
        chunk = blade & (Pos(0, 0, d.axial_length / 2.0) * shell)
        c = chunk.center()
        return math.atan2(c.Y, c.X)

    for r in (d.inducer_shroud_radius, 0.5 * (ri + ro), ro - 2.0 * thk):
        dth = theta_at(r + step / 2.0) - theta_at(r - step / 2.0)
        measured = math.degrees(math.atan2(r * dth, step))
        predicted = meanline.built_blade_angle(d, r)
        assert measured == pytest.approx(predicted, abs=1.5), (r, measured,
                                                               predicted)
        # ...and the metal is steeper than the design's own camber law says
        law = (d.beta1_deg + (d.beta2_deg - d.beta1_deg)
               * (r - ri) / (ro - ri))
        assert measured > law, (r, measured, law)


def test_the_design_says_where_its_inducer_angle_is_not_the_one_it_builds():
    """A note, not a refusal: the geometry is sound and the kernel builds it —
    what is wrong is the SENTENCE, so the sentence is what changes. Same shape
    as the exit-width clamp round two closed."""
    d = meanline.design(duty(mass_flow=0.05, pressure_ratio=1.8, rpm=180000))
    note = " ".join(d.notes)
    assert "inducer angle" in note, note
    assert "67.4 degrees" in note, note        # what it publishes
    assert "46.9 degrees" in note, note        # what it cuts
    assert "20.5 out" in note, note            # and the gap, in words
    assert "Lower the speed" in note, note     # the dial that closes it
    assert "NOTE:" in d.report(), d.report()
    # ...and it stays quiet where the metal does carry the published angle
    for kw in (dict(), dict(mass_flow=2.0, pressure_ratio=4.0, rpm=25000),
               dict(mass_flow=50.0, pressure_ratio=2.0, rpm=3000)):
        quiet = meanline.design(duty(**kw))
        assert "inducer angle" not in " ".join(quiet.notes), kw


def test_the_width_note_does_not_say_one_times():
    """`{ratio:,.0f} times` rounded every overstatement from 1.01 to 1.49 to
    "1 times wider than this flow needs", which is not a sentence. Measured on
    a 0.01 kg/s blower at 90,000 rpm: 0.88 mm wanted, the 1.00 mm floor built
    (probes/meanline_round4_kernel.py)."""
    d = meanline.design(duty(mass_flow=0.01, pressure_ratio=1.3, rpm=90000))
    note = " ".join(d.notes)
    assert "exit blade width" in note, note
    assert "1 times wider" not in note, note
    assert "14% wider" in note, note
    # the big overstatements still read as multiples
    big = meanline.design(duty(pressure_ratio=3.0, rpm=1000))
    assert "18 times wider" in " ".join(big.notes), big.notes


# ------------- and the inlet has to pass the flow the duty asks for ---------

# The tenth of a ring `_EYE_OPEN_FRACTION` asks for cannot ask whether the air
# fits: that depends on the duty. See `_EYE_CHOKE_MARGIN` for the measurements
# — 3,178 of 6,273 designs in a grid pass the tenth with a passage that cannot
# take their own mass flow at the speed of sound, up to 9.4x over.


def test_the_choke_flux_is_the_textbook_one():
    """241.3 kg/s per square metre for air at 288.15 K and 101,325 Pa. The
    whole rule rests on this number, so it is pinned against the figure any
    gas-dynamics table prints, not against itself."""
    flux = meanline._choke_flux(meanline.Duty(mass_flow=1.0,
                                              pressure_ratio=2.0, rpm=10000))
    assert flux * 1e6 == pytest.approx(241.3, abs=0.1)
    # a design carries it, and a hand-built one does not
    d = meanline.design(duty())
    assert d.inlet_choke_flux == pytest.approx(flux, rel=1e-9)
    assert d.mass_flow == 0.5


def test_an_inlet_that_cannot_pass_its_own_flow_is_refused():
    """The wheel the tenth passes and the air cannot get into. A ring standing
    in the eye, in the shape a test can afford; a quarter of the shipped
    sample's ring can take about 0.19 kg/s at the speed of sound, and the duty
    asks for 0.5."""
    d = meanline.design(duty())
    blocked = _wheel_with_eye_blocked_to(d, 0.25)
    open_mm2, available = meanline.eye_passage(blocked, d)
    assert open_mm2 / available > meanline._EYE_OPEN_FRACTION   # the tenth
    problem = meanline.eye_problem(blocked, d)                  # passes it
    assert problem and "cannot pass this flow" in problem, problem
    assert "0.5 kg/s" in problem, problem            # what was asked
    assert "speed of sound" in problem, problem      # why that is the ceiling
    assert "13 blades" in problem, problem           # what is standing in it
    assert "lower the speed" in problem, problem
    assert "lower the pressure ratio" in problem, problem


def test_a_hand_built_design_is_not_asked_a_question_it_cannot_answer():
    """`mass_flow` and `inlet_choke_flux` are 0.0 on a CompressorDesign built
    by an editor, a repair loop or a saved file, exactly as `exit_width_ideal`
    is. The flow rule then says nothing rather than refusing everything."""
    d = meanline.design(duty())
    blocked = _wheel_with_eye_blocked_to(d, 0.25)
    assert meanline.eye_problem(blocked, d) is not None
    hand_built = dataclasses.replace(d, mass_flow=0.0, inlet_choke_flux=0.0)
    assert meanline.eye_problem(blocked, hand_built) is None


# name, duty, the percentage the KERNEL measured at 967963d, the choke ratio
# that passage earns (probes/meanline_round4_numbers.py)
KERNEL_MEASURED = [
    ("3.21", dict(mass_flow=0.005, pressure_ratio=1.8, rpm=250000,
                  backsweep_deg=60.0), 3.21, 21.54),
    ("3.36", dict(mass_flow=0.005, pressure_ratio=1.1, rpm=100000), 3.36,
     5.91),
    ("6.55", dict(mass_flow=0.005, pressure_ratio=1.8, rpm=90000,
                  backsweep_deg=-20.0), 6.55, 6.19),
    ("16.06", dict(mass_flow=0.02, pressure_ratio=2.5, rpm=150000), 16.06,
     3.78),
    ("26.50", dict(mass_flow=0.005, pressure_ratio=4.0, rpm=90000,
                   backsweep_deg=0.0), 26.50, 2.63),
    ("31.37", dict(mass_flow=0.05, pressure_ratio=1.8, rpm=180000), 31.37,
     1.52),
    ("37.43", dict(mass_flow=0.1, pressure_ratio=4.0, rpm=250000,
                   backsweep_deg=25.0), 37.43, 1.99),
    ("68.96", dict(mass_flow=20.0, pressure_ratio=2.5, rpm=5000), 68.96, 0.88),
    ("70.71", dict(mass_flow=0.5, pressure_ratio=3.0, rpm=45000), 70.71, 0.95),
]


@pytest.mark.parametrize("name,kw,pct,ratio", KERNEL_MEASURED,
                         ids=[s[0] for s in KERNEL_MEASURED])
def test_both_sides_of_the_flow_rule_on_the_wheels_the_kernel_measured(
        name, kw, pct, ratio):
    """BOTH SIDES, on nine wheels OpenCASCADE actually built (round three's
    own calibration set), with no model anywhere in it: the passage is the
    percentage the kernel read, and the question is what that passage can pass.

    The micro turbo at 1.52x keeps building — measured end to end, 16.0 s,
    ok=True, one watertight 13-fold solid (probes/meanline_round4_kernel.py) —
    and the 0.01 kg/s blower at 11.91% open, which the tenth passed, is
    refused at 2.6x. Two of round three's nine are refused with it, at 3.78x
    and 2.63x; both were called sound by a fraction that never asked what the
    duty was."""
    d = meanline.design(duty(**kw))
    inner = max(d.inducer_hub_radius, d.bore_radius)
    available = math.pi * (d.inducer_shroud_radius ** 2 - inner ** 2)
    open_mm2 = pct / 100.0 * available
    most = d.inlet_choke_flux * open_mm2
    assert d.mass_flow / most == pytest.approx(ratio, abs=0.01), name
    refused_by_tenth = pct / 100.0 < meanline._EYE_OPEN_FRACTION
    refused_by_flow = d.mass_flow > meanline._EYE_CHOKE_MARGIN * most
    # every wheel the old rule refused is refused by the new one too
    assert not refused_by_tenth or refused_by_flow, name
    # and the corpus's own wheels still build
    assert (ratio < 2.0) == (not refused_by_flow), name
