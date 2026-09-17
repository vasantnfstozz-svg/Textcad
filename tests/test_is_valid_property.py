"""LAUNCH-PLAN §10 — "`blocks.py` calls `is_valid()` as a METHOD (it is a
PROPERTY in build123d 0.11) inside a bare except, so the as-is Solid fast path
is likely dead" (reader, 2026-09-02).

Re-measured 2026-09-17 (probes/s10_required_params_probe.py): the reader was
right and the section-8 review already FIXED the one live call on 2026-09-12 —
blocks._stl_bytes_to_solids reads `shp.is_valid` as a property, and
tests/test_import_stl.py holds the hollow-part case it cost. No product module
calls it as a method any more.

What is new here is the guard, because the failure mode is silent: the call
sits inside a bare `except`, so getting it wrong does not raise — it quietly
disables the branch it guards, and a hollow 936 mm3 part came back as TWO
bodies totalling 1064 with every check green.
"""
import re
from pathlib import Path

import build123d as b3d
import pytest

# the modules of this pass; the same rule holds for all of them
CHECKED = ("blocks.py", "document.py", "author.py", "pattern.py",
           "sketch.py", "inspector.py")


def test_is_valid_is_a_property_in_this_build123d():
    """build123d 0.11.1: a property on Shape. Calling it raises TypeError
    ('bool' object is not callable), which a bare except swallows whole."""
    box = b3d.Box(10, 10, 10)
    assert isinstance(box.is_valid, bool)
    with pytest.raises(TypeError):
        box.is_valid()


def test_no_module_calls_is_valid_as_a_method():
    root = Path(__file__).resolve().parent.parent
    for name in CHECKED:
        for i, line in enumerate(
                (root / name).read_text(encoding="utf-8").splitlines(), 1):
            assert not re.search(r"\.is_valid\s*\(", line), f"{name}:{i} {line}"


def test_the_stl_as_is_fast_path_is_alive():
    """What the revived branch actually decides, measured rather than inferred:
    a closed box Solid is `isinstance(Solid)`, has a positive volume and is
    valid — all three, so it is taken AS-IS instead of being exploded per
    shell (which is what turned a hollow part into a filled one plus a phantom
    block inside it)."""
    import blocks

    solid = b3d.Solid.make_box(10, 10, 10)
    assert isinstance(solid, b3d.Solid)
    assert solid.volume > 0
    assert bool(solid.is_valid) is True
    # and the branch is reachable in the shipped source, not commented out
    src = Path(blocks.__file__).read_text(encoding="utf-8")
    assert "isinstance(shp, Solid) and shp.volume > 0 and shp.is_valid" in src
