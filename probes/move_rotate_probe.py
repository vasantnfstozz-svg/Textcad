"""Move / Rotate probe (LAUNCH-PLAN.md P4, specs/move-rotate.md) — 2026-09-11.

What the kernel does, measured, before the tool is written:

  1. Part.rotate(Axis(pivot, dir), deg) turns about THAT pivot: a plate at
     x=100 turned about its own bounding-box centre stays at x=100; about
     Axis.Z (the world origin — the legacy op) it lands at y=90..110.
  2. The sign is the right-hand rule on every axis: about Z, +X -> +Y;
     about X, +Y -> +Z; about Y, +Z -> +X. The ring's frame must be
     (X, Y) for Z, (Y, Z) for X, (Z, X) for Y so its positive turn is the
     kernel's.
  3. bounding_box().center() is the pivot Fusion uses by default; it is
     exact on a box, a cylinder and a sphere (optimal=True, the default).
  4. A pivoted turn of a sphere keeps its centre, its volume and its health.
  5. Pos(dx, dy, dz) * part moves the bounding-box centre by exactly that.
  6. float('abc') raises with Python wording — `move` must translate it.

Run: PYTHONIOENCODING=utf-8 C:/Python314/python.exe probes/move_rotate_probe.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import build123d as b3d                                    # noqa: E402
from build123d import Axis, Pos                            # noqa: E402

import blocks                                              # noqa: E402
import inspector                                           # noqa: E402


def c(shape):
    v = shape.bounding_box().center()
    return round(v.X, 6), round(v.Y, 6), round(v.Z, 6)


plate = Pos(100, 0, 0) * b3d.Box(20, 40, 10)
print("1. plate at x=100, centre", c(plate))
print("   about its centre, Z +90 ->", c(plate.rotate(Axis(plate.bounding_box().center(), (0, 0, 1)), 90)))
print("   about the world Z (legacy) ->", c(blocks.rotate(plate, "Z", 90)))

dot = b3d.Box(2, 2, 2)
print("2. +90 about Z of +X:", c((Pos(100, 0, 0) * dot).rotate(Axis.Z, 90)))
print("   +90 about X of +Y:", c((Pos(0, 100, 0) * dot).rotate(Axis.X, 90)))
print("   +90 about Y of +Z:", c((Pos(0, 0, 100) * dot).rotate(Axis.Y, 90)))

cyl = Pos(30, 0, 0) * b3d.Cylinder(10, 20)
sph = Pos(5, 5, 5) * b3d.Sphere(7)
print("3. centres: cylinder", c(cyl), "sphere", c(sph))

out = sph.rotate(Axis(sph.bounding_box().center(), (1, 0, 0)), 37)
print("4. sphere turned 37 about X through its centre:", c(out),
      "volume", round(out.volume, 6), "==", round(sph.volume, 6), "health", inspector.health(out))

print("5. plate moved by (-3.5, 2, 1):", c(Pos(-3.5, 2, 1) * plate))

try:
    float("abc")
except ValueError as e:
    print("6. float('abc'):", e)
