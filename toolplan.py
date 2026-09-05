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

import blocks
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
        f = _edit_input(doc, fid, ("extrude", "extrude_face"))
        if f.op == "extrude_face":
            body_id = (f.inputs or [None])[0]
            face_center = f.params.get("face_center")
            face_normal = f.params.get("face_normal")
        else:
            sketch_id = (f.inputs or [None])[0]

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
    profile, pl, into_sign = _profile(doc, sketch_id)
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


def _edit_input(doc, fid: str, ops: tuple):
    """The feature an EDIT session reopens, checked to be one of this tool's ops."""
    f = _feature(doc, fid)
    if f is None:
        raise ValueError(f"no feature '{fid}' in this design")
    if f.op not in ops:
        raise ValueError(f"'{fid}' is a {f.op}, not {' / '.join(ops)}")
    return f


def _sketch_part(doc, sketch_id: str):
    """A sketch feature and its built profile — the cheap lookup every
    profile-consuming tool starts from."""
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
    return prof, profile


def _profile(doc, sketch_id: str):
    """A sketch feature's built profile, the plane it was drawn on, and — for a
    face sketch — which SIGN goes into the host body (Extrude needs the host
    face for that; Revolve reads the plane the sketch carries instead)."""
    prof, profile = _sketch_part(doc, sketch_id)
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
    return profile, pl, into_sign


def _coincides(pl: Plane, world: str):
    """The local axis name ("u" / "v") whose LINE is the world axis `world`, else
    None — only then may a legacy world name become the riding local name."""
    d = sk._AXES[world].direction
    if (pl.origin - d * pl.origin.dot(d)).length > 1e-6:    # the plane origin is off that line
        return None
    for name, attr in sk._LOCAL_AXES.items():
        if abs(abs(getattr(pl, attr).dot(d)) - 1.0) < 1e-6:
            return name
    return None


def _revolve_geometry(profile, ax, n, ext) -> dict:
    """What the tool draws for ONE axis: the axis, the ring's centre on it level
    with the profile, the ring frame (x = radial toward the material, z = the
    axis, y = z × x so a positive drag turns the way the kernel sweeps — probed
    right-handed), the outline as (radial, axial) pairs, and the sizes."""
    r_lo, r_hi, h_lo, h_hi, _ = ext
    axis_dir = ax.direction
    side = 1.0 if abs(r_hi) >= abs(r_lo) else -1.0
    radial = n.cross(axis_dir).normalized() * side
    origin = ax.position + axis_dir * ((h_lo + h_hi) / 2.0)
    ring = Plane(origin=origin, x_dir=radial, z_dir=axis_dir)
    lathe = Plane(origin=origin, x_dir=radial, z_dir=radial.cross(axis_dir))
    radius = max(abs(r_lo), abs(r_hi), 1.0)
    return {"axis": _vec(axis_dir), "origin": _vec(origin), "frame": _frame(ring),
            "loops": _loops(list(profile.faces()), lathe),
            "limits": {"radius": round(radius, 4),
                       "axis_half": round(max(radius, (h_hi - h_lo) / 2.0) * 1.3, 4),
                       "max_angle": sk.MAX_REVOLVE_DEG}}


def _edge_label(p, q) -> str:
    """How the panel names an outline edge: by where it lies in the plane."""
    length = round(math.hypot(q[0] - p[0], q[1] - p[1]), 3)
    if abs(q[0] - p[0]) < 1e-6:
        return f"edge at u = {p[0]:g} ({length:g} mm, along v)"
    if abs(q[1] - p[1]) < 1e-6:
        return f"edge at v = {p[1]:g} ({length:g} mm, along u)"
    return f"edge ({p[0]:g}, {p[1]:g}) → ({q[0]:g}, {q[1]:g}) ({length:g} mm)"


_AXIS_LABELS = {"v": "v — the plane's vertical axis",
                "u": "u — the plane's horizontal axis"}


def _same_line(a, b) -> bool:
    """Two ((u1, v1), (u2, v2)) lines with the same endpoints, either way round."""
    (p, q), (r, s) = a, b

    def close(x, y):
        return abs(x[0] - y[0]) < 1e-3 and abs(x[1] - y[1]) < 1e-3
    return (close(p, r) and close(q, s)) or (close(p, s) and close(q, r))


