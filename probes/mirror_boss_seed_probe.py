"""Probe (2026-09-07, the deferred Mirror findings): what does `_repeat` say when a
BOSS's mirror image adds nothing?

Two ways a fused image can add exactly 0.0:
  §1 the plane runs THROUGH the boss (the body's mid-plane, boss centred on it)
     -> the image IS the boss: "is the seed itself" is the true remedy
  §2 the plane is the boss's own base face -> the image hangs down INSIDE the
     body: "adds nothing (it lies inside the body)" is the true remedy
Before the fix both said §2's sentence. The cut branch already told them apart
by image ∩ seed; this probe measures that the same discriminator holds for a
fuse, so the added branch can use it.

Run: set PYTHONIOENCODING=utf-8 & C:\\Python314\\python.exe probes\\mirror_boss_seed_probe.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build123d as b3d
from build123d import Cylinder, Pos

import pattern


def body_and_boss(bx=0.0):
    b = b3d.Box(80, 80, 12)                        # top at z = 6
    boss = Cylinder(5, 6).moved(Pos(bx, 20, 9))    # a ⌀10 x 6 boss standing on the top
    return b, b + boss


def section(title, plane, bx=0.0):
    b, after = body_and_boss(bx)
    removed, added = pattern.delta(b, after)
    pl, words = pattern.plane_of(after, plane)
    image = added.mirror(pl)
    v0 = float(after.volume)
    fused = after + image
    dv = float(fused.volume) - v0
    print(f"\n{title}: plane = {words}")
    print(f"  fuse adds {dv:.3e} mm3; image ∩ seed overlaps = {pattern._overlaps(image, added)}")
    try:
        pattern.mirror(after, plane, seed="boss1", _before=b, _after=after)
        print("  op: BUILT (no refusal)")
    except ValueError as e:
        print(f"  op says: {e}")


section("§1 plane THROUGH the boss (mid-plane across X, boss on x = 0)", {"mid": "X"})
section("§2 plane = the boss's base face (the top): image inside the body",
        {"face_center": [0.0, 0.0, 6.0], "face_normal": [0.0, 0.0, 1.0]})
section("§3 control: boss OFF the mid-plane (x = 15) builds a second boss", {"mid": "X"}, bx=15.0)
