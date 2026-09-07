"""The two follow-ups found while fixing the big P4 review's P0s, each
reproduced before it is fixed (house rule 3: never trust, always measure).

Run: PYTHONIOENCODING=utf-8 python probes/pattern_barrier_probe.py

  §1  `pattern.delta` subtracts OUTSIDE any barrier and `_seed` calls it at the
      op's top level, so an OCCT failure there escapes as a RAW kernel
      exception. `document.rebuild` catches it as `repr(e)` — the banned
      "kernel exception reaches the user" mode (textcad-dev rule 5).
  §2  A pattern's AXIS click resolves against the pre-pattern body with
      `sk.pick_face`'s unbounded nearest-centre match, so a click on a COPY's
      bore wall silently comes back as some other face and the pattern
      re-aims. §3 measures why Mirror's plane rule cannot be reused and what
      bound works instead.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import build123d as b3d

import document
import pattern
import sketch as sk
import toolplan


def line(t):
    print(f"\n{'-' * 70}\n{t}\n{'-' * 70}")


class KernelBoom(Exception):
    """what OCP raises: an Exception, NOT a RuntimeError — an
    `except RuntimeError` barrier does not catch it"""


class Boom:
    """a shape whose boolean fails in the kernel"""

    def __sub__(self, other):
        raise KernelBoom("StdFail_NotDone: BRepAlgoAPI_Cut::Build() failed")


# --------------------------------------------------------------- §1 --------
line("§1  a kernel failure in the seed's delta escapes RAW")

escaped = False

for what, call in (("pattern.delta(before, after)", lambda: pattern.delta(Boom(), Boom())),
                   ("pattern.mirror(seed=...)",
                    lambda: pattern.mirror(b3d.Box(40, 40, 10), "YZ", seed="h",
                                           _before=Boom(), _after=Boom())),
                   ("pattern.polar_pattern(seed=...)",
                    lambda: pattern.polar_pattern(b3d.Box(40, 40, 10), 3, axis="+z", seed="h",
                                                  _before=Boom(), _after=Boom()))):
    try:
        call()
        print(f"  {what:34} -> returned (no failure)")
    except ValueError as e:
        print(f"  {what:34} -> a SENTENCE: {e}")
    except Exception as e:                       # noqa: BLE001 - that is the finding
        escaped = True
        print(f"  {what:34} -> RAW {type(e).__name__}: {e}")
        print(f"  {'':34}    the tree would show: {repr(e)[:60]}")

if escaped:
    print("\nVERDICT: BROKEN — a kernel exception reached the caller, and "
          "document.rebuild\n         stores it as repr(e): gibberish in the "
          "tree instead of a sentence")
else:
    print("\nVERDICT: fixed — every kernel failure in the seed's delta comes "
          "back as a sentence\n         that names the op and the seed")

# --------------------------------------------------------------- §2 --------
line("§2  a pattern's axis click resolves against the PRE-pattern body")

doc = document.Document("t")
doc.add("box1", "plate", {"width": 80, "depth": 80, "thickness": 12})
doc.add("hole1", "hole", {"face": "top", "at": [-25, 0], "diameter": 6,
                          "through": True, "depth": 1}, inputs=["box1"])
doc.add("pat", "polar_pattern", {"seed": "hole1", "count": 3,
                                 "axis": {"face": "top"}}, inputs=["hole1"])
doc.rebuild()

part, shown = doc._parts["hole1"], doc._parts["pat"]      # the plan's body vs the screen's
bores = sorted((f for f in shown.faces() if f.geom_type == b3d.GeomType.CYLINDER),
               key=lambda f: (f.center().X, f.center().Y))
copy_bore = bores[-1]                                     # a wall only a COPY has
c = copy_bore.center()
print(f"the body the plan resolves against has {len([f for f in part.faces() if f.geom_type == b3d.GeomType.CYLINDER])} bore(s); "
      f"the screen shows {len(bores)}")
print(f"clicking the LAST copy's wall, centre = ({c.X:.2f}, {c.Y:.2f}, {c.Z:.2f})")

pick = {"center": [round(c.X, 2), round(c.Y, 2), round(c.Z, 2)],
        "normal": [round(v, 3) for v in copy_bore.normal_at(c)]}
got = sk.pick_face(part, pick["center"], pick["normal"])
gc = got.center()
print(f"  sk.pick_face returned a {got.geom_type.name} at "
      f"({gc.X:.2f}, {gc.Y:.2f}, {gc.Z:.2f}) — {(gc - c).length:.1f} mm away")
o, d, words = pattern.axis_of(part, pattern.stored_face(part, got))
print(f"  so the stored axis would be: {words}, through "
      f"({o.X:.2f}, {o.Y:.2f}, {o.Z:.2f})")

plan = toolplan.plan(doc, {"tool": "polar_pattern", "feature_id": "pat",
                           "axis_pick": pick})
print(f"  plan ok={plan.get('ok')}  axis_words={plan.get('axis_words')!r}")
if plan.get("ok"):
    print("VERDICT: BROKEN — a click on a copy's wall was accepted and re-aimed "
          "the pattern")
else:
    print(f"VERDICT: fixed — refused: {plan.get('error')}")

# --------------------------------------------------------------- §3 --------
line("§3  why the mirror plane's rule cannot be reused, and what bound can")


def top_face(p):
    fs = [f for f in p.faces() if f.geom_type == b3d.GeomType.PLANE
          and abs(f.normal_at(f.center()).Z - 1) < 1e-6]
    return max(fs, key=lambda f: f.center().Z)


a, b = top_face(part).center(), top_face(shown).center()
print(f"the SAME top face, before the pattern: ({a.X:.4f}, {a.Y:.4f}, {a.Z:.4f})")
print(f"                    after it punched 2 more holes: ({b.X:.4f}, {b.Y:.4f}, {b.Z:.4f})")
print(f"  the centroid MOVED {(b - a).length:.4f} mm, so an exact centre match "
      f"would refuse a legal click")
print("  and a flat face's axis is its normal THROUGH ITS CENTRE, so the plane "
      "test does not transfer")

print("\nthe bound that does work — the clicked centre lies inside the resolved "
      "face's own bounding box:")
for name, clicked, target in (("the shared top face", b, top_face(part)),
                              ("a copy's bore wall", c, sk.pick_face(part, pick["center"],
                                                                     pick["normal"])),
                              ("a click 200 mm away", b3d.Vector(200, 0, 0),
                               top_face(part))):
    bb = target.bounding_box()
    tol = 0.05
    inside = all(lo - tol <= v <= hi + tol for v, lo, hi in
                 ((clicked.X, bb.min.X, bb.max.X), (clicked.Y, bb.min.Y, bb.max.Y),
                  (clicked.Z, bb.min.Z, bb.max.Z)))
    print(f"  {name:22} -> {'INSIDE (accept)' if inside else 'outside (refuse)'}")