def _axis_entries(profile, want) -> list[dict]:
    """Every axis this profile could turn about, each TESTED (P3b): u and v
    first — always listed, greyed with the reason when the profile crosses them
    — then the straight edges of the outline, longest first, named e1…eN and
    labelled by position; then, when `want` is a stored line that no longer
    matches an edge, that line under the name "stored" (a construction line:
    offered while it works, explained when it does not); a legacy WORLD axis
    under its own name. `param` is what the feature stores for that entry —
    the name, or the line — so the browser forwards it and derives nothing
    (R1). `ext` is revolve_extent's answer, for the handles."""
    entries = []

    def add(name, label, param):
        why = None
        try:
            ext = sk.revolve_extent(profile, sk.revolve_axis(profile, param))
        except ValueError as e:                  # a line the plane refuses
            ext, why = None, str(e)
        if ext is None:
            why = why or f"the world {name} axis runs outside the sketch plane"
        elif ext[4]:
            why = f"it crosses {name} ({ext[0]:.3g} to {ext[1]:.3g} mm)"
        entries.append({"name": name, "label": label, "param": param,
                        "ok": why is None, "why": why, "ext": ext})

    for name in ("v", "u"):
        add(name, _AXIS_LABELS[name], name)
    lines = sk.revolve_edge_lines(profile)
    for i, (p, q) in enumerate(lines, 1):
        add(f"e{i}", _edge_label(p, q), [list(p), list(q)])
    want_line = sk._axis_line(want)
    if want_line is not None:
        if not any(_same_line(want_line, line) for line in lines):
            p, q = want_line
            add("stored", f"the stored line ({p[0]:g}, {p[1]:g}) → ({q[0]:g}, {q[1]:g})",
                [list(p), list(q)])
    elif isinstance(want, str) and want in sk._AXES:
        add(want, f"{want} — world axis", want)
    return entries


def _is_edge(entry: dict) -> bool:
    return entry["name"].startswith("e")


def _matches(entry: dict, want) -> bool:
    """Is `entry` the axis `want` names — by name, or by the same line?"""
    want_line = sk._axis_line(want)
    if want_line is None:
        return entry["name"] == want
    mine = sk._axis_line(entry["param"])
    return mine is not None and _same_line(want_line, mine)


