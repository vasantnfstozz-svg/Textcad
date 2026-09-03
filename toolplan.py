"""toolplan.py — ONE geometry authority for the design tools (LAUNCH-PLAN.md R1).

Given a tool and its input, answer everything the browser needs to draw the
tool's handles, so it draws what it is told and computes nothing:

    axis          world direction a POSITIVE value moves material (unflipped)
    origin        where the drag arrow sits — the profile's centre, on its plane
    frame         the profile's 2D frame {origin, x_dir, y_dir, z_dir} (ghost);
                  its z_dir IS the axis, so a ghost depth is simply the amount
    loops         the profile's outline in that frame: [{outer, holes}, ...]
    into_sign     which SIGN of the value goes INTO the material (face sketches
                  and face picks; None for a free-standing plane sketch)
    limits        outer_radius (the taper ring), has_holes, max_taper (89: a
                  wall cannot lean past flat), apex_fraction (0.999: the kernel
                  refuses the exact tip), and — only with measure_collapse —
                  collapse: per face, how far the walls move inward before they
                  MEET (kernel-measured, sketch.collapse_offset; a narrowing
                  taper ends that face at apex_fraction * collapse / tan(angle))
    target_body   the body a Join / Cut targets by default
    will_build    one sentence: which op, on what, along which way

Why this exists: extrude.js carried a hand copy of build123d's plane frames and
a JS re-implementation of sketch.face_sketch_plane(); the arrow, the ghost and
the solid each had their own opinion of "which way" and disagreed on exactly
half the faces of a box (user, 2026-09-01). Two homes for one fact always
drift. From here on, if the UI needs a geometric fact, it is a field of the
plan — never a calculation in JS.

Pure functions over a Document; no HTTP, no state. plan() never raises: every
failure comes back as {"ok": False, "error": "<what to change>"}.
"""
from __future__ import annotations

import math

import build123d as b3d
from build123d import Plane

import sketch as sk

_AXIS_NAMES = {(0, 0, 1): "+Z", (0, 0, -1): "-Z", (1, 0, 0): "+X",
               (-1, 0, 0): "-X", (0, 1, 0): "+Y", (0, -1, 0): "-Y"}


# ------------------------------------------------------------------ helpers ---

def _vec(v) -> list[float]:
    return [round(float(v.X), 4), round(float(v.Y), 4), round(float(v.Z), 4)]


def _frame(pl: Plane) -> dict:
    return {"origin": _vec(pl.origin), "x_dir": _vec(pl.x_dir),
            "y_dir": _vec(pl.y_dir), "z_dir": _vec(pl.z_dir)}


def _axis_name(axis: list[float]) -> str:
    key = tuple(int(round(a)) for a in axis)
    if key in _AXIS_NAMES and all(abs(a - round(a)) < 1e-3 for a in axis):
        return _AXIS_NAMES[key]
    return "(" + ", ".join(f"{a:.3f}" for a in axis) + ")"


def _project_wire(wire, pl: Plane) -> list[list[float]]:
    """Sample a closed wire into the plane's local 2D as a polygon WITHOUT
    duplicate points: each edge contributes its start and interior samples,
    the next edge supplies the end. (Repeating the seam point biased a
    circle's centroid by r/n — 0.2 mm on an r5 circle — the same trap the
    sketcher's ringCentroid() had to work around.)"""
    poly = []
    for e in wire.edges():
        steps = 2 if e.geom_type == b3d.GeomType.LINE else 24
        for i in range(steps):
            loc = pl.to_local_coords(e @ (i / steps))
            poly.append([round(loc.X, 3), round(loc.Y, 3)])
    return poly


def _loops(faces, pl: Plane) -> list[dict]:
    """Every face's outer boundary plus its holes, in the plane's frame."""
    loops = []
    for f in faces:
        outer = f.outer_wire()
        holes = [_project_wire(w, pl) for w in f.wires()
                 if w.length != outer.length]
        loops.append({"outer": _project_wire(outer, pl), "holes": holes})
    return loops


def _limits(loops: list[dict]) -> tuple[dict, tuple[float, float] | None]:
    """The gizmo sizes and the centre of all outer points: outer_radius = the
    farthest boundary point from the common centre (the taper ring's size),
    has_holes, plus the two taper constants the UI must not own itself
    (LAUNCH-PLAN.md R1): max_taper (a wall cannot lean past flat) and
    apex_fraction (the kernel refuses the exact tip). Where the walls MEET is
    a kernel measurement — see _collapse(), asked for lazily."""
    cx = cy = 0.0
    n = 0
    for L in loops:
        pts = L["outer"]
        if len(pts) < 3:
            continue
        for p in pts:
            cx += p[0]
            cy += p[1]
            n += 1
    base = {"has_holes": any(L["holes"] for L in loops),
            "max_taper": sk.MAX_TAPER_DEG, "apex_fraction": sk.APEX_FRACTION}
    if not n:
        return ({**base, "outer_radius": 0.0}, None)
    cx /= n
    cy /= n
    outer_r = max(math.hypot(p[0] - cx, p[1] - cy) for L in loops for p in L["outer"])
    return ({**base, "outer_radius": round(outer_r, 4)}, (cx, cy))


