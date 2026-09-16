"""Section 12 ROUND TWO — what /api/export now decides for each LIVE design.

Round one keyed the export file (and its new clash guard) off doc.NAME.
A design opened from the library is bound to its FILE, and four of the 50
designs carry a name that does not slug to their own file stem. This measures,
for every saved design, opened exactly as /api/open opens it:

  * the export path round one's rule produces, vs the design's own file stem;
  * whether _name_clash REFUSES that export.

Nothing is written: the decision is read from _design_slug / _name_clash
directly, so no kernel call and no file in designs/ is touched.

Run: C:\\Python314\\python.exe probes/section12_round2_export_probe.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("TEXTCAD_HISTORY_ROOT",
                      tempfile.mkdtemp(prefix="s12r2-hist-"))

import studio                                            # noqa: E402
from document import Document                            # noqa: E402

DESIGNS = ROOT / "designs"


def main():
    print("=" * 74)
    print("Every saved design, opened from the library, asked to EXPORT")
    print("=" * 74)
    refused, moved = [], []
    for p in sorted(DESIGNS.glob("*.tcad.json")):
        stem = p.name[:-len(".tcad.json")]
        data = json.loads(p.read_text(encoding="utf-8"))
        studio.STATE["docs"], studio.STATE["active"] = {}, None
        studio.STATE["seq"] = 0
        doc = Document.from_data(data)
        studio._new_tab(doc, source=f"file:{stem}")       # exactly /api/open
        slug = studio._design_slug(doc.name)
        clash = studio._name_clash(slug, "exporting")
        if clash:
            refused.append((stem, doc.name, slug, clash))
        elif slug != stem:
            moved.append((stem, doc.name, slug))

    print(f"\nEXPORT REFUSED on {len(refused)} of the user's own designs:")
    for stem, name, slug, why in refused:
        print(f"  designs/{stem}.tcad.json (name {name!r})")
        print(f"     -> export would write designs/{slug}.step")
        print(f"     -> REFUSED: {why}")
    print(f"\nEXPORT PATH MOVED off its own file stem on {len(moved)}:")
    for stem, name, slug in moved:
        print(f"  designs/{stem}.tcad.json (name {name!r})"
              f" -> designs/{slug}.step  (expected designs/{stem}.step)")

    # The fix under test: a bound tab exports under the FILE it is bound to.
    print("\n" + "-" * 74)
    print("With the export keyed off the BOUND FILE instead of the name:")
    still_refused, still_moved = [], []
    for p in sorted(DESIGNS.glob("*.tcad.json")):
        stem = p.name[:-len(".tcad.json")]
        data = json.loads(p.read_text(encoding="utf-8"))
        studio.STATE["docs"], studio.STATE["active"] = {}, None
        studio.STATE["seq"] = 0
        doc = Document.from_data(data)
        studio._new_tab(doc, source=f"file:{stem}")
        slug = studio._slug_of_active() or studio._design_slug(doc.name)
        clash = studio._name_clash(slug, "exporting")
        if clash:
            still_refused.append((stem, clash))
        elif slug != stem:
            still_moved.append((stem, slug))
    print(f"  refused: {len(still_refused)} {still_refused}")
    print(f"  moved  : {len(still_moved)} {still_moved}")


if __name__ == "__main__":
    main()
