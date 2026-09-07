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
from types import SimpleNamespace

import build123d as b3d
from build123d import Plane

import blocks
import pattern
import provenance
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
    """The face a sketch_on_face / extrude_face / hole names, the two ways they
    may name it (by direction, or by a real pick's centre + normal) — the op's
    own rule, sketch.pick_face."""
    return sk.pick_face(part, params.get("face_center"), params.get("face_normal"),
                        params.get("face"))


def _flat_or_raise(face, verb: str = "extruded"):
    fp = sk.face_plane(face)
    if fp is None:
        raise ValueError(f"that face is {face.geom_type.name} (curved) — only a "
                         f"FLAT face can be {verb}; tilted flat faces are fine")
    return fp


def _pick_body(doc, body_id, what: str):
    """The body a face was picked from — that one when it is built, else the
    document's result under the newest solid's id (a pick before any body was
    named) — or the sentence. ONE rule for every face-mode plan."""
    part = doc._parts.get(body_id) if body_id else None
    if part is None:
        part = doc.result()
        body_id = body_id or (_solids(doc)[-1].id if _solids(doc) else None)
    if part is None:
        raise ValueError(f"no solid to {what} — build a body first")
    return part, body_id


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
        part, body_id = _pick_body(doc, body_id, "extrude a face from")
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
                       "max_angle": sk.MAX_REVOLVE_DEG,
                       "max_each_side": sk.MAX_REVOLVE_DEG / 2}}   # a symmetric sweep


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


MAX_EDGE_AXES = 12     # the longest straight edges offered as axes — a traced outline has hundreds


def _axis_entries(profile, want, edges_first: bool = False) -> list[dict]:
    """Every axis this profile could turn about, each TESTED (P3b): u and v —
    always listed, greyed with the reason when the profile crosses them — and
    the longest straight edges of the outline (at most MAX_EDGE_AXES), named
    e1…eN and labelled by position. A sketch lists u, v first (its origin is
    the sketch's own); a picked FACE lists the edges first, because its plane's
    origin is the world origin's foot, an axis far from a body that is not
    centred on it. Then, when `want` is a stored line that matches no offered
    edge, that line under the name "stored" (a construction line: offered while
    it works, explained when it does not); a legacy WORLD axis under its own
    name. `kind` says which of those it is, `param` what the feature stores —
    the name, or the line — so the browser forwards it and derives nothing
    (R1); `ax` / `ext` are the measured Axis and revolve_extent, for the
    handles. One candidate the kernel chokes on is greyed, not the tool refused
    (OCP errors do not derive from RuntimeError)."""
    entries = []

    def add(kind, name, label, param):
        why, ext, ax = None, None, None
        try:
            ax = sk.revolve_axis(profile, param)
            ext = sk.revolve_extent(profile, ax)
        except ValueError as e:                  # a line the plane refuses
            why = str(e)
        except Exception:                        # the kernel: this axis only
            why = f"the kernel could not measure {label}"
        word = name if kind in ("local", "world") else label
        if why is None:
            if ext is None:
                why = f"{word} runs outside the sketch plane"
            elif ext[4]:
                why = f"it crosses {word} ({ext[0]:.3g} to {ext[1]:.3g} mm)"
        entries.append({"kind": kind, "name": name, "label": label, "param": param,
                        "ok": why is None, "why": why, "ext": ext, "ax": ax})

    lines = sk.revolve_edge_lines(profile)[:MAX_EDGE_AXES]
    local = [("local", n, _AXIS_LABELS[n], n) for n in ("v", "u")]
    edges = [("edge", f"e{i}", _edge_label(p, q), [list(p), list(q)])
             for i, (p, q) in enumerate(lines, 1)]
    for spec in (edges + local if edges_first else local + edges):
        add(*spec)
    want_line = sk._axis_line(want)
    if want_line is not None:
        if not any(_same_line(want_line, line) for line in lines):
            p, q = want_line
            add("stored", "stored",
                f"the stored line ({p[0]:g}, {p[1]:g}) → ({q[0]:g}, {q[1]:g})",
                [list(p), list(q)])
    elif isinstance(want, str) and want in sk._AXES:
        add("world", want, f"{want} — world axis", want)
    return entries


