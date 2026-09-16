import contextlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))       # tests/gauntlet.py

import pytest

# .step files in designs/ that a fast test writes under a LIBRARY design's
# name — a name the user can produce themselves by opening that design and
# pressing Export.
LIBRARY_STEPS = ("flange-100.step", "roundtrip-src.step")


@contextlib.contextmanager
def library_steps_kept(*names: str):
    """Leave designs/<name>.step exactly as it was found — either way.

    The export tests write into the real designs/ folder on purpose: the path
    IS what they assert. Section 12 round two cured "a test leaves
    flange-100.step behind" with an unconditional `unlink(missing_ok=True)`,
    and round three measured the other half of it — the fast tier DELETING a
    flange-100.step it had not created (51 tests green, the user's file gone:
    probes/section12_round3_fixture_probe.py). flange-100 is a gallery design;
    that .step may be the user's own export. Overwriting it is the same loss,
    so the bytes are put back, not just the absence."""
    import studio
    was = {n: (studio.DESIGNS / n).read_bytes()
           if (studio.DESIGNS / n).exists() else None for n in names}
    try:
        yield was
    finally:
        for n, data in was.items():
            p = studio.DESIGNS / n
            if data is None:
                p.unlink(missing_ok=True)      # ours: the test made it
            else:
                p.write_bytes(data)            # the user's: put it back


@pytest.fixture()
def library_steps_untouched():
    """Fixture form of `library_steps_kept`, for a test file whose client
    fixture exports into designs/."""
    with library_steps_kept(*LIBRARY_STEPS) as was:
        yield was


@pytest.fixture(autouse=True)
def _isolate_version_histories(tmp_path, monkeypatch):
    """No test may write a version history into the user's designs/ library.

    Autouse because the pollution would be SILENT: since VERSION-TREE-PLAN.md
    P2, /api/open mints a version as a side effect, so a test that merely opens
    flange-100 creates designs/flange-100.history/ — inside tracked user work.
    Every test gets its own throwaway root instead."""
    monkeypatch.setenv("TEXTCAD_HISTORY_ROOT", str(tmp_path / "histories"))


@pytest.fixture
def in_process_kernel(monkeypatch):
    """Run fillet / chamfer / shell HERE instead of in the kernel worker.

    Since kernelguard.py the dangerous kernel calls happen in a child process,
    which is the whole point — an access violation there is a sentence instead
    of a dead server. But it puts a process boundary between a test and the
    kernel, so a test that SPIES on `blocks._b3d_fillet`, or makes it throw, is
    patching a function the work no longer runs through. Those tests are about
    the in-process guard chain, so they ask for it by name."""
    monkeypatch.setenv("TEXTCAD_KERNEL_GUARD", "0")