def _collapse(faces, req: dict) -> list | None:
    """Per face, how far the outline can move inward before the walls meet —
    sketch.collapse_offset, the SAME measurement the build uses (None where it
    cannot be measured). 18 kernel offsets per face, so only when asked
    (`measure_collapse`): the tool fetches it the first time a taper needs it,
    not on every open (a 64-face plate took 1.9 s per plan — review 2026-09-03)."""
    if not req.get("measure_collapse"):
        return None
    out = []
    for f in faces:
        r = sk.collapse_offset(f)
        out.append(round(r, 4) if r is not None else None)
    return out


def _world(pl: Plane, cx: float, cy: float) -> list[float]:
    return _vec(pl.origin + pl.x_dir * cx + pl.y_dir * cy)


def _feature(doc, fid):
    return next((f for f in doc.features if f.id == fid), None)


def _solids(doc) -> list:
    """Features that ARE a solid right now (a built volume, not struck out),
    in tree order — the bodies a Join / Cut can target."""
    return [f for f in doc.features if f.volume is not None and not f.suppressed]


def _latest_descendant(doc, fid: str) -> str:
    """The body a solid feature has BECOME: follow solid-producing consumers down
    the tree (a cut / fillet / pattern of X is the current state of X)."""
    cur = fid
    while True:
        nxt = next((f for f in reversed(doc.features)
                    if f.volume is not None and not f.suppressed
                    and cur in (f.inputs or [])), None)
        if nxt is None:
            return cur
        cur = nxt.id


def _default_target(doc, profile_id: str) -> str | None:
    """Fusion parity: Join / Cut applies to the body the sketch LIVES ON — a
    face sketch targets its parent body walked to its current state, a plane
    sketch the NEWEST solid. Never the first body in the tree (2026-08-24:
    that default cut the raw stock instead of the user's panel)."""
    bods = _solids(doc)
    prof = _feature(doc, profile_id)
    if prof is not None and prof.op == "sketch_on_face" and prof.inputs:
        cur = _latest_descendant(doc, prof.inputs[0])
        if any(b.id == cur for b in bods):
            return cur
    return bods[-1].id if bods else None


def _pick_face(part, params: dict):
    """The face a sketch_on_face / extrude_face names, the two ways they may
    name it (by direction, or by a real pick's centre + normal)."""
    if params.get("face"):
        return sk.named_face(part, params["face"])
    if params.get("face_center") is not None:
        return sk.resolve_face(part, params["face_center"], params.get("face_normal"))
    raise ValueError('the face is not named — give face="top"/"+x"/... or a '
                     "face_center from an actual pick")


def _flat_or_raise(face):
    fp = sk.face_plane(face)
    if fp is None:
        raise ValueError(f"that face is {face.geom_type.name} (curved) — only a "
                         f"FLAT face can be extruded; tilted flat faces are fine")
    return fp


# ------------------------------------------------------------------ extrude ---