def plan_revolve(doc, req: dict) -> dict:
    """The Revolve tool's plan (specs/revolve.md). Input is ONE of:
        sketch_id                      — a sketch / sketch_on_face profile
        body_id + face_center[+normal] — a picked flat face of that body (P3b)
        feature_id                     — an existing revolve / revolve_face
                                         (edit: the input and the stored axis
                                         are read here)
    plus an optional axis name.

    The axis is DERIVED, not asked for: every axis that works is returned with
    its own handles (`alternatives`), the lathe axis v first, so a swap in the
    panel is a local choice. `axes` lists them all for the panel — u, v, the
    outline's straight edges, a stored line — each with what the feature would
    store. A legacy tree's WORLD axis is kept when its line lies in the plane
    (mapped to the local name when they coincide, offered under its own name
    otherwise); when the stored axis cannot be used the plan opens on one that
    can and says so in `fallback`, so the tool can tell the user before OK
    saves the change."""
    sketch_id = req.get("sketch_id")
    body_id = req.get("body_id")
    face_center = req.get("face_center")
    face_normal = req.get("face_normal")
    want = req.get("axis")
    fid = req.get("feature_id")
    if fid:
        f = _edit_input(doc, fid, ("revolve", "revolve_face"))
        p = f.params or {}
        if f.op == "revolve_face":
            body_id = (f.inputs or [None])[0]
            face_center, face_normal = p.get("face_center"), p.get("face_normal")
            want = want or p.get("axis")
        else:
            sketch_id = (f.inputs or [None])[0]
            want = want or p.get("axis") or "Z"    # the op's default when a tree names none
    if sketch_id is None and face_center is None:
        raise ValueError("Revolve needs a sketch profile or a picked flat face")

    if sketch_id is None:                       # ---- face mode (P3b) ----
        part = doc._parts.get(body_id) if body_id else None
        if part is None:
            part = doc.result()
            body_id = body_id or (_solids(doc)[-1].id if _solids(doc) else None)
        if part is None:
            raise ValueError("no solid to revolve a face of — build a body first")
        picked = sk.resolve_face(part, face_center, face_normal)
        fp = sk.face_profile_plane(picked)
        if fp is None:
            raise ValueError(f"that face is {picked.geom_type.name} (curved) — only a "
                             f"FLAT face can be revolved; tilted flat faces are fine")
        profile = sk._on_plane(b3d.Sketch([picked]), fp)
        input_id, mode, op, target = body_id, "face", "revolve_face", body_id
    else:                                       # ---- sketch mode ----
        _prof, profile = _sketch_part(doc, sketch_id)
        input_id, mode, op = sketch_id, "sketch", "revolve"
        target = _default_target(doc, sketch_id)
    pl = sk.sketch_plane_of(profile)            # the very plane the op will use (or its sentence)
    n = pl.z_dir

    if isinstance(want, str) and want in sk._AXES:
        want = _coincides(pl, want) or want     # the same line, under the name that rides
    entries = _axis_entries(profile, want)
    valid = [e for e in entries if e["ok"]]
    if not valid:
        why = " and ".join(e["why"] for e in entries if e["why"] and not _is_edge(e))
        edges = ("it crosses every straight edge of its outline"
                 if any(_is_edge(e) for e in entries)
                 else "its outline has no straight edge to turn about")
        raise ValueError(f"this profile cannot be revolved: {why}, and {edges}. Move the "
                         f"profile entirely to one side of an axis in its plane, or give "
                         f"it a straight edge to turn about.")
    chosen = next((e for e in valid if _matches(e, want)), None) if want is not None else None
    fallback = None
    if chosen is None:
        chosen = valid[0]
        if want is not None:
            asked = next((e for e in entries if _matches(e, want)), None)
            fallback = {"from": want if isinstance(want, str) else "the stored line",
                        "why": (asked["why"] if asked and asked["why"]
                                else f"{want} is not one of this profile's axes")}
    name = chosen["name"]
    geo = _revolve_geometry(profile, sk.revolve_axis(profile, chosen["param"]), n, chosen["ext"])
    return {
        "ok": True, "tool": "revolve", "mode": mode, "op": op, "input": input_id,
        **geo, "axis_name": name, "axis_param": chosen["param"],
        "axes": [{k: e[k] for k in ("name", "label", "param", "ok", "why")}
                 for e in entries if e["ok"] or not _is_edge(e)],
        "candidates": [e["name"] for e in valid],
        "alternatives": {e["name"]: _revolve_geometry(profile, sk.revolve_axis(profile, e["param"]),
                                                      n, e["ext"])
                         for e in valid if e["name"] != name},
        "fallback": fallback,
        "target_body": target,
        "will_build": f"{op} on {input_id} about {chosen['label']} "
                      f"({_axis_name(geo['axis'])})",
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


# ------------------------------------------------------- fillet / chamfer ---

def edge_polyline(edge) -> list[list[float]]:
    """Points along an edge for drawing it: 2 for a line, 24 steps otherwise.
    (Shared with /api/model's edge outlines when the shared mesh has none.)"""
    n = 2 if str(edge.geom_type).split(".")[-1] == "LINE" else 24
    return [_vec(edge @ (i / n)) for i in range(n + 1)]


def _body_part(doc, body_id: str):
    """A solid feature and its built Part — what an edge tool works on."""
    f = _feature(doc, body_id)
    if f is None:
        raise ValueError(f"no body '{body_id}' in this design")
    part = doc._parts.get(body_id)
    if part is None or f.volume is None:
        raise ValueError(f"'{body_id}' is not a built solid"
                         + (f" ({f.problems[0]})" if f.problems else "")
                         + " — fix it first")
    return f, part


def _ball(part, edge, faces_by_edge: dict) -> dict:
    """Where the handle sits and which way it drags: the edge's midpoint, and
    the bisector of the two faces there pointing INTO the material (probed:
    -(n1 + n2) — on a box's top edge that is (0, .707, -.707))."""
    mid = edge @ 0.5
    ns = []
    for f in faces_by_edge.get(blocks._shape_key(edge), [])[:2]:
        try:
            ns.append(f.normal_at(mid))
        except Exception:
            ns.append(f.normal_at(f.center()))
    if not ns:
        raise ValueError("that edge belongs to no face of the body — pick another edge")
    d = -(ns[0] + ns[1]) if len(ns) == 2 else -ns[0]
    if d.length < 1e-6:                          # tangent faces meet flat: no bisector
        d = -ns[0]
    return {"origin": _vec(mid), "dir": _vec(d.normalized())}


def _stored(part, ref, by_edge: dict) -> dict:
    """A pick in stored form: an edge_ref already, or resolved into one."""
    if isinstance(ref, dict) and "faces" in ref:
        return ref
    ref = ref if isinstance(ref, dict) else {"mid": list(ref)}
    return blocks.edge_ref(part, blocks.resolve_edge(part, ref), by_edge)


def _expand(part, refs, chain: bool) -> list:
    """The edges a pick list means, grown into tangent chains when asked."""
    picked = blocks.edges_for(part, refs)
    if not (chain and isinstance(refs, (list, tuple))):
        return picked
    seen, grown = set(), []
    for e in picked:
        for c in blocks.tangent_chain(part, e):
            if blocks._shape_key(c) not in seen:
                seen.add(blocks._shape_key(c))
                grown.append(c)
    return grown


def _toggle_pick(part, refs, click: dict, chain: bool, by_edge: dict) -> list:
    """Fusion's click rule: an edge not yet selected joins the picks; one that
    IS selected — directly or through a pick's tangent chain — takes that pick
    out. Decided here because only the kernel knows which chain an edge is in."""
    hit = blocks._shape_key(blocks.resolve_edge(part, click))
    keep = [r for r in refs
            if hit not in {blocks._shape_key(e) for e in _expand(part, [r], chain)}]
    if len(keep) == len(refs):                   # not selected yet: add it
        keep.append(blocks.edge_ref(part, blocks.resolve_edge(part, click), by_edge))
    return keep


def plan_fillet(doc, req: dict) -> dict:
    """The Fillet / Chamfer tool's plan (specs/fillet-chamfer.md). Input: the
    body and its picked edges (`edges`: edge_ref dicts or [x, y, z] midpoints
    straight from the model's edge lines), or the feature_id of an existing
    fillet / chamfer (edit: its stored edges are read here). `chain` (default
    on) grows every pick into its tangent chain, Fusion's default.

    Returns the resolved edges in their STORED form (`edges_param`, what the op
    will be given, so the tree never carries an index), each with the points to
    draw it gold, and the ball handle's origin and direction — the browser
    draws what this says and computes nothing (R1). With nothing picked yet the
    plan is still ok, so the tool can keep the pick alive.
    """
    tool = str(req.get("tool") or "fillet").lower()
    fid = req.get("feature_id")
    body = req.get("body_id")
    refs = req.get("edges")
    want_chain = req.get("chain")
    stored = False                               # did these edges come from the tree?
    if fid:
        f = _edit_input(doc, fid, ("fillet", "chamfer"))
        body = (f.inputs or [None])[0]
        if refs is None:
            refs = (f.params or {}).get("edges", "all")
            stored = True
    if not body:
        raise ValueError(f"{tool.capitalize()} needs the edges of a body — click an edge in the viewport")
    _bf, part = _body_part(doc, body)
    by_edge = blocks._edge_faces(part)
    tog = req.get("toggle")
    # A legacy GROUP ("all"/"vertical"/…) becomes explicit picks the moment the
    # user clicks — converted BEFORE the chain default is worked out, so a group
    # whose edges have tangent neighbours is not silently grown by that click.
    if tog is not None and isinstance(refs, str):
        refs = [blocks.edge_ref(part, e, by_edge)
                for e in blocks.edges_for(part, refs)]
    # THE CHAIN DEFAULT. Fresh picking chains (Fusion). A STORED selection does
    # not: it is already the answer, and re-expanding it can only add edges the
    # user never picked — a chain-off fillet reopened, or an AI-authored group
    # whose edges have tangent neighbours. Keyed on where the edges came from,
    # which only the server knows, so a caller that forgets to say is safe.
    chain = bool(want_chain) if want_chain is not None else not stored
    if tog is not None:                          # a click: add the edge, or take it out
        refs = _toggle_pick(part, refs or [], tog, chain, by_edge)
    # the user's own picks in STORED form (unexpanded) — what the tool sends
    # back with the next click, so every request is exact
    picks = (refs if isinstance(refs, str)
             else [_stored(part, r, by_edge) for r in (refs or [])])
    if not refs:
        return {"ok": True, "tool": tool, "op": tool, "input": body, "edges": [],
                "edges_param": [], "picks": [], "ball": None, "chain": chain,
                "will_build": f"{tool} — pick the edges of {body}"}
    picked = _expand(part, refs, chain)          # a gone edge raises its sentence
    out_refs = [blocks.edge_ref(part, e, by_edge) for e in picked]
    edges = [{**r, "points": edge_polyline(e), "length": round(e.length, 2)}
             for r, e in zip(out_refs, picked)]
    n = len(picked)
    return {
        "ok": True, "tool": tool, "op": tool, "input": body,
        "edges": edges,
        # a legacy GROUP stays a group unless the user re-picks (the AI's trees
        # keep their vocabulary); a pick is stored as the resolved list
        "edges_param": refs if isinstance(refs, str) else out_refs,
        "picks": picks,
        "ball": _ball(part, picked[0], by_edge),
        "chain": chain,
        "will_build": f"{tool} {n} edge{'s' if n != 1 else ''} of {body}",
    }


_PLANNERS = {"extrude": plan_extrude, "revolve": plan_revolve, "sketch": plan_sketch,
             "fillet": plan_fillet, "chamfer": plan_fillet}


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
