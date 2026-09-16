"""The kernel worker: a crash is a sentence, and the sentence is about the
right shape.

The overnight journey run of 2026-09-13 filed four folders where OpenCASCADE
took the whole server down in one click — a fillet on eight picked rims of a
sliver body, a shell with an open bottom on the oneplus case, a closed shell on
the pump impeller's three lumps, and one /api/edit that never came back. None
of those is catchable: an access violation is not an exception. kernelguard.py
runs the dangerous call in a warm worker instead, so its death is a refusal.

Three things have to be true, and each of them is a separate way to be wrong:

  1. the crash is refused and the process LIVES (the point),
  2. the refusal is a PLAIN sentence with no kernel jargon and no worker
     plumbing in it (the house rule for every refusal),
  3. the worker works on the SAME shape the parent picked — a crash turned
     into silently-wrong geometry would be worse than the crash.

Nothing here is inferred: the crash bodies are the committed .brep files the
journey run produced, and (1) is proved by running a real child and reading its
exit code.
"""
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from build123d import Box, Part, import_brep

import blocks
import kernelguard
import sketch

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"


def body(name: str) -> Part:
    return Part(import_brep(str(FIXTURES / f"{name}.brep")).wrapped)


def box() -> Part:
    return Part(Box(20, 10, 5).wrapped)


def run_child(code: str, timeout: int = 600) -> subprocess.CompletedProcess:
    """A real child process, the way test_shell_tool.py and test_mirror_tool.py
    already prove a crash is survived. The assertion that matters is on the
    child's RETURN CODE: 0 means the refusal happened without the process
    dying, and any 0xC00000xx means it did not."""
    env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code)],
                          capture_output=True, text=True, timeout=timeout,
                          env=env, cwd=str(ROOT))


# ---------------------------------------------------------------------------
# 1. the three bodies that killed the server
# ---------------------------------------------------------------------------

CRASHERS = {
    # my-part-8 seed 46791 step 14: eight flat rims at once, 0xC0000005 at
    # every radius from 0.05 to 0.5 (probes/fillet_crash_sweep.py)
    "fillet_sliver": """
        import blocks, kernelguard
        from build123d import Part, import_brep
        p = Part(import_brep("tests/fixtures/sliver_intersect_plate.brep").wrapped)
        try:
            blocks.fillet_edges(p, 0.4, "horizontal")
            print("BUILT")
        except ValueError as e:
            print("REFUSED", e)
    """,
}


KILLERS = {
    # my-part-8 seed 46791 step 14: eight flat rims at once, 0xC0000005 at
    # every radius from 0.05 to 0.5 (probes/fillet_crash_sweep.py)
    "fillet_sliver": lambda: blocks.fillet_edges(
        body("sliver_intersect_plate"), 0.4, "horizontal"),
    # oneplus_7_pro_case seed 46794 step 8 (probes/shell_open_face_crash.py)
    "shell_open_case": lambda: sketch.shell(
        body("oneplus_case_shell_body"), 1.1, None, "inside", "bottom"),
    # pump-impeller seed 47244 step 56 (probes/shell_third_crash.py)
    "shell_closed_impeller": lambda: sketch.shell(
        body("impeller_cut_shell_body"), 1.9, None, "inside", None),
    # my-part-5 seed 18800 step 25 (probes/shell_mirror_crash.py): an OPEN
    # bottom on a mirrored body, and unlike the oneplus case the window is not
    # a window at all — every thickness from 0.2 to 5 mm dies with the bottom
    # open, and all but 0.2 with the top open
    "shell_open_mirror": lambda: sketch.shell(
        body("my_part_5_mirror_body"), 2.1, None, "inside", "bottom"),
    # my-part seed 95959 step 18 (probes/shell_thin_wall_probe.py): a SECOND
    # shell, top open, on a 23.4 x 17.1 x 12.7 box already shelled at 1.3 mm
    # with the bottom open — a legitimate 0.2 mm recess in the lid, and
    # 0xC0000005 at every wall from 0.66 mm up (0.64 builds). The rays of
    # `assert_something_would_be_hollowed` draw the line at 1.3 for the open
    # lid, so this one is the worker's to catch.
    "shell_twice": lambda: sketch.shell(sketch.shell(sketch.extrude_sketch(
        sketch.make_sketch("XY", 0, [dict(kind="rectangle", mode="add", x=0, y=0,
                                          rotation=0, w=23.4, h=17.1)]), amount=12.7),
        1.3, ["bottom"]), 1.1, ["top"]),
}