def plan_extrude(doc, req: dict) -> dict:
    """The Extrude tool's plan. Input is ONE of:
        sketch_id                     — a sketch / sketch_on_face profile
        body_id + face_center[+normal]— a picked flat face of that body
        feature_id                    — an existing extrude / extrude_face
                                        (edit mode: the input is derived)"""
    sketch_id = req.get("sketch_id")
    body_id = req.get("body_id")
    face_center = req.get("face_center")
    face_normal = req.get("face_normal")

    fid = req.get("feature_id")
    if fid:
        f = _feature(doc, fid)
        if f is None:
            raise ValueError(f"no feature '{fid}' in this design")
        if f.op == "extrude_face":
            body_id = (f.inputs or [None])[0]
            face_center = f.params.get("face_center")
            face_normal = f.params.get("face_normal")
        elif f.op == "extrude":
            sketch_id = (f.inputs or [None])[0]
        else:
            raise ValueError(f"'{fid}' is a {f.op}, not an extrude")

    if sketch_id is None and face_center is None:
        raise ValueError("Extrude needs a sketch profile or a picked flat face")

    # ---- face mode: extrude_face runs along the face's OUTWARD normal --------
    if sketch_id is None:
        part = doc._parts.get(body_id) if body_id else None
        if part is None:
            part = doc.result()
            body_id = body_id or (_solids(doc)[-1].id if _solids(doc) else None)
        if part is None:
            raise ValueError("no solid to extrude a face from — build a body first")
        picked = sk.resolve_face(part, face_center, face_normal)
        # the face's OWN plane: z = the outward normal = the build direction.
        # (Not face_sketch_plane: that canonicalises, and snaps a face tilted
        # under ~25° to a principal plane — the ghost would then grow along a
        # different axis than the solid.) The ghost lives in this frame, so
        # its depth is simply the amount, along the arrow.
        fp = _flat_or_raise(picked)
        loops = _loops([picked], fp)
        limits, _centre = _limits(loops)
        limits["collapse"] = _collapse([picked], req)
        axis = _vec(fp.z_dir)
        return {
            "ok": True, "tool": "extrude", "mode": "face", "op": "extrude_face",
            "input": body_id, "axis": axis, "origin": _vec(picked.center()),
            "frame": _frame(fp), "loops": loops,
            "into_sign": -1,                    # the axis points OUT of the body
            "limits": limits, "target_body": body_id,
            "will_build": f"extrude_face on {body_id} along {_axis_name(axis)}",
        }

    # ---- sketch mode: extrude_sketch runs along the SKETCH's own plane -------
    prof = _feature(doc, sketch_id)
    if prof is None:
        raise ValueError(f"no sketch '{sketch_id}' in this design")
    if prof.op not in ("sketch", "sketch_on_face"):
        raise ValueError(f"'{sketch_id}' is a {prof.op}, not a sketch")
    profile = doc._parts.get(sketch_id)
    if profile is None:
        raise ValueError(f"sketch '{sketch_id}' has not been built"
                         + (f" ({prof.problems[0]})" if getattr(prof, "problems", None) else "")
                         + " — fix the sketch first")
    p = prof.params or {}
    offset = float(p.get("offset") or 0.0)
    into_sign = None
    if prof.op == "sketch_on_face":
        host = (prof.inputs or [None])[0]
        part = doc._parts.get(host) if host else None
        if part is None:
            raise ValueError(f"the body '{host}' this sketch sits on has not been built")
        picked = _pick_face(part, p)
        outward = _flat_or_raise(picked).z_dir
        pl = sk.face_sketch_plane(picked)
        # a face gives the plane its POSITION, never its ORIENTATION: on a
        # bottom / -x / +y face the canonical frame points INTO the body, so
        # there a POSITIVE value is the pocket direction
        into_sign = -1 if outward.dot(pl.z_dir) > 0 else 1
        if offset:
            pl = pl.offset(offset)
    else:
        # the very plane make_sketch() built the profile on — one home; it
        # refuses exactly what the kernel refuses (no upper(), no fallback)
        pl = sk.sketch_plane(str(p.get("plane") or "XY"), offset)
    faces = list(profile.faces())
    loops = _loops(faces, pl)
    limits, centre = _limits(loops)
    if centre is None:
        raise ValueError(f"sketch '{sketch_id}' has no area to extrude")
    limits["collapse"] = _collapse(faces, req)
    axis = _vec(pl.z_dir)
    return {
        "ok": True, "tool": "extrude", "mode": "sketch", "op": "extrude",
        "input": sketch_id, "axis": axis, "origin": _world(pl, *centre),
        "frame": _frame(pl), "loops": loops,
        "into_sign": into_sign, "limits": limits,
        "target_body": _default_target(doc, sketch_id),
        "will_build": f"extrude on {sketch_id} along {_axis_name(axis)}",
    }


def plan_sketch(doc, req: dict) -> dict:
    """The frame a NEW plane sketch is drawn in: {plane, offset} -> the very
    plane make_sketch() will build the profile on (sketch.sketch_plane), as
    {origin, x_dir, y_dir, z_dir}. sketcher.js carried its own copy of these
    three frames until P2 of LAUNCH-PLAN.md; the grid is drawn where the
    kernel will build, and nowhere else is that fact written down."""
    plane = str(req.get("plane") or "XY")
    off = float(req.get("offset") or 0)
    pl = sk.sketch_plane(plane, off)            # raises the op's own sentence
    return {
        "ok": True, "tool": "sketch", "plane": plane, "offset": off,
        "frame": _frame(pl),
        "will_build": f"a sketch on the {plane} plane"
                      + (f", offset {off:g} mm along {_axis_name(_vec(pl.z_dir))}"
                         if off else ""),
    }


_PLANNERS = {"extrude": plan_extrude, "sketch": plan_sketch}


def plan(doc, req: dict) -> dict:
    """Dispatch by tool. Never raises — a failure is a sentence the UI can show
    (fusion-parity rule 7: failures speak)."""
    tool = str(req.get("tool") or "").lower()
    fn = _PLANNERS.get(tool)
    if fn is None:
        return {"ok": False, "tool": tool,
                "error": f"no plan for tool '{tool}' — known: {sorted(_PLANNERS)}"}
    try:
        return fn(doc, req)
    except Exception as e:                      # OCP errors are Exception, not RuntimeError
        return {"ok": False, "tool": tool, "error": str(e) or type(e).__name__}