def _is_edge(entry: dict) -> bool:
    return entry["kind"] == "edge"


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
        part, body_id = _pick_body(doc, body_id, "revolve a face of")
        _picked, _fp, profile = sk.face_profile(part, face_center, face_normal)  # the op's own object
        input_id, mode, op, target = body_id, "face", "revolve_face", body_id
    else:                                       # ---- sketch mode ----
        _prof, profile = _sketch_part(doc, sketch_id)
        input_id, mode, op = sketch_id, "sketch", "revolve"
        target = _default_target(doc, sketch_id)
    pl = sk.sketch_plane_of(profile)            # the very plane the op will use (or its sentence)
    n = pl.z_dir

    if isinstance(want, str) and want in sk._AXES:
        want = _coincides(pl, want) or want     # the same line, under the name that rides
    entries = _axis_entries(profile, want, edges_first=(mode == "face"))
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
    geo = _revolve_geometry(profile, chosen["ax"], n, chosen["ext"])
    return {
        "ok": True, "tool": "revolve", "mode": mode, "op": op, "input": input_id,
        **geo, "axis_name": name, "axis_param": chosen["param"],
        "axes": [{k: e[k] for k in ("kind", "name", "label", "param", "ok", "why")}
                 for e in entries if e["ok"] or not _is_edge(e)],
        "alternatives": {e["name"]: _revolve_geometry(profile, e["ax"], n, e["ext"])
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


def _toggle_set(part, refs: list, edges: list, by_edge: dict) -> tuple[list, str, int]:
    """A whole SET of edges (a group chip, or every edge of a clicked face) as
    one click: the ones not yet picked join the picks; when every one of them
    is picked already, the set comes out. Returns (refs, 'added'|'removed', n)."""
    have = [(r, blocks._shape_key(blocks.resolve_edge(part, r))) for r in refs]
    keys = {k for _, k in have}
    missing = [e for e in edges if blocks._shape_key(e) not in keys]
    if missing:
        return (refs + [blocks.edge_ref(part, e, by_edge) for e in missing],
                "added", len(missing))
    drop = {blocks._shape_key(e) for e in edges}
    keep = [r for r, k in have if k not in drop]
    return keep, "removed", len(refs) - len(keep)


def _group_words(key: str) -> str:
    side, dir_ = key.split("/")
    what = {"vertical": "upright", "horizontal": "flat-lying", "all": ""}[dir_]
    kind = "inside-corner" if side == "inside" else "outside"
    return f"{what} {kind} edges".replace("  ", " ").strip()


def _groups_state(groups: dict, picked_keys: set) -> dict:
    """For the panel's chips: how many edges each group has, how many of them
    are picked right now — the chip's lit / dashed / dim state is read off this."""
    return {k: {"total": len(es),
                "picked": sum(1 for e in es if blocks._shape_key(e) in picked_keys)}
            for k, es in groups.items()}


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
    tog, gtog = req.get("toggle"), req.get("group_toggle")
    clicked = tog is not None or gtog is not None
    # A legacy GROUP ("all"/"vertical"/…) becomes explicit picks the moment the
    # user clicks — converted BEFORE the chain default is worked out, so a group
    # whose edges have tangent neighbours is not silently grown by that click.
    if clicked and isinstance(refs, str):
        refs = [blocks.edge_ref(part, e, by_edge)
                for e in blocks.edges_for(part, refs)]
    # the body's edges by kind — inside corner / outside edge x upright /
    # flat-lying / all — for the panel's chips (classified once per body)
    groups = blocks.edge_groups(part, by_edge)
    click, click_n = None, 0
    if gtog is not None:                         # a chip: a whole group in one click
        key = f"{gtog.get('side')}/{gtog.get('dir')}"
        if key not in groups:
            raise ValueError(f"no edge group '{key}' — the groups are inside / outside "
                             f"× vertical / horizontal / all")
        if not groups[key]:
            raise ValueError(f"{body} has no {_group_words(key)} — a smooth seam between "
                             f"a round and a flat is not a corner")
        refs, click, click_n = _toggle_set(part, refs or [], groups[key], by_edge)
    # THE CHAIN DEFAULT. Fresh picking chains (Fusion). A STORED selection does
    # not: it is already the answer, and re-expanding it can only add edges the
    # user never picked — a chain-off fillet reopened, or an AI-authored group
    # whose edges have tangent neighbours. Keyed on where the edges came from,
    # which only the server knows, so a caller that forgets to say is safe.
    chain = bool(want_chain) if want_chain is not None else not stored
    if tog is not None:                          # a click: add the edge, or take it out
        before = len(refs or [])
        refs = _toggle_pick(part, refs or [], tog, chain, by_edge)
        # said in the browser when a click REMOVED: with chain on, a click on any
        # edge of a picked smooth rim releases the rim, which reads as "the edge
        # will not select" when nothing says otherwise
        click = "removed" if len(refs) < before else "added"
        click_n = 1
    # the user's own picks in STORED form (unexpanded) — what the tool sends
    # back with the next click, so every request is exact
    picks = (refs if isinstance(refs, str)
             else [_stored(part, r, by_edge) for r in (refs or [])])
    if not refs:
        return {"ok": True, "tool": tool, "op": tool, "input": body, "edges": [],
                "edges_param": [], "picks": [], "ball": None, "chain": chain,
                "click": click, "click_n": click_n, "groups": _groups_state(groups, set()),
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
        "click": click,
        "click_n": click_n,
        "groups": _groups_state(groups, {blocks._shape_key(e) for e in picked}),
        "will_build": f"{tool} {n} edge{'s' if n != 1 else ''} of {body}",
    }


# --------------------------------------------------------------------- hole ---

def plan_hole(doc, req: dict) -> dict:
    """The Hole tool's plan (specs/hole.md). Input: body_id + face_center
    [+ face_normal] + face_point (where the face was clicked, world) — or the
    feature_id of an existing hole, whose stored face and `at` then stand in
    for whatever the request does NOT carry. The request is authoritative
    either way, so a click during an EDIT moves the hole exactly as it does
    while creating one (it used to be silently ignored).

    Returns where the hole sits (`origin`, and `at` in the face's own frame —
    the form the op stores), the face in ONE stored form (a NAME, or a centre +
    normal, never both — two forms can disagree about which face it is), the
    arrow's axis INTO the material and the marker circle's frame (right-handed,
    for THREE.Matrix4.makeBasis; the drilling direction is `axis`).

    `limits.material` — how much material lies under the point, kernel-measured
    — is measured only when the tool asks (`measure_material`), the way Extrude
    asks for its taper limits: it is an Edge-intersect-Solid boolean costing
    250-510 ms on a real body, and it answers one advisory sentence that a
    through hole never needs. The browser draws what this says and computes
    nothing (R1)."""
    body_id, params = req.get("body_id"), {}
    face_center, face_normal = req.get("face_center"), req.get("face_normal")
    point, at, face_name = req.get("face_point"), None, None
    fid = req.get("feature_id")
    if fid:
        f = _edit_input(doc, fid, ("hole",))
        body_id = (f.inputs or [None])[0]
        params = f.params or {}
        # STORED IS THE FALLBACK, never the override (plan_revolve does the
        # same with its axis) — otherwise the re-pick the tool arms in edit
        # mode moves nothing and says nothing
        face_center = face_center if face_center is not None else params.get("face_center")
        face_normal = face_normal if face_normal is not None else params.get("face_normal")
        if point is None:                # no fresh click: the stored face and point stand
            face_name = params.get("face")
            at = params.get("at")
            if at is None:               # never said: the OP's own default, not the
                at = list(sk.HOLE_AT)    # face centre — the marker must not lie
    if face_center is None and not face_name:
        raise ValueError("Hole needs a flat face — click a face of a body")
    part, body_id = _pick_body(doc, body_id, "drill")
    face = sk.pick_face(part, face_center, face_normal, face_name)
    # ONE flat-face guard and ONE framing rule, the op's own: a curved face, a
    # point off the face and the click -> `at` all speak there
    pl, centre, n, at = sk.hole_frame(face, at, point)
    into = n * -1.0
    return {
        "ok": True, "tool": "hole", "mode": "face", "op": "hole", "input": body_id,
        "origin": _vec(centre), "axis": _vec(into), "at": at,
        "face": face_name,
        "face_center": None if face_name else _vec(face.center()),
        "face_normal": None if face_name else _vec(n),
        # the marker circle's frame: the face's own right-handed axes, moved to
        # the hole's centre
        "frame": {**_frame(pl), "origin": _vec(centre)},
        "limits": ({"material": sk.material_depth(part, centre, into,
                                                  sk.through_reach(part))}
                   if req.get("measure_material") else {}),
        "target_body": body_id,
        "will_build": f"hole on {body_id} at ({at[0]:g}, {at[1]:g}) "
                      f"along {_axis_name(_vec(into))}",
    }


# ------------------------------------------------------------------ pattern ---

def _perp(d):
    ref = b3d.Vector(1, 0, 0) if abs(d.X) < 0.9 else b3d.Vector(0, 1, 0)
    return d.cross(ref).normalized()


def _same_dir(a, b) -> bool:
    try:
        return sum(float(x) * float(y) for x, y in zip(a, b)) > 0.999
    except (TypeError, ValueError):
        return False


def _seed_plan(doc, req: dict, tool: str, name: str, verb: str) -> SimpleNamespace:
    """The seed of a Pattern / Mirror plan, resolved ONE way (specs/pattern.md,
    specs/mirror.md). Input: `seed_id` (a tree row), or `body_id` +
    `face_center` [+ `face_point`] (a face pick — provenance says which feature
    made that face, or that it is the body's own), or `feature_id` (edit: an
    existing feature, whose stored seed stands in) / `own_id` (the feature THIS
    session built: replanning must read ITS stored params and the body it sits
    on, or `_latest_descendant` walks into the tool's own output and the next
    plan aims at the already-patterned solid — P4 code review; ignored while
    the feature is still in flight).

    `document.delta_features` (the tree's folding rule) decides what "the
    feature" means; the tool goes on the seed body's CURRENT state (`tip`).
    Returns fid, params (stored), tip, part, before, removed, added, seed_param,
    seed_words, face (the flat face the seed sits on, None for a body), centre
    (where the seed is) and half (a handle length: ¾ of the body's extent)."""
    fid = req.get("feature_id")
    if not fid:
        own = req.get("own_id")
        f_own = _feature(doc, own) if own else None
        if f_own is not None and f_own.op == tool:
            fid = own
    params, tip, seed, body_seed = {}, None, req.get("seed_id"), False
    if fid:
        f = _edit_input(doc, fid, (tool,))
        tip = (f.inputs or [None])[0]
        params = dict(f.params or {})
        seed = params.get("seed")
        if seed is None:                          # a body pattern / mirror: the body is the seed
            seed, body_seed = tip, True
    elif seed is None and req.get("face_center") is not None:
        att = provenance.attribute_face(doc, body_id=req.get("body_id"),
                                        point=req.get("face_point"), center=req.get("face_center"))
        seed = att.get("feature")
        if not seed:                              # an unattributable face: the body itself
            seed, body_seed = att.get("body") or req.get("body_id"), True
    if not seed:
        raise ValueError(f"{name} needs a feature or a body to {verb} — click a hole, a boss "
                         f"or a body, or select a row in the tree")
    before_id, after_id = (None, seed) if body_seed else doc.delta_features(seed)
    if fid:
        if after_id != tip and after_id not in doc.ancestors(tip):
            raise ValueError(f"'{seed}' is not part of {tip}'s history — {tool} works on a "
                             f"feature of the body it is on")
    else:
        tip = _latest_descendant(doc, after_id)
    part = doc._parts.get(tip)
    before = doc._parts.get(before_id) if before_id else None
    after = doc._parts.get(after_id)
    if part is None or after is None or (before_id and before is None):
        raise ValueError(f"'{seed}' is not built (failed upstream?) — fix it first")
    if before_id:
        try:
            removed, added = pattern.delta(before, after)
        except ValueError:                        # the same sentence the op gives
            raise ValueError(f"the kernel could not work out what '{seed}' changed — "
                             f"pick another feature to {verb}") from None
        if removed is None and added is None:
            raise ValueError(f"'{seed}' neither removed nor added material — there is nothing to {verb}")
        seed_param = seed
        seed_words = seed if tip == seed else f"{seed} (on {tip})"
        face = pattern.seed_face(before, removed, added)
    else:
        removed, added = None, part
        seed_param, seed_words, face = None, f"the body {tip}", None
    bb = part.bounding_box()
    return SimpleNamespace(fid=fid, params=params, tip=tip, part=part, before=before,
                           removed=removed, added=added, seed_param=seed_param,
                           seed_words=seed_words, face=face,
                           centre=pattern.seed_centre(removed, added, part),
                           half=round(max(bb.size.X, bb.size.Y, bb.size.Z) * 0.75, 2))


def _axis_face(part, pick: dict, tip: str):
    """The face of `part` whose axis the user clicked — or the sentence that
    says there is none.

    `sk.pick_face`'s nearest-centre match is unbounded and the framework hands
    this tool clicks on its OWN result body (tool.js `armRepick`), so a click on
    a COPY's bore wall came back as a face of the pre-pattern body 21 mm away
    and the pattern silently re-aimed to it (P4 review follow-up,
    probes/pattern_barrier_probe.py §2 — the same class as the mirror plane's
    `_plane_face`).

    Mirror's rule cannot be reused, and §3 measures why: a mirror PLANE is the
    same wherever in it the face sits, but an axis is not — a flat face's axis
    is its normal THROUGH ITS CENTRE — and that centre MOVES as the pattern
    punches more holes in the face (0.11 mm on an 80 mm plate), so the clicked
    centre cannot be matched exactly either. What holds for every face type is
    that the click must be somewhere `part` really has that face: inside the
    resolved face's own bounding box. A face the result body shares passes even
    with its centroid drifted; a copy's face is tens of mm outside it."""
    picked = sk.pick_face(part, pick.get("center"), pick.get("normal"))
    c = pick.get("center")
    if c is not None:
        bb = picked.bounding_box()
        # the tolerance covers studio.py's 2-decimal rounding of a picked
        # centre and the centroid's drift, nothing wider
        tol = 0.05
        span = ((bb.min.X, bb.max.X), (bb.min.Y, bb.max.Y), (bb.min.Z, bb.max.Z))
        if any(float(v) < lo - tol or float(v) > hi + tol
               for v, (lo, hi) in zip(c, span)):
            raise ValueError(f"that face is not on {tip} — a pattern's axis comes from a face "
                             f"of the body being patterned, not one that only a copy has; "
                             f"click a face of {tip}, or a bore on it")
    return picked


def plan_pattern(doc, req: dict) -> dict:
    """The Circular / Rectangular Pattern tools' plan (specs/pattern.md). The
    seed is `_seed_plan`'s; `axis_pick` (circular) is a face clicked while the
    panel is open: its axis replaces the current one. `along` (rectangular)
    names which alternative is direction 1.

    Returns what the handles need and nothing the browser could derive (R1):
    the seed's centre, the ring's frame / radius / axis line for circular, the
    arrows' directions and the swap alternatives for rectangular, the axis in
    its ONE stored form and the words for it, and `params` — the stored values
    a new feature starts from."""
    tool = str(req.get("tool") or "polar_pattern").lower()
    circular = tool == "polar_pattern"
    s = _seed_plan(doc, req, tool, "Circular Pattern" if circular else "Rectangular Pattern", "repeat")
    fid, params, tip, part, face = s.fid, s.params, s.tip, s.part, s.face
    seed_param, seed_words, centre, half = s.seed_param, s.seed_words, s.centre, s.half
    out = {"ok": True, "tool": tool, "op": tool, "input": tip, "target_body": tip,
           "seed": seed_param, "seed_words": seed_words, "centre": _vec(centre)}
    if circular:
        axis, pick = params.get("axis"), req.get("axis_pick")
        if pick:                                  # a click: THAT face's axis, in stored form
            picked = _axis_face(part, pick, tip)
            pattern.face_axis(picked)             # a face that has no axis says so here
            axis = pattern.stored_face(part, picked)
        elif axis is None and face is not None and not fid:
            axis = pattern.stored_face(part, face)    # the default: the seed's face
        origin, d, words = pattern.axis_of(part, axis)
        foot = origin + d * (centre - origin).dot(d)
        rvec = centre - foot
        radius = rvec.length
        x = rvec.normalized() if radius > 1e-6 else _perp(d)
        out.update({
            "axis": axis, "axis_words": words, "origin": _vec(foot), "axis_dir": _vec(d),
            "radius": round(radius, 4), "axis_half": half,
            "frame": {"origin": _vec(foot), "x_dir": _vec(x), "y_dir": _vec(d.cross(x)),
                      "z_dir": _vec(d)},
            "params": {"seed": seed_param, "axis": axis},
            "will_build": f"{tool} of {seed_words} about {words}",
        })
        return out
    # rectangular: the directions are the seed face's own axes (a body: the world's)
    if face is not None:
        pl = sk.face_profile_plane(face)
        alts = [{"name": "x", "label": f"the face's x ({_axis_name(_vec(pl.x_dir))})",
                 "dir": _vec(pl.x_dir)},
                {"name": "y", "label": f"the face's y ({_axis_name(_vec(pl.y_dir))})",
                 "dir": _vec(pl.y_dir)}]
    else:
        alts = [{"name": n, "label": f"world {n.upper()}", "dir": v}
                for n, v in (("x", [1.0, 0.0, 0.0]), ("y", [0.0, 1.0, 0.0]), ("z", [0.0, 0.0, 1.0]))]
    along, stored, stored2 = req.get("along"), params.get("direction"), params.get("direction2")
    legacy_dist = None
    if fid and stored is None:                    # a legacy feature: its (dx, dy, dz) step IS
        legacy = pattern.legacy_step(params)      # a direction and a distance — edit those
        if legacy is not None:
            stored, legacy_dist = legacy
    if stored is not None:
        # the stored direction is ALWAYS one of the alternatives, not only on the
        # first plan: it used to be added just when `along` was unset, so the next
        # replan (the user opening the dropdown) dropped it and re-aimed a diagonal
        # pattern to world X
        if not any(_same_dir(a["dir"], stored) for a in alts):
            alts.insert(0, {"name": "stored", "label": "the stored direction",
                            "dir": [float(c) for c in stored]})
        if along is None:                         # edit: it leads until the user picks
            along = next(a["name"] for a in alts if _same_dir(a["dir"], stored))
    first = next((a for a in alts if a["name"] == along), alts[0])
    second = next(a for a in alts if a["name"] != first["name"])
    d2 = second["dir"]
    if req.get("along") is None and stored2 is not None:
        d2 = [float(c) for c in stored2]
    out.update({
        "direction": first["dir"], "direction2": d2, "alternatives": alts, "along": first["name"],
        "arrow_half": half,
        "params": {"seed": seed_param, "direction": first["dir"], "direction2": d2,
                   **({"distance": legacy_dist} if legacy_dist is not None else {})},
        "will_build": f"{tool} of {seed_words} along {_axis_name(first['dir'])}",
    })
    return out


_ORIGIN_PLANES = (("yz", "YZ"), ("xz", "XZ"), ("xy", "XY"))


def _same_plane(a, b) -> bool:
    """are two STORED planes the same one? (a name, a mid-plane, a face)"""
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().upper() == b.strip().upper()
    if isinstance(a, dict) and isinstance(b, dict):
        if a.get("mid") and b.get("mid"):
            return str(a["mid"]).upper() == str(b["mid"]).upper()
        if a.get("face_center") is not None and b.get("face_center") is not None:
            try:
                near = all(abs(float(x) - float(y)) < 1e-3
                           for x, y in zip(a["face_center"], b["face_center"]))
            except (TypeError, ValueError):
                return False
            return near and _same_dir(a.get("face_normal") or (), b.get("face_normal") or ())
        return a == b
    return False


def _plane_face(part, pick: dict, tip: str):
    """The face of `part` whose PLANE the user clicked, in the form Mirror
    stores (`pattern.stored_face`) — or the sentence that says why there is none.

    Matched by the PLANE, not by the nearest centre: the framework hands this
    tool clicks on its OWN result body (tool.js `armRepick`), a mirror image has
    faces the input body has not, and `sk.pick_face`'s nearest-centre match is
    unbounded — so a click on the doubled plate's top face came back as its +x
    face and the mirror silently re-aimed (P4 review). A face of the image lying
    in a plane the body really has (the doubled plate's top, bottom, sides)
    still counts; anything else is refused. The op resolves the stored face on
    this same body at every rebuild (`pattern.plane_of`), so a face of the image
    could not be stored anyway."""
    c, nrm = pick.get("center"), pick.get("normal")
    c = b3d.Vector(*(float(v) for v in c)) if c else None
    nrm = b3d.Vector(*(float(v) for v in nrm)) if nrm else None

    def clicked(o, n) -> bool:                    # the click lies IN this plane, facing it
        # 1e-2 is `sk.face_plane`'s own tolerance and must not be tightened:
        # studio.py rounds a picked centre to 2 decimals, so a point that truly
        # lies in the plane can sit 0.0087 mm off it
        return (c is not None and abs((c - o).dot(n)) <= 1e-2
                and (nrm is None or abs(n.dot(nrm)) >= 0.999))

    best = None
    for f in part.faces():                        # a PLANE face IS (centre, normal) —
        if f.geom_type != b3d.GeomType.PLANE:     # the form resolve_face already uses
            continue
        fc = f.center()
        if clicked(fc, f.normal_at(fc)) and (best is None or
                                             (fc - c).length < (best.center() - c).length):
            best = f
    if best is not None:
        return best
    picked = sk.pick_face(part, pick.get("center"), pick.get("normal"))   # name what was clicked
    pl = sk.face_plane(picked)                    # a dead-flat BSPLINE wall is a plane too
    if pl is None:
        raise ValueError(f"the picked face is {picked.geom_type.name} — a mirror plane is "
                         f"a flat face, an origin plane or the body's mid-plane")
    if clicked(b3d.Vector(pl.origin), b3d.Vector(pl.z_dir)):
        return picked
    raise ValueError(f"that face is not on {tip} — the mirror plane must be a flat face of "
                     f"the body being mirrored, not one that only its mirror image has; click a "
                     f"face of {tip}, an origin plane, or pick a mid-plane in the Plane box")


def plan_mirror(doc, req: dict) -> dict:
    """The Mirror tool's plan (specs/mirror.md). The seed is `_seed_plan`'s. The
    plane: `plane_pick` — a face ({center, normal}) or an origin plane
    ({world: "YZ"}) clicked while the panel is open — beats `plane` (the name
    of an alternative chosen in the panel), which beats the stored one (edit /
    the session's own feature); a NEW session starts with none, so nothing is
    built until the user picks (rule 4). Returns the plane in its ONE stored
    form and the words for it, the gold quad's frame (the body's centre
    projected onto the plane) and size, the alternatives (the three origin
    planes, the body's three mid-planes, and the current plane if it is
    neither — a picked face, a legacy plane), the name of the current one, and
    `params` — `join` is what a BODY mirror does, so a NEW mirror joins only
    when it has no seed; an EDIT keeps the stored value while the stored params
    and this plan AGREE about whether there is a seed, so a legacy copy-only
    mirror edited here stays one, and one whose stored seed has stopped
    resolving comes back as a body Join, never as that copy."""
    s = _seed_plan(doc, req, "mirror", "Mirror", "mirror")
    part, params = s.part, s.params
    alts = [{"name": n, "label": f"the {w} plane (through the origin)", "plane": w}
            for n, w in _ORIGIN_PLANES]
    if s.seed_param is not None:
        # The body's own mid-plane runs through its bounding-box centre, so a
        # BODY Join across it can never leave that box — the part cannot grow,
        # and on a symmetric body nothing changes at all while the tool still
        # says "Mirror created" (P4 review, P0 — probes/mirror_p0_probe.py §4).
        # For a FEATURE it is the plane a machinist reaches for first. A design
        # that already stores one still builds and is still offered, below, as
        # the current plane — a saved design may never stop rebuilding.
        alts += [{"name": f"mid{ax.lower()}", "label": f"the body's mid-plane across {ax}",
                  "plane": {"mid": ax}} for ax in ("X", "Y", "Z")]
    plane, pick = params.get("plane"), req.get("plane_pick")
    if pick:
        if pick.get("world"):
            plane = str(pick["world"]).upper()
        else:
            plane = pattern.stored_face(part, _plane_face(part, pick, s.tip))
    elif req.get("plane"):
        # "face" / "stored" are the names the panel gives the plane already in
        # force when it is none of the alternatives (inserted below): choosing
        # it again keeps it. Any other unknown name is refused with the names
        # that exist, never ignored in silence (P4 review)
        chosen = next((a for a in alts if a["name"] == req["plane"]), None)
        if chosen is not None:
            plane = chosen["plane"]
        elif req["plane"] not in ("face", "stored"):
            raise ValueError(f"'{req['plane']}' is not a plane Mirror offers here — choose one of "
                             f"{', '.join(a['name'] for a in alts)}, or click a flat face or an "
                             f"origin plane")
    # `join` is what a BODY mirror does (Fusion's Join). Stamped on a SEEDED
    # row it was a loaded gun: the op branches on the truthiness of `seed`, so
    # the moment a seed arrived empty the feature mirror became a whole-body
    # Join at twice the size, silently (P4 review, P0 — probe §2).
    #
    # An edit reads the STORED value, so a legacy copy-only mirror stays a
    # copy — but ONLY while the stored params and this plan agree about whether
    # there is a seed. When they disagree the stored seed has stopped resolving
    # to a feature (it names a whole body, or a PLACEMENT row that now folds to
    # one) and its `join: False` does not mean "a copy", it means nothing: the
    # plan came back as the legacy COPY form and applying it replaced the body
    # with a detached reflection, with no Join row to undo from (the P0 of the
    # /code-review of c4d5961 — measured: an 80 mm plate relocated to
    # x 40..120, zero overlap with where it was). A body mirror is a Join.
    stored_seed, planned_seed = params.get("seed"), s.seed_param is not None
    keep_stored = bool(s.fid) and bool(stored_seed) == planned_seed
    join = bool(params.get("join", False)) if keep_stored else not planned_seed
    out = {"ok": True, "tool": "mirror", "op": "mirror", "input": s.tip, "target_body": s.tip,
           "seed": s.seed_param, "seed_words": s.seed_words, "centre": _vec(s.centre),
           "half": s.half, "params": {"seed": s.seed_param, "plane": plane, "join": join}}
    if plane is None:
        out.update({"plane": None, "plane_words": None, "plane_name": "", "frame": None,
                    "alternatives": alts, "will_build": f"mirror of {s.seed_words} — no plane yet"})
        return out
    pl, words = pattern.plane_of(part, plane)         # an unusable stored plane says so here
    current = next((a for a in alts if _same_plane(a["plane"], plane)), None)
    if current is None:                               # a face, or a legacy plane: always offered
        is_face = isinstance(plane, dict) and (plane.get("face") or plane.get("face_center") is not None)
        alts.insert(0, {"name": "face" if is_face else "stored", "label": words, "plane": plane})
        current = alts[0]
    n, o, x = b3d.Vector(pl.z_dir), b3d.Vector(pl.origin), b3d.Vector(pl.x_dir)
    c = part.bounding_box().center()
    foot = c - n * (c - o).dot(n)                     # the quad sits ON the body, in the plane
    out.update({"plane": plane, "plane_words": words, "plane_name": current["name"],
                "alternatives": alts,
                "frame": {"origin": _vec(foot), "x_dir": _vec(x), "y_dir": _vec(n.cross(x)),
                          "z_dir": _vec(n)},
                "will_build": f"mirror of {s.seed_words} across {words}"})
    return out


_PLANNERS = {"extrude": plan_extrude, "revolve": plan_revolve, "sketch": plan_sketch,
             "fillet": plan_fillet, "chamfer": plan_fillet, "hole": plan_hole,
             "polar_pattern": plan_pattern, "linear_pattern": plan_pattern,
             "mirror": plan_mirror}


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
        msg = str(e) or type(e).__name__
        # the op's sentences name themselves ("hole: …") and the UI already
        # says which tool ("Hole cannot start: …") — one name is enough
        if msg.lower().startswith(f"{tool}:"):
            msg = msg[len(tool) + 1:].strip()
        return {"ok": False, "tool": tool, "error": msg}
