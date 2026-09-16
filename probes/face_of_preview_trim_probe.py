"""Section 11 round three, PART B — the defect section 10's round two MEASURED
in toolplan._face_of but could not fix (toolplan.py is section 11's file).

THE CLAIM. A live face click carries the area of the mesh ON SCREEN. While
Fillet / Chamfer / Shell is open, that mesh is the tool's PREVIEW body, and a
face the preview has TRIMMED is no longer its original size — so since the
face-pick size gate landed (1a8d28f) the trimmed area is the identity
resolve_face uses on the INPUT body. Two pads whose tops are 200 mm2 and
180 mm2, and an r1 blend that leaves exactly 180 of the first, resolve to each
other; surface_gap ignores trimming on purpose and cannot tell, because both
tops are coplanar +Z.

    section 1  the silent wrong face  (coplanar pads)
    section 2  the false REFUSAL      (the same coincidence, pads at
                                       different heights)
    section 3  the fix, on both
    section 4  the whole gauntlet corpus: how many honest picks the new rule
               newly refuses, or newly answers differently  (must be 0)

Usage:  C:\\Python314\\python.exe probes/face_of_preview_trim_probe.py
"""
from __future__ import annotations

import contextlib
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import build123d as b3d  # noqa: E402

import blocks  # noqa: E402
import provenance  # noqa: E402
import toolplan  # noqa: E402
from tests.gauntlet import BODIES, planar_faces  # noqa: E402


def _round_pick(face):
    """A click as the browser makes it: studio rounds a face centre to 2
    decimals and a normal to 3, and the area is blocks.stored_area."""
    c = face.center()
    n = face.normal_at(c)
    return {"center": [round(float(c.X), 2), round(float(c.Y), 2),
                       round(float(c.Z), 2)],
            "normal": [round(float(n.X), 3), round(float(n.Y), 3),
                       round(float(n.Z), 3)],
            "area": blocks.stored_area(face)}


def _top_at(solid, x, tol=1.0):
    """the +Z face whose centre sits at x (the pad tops)."""
    best = None
    for f in solid.faces():
        try:
            c = f.center()
            n = f.normal_at(c)
        except Exception:
            continue
        if n.Z < 0.99:
            continue
        if abs(c.X - x) <= tol and (best is None or c.Z > best[1]):
            best = (f, c.Z)
    return best[0] if best else None


def _bracket(q_height: float):
    """base plate + pad P (top 20x10 = 200 mm2) + pad Q (top 20x9 = 180),
    50 mm apart. q_height sets pad Q's top Z."""
    base = b3d.Box(120, 40, 10, align=(b3d.Align.CENTER, b3d.Align.CENTER,
                                       b3d.Align.MIN))
    padp = b3d.Pos(-25, 0, 10) * b3d.Box(
        20, 10, 5, align=(b3d.Align.CENTER, b3d.Align.CENTER, b3d.Align.MIN))
    padq = b3d.Pos(25, 0, 10) * b3d.Box(
        20, 9, q_height, align=(b3d.Align.CENTER, b3d.Align.CENTER,
                                b3d.Align.MIN))
    return b3d.Part() + base + padp + padq


def _preview(body):
    """what the tool draws while the panel is open: an r1 blend on ONE top
    edge of pad P, which trims its top from 200 mm2 to exactly 180."""
    top = _top_at(body, -25)
    # the 20 mm edge of pad P's top that runs along X
    edge = max((e for e in top.edges()), key=lambda e: e.length
               if abs(e.center().Y) > 1e-6 else -1)
    return b3d.fillet(edge, 1.0)


def _resolved(part, pick, label):
    try:
        f = toolplan._face_of(part, pick, "body1")
    except ValueError as e:
        return None, f"REFUSED: {e}"
    c = f.center()
    return f, (f"{label}: centre ({c.X:.2f}, {c.Y:.2f}, {c.Z:.2f})  "
               f"area {blocks.area_of(f):.2f} mm2")


def section(n, title):
    print(f"\n=== {n}. {title}")


_FIX = toolplan._not_the_preview_trim


class fix_off:
    """run a block with the new rule taken back out, so every count below is
    a BEFORE / AFTER pair and not a claim."""

    def __enter__(self):
        toolplan._not_the_preview_trim = lambda part, face, p, nrm: face

    def __exit__(self, *a):
        toolplan._not_the_preview_trim = _FIX


