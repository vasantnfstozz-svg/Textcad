"""WHICH ops carry their input's translation, and which PLACE geometry in the
world?  `Document._carry_face_picks` assumes every op does the first.

For each modifier: build the same design with move.x = 30 and with move.x = 36
and ask whether the op's OUTPUT simply moved +6 in x (every face centre) —
that, and only that, is what makes the move's delta the right thing to add to
a pick stored downstream of it."""
import sys

sys.path.insert(0, ".")
from document import Document                     # noqa: E402

D = 6.0


def build(op, params, move_x):
    doc = Document(name="t-commute")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 60, "h": 30}]})
    doc.add("base", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("boss_sk", "sketch", {"plane": "XY", "offset": 10, "entities": [
        {"kind": "rectangle", "w": 12, "h": 12, "x": 15, "y": 0}]})
    doc.add("boss", "extrude", {"amount": 5}, inputs=["boss_sk"])
    doc.add("part", "fuse", {}, inputs=["base", "boss"])
    doc.add("placed", "move", {"x": move_x, "y": 0, "z": 0}, inputs=["part"])
    if op:
        doc.add("flip", op, dict(params), inputs=["placed"])
    doc._cache = {}
    if not doc.rebuild():
        return None, doc.tree()
    return doc._parts["flip" if op else "placed"], None


def centres(part):
    return sorted((round(c.X, 6), round(c.Y, 6), round(c.Z, 6))
                  for c in (f.center() for f in part.faces()))


CASES = [
    ("(no op — the move itself)", None, {}),
    ("rotate axis=Z 90 (default world-origin pivot)", "rotate",
     {"axis": "Z", "angle_deg": 90}),
    ("rotate axis=Z 90 pivot=center (what the tool sends)", "rotate",
     {"axis": "Z", "angle_deg": 90, "pivot": "center"}),
    ("mirror plane=YZ (legacy copy)", "mirror", {"plane": "YZ"}),
    ("mirror plane=YZ join=True", "mirror", {"plane": "YZ", "join": True}),
    ("scale 2x", "scale", {"factor": 2}),
    ("linear_pattern count=3 dx=25", "linear_pattern",
     {"count": 3, "dx": 25}),
    ("polar_pattern count=4 axis=Z", "polar_pattern",
     {"count": 4, "axis": "Z"}),
    ("fillet r=2 edges=all", "fillet", {"radius": 2, "edges": "all"}),
    ("shell t=2 faces=top", "shell", {"thickness": 2, "faces": "top"}),
]

print(f"{'op':<52} {'output translates by the move delta?'}")
print("-" * 92)
for label, op, params in CASES:
    a, err = build(op, params, 30.0)
    if a is None:
        print(f"{label:<52} build failed: {str(err)[:30]}")
        continue
    b, err = build(op, params, 30.0 + D)
    if b is None:
        print(f"{label:<52} build failed: {str(err)[:30]}")
        continue
    ca, cb = centres(a), centres(b)
    if len(ca) != len(cb):
        print(f"{label:<52} NO  (face count {len(ca)} -> {len(cb)})")
        continue
    shifted = sorted((round(x + D, 6), y, z) for x, y, z in ca)
    worst = max((abs(p[0] - q[0]) + abs(p[1] - q[1]) + abs(p[2] - q[2]))
                for p, q in zip(shifted, cb))
    print(f"{label:<52} {'YES' if worst < 1e-6 else 'NO '}"
          f"   (worst face-centre error {worst:.4f} mm)")


# ---- the two the first table could not build, and the SEEDED pattern forms ---

def build2(steps, move_x):
    doc = Document(name="t-commute2")
    doc.add("outline", "sketch", {"plane": "XY", "entities": [
        {"kind": "rectangle", "w": 60, "h": 30}]})
    doc.add("base", "extrude", {"amount": 10}, inputs=["outline"])
    doc.add("hole1", "hole", {"face": "top", "at": [-20, 0], "diameter": 6,
                              "depth": 4}, inputs=["base"])
    doc.add("placed", "move", {"x": move_x, "y": 0, "z": 0}, inputs=["hole1"])
    last = "placed"
    for i, (op, params) in enumerate(steps):
        doc.add(f"s{i}", op, dict(params), inputs=[last])
        last = f"s{i}"
    doc._cache = {}
    if not doc.rebuild():
        return None, doc.tree()
    return doc._parts[last], None


MORE = [
    ("polar_pattern count=2 angle=90 (world Z, legacy)",
     [("polar_pattern", {"count": 2, "angle": 90})]),
    ("linear_pattern SEEDED on hole1", [("linear_pattern",
     {"count": 3, "dx": 12, "seed": "hole1"})]),
    ("polar_pattern SEEDED on hole1", [("polar_pattern",
     {"count": 3, "angle": 90, "seed": "hole1"})]),
    ("mirror SEEDED on hole1", [("mirror", {"plane": "YZ", "seed": "hole1"})]),
]
print()
for label, steps in MORE:
    a, err = build2(steps, 30.0)
    if a is None:
        print(f"{label:<52} build failed: {' '.join(str(err).split())[:60]}")
        continue
    b, err = build2(steps, 30.0 + D)
    if b is None:
        print(f"{label:<52} build failed: {' '.join(str(err).split())[:60]}")
        continue
    ca, cb = centres(a), centres(b)
    if len(ca) != len(cb):
        print(f"{label:<52} NO  (face count {len(ca)} -> {len(cb)})")
        continue
    shifted = sorted((round(x + D, 6), y, z) for x, y, z in ca)
    worst = max((abs(p[0] - q[0]) + abs(p[1] - q[1]) + abs(p[2] - q[2]))
                for p, q in zip(shifted, cb))
    print(f"{label:<52} {'YES' if worst < 1e-6 else 'NO '}"
          f"   (worst face-centre error {worst:.4f} mm)")