@pytest.mark.parametrize("case", sorted(KILLERS))
def test_a_body_that_kills_the_kernel_is_a_sentence_in_a_process_that_lives(case):
    """Run in THIS process on purpose. Before kernelguard each of these three
    ended the run where it stands — pytest surviving to the assertion below is
    itself the result being tested, and it costs no child."""
    with pytest.raises(ValueError) as ei:
        KILLERS[case]()
    said = str(ei.value)
    assert kernelguard.CRASH_PHRASE in said, (
        f"it was refused, but not as a crash — the guard may be catching "
        f"something else: {said}")
    for leak in ("TopoDS", "NCollection", "Standard_", "BRep", "StdFail",
                 "Traceback", "kernelguard", "subprocess", "0xC0000005",
                 "brep", "seq"):
        assert leak not in said, f"{leak!r} reached the user: {said}"
    for helpful in ("nothing was changed", "Try"):
        assert helpful.lower() in said.lower(), said


def test_the_refusal_holds_in_a_pristine_process_too():
    """One real child, with nothing else going on in it, reading the exit code
    itself: 0 means the refusal happened without the process dying, and any
    0xC00000xx means the guard did not hold. The same shape as the crash tests
    in test_shell_tool.py and test_mirror_tool.py."""
    p = run_child(CRASHERS["fillet_sliver"])
    assert p.returncode == 0, (
        f"the process DIED with {p.returncode & 0xFFFFFFFF:#010x} — the guard did "
        f"not hold: {p.stderr[-500:]}")
    assert "REFUSED" in p.stdout, p.stdout[-500:]
    assert kernelguard.CRASH_PHRASE in p.stdout, p.stdout[-400:]


def test_a_crash_is_recorded_even_though_it_was_made_polite(tmp_path, monkeypatch):
    """A crash that becomes a friendly sentence must still be FINDABLE, or the
    journey runner stops filing them and the next one is invisible."""
    log = tmp_path / "kernel-crashes.log"
    monkeypatch.setattr(kernelguard, "CRASH_LOG", log)
    with pytest.raises(ValueError):
        blocks.fillet_edges(body("sliver_intersect_plate"), 0.4, "horizontal")
    rows = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["what"] == "crash"
    assert rows[0]["kind"] == "fillet"
    assert rows[0]["exit"].lower() == "0xc0000005"


# ---------------------------------------------------------------------------
# 2. the answer is about the shape the parent picked
# ---------------------------------------------------------------------------

def test_the_worker_returns_the_same_geometry_as_this_process(monkeypatch):
    """The guard must be invisible when nothing goes wrong. Same body, same
    numbers, to the last decimal the kernel produces."""
    monkeypatch.setenv("TEXTCAD_KERNEL_GUARD", "0")
    here = blocks.fillet_edges(box(), 1.0, "top")
    monkeypatch.setenv("TEXTCAD_KERNEL_GUARD", "1")
    there = blocks.fillet_edges(box(), 1.0, "top")
    assert there.volume == pytest.approx(here.volume, abs=1e-9)
    assert len(there.faces()) == len(here.faces())
    assert len(there.edges()) == len(here.edges())


