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
import math

import pytest

import blocks
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
    ("1000 rpm", dict(rpm=1000), "metres"),
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
    # the speed it names is arithmetic, not advice: r2 = U2 / omega
    assert "2,111 rpm" in msg, msg


def test_the_pressure_ratio_1_001_refusal_quotes_both_numbers():
    with pytest.raises(ValueError) as e:
        meanline.design(duty(pressure_ratio=1.001))
    msg = str(e.value)
    assert "7,217.26 mm" in msg and "2.61 mm" in msg, msg
    assert "at 0.5 kg/s and pressure ratio 1.001" in msg, msg


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
    assert p["hub"]["radius"] == 4.92
    assert p["blade"] == {"inner_radius": 7.39, "outer_radius": 93.8,
                          "inlet_angle_deg": 49.4, "exit_angle_deg": 35.0,
                          "height": 32.83, "thickness": 1.88}
    assert p["blades_raw"]["count"] == 13
    assert p["shroud_cutter"]["points"] == [
        [5.39, 35.64], [32.81, 35.64], [93.8, 5.359999999999999],
        [108.8, 5.359999999999999], [108.8, 85.64], [5.39, 85.64]]
    assert doc.spec == {"symmetry": 13, "n_solids": 1, "tip_radius": 93.8,
                        "tol": 1.0}


def test_the_gate_reads_the_geometry_it_will_actually_build():
    """`exit_width` is CLAMPED to a machinable 1.0 mm minimum, so the gate has
    to judge the clamped number — that is the blade the kernel will cut."""
    d = meanline.design(duty(mass_flow=1e-6))
    assert d.exit_width == 1.0                      # the clamp bit
    assert d.exit_width < d.tip_radius              # and it is still a wheel
    assert all(math.isfinite(v) for v in
               (d.tip_radius, d.exit_width, d.inducer_shroud_radius))
