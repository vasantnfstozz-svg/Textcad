"""The two viewport rules of REVIEW-QUEUE section 10 that a grep can hold.

Neither can be tested through the kernel, because both are decisions the
BROWSER makes about a payload the server already got right. So each test comes
in two halves: what the server actually says (measured through build123d), and
the one line of `static/js/viewport.js` that has to agree with it.

1. FLAT IS `planar`, NOT THE SURFACE TYPE. A taper / loft / sweep wall is dead
   flat and OCCT stores it as BSPLINE, and `sketch_on_face` takes it. The
   plane picker (the Sketch ribbon button) tested `info.type === 'PLANE'` and
   refused all four walls of a tapered box as "bspline, not flat", while the
   pick panel's own "Sketch on this face" button on the SAME face worked.

2. THE FEATURE OVERLAY'S FRESHNESS GUARD IS ITS OWN, NOT THE TREE'S SELECTION.
   `showFeatureOverlay` returned early unless `S.selected` equalled the id it
   was given, and only tree.js ever sets `S.selected` — so the provenance
   panel's "Created by" links fetched a highlight and dropped it on the floor.
"""
import re
from pathlib import Path

import sketch as sk
import studio
from document import Document

VIEWPORT = (Path(__file__).resolve().parents[1]
            / "static" / "js" / "viewport.js").read_text(encoding="utf-8")


def tapered_body():
    """A 12-degree tapered extrude: four dead-flat walls the kernel types
    BSPLINE, and two real PLANEs."""
    doc = Document(name="t-taper-pick")
    doc.add("prof", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 40, "h": 30, "x": 0, "y": 0}]})
    doc.add("body", "extrude", {"amount": 20, "taper": 12}, inputs=["prof"])
    assert doc.rebuild(), doc.tree()
    return doc.result()


# ------------------------------------------------ 1. flat is not a type ------

def test_a_tapered_wall_is_flat_and_sketchable_but_not_typed_plane():
    part = tapered_body()
    odd = [f for f in part.faces()
           if str(f.geom_type).split(".")[-1] != "PLANE"
           and sk.face_plane(f) is not None]
    assert len(odd) == 4, [str(f.geom_type) for f in part.faces()]
    payload = studio._tagged_mesh(part, body_id="body")
    for info in payload["faces"]:
        if info["type"] != "PLANE":
            assert info["planar"] is True, info      # the server says FLAT
    # ...and the server will really put a sketch on one
    face = odd[0]
    c = face.center()
    out = sk.face_outline_2d(part, [c.X, c.Y, c.Z], list(face.normal_at(c)),
                             face_area=round(face.area, 2))
    assert out["planar"] and len(out["outer"]) > 3, out.get("error")


def test_the_viewport_decides_flat_in_exactly_one_place():
    """One rule, one line: `isFlatFace`. A second `type === 'PLANE'` anywhere
    in the file is a picker that has gone back to reading the surface type."""
    assert len(re.findall(r"type === 'PLANE'", VIEWPORT)) == 1, \
        "a picker is deciding FLAT from the surface type again"
    assert "isFlatFace" in VIEWPORT
    # the plane picker and its hover are the two that had it wrong
    for fn in ("function planePickAt", "function planePickHover"):
        body = VIEWPORT.split(fn, 1)[1].split("\n}\n", 1)[0]
        assert "isFlatFace" in body, f"{fn} does not use the shared flat rule"


# ------------------------------- 2. the overlay's own freshness sequence ------

def _fn_body(name):
    return VIEWPORT.split(name, 1)[1].split("\n}\n", 1)[0]


def test_the_feature_overlay_does_not_ask_the_tree_who_is_selected():
    body = _fn_body("export async function showFeatureOverlay")
    assert "S.selected" not in body, \
        "showFeatureOverlay drops an overlay nobody selected in the tree"
    assert body.count("overlaySeq") >= 2, "no freshness guard of its own"
    assert "overlaySeq++" in _fn_body("export function clearHighlight")