@pytest.mark.parametrize("make,volume", [
    (lambda: Part(Box(20, 10, 5).wrapped), 1000.0),          # a Part -> a Compound
    (lambda: __import__("build123d").Solid.make_box(40, 30, 20), 24000.0),
])
def test_a_body_crosses_as_the_kind_of_shape_it_was(make, volume):
    """Found by the fast tier, not by reasoning: `import_brep` hands back a
    Compound for a body that was a `Part` and a BARE `Solid` for one that was a
    bare Solid, and `Part(solid.wrapped)` reads volume **0** — 24000 mm3 became
    0.0000 (probes/brep_reimport_types.py). Both kinds reach `fillet_edges`:
    the tree passes a Part, `tests/test_health_degenerate_edges.py` passes a
    bare Solid. The weight check is what caught it, and it is the reason this
    test can be about the weight."""
    body = make()
    assert body.volume == pytest.approx(volume)
    out = blocks.fillet_edges(body, 1.0, "vertical")
    assert out.volume > 0, "the body arrived weighing nothing"
    assert out.volume < volume, "a fillet removes material"
    assert out.volume > volume * 0.9, "it removed far too much"


def test_a_shell_through_the_worker_opens_the_face_that_was_picked():
    """build123d DROPS an opening face that is not IsSame with a face of the
    solid it offsets — silently, leaving a closed hollow that passes every
    volume rule. So the opening has to be re-found on the body the worker read,
    and this is the test that it really is the same face."""
    open_top = sketch.shell(Part(Box(50, 50, 30).wrapped), 3, None, "inside", "top")
    closed = sketch.shell(Part(Box(50, 50, 30).wrapped), 3, None, "inside", None)
    # exactly the top wall is missing: the inner 44 x 44 lid, 3 mm thick
    assert closed.volume - open_top.volume == pytest.approx(44 * 44 * 3, rel=1e-6), (
        "the open face was dropped: an open shell weighs the same as a closed one")
    # and it is the TOP that is open, not the bottom — by symmetry the volume
    # alone cannot tell those apart, so ask where the big flat skin is
    def skin(part, z):
        return [f for f in part.faces()
                if abs(f.center().Z - z) < 1e-6 and f.area > 1000]
    lo, hi = open_top.bounding_box().min.Z, open_top.bounding_box().max.Z
    assert not skin(open_top, hi), "the top is still closed"
    assert skin(open_top, lo), "the BOTTOM was opened instead of the top"


def test_a_pick_that_does_not_match_on_the_other_side_is_refused_not_guessed():
    """`take` is the check that the worker is holding the shape the parent
    picked. If it ever disagrees, the step must FAIL — never fall back to
    'something near enough', which would turn a crash into wrong geometry."""
    b = box()
    edges = b.edges()
    good = kernelguard._marks([edges[0]])
    with pytest.raises(kernelguard.KernelGone, match="measures differently"):
        kernelguard.take(edges, [1], good, "edge")
    with pytest.raises(kernelguard.KernelGone, match="no longer on this body"):
        kernelguard.take(edges, [len(edges)], good, "edge")
    assert kernelguard.take(edges, [0], good, "edge") == [edges[0]]


def test_the_index_of_a_pick_is_found_by_identity_not_by_measurement():
    """A box has twelve edges and several of them are the same length in the
    same place by symmetry; `indices` must answer with OCCT's own identity."""
    b = box()
    edges = b.edges()
    picked = [edges[7], edges[2], edges[7]]
    assert kernelguard.indices(edges, picked) == [7, 2, 7]
    with pytest.raises(kernelguard.KernelGone, match="not part of this body"):
        kernelguard.indices(edges, [Part(Box(3, 3, 3).wrapped).edges()[0]])


# ---------------------------------------------------------------------------
# 3. a refusal is still a refusal, and the guard changes nothing about it
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("call,words", [
    (lambda: blocks.fillet_edges(box(), 50, "top"), "does not fit"),
    (lambda: blocks.fillet_edges(box(), 0, "top"), "must be positive"),
    (lambda: sketch.shell(Part(Box(50, 50, 30).wrapped), 40, None, "inside", None),
     "meet in the middle"),
    (lambda: sketch.shell(Part(Box(50, 50, 30).wrapped), 0, None, "inside", None),
     "must be positive"),
])
def test_an_ordinary_refusal_reads_exactly_as_it_did_before(call, words):
    with pytest.raises(ValueError, match=words) as ei:
        call()
    said = str(ei.value)
    assert kernelguard.CRASH_PHRASE not in said
    assert kernelguard.STOPPED_PHRASE not in said
    for leak in ("worker", "seq", "brep", "Traceback"):
        assert leak not in said, said