def main() -> int:
    bad = 0

    # ---------------- 1. the silent wrong face -----------------------------
    section(1, "coplanar pads: the click lands on the pad 50 mm away")
    body = _bracket(5.0)                      # both tops at z = 15
    prev = _preview(body)
    p_in = _top_at(body, -25)
    q_in = _top_at(body, 25)
    print(f"   input  pad P top {blocks.area_of(p_in):8.2f} mm2 at "
          f"x={p_in.center().X:6.2f} z={p_in.center().Z:.2f}")
    print(f"   input  pad Q top {blocks.area_of(q_in):8.2f} mm2 at "
          f"x={q_in.center().X:6.2f} z={q_in.center().Z:.2f}")
    p_prev = _top_at(prev, -25)
    print(f"   PREVIEW pad P top {blocks.area_of(p_prev):7.2f} mm2 "
          f"(the blend trimmed it)")
    pick = _round_pick(p_prev)
    print(f"   the click: {pick}")
    face, why = _resolved(body, pick, "resolved on the INPUT body")
    print(f"   {why}")
    if face is not None and blocks._shape_key(face) == blocks._shape_key(q_in):
        print("   >>> WRONG FACE: pad Q, 50 mm away. plan_fillet would take "
              "every edge of it.")
        bad += 1
    elif face is not None and blocks._shape_key(face) == blocks._shape_key(p_in):
        print("   OK: pad P, the face the user clicked.")

    # what a sizeless resolve says (what this answered before 1a8d28f)
    old = blocks.resolve_face(body, pick["center"], pick["normal"], None)
    print(f"   sizeless resolve (pre-1a8d28f) -> "
          f"{'pad P' if blocks._shape_key(old) == blocks._shape_key(p_in) else 'pad Q'}")

    # ---------------- 2. the false refusal ---------------------------------
    section(2, "pads at DIFFERENT heights: the same coincidence refuses")
    body2 = _bracket(4.0)                     # pad Q top at z = 14
    prev2 = _preview(body2)
    p2 = _top_at(body2, -25)
    q2 = _top_at(body2, 25)
    print(f"   input  pad P top {blocks.area_of(p2):8.2f} mm2 z={p2.center().Z:.2f}")
    print(f"   input  pad Q top {blocks.area_of(q2):8.2f} mm2 z={q2.center().Z:.2f}")
    pick2 = _round_pick(_top_at(prev2, -25))
    face2, why2 = _resolved(body2, pick2, "resolved on the INPUT body")
    print(f"   {why2}")
    if face2 is None:
        print("   >>> FALSE REFUSAL: pad P's top is right there, unchanged.")
        bad += 1

    # ---------------- 3. what the fix has to answer ------------------------
    section(3, "what the answer has to be")
    print("   1: pad P's top (200.00 mm2, x=-25)   2: pad P's top (200.00, x=-25)")

    # ---------------- 4. the corpus: does the rule refuse anything ---------
    section(4, "the gauntlet corpus — honest picks, made ON the body itself")
    total = changed = refused = 0
    worst = 0.0
    for name, make in BODIES.items():
        solid = make()
        for idx, f, _c, _n in planar_faces(solid):
            pick = _round_pick(f)
            if pick["area"] is None:
                continue
            total += 1
            worst = max(worst, toolplan._centre_gap(f, tuple(pick["center"])))
            try:
                got = toolplan._face_of(solid, pick, name)
            except ValueError:
                refused += 1
                print(f"   {name}.f{idx}: REFUSED")
                continue
            if blocks._shape_key(got) != blocks._shape_key(f):
                changed += 1
                print(f"   {name}.f{idx}: answered a DIFFERENT face")
    print(f"   {total} planar picks: {refused} refused, {changed} answered "
          f"a different face than the one clicked")
    print(f"   worst gap between a clicked centre and its own face's centre: "
          f"{worst:.6f} mm  (_PICK_SLACK is {toolplan._PICK_SLACK})")

    # ...and the same picks through a PREVIEW-shaped click: the face's own
    # centre, its own normal, but an area 10 per cent small (a blend trim)
    section(5, "the same picks with a TRIMMED area (10 % off)")
    t_total = t_ref = t_changed = 0
    for name, make in BODIES.items():
        solid = make()
        for idx, f, _c, _n in planar_faces(solid):
            pick = _round_pick(f)
            if pick["area"] is None:
                continue
            pick["area"] = round(pick["area"] * 0.9, 2)
            t_total += 1
            try:
                got = toolplan._face_of(solid, pick, name)
            except ValueError:
                t_ref += 1
                continue
            if blocks._shape_key(got) != blocks._shape_key(f):
                t_changed += 1
                print(f"   {name}.f{idx}: a trimmed area moved the answer to "
                      f"another face")
    print(f"   {t_total} picks: {t_ref} refused, {t_changed} moved to another face")

    # --- 6. the documented TIE the size gate exists to decide ---------------
    section(6, "the tie: a flush pad in a round pocket (two centroids at one point)")
    pocket = b3d.Part() + b3d.extrude(b3d.Plane.XY * b3d.Circle(20), amount=10)
    pocket -= b3d.Pos(0, 0, 5) * b3d.extrude(b3d.Plane.XY * b3d.Circle(12),
                                             amount=5)
    pocket += b3d.Pos(0, 0, 5) * b3d.extrude(b3d.Plane.XY * b3d.Circle(6),
                                             amount=5)
    tops = [f for f in pocket.faces()
            if abs(f.center().Z - 10) < 1e-6
            and f.normal_at(f.center()).Z > 0.99]
    for f in sorted(tops, key=lambda f: blocks.area_of(f)):
        pick = _round_pick(f)
        got = toolplan._face_of(pocket, pick, "pocket")
        same = blocks._shape_key(got) == blocks._shape_key(f)
        c = f.center()
        print(f"   clicked {blocks.area_of(f):8.3f} mm2 at centroid "
              f"({c.X:.2f},{c.Y:.2f},{c.Z:.2f}) -> got {blocks.area_of(got):8.3f} "
              f"mm2  {'SAME' if same else '*** SWITCHED ***'}")
        if not same:
            bad += 1

    # --- 7. every face of a REAL preview body, before and after ------------
    section(7, "a real preview (fillet r0.8 on every edge): the SAME answer?")
    same = moved = newly_ok = newly_ref = 0
    for name, make in BODIES.items():
        solid = make()
        try:
            prev = b3d.fillet(solid.edges(), 0.8)
        except Exception:
            continue
        for f in prev.faces():
            try:
                c = f.center()
                n = f.normal_at(c)
            except Exception:
                continue
            pick = {"center": [round(float(c.X), 2), round(float(c.Y), 2),
                               round(float(c.Z), 2)],
                    "normal": [round(float(n.X), 3), round(float(n.Y), 3),
                               round(float(n.Z), 3)],
                    "area": blocks.stored_area(f)}
            with fix_off():
                try:
                    before = blocks._shape_key(toolplan._face_of(solid, pick, name))
                except ValueError:
                    before = None
            try:
                after = blocks._shape_key(toolplan._face_of(solid, pick, name))
            except ValueError:
                after = None
            if before == after:
                same += 1
            elif before is None:
                newly_ok += 1
            elif after is None:
                newly_ref += 1
                print(f"   {name}: a click the old rule ACCEPTED is now refused")
            else:
                moved += 1
    print(f"   {same + moved + newly_ok + newly_ref} clicks on preview faces: "
          f"{same} unchanged, {moved} moved to another face, "
          f"{newly_ok} refusals turned into a face, {newly_ref} NEWLY REFUSED")

    section(8, "OnFace on faces whose CENTROID is off their own material")
    ring = b3d.Part() + b3d.extrude(b3d.Plane.XY * (b3d.Circle(20) - b3d.Circle(8)),
                                    amount=5)
    top = _top_at(ring, 0)
    c = top.center()
    on = provenance.OnFace(top.wrapped)
    print(f"   annulus top: centroid ({c.X:.2f}, {c.Y:.2f}, {c.Z:.2f}), "
          f"OnFace(centroid) = {on(float(c.X), float(c.Y), float(c.Z))}")
    print("   -> OnFace(centre) can NEVER be a mandatory gate: it refuses "
          "every annulus and U-shape (surface_gap's docstring says so).")

    # --- 9. the cost (section 8 round four's lesson) ------------------------
    section(9, "what the new rule costs per click")
    heavy = BODIES["clipped_ball"]()
    picks = [_round_pick(f) for _i, f, _c, _n in planar_faces(heavy)]
    picks = [p for p in picks if p["area"] is not None]
    for label, ctx in (("without", fix_off()), ("with   ", contextlib.nullcontext())):
        with ctx:
            t0 = time.perf_counter()
            for _ in range(20):
                for p in picks:
                    toolplan._face_of(heavy, p, "clipped_ball")
            n = 20 * len(picks)
            print(f"   {label} the rule: {1e6 * (time.perf_counter() - t0) / n:8.1f} "
                  f"us per click ({n} clicks)")

    print(f"\n{bad} defect(s) reproduced")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
