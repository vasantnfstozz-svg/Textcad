import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))       # tests/gauntlet.py

import pytest


@pytest.fixture(autouse=True)
def _isolate_version_histories(tmp_path, monkeypatch):
    """No test may write a version history into the user's designs/ library.

    Autouse because the pollution would be SILENT: since VERSION-TREE-PLAN.md
    P2, /api/open mints a version as a side effect, so a test that merely opens
    flange-100 creates designs/flange-100.history/ — inside tracked user work.
    Every test gets its own throwaway root instead."""
    monkeypatch.setenv("TEXTCAD_HISTORY_ROOT", str(tmp_path / "histories"))