def test_a_crash_refusal_is_not_cached_against_the_feature():
    """Document.rebuild caches a failure so a broken parameter does not cost a
    full rebuild while the user fixes it. A crash is NOT a broken parameter,
    the cache is shared by every tab in the process, and a user who presses the
    same button again must get a real attempt."""
    assert kernelguard.KernelGone.transient is True
    assert not getattr(ValueError("an ordinary refusal"), "transient", False)


def test_the_guard_can_be_turned_off_and_then_the_kernel_runs_here(monkeypatch):
    calls = []
    real = blocks._b3d_fillet
    monkeypatch.setenv("TEXTCAD_KERNEL_GUARD", "0")
    monkeypatch.setattr(blocks, "_b3d_fillet",
                        lambda es, **kw: calls.append(kw) or real(es, **kw))
    blocks.fillet_edges(box(), 1.0, "top")
    assert calls == [{"radius": 1.0}], calls


def test_the_worker_restarts_itself_after_a_death():
    """One crash must not end the session's ability to do geometry. The next
    call gets a fresh worker (the replacement is started in the background, so
    in the app the user's next click is usually already warm)."""
    with pytest.raises(ValueError):
        blocks.fillet_edges(body("sliver_intersect_plate"), 0.4, "horizontal")
    after = blocks.fillet_edges(box(), 1.0, "top")
    assert after.volume > 0
    assert len(after.faces()) > 6


# ---------------------------------------------------------------------------
# 4. the clock
# ---------------------------------------------------------------------------

def test_a_kernel_call_past_its_budget_is_stopped_and_says_so(monkeypatch):
    """One /api/edit in the overnight run ran for 3 hours 6 minutes with a flat
    working set — a spin, not work. The budget is what ends it. It is
    deliberately generous (the same run recorded a CORRECT chamfer at 630 s),
    so this test sets a tiny one rather than waiting for the real ceiling."""
    monkeypatch.setattr(kernelguard, "DEFAULT_BUDGET", 0.2)
    with pytest.raises(kernelguard.KernelGone) as ei:
        sketch.shell(body("oneplus_case_shell_body"), 0.2, None, "inside", "bottom")
    said = str(ei.value)
    assert kernelguard.STOPPED_PHRASE in said
    assert "0.2 seconds" in said
    assert "nothing was changed" in said
    # and the session still works afterwards
    assert blocks.fillet_edges(box(), 1.0, "top").volume > 0


def test_the_shipped_budget_is_above_every_correct_answer_ever_measured():
    """The overnight run's slowest CORRECT kernel call was 1195 s (a shell on
    autonomiq-panel); its slowest correct blend was 630 s. A ceiling under
    those would refuse the user's own parts to catch a spin. 900 s sits above
    the blends and below the 3-hour spin; the shell above it is itself a
    finding the user should hear about, not silently wait 20 minutes for.

    The lower bound is 879 s, not 630, since 2026-09-14: a closed 2.7 mm shell
    on a 1.5x scale of designs/autonomiq-panel (675 faces, one lump) is
    REFUSED by the kernel — "the kernel could not offset its faces", the
    sentence the user should read — and takes 879 s standalone, 692 s through
    the API, to say so (probes/shell_slow_panel.py; bugs/fixed/...s18884).
    A budget under that turns a correct refusal into "was stopped after 15
    minutes", which tells the user nothing they can act on. The margin is 21
    seconds, and that is the honest state of it: a slower box crosses the
    line."""
    assert 879 < kernelguard.DEFAULT_BUDGET < 3 * 3600


def test_the_budget_reads_in_words_a_person_can_act_on():
    assert kernelguard._minutes(900) == "15 minutes"
    assert kernelguard._minutes(60) == "60 seconds"
    assert kernelguard._minutes(0.25) == "0.25 seconds"
    assert kernelguard._minutes(120) == "2 minutes"
