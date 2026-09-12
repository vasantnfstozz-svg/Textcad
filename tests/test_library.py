"""The user's LIVE designs/ library (LAUNCH-PLAN.md R6 and P5b). Opt-in:

    python -m pytest tests -m library -q

Code tests read frozen fixtures; this tier is the one check that protects
the user's real parts, so it runs before every ship. Every committed design
must open and rebuild without a kernel exception, its file must round-trip,
every GREEN body on screen must be sound, and every live feature must be
green. A red feature is reported with its own sentence, never hidden: a red
row here is news about the design, and the design is the user's.

Designs are read with Document.from_data — never /api/open, which mints a
version into the real .history/ as a side effect."""
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.library

DESIGNS = sorted((Path(__file__).resolve().parents[1] / "designs").glob("*.tcad.json"))


def _name(path: Path) -> str:
    return path.name[:-len(".tcad.json")]


@pytest.fixture(scope="module")
def built():
    """Each design rebuilt ONCE for the module (esp32-remote costs ~45 s)."""
    cache: dict = {}

    def get(path: Path):
        if path not in cache:
            from document import Document
            doc = Document.from_data(json.loads(path.read_text(encoding="utf-8")))
            doc.rebuild()            # a kernel exception here would reach the user on open
            cache[path] = doc
        return cache[path]
    return get


@pytest.mark.parametrize("path", DESIGNS, ids=_name)
def test_opens_round_trips_and_every_green_body_is_sound(path, built):
    import inspector
    from document import Document
    doc = built(path)
    assert Document.from_data(doc.to_data()).to_data() == doc.to_data(), "file round-trip"
    for fid in doc.leaf_solid_ids():
        f = doc.get(fid)
        if f.status != "ok" or f.suppressed:
            continue
        part = doc._parts.get(fid)
        assert part is not None, f"'{fid}' ({f.op}) is green but has no shape"
        problems = inspector.health(part)
        assert not problems, f"'{fid}' ({f.op}) is green but: " + "; ".join(problems)
    for f in doc.features:
        if f.status == "failed" and not f.suppressed:
            assert f.problems, f"'{f.id}' ({f.op}) is red with no problem text"


@pytest.mark.parametrize("path", DESIGNS, ids=_name)
def test_every_live_feature_is_green(path, built):
    doc = built(path)
    reds = [f"'{f.id}' ({f.op}): " + ("; ".join(f.problems) or "no problem text")
            for f in doc.features if not f.suppressed and f.status != "ok"]
    assert not reds, f"{_name(path)} has red features: " + " | ".join(reds)
