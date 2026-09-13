"""
document.py — the feature tree: TextCAD's design document engine.

In SolidWorks the FeatureManager tree is what makes a part EDITABLE: every
feature is a named, parameterized step, and changing one parameter rebuilds the
part deterministically. This module brings that to TextCAD — and it is also our
strongest anti-hallucination move yet:

    Editing by REGENERATION is where LLMs drift ("change the bore" quietly
    becomes a different design). Editing a FEATURE TREE is deterministic:
    one parameter changes in one named node, the tree rebuilds through the
    verified blocks, and nothing else CAN change.

A design is a Document: an ordered list of Features. Each Feature is either
  * a CREATOR   — a verified block call (disc, revolve_profile, curved_blade..),
  * a MODIFIER  — takes one upstream feature (with_center_hole, polar_pattern..),
  * a COMBINER  — fuse / cut / intersect / move on upstream features.

Rebuild evaluates the list in order (it is a DAG: `inputs` name upstream ids),
health-checks EVERY node's output, verifies the final solid against the
document's Spec, and records per-node status — exactly what a UI tree needs to
render (name, params, OK/FAIL badge).

Documents serialize to plain JSON (save/load), so a design is a durable file —
the recipe is the artifact, not just the STEP it produces.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from functools import lru_cache
import inspect
import hashlib
import json
import math
import os
import re

import build123d as b3d
from build123d import Pos
from OCP.TopAbs import TopAbs_ShapeEnum
from OCP.TopExp import TopExp_Explorer

import blocks
import inspector
import pattern
import sketch as sk


# ---------------------------------------------------------------------------
# Operation registry — every node runs ONLY these (verified blocks + booleans)
# ---------------------------------------------------------------------------

# creators: no geometric inputs, params only  (from the verified block library)
CREATORS = {name: blocks.EXPORTS[name] for name in
            ("plate", "disc", "ball", "cone", "tube", "polygon_plate",
             "hex_plate", "revolve_profile", "curved_blade")}
CREATORS["sketch"] = sk.make_sketch     # produces a 2D Sketch, not a solid
CREATORS["import_stl"] = blocks.import_stl   # external mesh file -> solid body
CREATORS["import_step"] = blocks.import_step  # exact BREP import (incl. our own exports)

# modifiers: exactly one upstream Part + numeric/string params
MODIFIERS = {
    "with_center_hole": blocks.with_center_hole,
    "with_bolt_circle": blocks.with_bolt_circle,
    "polar_pattern": pattern.polar_pattern,    # a body, or a FEATURE's delta, about an axis (P4)
    "rotate": blocks.rotate,
    "mirror": pattern.mirror,                  # a body (join / the legacy copy) or a FEATURE's delta across a plane (P4)
    "scale": blocks.scale_uniform,
    "linear_pattern": pattern.linear_pattern,  # … along one or two directions (P4)
    "fillet": blocks.fillet_edges,
    "chamfer": blocks.chamfer_edges,
    "shell": sk.shell,                  # solid + picked faces -> the hollowed body (P4)
    "extrude": sk.extrude_sketch,       # sketch -> solid
    "extrude_face": sk.extrude_face,    # solid's picked face -> prism (boss/pocket)
    "revolve": sk.revolve_sketch,       # sketch -> solid
    "revolve_face": sk.revolve_face,    # solid's picked face -> solid of revolution (P3b)
    "hole": sk.hole,                    # solid + a point on a flat face -> the body WITH the hole (P4)
    "sweep": sk.sweep_sketch,           # sketch + path -> solid
    "sketch_on_face": sk.sketch_on_face,  # solid -> sketch (on a picked face)
}

# combiners: pure topology ops on upstream Parts
def _fuse(parts):      # union of all inputs
    out = parts[0]
    for p in parts[1:]:
        out = out + p
    return out

def _cut(parts):       # first input minus the rest
    out = parts[0]
    for p in parts[1:]:
        out = out - p
    return out

def _intersect(parts):
    out = parts[0]
    for p in parts[1:]:
        out = out & p
    return out

def _loft(parts):      # blend 2+ sketches into a solid
    try:
        out = sk.loft_sketches(parts)
    except Exception:
        # EVERYTHING is translated, ValueError included. Two holes in the
        # first version of this guard, both found by the follow-up read of
        # c9b2e92 and both measured: OCP errors derive from Exception
        # (StdFail_NotDone('BRep_API: command not done'),
        # Standard_NoSuchObject('NCollection_DataMap::Find')), and build123d
        # raises its OWN bare ValueErrors with kernel wording
        # ("More than one wire is required"), so re-raising a ValueError as
        # "already a sentence" let that straight out. Nothing above this line
        # produces a sentence worth keeping: the count check is in _eval and
        # the kind check in _check_combiner_inputs, both of which run first.
        raise ValueError(
            "loft could not blend these profiles — they must be on DIFFERENT "
            "planes, each one a single closed area") from None
    # inspector._try, not getattr: a default only covers AttributeError, so a
    # volume property that RAISES went straight past `getattr(out, "volume", 0)`
    # and out of this function as kernel text (measured).
    if not (inspector._try(lambda: out.volume) or 0) > 0:
        # coplanar profiles build a zero-volume "solid" (measured): health
        # catches it, but "empty solid" does not say what to change.
        raise ValueError(
            "loft produced no solid — the profiles are on the same plane; a "
            "loft needs them on DIFFERENT planes")
    return out

COMBINERS = {"fuse": _fuse, "cut": _cut, "intersect": _intersect,
             "loft": _loft}


def _check_combiner_inputs(op: str, ids: list, parts: list) -> None:
    """Refuse a combiner whose inputs are the wrong KIND — BEFORE the kernel.

    A pre-check, not a try/except, because one of these cannot be caught at
    all: `loft` of a sketch and a solid SEGFAULTS OpenCASCADE (measured
    2026-09-10, access violation inside BRepOffsetAPI_ThruSections), which
    takes the server child down with it. The other door is silent rather than
    loud: `intersect` of a body and a sketch returned a 2D Sketch, CONSUMED
    the body, and left the design with no bodies at all while every tree row
    stayed green (leaves [], result_shape() None, no warning).

    The Add Feature dialog offers a checkbox for every feature, sketches
    included, so both are one mis-click away."""
    flat = [i for i, p in zip(ids, parts) if sk.is_sketch(p)]
    if op == "loft":
        solids = [i for i, p in zip(ids, parts) if not sk.is_sketch(p)]
        if solids:
            raise ValueError(
                f"loft blends SKETCH profiles, and {_name_list(solids)} "
                + ("is a solid body" if len(solids) == 1 else "are solid bodies")
                + " — loft the sketches, then fuse the result to the body")
        if len(set(ids)) < len(ids):
            raise ValueError("loft needs 2 DIFFERENT profiles — the same "
                             "sketch is named twice")
        # ONE profile per section. build123d flattens every section's faces
        # into a SINGLE chain (`for face in s.faces(): loft_sections.append(
        # face.outer_wire())`), so two sketches of two circles each blended
        # A1 -> A2 -> B1 -> B2: one snaking solid of 1570.8 mm3 where the two
        # honest tubes are 3141.6, reaching z -3.92..23.92 outside BOTH sketch
        # planes, status ok and not one warning (measured 2026-09-11). Which
        # profile pairs with which is kernel face order, so there is nothing
        # to guess at either.
        many = [(i, len(p.faces())) for i, p in zip(ids, parts)
                if len(p.faces()) > 1]
        if many:
            # each section names its OWN count: quoting the first one for all of
            # them said "a and b hold 2" where b held 3 (round two of this fix)
            held = _name_list([f"{i} ({n} profiles)" for i, n in many])
            raise ValueError(
                f"loft blends ONE closed profile per sketch, and {held} — draw "
                f"each profile in its own sketch and loft them in pairs")
        return
    if flat:
        raise ValueError(
            f"{op} works on solid bodies, and {_name_list(flat)} "
            + ("is a sketch" if len(flat) == 1 else "are sketches")
            + f" — extrude or revolve it first, then {op} the body")

# modifiers that pull a 2D PROFILE into a solid — the ops whose input must be
# a sketch and never a body (`loft` is a combiner and gated above)
SKETCH_CONSUMING_MODIFIERS = {"extrude", "revolve", "sweep"}


def _check_modifier_input(op: str, fid: str, part) -> None:
    """Refuse a profile op fed a solid BODY — BEFORE the kernel.

    `sweep` is the silent one: build123d takes `sections.faces()`, so a BODY is
    swept FACE BY FACE. A 24 000 mm3 plate came back as a 178 000 mm3 six-lump
    blob with status ok, no problems and no warning — and the plate itself was
    consumed, because a modifier's input is (measured 2026-09-11). `extrude`
    and `revolve` do fail there, but on health, in kernel wording that names
    nothing the user can act on. The Add Feature dialog pre-ticks the NEWEST
    feature, so on a design with a body all three are one click away.

    The test is SOLIDS, not `is_sketch`: a sketch of disjoint islands composes
    into a Compound that is not a Sketch instance (rebuild() classifies 2D
    results by op as well as by type), and refusing those would take away
    designs that work today."""
    if op in SKETCH_CONSUMING_MODIFIERS and (n_solids(part) or 0) > 0:
        raise ValueError(
            f"{op} pulls a SKETCH profile, and '{fid}' is a solid body — "
            f"sketch on one of its faces, then {op} that sketch")


KNOWN_OPS = set(CREATORS) | set(MODIFIERS) | set(COMBINERS) | {"move"}


@lru_cache(maxsize=None)
def op_params(op: str) -> tuple:
    """Every parameter `op` accepts, in signature order, as (name, default)
    pairs — read from the function the rebuild unpacks the params into.

    ONE source, because there were two: the edit guard and the catalogue the
    AI reads (`author.op_catalog`) each walked the registries with their own
    copy of the same three rules, so a new op needing a special case had to be
    remembered twice. Combiners take none; `move` is x, y, z; an op this build
    does not know (a design written by a newer one) reports none rather than
    raising — loading such a file must still work."""
    if op == "move":
        return (("x", 0), ("y", 0), ("z", 0))
    fn = CREATORS.get(op) or MODIFIERS.get(op)
    if fn is None:
        return ()
    sig = list(inspect.signature(fn).parameters.values())
    if op in MODIFIERS:
        sig = sig[1:]                    # the upstream part
    # an underscored parameter is the document's, not the user's: the pattern
    # ops take the seed's before / after bodies that way (Document._eval)
    return tuple((p.name, None if p.default is inspect._empty else p.default)
                 for p in sig
                 if p.kind not in (p.VAR_KEYWORD, p.VAR_POSITIONAL)
                 and not p.name.startswith("_"))

# how many inputs an op NEEDS to still mean something (used when a delete
# takes one of its inputs away: a modifier with none left cannot survive)
def _min_inputs(op: str) -> int:
    if op in CREATORS:
        return 0
    if op in COMBINERS:
        return 2
    return 1                    # modifiers + move


# A sketch and a solid are NOT interchangeable, so a delete may never silently
# reconnect one to the other.
def _kind_of(op: str) -> str:
    return "sketch" if op in sk.SKETCH_PRODUCERS else "solid"


def _move_offsets(params: dict) -> tuple[float, float, float]:
    """`move`'s x / y / z as numbers, or a sentence naming the one that is not
    (float() alone says "could not convert string to float: 'abc'" — Python
    wording, banned from the user's chat; specs/move-rotate.md)."""
    out = []
    for k in ("x", "y", "z"):
        v = (params or {}).get(k, 0)
        try:
            n = float(0 if v is None else v)
            if not math.isfinite(n):
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError(f"move: {k} must be a number in mm (got {v!r})") from None
        out.append(n)
    return out[0], out[1], out[2]


DELETE_MODES = ("auto", "cascade", "strict")

# A parameter that NAMES another feature. `inputs` is the body a feature works
# ON; this is the feature it points AT -- a pattern's `seed`, the tree's one
# reference that is not an input. Rename and delete must walk BOTH: renaming
# the seed used to break every pattern of it ("the seed 'hole1' is not in the
# tree") and deleting the seed left a pattern repeating a ghost, because both
# only ever looked at `inputs` (found by the P4 code review).
REF_PARAMS = {op: ("seed",) for op in pattern.SEEDED_OPS}

# ---------------------------------------------------------------------------
# Rebuild cache: a feature's output is a pure function of (op, params, inputs)
#
# Every rebuild used to re-evaluate all 73 features AND re-run the health check
# on each one, even when nothing had changed. Entering and leaving sketch mode
# does exactly that twice (the rollback bar goes on, then off), so visiting a
# sketch and changing NOTHING cost ~10 s on esp32-remote. Features are content-
# addressed instead: a signature over the op, its params and its INPUTS'
# signatures. Same signature -> same geometry, so the part, its problems and
# its volume are all reused.
#
# The signature covers inputs by content, not by name, so renaming a feature
# keeps every cache entry, and editing one parameter invalidates exactly that
# feature and everything downstream of it.
# ---------------------------------------------------------------------------

CACHE_MAX = 400          # entries; a part is a shape handle, not a mesh


def _deep_valid(part):
    """OpenCASCADE's validity analysis on ONE body: True, False, or None when
    the kernel could not answer. ~270 ms on a large solid, which is why the
    per-feature pass skips it (inspector.health(check_valid=False)) and only
    the finished bodies pay it.

    Named at module level so a test can stand in for it: an invalid solid
    cannot be built to order, and the rule worth locking is which bodies are
    checked, not what the kernel says about them."""
    return inspector._try(lambda: bool(part.is_valid))


def n_solids(part) -> int:
    """How many SEPARATE lumps this shape is. 0.4 ms for a 73-feature design.

    A part that falls into two pieces is the failure this project cares about
    most: shorten the plate under a boss and the boss floats, sever a plate with
    a slot and it becomes two halves — and OCCT is perfectly happy either way.
    inspector.health() reports such a result as clean, so without this the tree
    stayed green while the design silently stopped being one part."""
    if part is None:
        return 0
    try:
        exp = TopExp_Explorer(part.wrapped, TopAbs_ShapeEnum.TopAbs_SOLID)
    except Exception:
        return 0
    n = 0
    while exp.More():
        n += 1
        exp.Next()
    return n


def _canon_number(v):
    """Numbers that MEAN the same must hash the same.

    JSON keeps -25.0 and -25 apart, and the sketch editor round-trips one into
    the other: finishing a sketch without touching it rewrote y: -25.0 as -25
    and offset: 6.0 as 6, which changed the signature and rebuilt every feature
    downstream — 13 s for a no-op. Integral floats collapse to int, and values
    are rounded to 9 decimals: OCCT's own tolerance is 1e-7 mm, so anything
    finer is noise, not geometry."""
    if isinstance(v, bool):
        return v
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")):
            return str(v)
        r = round(v, 9)
        return int(r) if r == int(r) else r
    if isinstance(v, int):
        return v
    if isinstance(v, dict):
        return {k: _canon_number(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_canon_number(x) for x in v]
    return v

# Reads a file that can change under us — the params alone do not describe the
# result, so its signature carries the file's fingerprint too.
FILE_BACKED_OPS = {"import_stl", "import_step"}

# ONE cache for the whole process. A signature already names the op, its
# parameters and its inputs' signatures, so an entry is valid for ANY document
# that asks the same question — reopening a design from the library, switching
# tabs, undoing into a new Document, or two designs sharing a base body all hit
# geometry that has already been built. Documents can still opt out (tests do)
# by assigning their own dict to `_cache`.
_SHARED_CACHE: dict = {}


def _name_list(ids, cap: int = 6) -> str:
    """'a, b and c' -- truncated so a 70-feature cascade stays readable."""
    ids = list(ids)
    if not ids:
        return "nothing"
    shown, rest = ids[:cap], len(ids) - cap
    if rest > 0:
        return ", ".join(shown) + f" and {rest} more"
    if len(shown) == 1:
        return shown[0]
    return ", ".join(shown[:-1]) + " and " + shown[-1]


def _delete_summary(plan: dict) -> str:
    """One honest sentence about what a delete does -- shown in the confirm
    dialog BEFORE it happens and in chat after. A delete must never quietly
    take more than the feature the user pointed at."""
    bits = [f"Delete '{plan['target']}'"]
    if plan["orphans"]:
        bits.append("with its leftover tool geometry "
                    + _name_list(plan["orphans"]))
    cascaded = [i for i in plan["cascaded"] if i not in plan["orphans"]]
    if cascaded:
        bits.append(f"and {len(cascaded)} dependent feature"
                    + ("s " if len(cascaded) != 1 else " ")
                    + f"that cannot be kept without it ({_name_list(cascaded)})")
    if plan["rewired"]:
        bits.append("reconnecting " + _name_list(
            [f"{r['id']} to {'+'.join(r['to']) or 'nothing'}"
             for r in plan["rewired"]]))
    head = ", ".join(bits) if len(bits) > 1 else bits[0]
    return (f"{head}. {len(plan['deleted'])} feature"
            f"{'s' if len(plan['deleted']) != 1 else ''} removed, "
            f"{plan['remaining']} left.")


# ---------------------------------------------------------------------------
# Feature + Document
# ---------------------------------------------------------------------------

@dataclass
class Feature:
    """One named node in the tree.

    id     : unique name shown in the tree (e.g. "hub", "bore", "blades").
    op     : an operation from KNOWN_OPS.
    params : JSON-safe keyword arguments for the op (numbers, lists).
    inputs : ids of upstream features consumed (modifiers: 1, combiners: 2+).
    suppressed : if True the node is skipped (its FIRST input passes through).
    # rebuild status (not saved as intent, refreshed on every rebuild):
    status : "ok" | "failed" | "stale"
    problems : list of failure strings from the last rebuild
    volume : measured volume from the last rebuild
    """
    id: str
    op: str
    params: dict = field(default_factory=dict)
    inputs: list = field(default_factory=list)
    suppressed: bool = False
    status: str = "stale"
    problems: list = field(default_factory=list)
    volume: float | None = None
    pieces: int | None = None      # separate lumps in this feature's solid
    notes: list = field(default_factory=list)   # non-fatal facts from the build
    #                                (e.g. a taper that ended at its tip) — shown
    #                                through Document.warnings on every path


@dataclass
class Document:
    """An editable, savable, rebuildable design."""
    name: str
    features: list[Feature] = field(default_factory=list)
    spec: dict = field(default_factory=dict)   # inspector.Spec fields, JSON-safe
    spec_problems: list = field(default_factory=list)
    # Whether the spec check RAN. False while it could not (the rollback bar
    # is parked) — NOT the same thing as failing it, and the UI must not paint
    # that red: 42 of the 50 live designs carry a spec, so "spec FAIL"
    # appeared the moment any editor opened (section 5 review, 2026-09-10).
    # Defaults FALSE, so a document that has never been rebuilt cannot report
    # a green "spec PASS" for geometry nothing has verified; `rebuild` sets it
    # (round two, same review).
    spec_checked: bool = False
    warnings: list = field(default_factory=list)  # non-fatal honesty flags
    rollback: str | None = None    # SolidWorks-style bar: build only up to this id
    _parts: dict = field(default_factory=dict, repr=False)   # id -> Part cache
    _cache: dict = field(default_factory=lambda: _SHARED_CACHE, repr=False)
    _spec_cache: tuple = field(default=None, repr=False)     # (sig, problems)
    _geom_version: str = field(default="", repr=False)       # what is drawable
    _sigs: dict = field(default_factory=dict, repr=False)   # feature id -> content signature
    _healing: bool = field(default=False, repr=False)         # heal re-entry guard
    # how many bodies the LAST to_step() actually wrote. Recorded there, while
    # the rollback bar is still released: a caller cannot count them afterwards
    # (to_step re-parks the bar on its way out, and result_bodies() then
    # describes the isolated build state again, not the file).
    exported_bodies: int = field(default=0, repr=False)
    _valid_cache: dict = field(default_factory=dict, repr=False)   # sig -> is_valid
    # (cut signature, tool id) pairs whose through-all probe has already been
    # tried and did not help — see _heal_stranding_cuts
    _heal_tried: dict = field(default_factory=dict, repr=False)
    # struck id -> the ids THAT strike actually suppressed. A restore must put
    # back exactly what its ✕ took away and nothing else: a feature the user
    # had already struck on purpose was in the plan too, and recomputing the
    # plan at restore time turned it back on (P5b review, 2026-09-12). Not
    # saved: a reopened file falls back to the plan, which is all the
    # information a file carries.
    _struck_by: dict = field(default_factory=dict, repr=False)

    # -- authoring ----------------------------------------------------------
    def add(self, id: str, op: str, params: dict | None = None,
            inputs: list[str] | None = None, strict: bool = False) -> "Document":
        """Append a node. `strict` also refuses a param the op cannot take.

        It is OFF by default because `from_data` builds every loaded design
        through here: a file written by another build must open even if one of
        its params has since been renamed (it will say so as a failed feature,
        which is recoverable — refusing to open is not). The doors where the
        node is being AUTHORED — the API's /api/feature/add and the AI's
        _to_document — pass strict=True, so a hallucinated key is a sentence
        now instead of a TypeError at the next rebuild."""
        if op not in KNOWN_OPS:
            raise ValueError(f"unknown op '{op}' — allowed: {sorted(KNOWN_OPS)}")
        if any(f.id == id for f in self.features):
            raise ValueError(f"duplicate feature id '{id}'")
        if strict:
            self.check_params(op, params or {}, id)
        for dep in (inputs or []):
            if not any(f.id == dep for f in self.features):
                raise ValueError(f"feature '{id}' references unknown input '{dep}'")
        self.features.append(Feature(id=id, op=op, params=params or {},
                                     inputs=list(inputs or [])))
        return self

    # -- the pattern's seed (specs/pattern.md) --------------------------------
    PULLED = ("extrude", "revolve", "loft", "sweep", "extrude_face", "revolve_face")
    # ops that RE-PLACE the whole body instead of adding to it or taking from
    # it, so they have no delta at all (`mirror` only in its legacy copy-only
    # form — with a seed it repeats a feature's delta, with `join` it ADDS its
    # reflection, and both of those are real deltas)
    PLACEMENT = ("move", "rotate", "scale", "mirror")

    def ancestors(self, fid: str) -> set:
        """every feature upstream of `fid`: its inputs, theirs, and so on"""
        by_id = {f.id: f for f in self.features}
        seen, todo = set(), list(by_id[fid].inputs) if fid in by_id else []
        while todo:
            d = todo.pop()
            if d in seen or d not in by_id:
                continue
            seen.add(d)
            todo.extend(by_id[d].inputs)
        return seen

    def delta_features(self, seed: str) -> tuple:
        """What "pattern THIS feature" means — ONE rule for the op and the plan,
        and the tree's own folding rule: (before_id, after_id), the body before
        the seed and the body after it. A modifier of a body (hole, fillet, a
        pattern…) is its own before / after; a pulled tool (extrude, revolve…)
        with a folded 2-input boolean is that BOOLEAN's; a bare boolean is its
        first input / itself; anything else — a creator, a standalone tool
        body, a fuse of separate bodies, a PLACEMENT that only re-places the
        body — is a BODY seed: (None, the body), the whole body is repeated.
        A sketch is refused with a sentence."""
        by_id = {f.id: f for f in self.features}
        f = by_id.get(seed)
        if f is None:
            raise ValueError(f"the seed '{seed}' is not in the tree — pick the feature to repeat again")
        if f.suppressed:
            raise ValueError(f"the seed '{seed}' is struck out — restore it, or pick another feature")
        if f.op in sk.SKETCH_PRODUCERS:
            raise ValueError("a sketch is not a feature to repeat (sketch patterns come with the "
                             "sketch tools) — click a hole, a boss, or a body")
        placed = f.op in self.PLACEMENT
        if f.op == "mirror":                     # only the legacy copy-only form
            placed = not (f.params.get("seed") or f.params.get("join"))
        if placed:
            # A placement's "before − after" is the body in its old spot and
            # its "after − before" the body in the new one, so repeating that
            # "delta" gouged a body-sized lump out of the part somewhere else
            # and reported success (P4 review, P0 — probes/mirror_p0_probe.py
            # §1, measured on the user's designs/sat-side-panel). What such a
            # row produces is a body, and a body is what it seeds.
            return None, f.id
        booleans = ("cut", "fuse", "intersect")
        if f.op in self.PULLED:
            bools = [b for b in self.features if b.op in booleans
                     and len(b.inputs) == 2 and b.inputs[1] == f.id]
            others = [x for x in self.features if x.id != f.id and f.id in x.inputs
                      and x not in bools]
            if len(bools) == 1 and not others:       # the tree folds it: one feature
                return bools[0].inputs[0], bools[0].id
            return None, f.id                        # a standalone tool body
        if f.op in MODIFIERS and f.inputs:
            src = by_id.get(f.inputs[0])
            if src is not None and src.op not in sk.SKETCH_PRODUCERS:
                return src.id, f.id
            return None, f.id
        if f.op in booleans and len(f.inputs) == 2:
            return f.inputs[0], f.id
        return None, f.id

    def _seed_parts(self, f: Feature, seed: str) -> dict:
        """the seed's before / after bodies for a pattern's rebuild, checked to
        be part of the pattern's own body's history"""
        try:
            before_id, after_id = self.delta_features(seed)
        except ValueError as e:
            raise ValueError(f"{f.op}: {e}") from None
        if before_id is None:
            raise ValueError(f"{f.op}: '{seed}' is a whole body, not a feature of one — leave "
                             f"`seed` empty to work on the body itself")
        body = f.inputs[0]
        if after_id != body and after_id not in self.ancestors(body):
            raise ValueError(f"{f.op}: '{seed}' is not part of {body}'s history — {f.op} works "
                             f"on a feature of the body it is on")
        before, after = self._parts.get(before_id), self._parts.get(after_id)
        if before is None or after is None:
            raise ValueError(f"{f.op}: the seed '{seed}' is not built (failed upstream?)")
        return {"_before": before, "_after": after}

    # -- editing (THE point of the tree) -------------------------------------
    def edit(self, feature_id: str, param: str, value) -> None:
        """Change ONE parameter of ONE named node. Nothing else can change."""
        self.edit_many(feature_id, {param: value})

    def edit_many(self, feature_id: str, params: dict) -> None:
        """Change named parameters of ONE node -- all of them or none. A key
        the feature neither stores nor its op accepts refuses the whole
        request with a sentence, so a typo can never half-apply, and never
        gets stored to fail the build later (the multi-param route used to
        write any key unchecked). A parameter the op knows but the feature has
        not stored yet IS accepted: `through` on an extrude saved as
        {amount} was refused for a month as "no such parameter"."""
        f = self.get(feature_id)
        self.check_params(f.op, params, feature_id, stored=f.params)
        f.params.update(params)
        self._mark_stale()

    @staticmethod
    def param_names(op: str) -> set:
        """Every parameter `op` accepts (see `op_params`)."""
        return {name for name, _ in op_params(op)}

    @staticmethod
    def numeric_params(op: str) -> set:
        """The parameters of `op` that are numbers — read from the type
        ANNOTATION on the function the rebuild unpacks into, so it is the same
        one source `op_params` uses and cannot drift.

        Deliberately narrow: only a bare `float` or `int` counts. The shape
        parameters (`edges`, `plane`, `axis`, `at`, a pattern's `count`) carry
        no annotation or a compound one, and they legitimately hold words,
        lists and dicts — type-checking those would refuse `edges="all"`."""
        fn = CREATORS.get(op) or MODIFIERS.get(op)
        if op == "move":
            return {"x", "y", "z"}
        if fn is None:
            return set()
        out = set()
        for p in inspect.signature(fn).parameters.values():
            if p.name.startswith("_") or p.kind in (p.VAR_KEYWORD,
                                                    p.VAR_POSITIONAL):
                continue
            ann = p.annotation
            # `from __future__ import annotations` makes these strings
            if isinstance(ann, str) and ann.strip() in ("float", "int"):
                out.add(p.name)
            elif ann in (float, int):
                out.add(p.name)
        return out

    @staticmethod
    def check_params(op: str, params: dict, feature_id: str,
                     stored: dict | None = None) -> None:
        """Refuse a key `op` cannot take, naming EVERY bad one so a save with
        three typos is not three round trips.

        `stored` (an edit) also allows a key the feature already holds, so a
        design written by another build stays editable; without it (authoring
        a NEW node) only the op's own parameters pass. LOADING a file never
        comes through here -- `Document.from_data` must always open."""
        allowed = Document.param_names(op) | set(stored or ())
        bad = [k for k in (params or {}) if k not in allowed]
        if bad:
            raise ValueError(
                f"'{feature_id}' ({op}) has no parameter "
                + ", ".join(repr(k) for k in bad)
                + f" -- it takes {sorted(allowed)}")
        # A NUMBER that is not a number. "8mm" is what a CAD user types, and
        # the tree's text edit passes any non-numeric text through on purpose
        # (edges="all", open_face="top" need it). It used to reach the kernel:
        # BRepPrimAPI_MakeBox answered with twelve lines of C++ overloads in
        # the feature row (measured 2026-09-10, section 5 review).
        numeric = Document.numeric_params(op)
        for k, v in (params or {}).items():
            if k not in numeric:
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                # unit-neutral on purpose: this also covers angles (degrees)
                # and counts, and naming the wrong unit is its own bug
                raise ValueError(
                    f"'{feature_id}' ({op}): {k} must be a number (got "
                    f"{v!r}) — type just the number, without units")

    def get(self, feature_id: str) -> Feature:
        for f in self.features:
            if f.id == feature_id:
                return f
        raise KeyError(f"no feature named '{feature_id}'")

    def _stamp_geometry(self) -> None:
        """A fingerprint of what the viewport would draw. The UI skips
        refetching and re-rendering the model when this has not moved — opening
        and closing a sketch without touching anything changes nothing, and
        used to cost a full re-tessellation plus a multi-megabyte transfer.
        Feature IDS are part of it: the viewport keys its bodies by id."""
        self._geom_version = hashlib.sha1(json.dumps(
            [[f.id, self._sigs.get(f.id), f.suppressed] for f in self.features]
            + [self.rollback], default=str).encode("utf-8")).hexdigest()

    @staticmethod
    def param_refs(f: "Feature") -> list:
        """The features `f` names in its PARAMS (a pattern's `seed`) -- see
        REF_PARAMS. Every id here is as much a dependency as an input."""
        return [str(f.params[k]) for k in REF_PARAMS.get(f.op, ())
                if f.params.get(k)]

    def rename(self, old: str, new: str) -> None:
        """Rename a feature EVERYWHERE it is referenced (Fusion's browser
        rename). The id doubles as the reference key, so inputs, the rollback
        bar and the part cache are rewritten atomically — a rename can never
        break the tree. Geometry is untouched: no rebuild needed."""
        f = self.get(old)
        new = (new or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", new):
            raise ValueError("feature names use letters, digits, '_' or '-' "
                             "(1-40 chars, no spaces)")
        if new == old:
            return
        if any(x.id == new for x in self.features):
            raise ValueError(f"duplicate feature id '{new}'")
        f.id = new
        for x in self.features:
            x.inputs = [new if d == old else d for d in x.inputs]
            for k in REF_PARAMS.get(x.op, ()):    # a pattern's seed is a reference too
                if x.params.get(k) == old:
                    x.params[k] = new
        if self.rollback == old:
            self.rollback = new
        if old in self._parts:
            self._parts[new] = self._parts.pop(old)
        if old in self._sigs:
            self._sigs[new] = self._sigs.pop(old)
        # ... including what a pending ✕ took away, or the ↩ that undoes it
        # would leave the renamed row struck (see _struck_by)
        self._struck_by = {(new if k == old else k):
                           [new if i == old else i for i in v]
                           for k, v in self._struck_by.items()}
        # the viewport keys its bodies by feature id, so a rename IS a change
        # of what is drawable: the fingerprint must move, or picks and
        # overlays keep resolving the OLD id (found by the P2 code review)
        self._stamp_geometry()

    # -- deleting: dependency-aware, like Fusion's browser Delete ------------
    def remove(self, feature_id: str, mode: str = "auto") -> dict:
        """Delete a feature AND keep the tree valid.

        The old rule was "refuse if anything downstream uses it". An
        AI-authored tree is one long chain (sketch -> extrude tool -> cut,
        repeated 70 deep), so that rule made every feature but the LAST
        undeletable -- the #1 editing complaint. Fusion deletes what you point
        at and repairs the history around it; these modes do the same:

          "auto"    (default) reconnect what can be reconnected -- a dependent
                    is rewired to the deleted node's own upstream body (the
                    pass-through a suppress would give), dependents that
                    CANNOT be reconnected go with it, and tool bodies that
                    existed only to feed a deleted cut are swept up so no
                    orphan prism is left floating in the viewport.
          "cascade" no reconnecting: the node and everything downstream.
          "strict"  the old behaviour -- refuse if anything depends on it.

        Returns the plan that was applied (see `remove_plan`) so the caller can
        tell the user exactly what went, in the user's own feature names.
        """
        plan = self.remove_plan(feature_id, mode)
        gone = set(plan["deleted"])
        rewire = {r["id"]: r["to"] for r in plan["rewired"]}
        self.features = [f for f in self.features if f.id not in gone]
        for f in self.features:
            if f.id in rewire:
                f.inputs = list(rewire[f.id])
        if self.rollback in gone:
            self.rollback = None            # the bar cannot point at a ghost
        self._mark_stale()
        return plan

    def set_suppressed(self, feature_id: str, value: bool) -> None:
        """Set the suppress flag by hand (/api/feature/suppress, the AI, the
        MCP) — NOT the tree's ✕, which is strike().

        This feature's flag becomes its OWN business, so it is dropped from
        every ✕'s record of what that ✕ swept up — otherwise striking A (which
        swept B), then suppressing and re-suppressing B by hand, then pressing
        ↩ on A, brings B back although the last hand on B struck it
        deliberately (measured 2026-09-12, P5b review round two).

        The record KEYED on this feature is left alone on purpose: what A's ✕
        took away does not change because someone toggled A's flag afterwards,
        and dropping it would fall back to the recomputed plan — which is the
        very thing round one found bringing unrelated rows back."""
        self.get(feature_id).suppressed = bool(value)
        for k, v in self._struck_by.items():
            if k != feature_id and feature_id in v:
                self._struck_by[k] = [i for i in v if i != feature_id]
        self._mark_stale()

    def strike(self, feature_id: str) -> dict:
        """SOFT delete (user mandate 2026-08-31: "instead of deleting the
        operation, just strike out that operation, also delete it in the
        design — if I want it back I simply press undo on that struck-out
        feature"). The geometry is removed exactly as `remove` would, but the
        rows STAY in the tree, struck out, and nothing is rewired — so
        restoring is exact.

        It works because the two mechanisms were built to agree: the delete
        plan's healing rewires each survivor to "the pass-through a suppress
        would give", and rebuild resolves a suppressed node to its first
        input's part. So suppressing precisely the set the plan would delete
        yields the same geometry as deleting it — reversibly."""
        f = self.get(feature_id)
        if f.suppressed:
            raise ValueError(f"'{feature_id}' is already struck out")
        plan = self.remove_plan(feature_id, "auto")
        gone = set(plan["deleted"])
        changed = []
        for f in self.features:
            if f.id in gone and not f.suppressed:
                f.suppressed = True
                changed.append(f.id)
        # what THIS ✕ took away, for the ↩ that undoes it (see _struck_by):
        # anything in the plan that was already struck stays the user's choice
        self._struck_by[feature_id] = changed
        self._mark_stale()
        return plan

    def unstrike(self, feature_id: str) -> dict:
        """Put a struck-out feature back — geometry and all.

        The set is what THIS ✕ actually suppressed (`_struck_by`), so a
        feature the user had already struck on purpose stays struck; a
        document reopened since the strike carries no such record and falls
        back to the delete plan, which is all a file knows.

        PLUS the struck ANCESTORS the restored set cannot build without:
        restoring an extrude whose sketch is still struck would bring it back
        broken, so the sketch comes back with it. A struck ancestor that hands
        its own input down is NOT one of those — rebuild resolves a suppressed
        node to its first input's part — and pulling those back anyway turned
        the logo back on in designs/esp32-remote and milled 227 mm3 away from
        a part the user had switched it off in (P5b review, 2026-09-12).
        `_passthrough` decides "hands it down", which is the same rule the
        delete plan heals with, so the two mechanisms still agree."""
        if not self.get(feature_id).suppressed:
            raise ValueError(f"'{feature_id}' is not struck out")
        plan = self.remove_plan(feature_id, "auto")
        recorded = self._struck_by.get(feature_id)
        # `is not None`, not truthiness: a record pruned down to nothing by
        # set_suppressed means "that ✕ swept up only its own row", and falling
        # back to the recomputed plan there is exactly round one's bug
        back = set(recorded if recorded is not None else plan["deleted"])
        back.add(feature_id)
        by_id = {f.id: f for f in self.features}
        kinds = self._kinds()
        still = {f.id for f in self.features if f.suppressed} - back
        stack = list(back)
        while stack:                       # walk upstream of everything restored
            f = by_id.get(stack.pop())
            if f is None:
                continue
            for dep in f.inputs:
                d = by_id.get(dep)
                if d is None or not d.suppressed or dep in back:
                    continue
                if self._passthrough(dep, still, by_id, kinds) is not None:
                    continue               # struck, but it passes its input down
                back.add(dep)
                still.discard(dep)
                stack.append(dep)
        plan["restored"] = [f.id for f in self.features if f.id in back]
        for f in self.features:
            if f.id in back:
                f.suppressed = False
        self._struck_by.pop(feature_id, None)
        self._mark_stale()
        return plan

    def remove_plan(self, feature_id: str, mode: str = "auto") -> dict:
        """What deleting `feature_id` WOULD do -- computed without mutating, so
        the UI can ask "this also removes X and Y, go ahead?" first."""
        if mode not in DELETE_MODES:
            raise ValueError(f"unknown delete mode '{mode}' -- "
                             f"use one of {list(DELETE_MODES)}")
        self.get(feature_id)                # KeyError if there is no such node
        by_id = {f.id: f for f in self.features}
        kinds = self._kinds()

        if mode == "strict":
            dependents = [f.id for f in self.features
                          if feature_id in f.inputs
                          or feature_id in self.param_refs(f)]
            if dependents:
                raise ValueError(
                    f"cannot remove '{feature_id}': used by {dependents}")
            return self._delete_plan(feature_id, mode, {feature_id},
                                     set(), set(), {})

        heal = mode == "auto"
        gone, cascaded, rewired = {feature_id}, set(), {}
        while True:                          # deletions can cascade further
            rewired, newly = {}, set()
            for f in self.features:
                if f.id in gone:
                    continue
                ins, base_ok = [], True
                for i, dep in enumerate(f.inputs):
                    keep = dep
                    if dep in gone:
                        keep = (self._passthrough(dep, gone, by_id, kinds)
                                if heal else None)
                    if keep is None:
                        if i == 0:
                            base_ok = False  # cut's FIRST input is the stock
                    elif keep not in ins:
                        ins.append(keep)     # never feed one node twice
                # a pattern whose SEED is going cannot be healed: rewiring it to
                # the seed's upstream would repeat a different feature, so it goes
                lost_seed = any(r in gone for r in self.param_refs(f))
                if (lost_seed or len(ins) < _min_inputs(f.op)
                        or (f.op == "cut" and not base_ok)):
                    newly.add(f.id)
                elif ins != f.inputs:
                    rewired[f.id] = ins
            if not newly:
                break
            gone |= newly
            cascaded |= newly
        orphans = self._orphan_sweep(gone, rewired, by_id) if heal else set()
        gone |= orphans
        return self._delete_plan(feature_id, mode, gone, cascaded, orphans,
                                 rewired)

    def _kinds(self) -> dict:
        """id -> "sketch" | "solid": what each feature hands downstream."""
        kind = {}
        for f in self.features:
            if f.op == "move" and f.inputs:          # move passes its type on
                kind[f.id] = kind.get(f.inputs[0], "solid")
            else:
                kind[f.id] = _kind_of(f.op)
        return kind

    @staticmethod
    def _passthrough(dep: str, gone: set, by_id: dict, kinds: dict):
        """The surviving upstream feature a dependent should reconnect to when
        `dep` is deleted: walk the first-input chain past other deleted nodes.
        Refused when the TYPE would change -- an extrude's input is a sketch,
        so a downstream cut cannot take it; those dependents cascade instead."""
        cur, seen = dep, set()
        while cur in gone:
            f = by_id.get(cur)
            if f is None or not f.inputs or cur in seen:
                return None
            seen.add(cur)
            nxt = f.inputs[0]
            if nxt not in by_id or kinds.get(nxt) != kinds.get(cur):
                return None
            cur = nxt
        return cur

    def _orphan_sweep(self, gone: set, rewired: dict, by_id: dict) -> set:
        """Sweep up the TOOL geometry a delete leaves behind.

        An AI-authored pocket is three nodes: sketch -> extrude (a tool prism)
        -> cut. Deleting only the cut would leave that prism floating in the
        viewport as a stray body, so the delete would look broken. A feature is
        swept when (a) nothing consumes it any more, (b) every feature that DID
        consume it is going away, and (c) one of those consumers used it in a
        TOOL slot (cut/intersect, not the base). Real bodies survive: deleting
        a fuse leaves both of its bodies -- exactly like Fusion -- because a
        fuse has no tool slot. The walk up a swept node's feeders stops at a
        FACE REFERENCE: a sketch drawn on a body names that body as an input,
        but the body is where the sketch sits, not tool geometry. Following it
        swept a whole 14-feature tree from its last cut (gear-case,
        2026-08-31: "removed one feature, 0 left")."""
        def has_live_consumer(fid, swept):
            for f in self.features:
                if f.id in gone or f.id in swept:
                    continue
                if (fid in rewired.get(f.id, f.inputs)
                        or fid in self.param_refs(f)):   # a live pattern's seed stays
                    return True
            return False

        queue = []
        for gid in gone:                     # tool inputs of the deleted nodes
            g = by_id.get(gid)
            if g is not None and g.op in ("cut", "intersect"):
                queue += [d for d in g.inputs[1:] if d not in gone]
        queue = list(dict.fromkeys(queue))
        swept = set()
        while queue:
            fid = queue.pop(0)
            if fid in swept or fid in gone or has_live_consumer(fid, swept):
                continue
            swept.add(fid)
            f = by_id.get(fid)
            if f is not None:                 # its own feeders may now be idle
                # A face reference is the FIRST input: the body the sketch is
                # drawn on. Skip that one edge, not the whole node, so a face
                # op that ever gains a second input (a path, a rail) still has
                # that genuinely disposable geometry swept with it.
                feeders = (f.inputs[1:] if f.op in sk.FACE_REFERENCE_OPS
                           else f.inputs)
                queue += [d for d in feeders
                          if d not in gone and d not in swept]
        return swept

    def _delete_plan(self, target, mode, gone, cascaded, orphans,
                     rewired) -> dict:
        order = [f.id for f in self.features if f.id in gone]
        plan = {
            "target": target,
            "mode": mode,
            "deleted": order,
            "cascaded": [i for i in order if i in cascaded],
            "orphans": [i for i in order if i in orphans],
            "rewired": [{"id": fid, "from": list(self.get(fid).inputs),
                         "to": list(ins)}
                        for fid, ins in rewired.items()],
            "remaining": len(self.features) - len(order),
        }
        plan["summary"] = _delete_summary(plan)
        return plan

    # -- content addressing --------------------------------------------------
    def _signature(self, f: Feature, sigs: dict) -> str:
        """Identity of what this feature WILL build: its op, its parameters and
        the signatures of its inputs. Inputs by signature (not by id) so a
        rename costs nothing and an upstream edit invalidates everything below
        it automatically."""
        payload = {
            "op": f.op,
            "params": _canon_number(f.params),
            "suppressed": f.suppressed,
            "inputs": [sigs.get(dep, "?") for dep in f.inputs],
        }
        if f.op in FILE_BACKED_OPS:
            try:                       # the file IS part of the input
                st = os.stat(str(f.params.get("file", "")))
                payload["file_stamp"] = [st.st_mtime_ns, st.st_size]
            except OSError:
                payload["file_stamp"] = None
        blob = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha1(blob.encode("utf-8")).hexdigest()

    def _cache_get(self, sig: str):
        hit = self._cache.get(sig)
        if hit is not None:            # keep it warm (LRU by re-insertion)
            del self._cache[sig]
            self._cache[sig] = hit
        return hit

    def _cache_put(self, sig: str, part, problems, volume, pieces=None,
                   notes=None) -> None:
        self._cache[sig] = (part, list(problems), volume, pieces, list(notes or []))
        while len(self._cache) > CACHE_MAX:
            self._cache.pop(next(iter(self._cache)))     # oldest out

    def _mark_stale(self):
        for f in self.features:
            f.status = "stale"
        self._parts.clear()
        self.spec_problems = []
        self.warnings = []

    # -- rebuild: deterministic, verified ------------------------------------
    def rebuild(self) -> bool:
        """Evaluate the tree through the verified blocks. Returns overall ok.
        Never raises for geometry problems — they land in feature.problems.
        If `rollback` names a feature, evaluation stops after it (features
        beyond the bar are marked, not built) — like dragging the SolidWorks
        rollback bar up the tree."""
        self._parts.clear()
        ok = True
        past_bar = False
        sigs: dict = {}
        for f in self.features:                 # cheap: no geometry involved
            sigs[f.id] = self._signature(f, sigs)
        for f in self.features:
            if past_bar:
                f.status, f.problems, f.volume = "stale", ["(after rollback bar)"], None
                # not built: it has nothing to report. `pieces` too — with
                # the bar parked before a severing cut, `_check_pieces`
                # (which filters only `suppressed`) went on telling the user
                # the part was in 2 separate pieces while it was whole
                # (measured, fourth review follow-up 2026-09-09).
                f.notes, f.pieces = [], None
                continue
            if self.rollback is not None and f.id == self.rollback:
                past_bar = True     # build this one, stop after
            if f.suppressed:
                f.status, f.problems, f.volume = "ok", ["(suppressed)"], None
                # A suppressed feature keeps its notes otherwise, and
                # `warnings` republishes them (line ~1211), so the tree's info
                # box stated a fact about geometry that is NOT in the model -
                # the user switched the sketch off and was still told what one
                # of its entities does (fourth code review, 2026-09-09).
                # `pieces` was the same fact by another name and was missed
                # then: the struck row went on saying "pieces 2", and
                # `_check_pieces` took that stale count as the BASELINE for
                # the feature below it, so a part measurably in two pieces was
                # reported by nothing at all (section 2 review, 2026-09-10).
                f.notes, f.pieces = [], None
                if f.inputs:
                    self._parts[f.id] = self._parts.get(f.inputs[0])
                continue
            hit = self._cache_get(sigs[f.id])
            if hit is not None:
                # identical inputs -> identical geometry: skip the build AND
                # the health check, which together are most of a rebuild
                part, problems, volume, pieces, *rest = hit
                f.problems, f.volume, f.pieces = list(problems), volume, pieces
                f.notes = list(rest[0]) if rest and rest[0] else []
                f.status = "ok" if not problems else "failed"
                self._parts[f.id] = part
                if f.status == "failed":
                    ok = False
                continue
            try:
                sk.drain_notes()                 # only THIS feature's notes below
                part = self._eval(f)
                # 2D result: check area, not solid health. Classified by OP as
                # well as type — disjoint entities compose into a Compound that
                # is not a Sketch instance, and solid-checking a 2D profile
                # produced false "empty solid" failures on correct designs.
                if f.op in sk.SKETCH_PRODUCERS or sk.is_sketch(part):
                    area = getattr(part, "area", 0.0)
                    f.problems = [] if area > 0 else ["sketch is empty"]
                    f.volume = None
                    f.pieces = None
                    f.status = "ok" if not f.problems else "failed"
                else:
                    # check_valid=False here: OpenCASCADE's validity analysis is
                    # ~270 ms on a large solid, and the rebuild would pay it once
                    # per feature. Every BODY of the design still gets the full
                    # check, in the deep-check pass right after this loop, so an
                    # invalid part can never reach the user unreported.
                    f.problems = inspector.health(part, check_valid=False)
                    f.volume = round(part.volume, 2)
                    f.pieces = n_solids(part)
                    f.status = "ok" if not f.problems else "failed"
                f.notes = sk.drain_notes()
                self._parts[f.id] = part
                self._cache_put(sigs[f.id], part, f.problems, f.volume,
                                f.pieces, f.notes)
            except Exception as e:
                # NEVER repr(e) here: this string is painted straight into the
                # feature row. A zero thickness read `Standard_DomainError('')`
                # and a string in a dimension printed twelve lines of pybind11
                # constructor overloads (measured 2026-09-10, section 5
                # review). blocks.plain_cause is the one translator.
                f.status, f.problems, f.volume = (
                    "failed", [blocks.plain_cause(e)], None)
                f.pieces = None
                f.notes = []
                sk.drain_notes()
                self._parts[f.id] = None
                # cache the FAILURE too: a broken parameter must not cost a
                # full re-evaluation on every rebuild while the user fixes it.
                # NOT a transient one (kernelguard.KernelGone: the geometry
                # worker died or was stopped). That is not a broken parameter,
                # the cache is shared by every tab in the process, and a user
                # who presses the same button again must get a real attempt
                # instead of yesterday's crash read back to them.
                if not getattr(e, "transient", False):
                    self._cache_put(sigs[f.id], None, f.problems, None, None)
            if f.status == "failed":
                ok = False

        self._sigs = sigs
        self._stamp_geometry()

        # A cut tool that STOPS INSIDE the material does not clear it, it
        # slices it, and whatever sat beyond the cut is left floating. The user
        # has reported this three times as "changing the number creates a new
        # body instead of changing the height", and a warning plainly is not a
        # fix. `through` (extrude's through-all extent) is the cure, so apply it
        # — but only where it demonstrably IS the cure.
        if not self._healing:
            fixed = self._heal_stranding_cuts()
            if fixed:
                self._healing = True
                try:
                    ok = self.rebuild()
                finally:
                    self._healing = False
                by_id = {f.id: f for f in self.features}
                movers = [by_id[t].inputs[0] for t in fixed
                          if by_id.get(t) and by_id[t].inputs]
                self.warnings = list(self.warnings) + [
                    "Extended " + ", ".join(f"'{t}'" for t in fixed) +
                    " to cut all the way through — at that distance the tool "
                    "stopped inside the material and left loose pieces. "
                    "'through' is now ticked on "
                    + ("it" if len(fixed) == 1 else "them") +
                    ", so the distance no longer changes anything: to raise or "
                    "lower this, edit the OFFSET on "
                    + ", ".join(f"'{m}'" for m in movers) +
                    ". Untick 'through' for the old behaviour."]
                return ok

        # Deep check on EVERY BODY OF THE DESIGN. Intermediates were checked
        # without OpenCASCADE validity above for speed; the bodies the user
        # actually gets are validated in full, and a failure here is a real
        # failure. It used to check the tree's TAIL alone — but a design
        # legitimately has several bodies (result_bodies(), the same rule the
        # viewport and the exporter follow), so an invalid body that was not the
        # tail was never validated: its row stayed green and _export_blockers,
        # which trusts `status`, handed it to the STEP file (2026-09-07 review;
        # the same class as the export that shipped one body of four).
        #
        # The verdict rides the body's content signature, so checking N bodies
        # instead of one does not cost N times ~270 ms on every rebuild: a body
        # that did not change is not re-validated. (The tail used to pay it on
        # every single rebuild, cache hit or not, so this is cheaper than what
        # it replaces for an unchanged design.)
        by_id_deep = {f.id: f for f in self.features}
        for fid in self.leaf_solid_ids():
            fd = by_id_deep.get(fid)
            if fd is None or fd.status != "ok":
                continue
            part = self._parts.get(fid)
            if part is None or sk.is_sketch(part):
                continue
            sig = sigs.get(fid)
            verdict = self._valid_cache.get(sig) if sig else None
            if verdict is None:
                verdict = _deep_valid(part)
                if sig:
                    self._valid_cache[sig] = verdict
                    while len(self._valid_cache) > CACHE_MAX:
                        self._valid_cache.pop(next(iter(self._valid_cache)))
            if verdict is False:
                fd.problems = list(fd.problems) + [
                    "OpenCASCADE reports the solid is invalid"]
                fd.status = "failed"
                ok = False

        self._check_dangling()
        self.spec_problems = []
        self.spec_checked = True
        if self.rollback is not None:
            self.spec_checked = False
            self.spec_problems = ["the spec is not checked while the rollback "
                                  "bar is parked — release it to check"]
            return ok
        # The spec is checked against the WHOLE design — every body — not the
        # tree's tail. Checking result() measured one body of a multi-body
        # design, so the size/hole/solid-count guarantee covered a fraction of
        # the part: on designs/esp32-remote it reported the case as 11x57x1mm
        # (a 249mm3 leaf) instead of the 90x200x12mm it is. The signature has
        # to span EVERY leaf for the same reason, or editing a body that is
        # not the tail would hand back a cached verdict about the old geometry.
        # verify() also runs health() on what it is given — including
        # OpenCASCADE's validity analysis, over the WHOLE design rather than
        # the tail. Every body has already been validated one by one in the
        # deep pass above, so this repeats work; it is left as it is because
        # verify() is a self-contained guarantee for every caller (the MCP and
        # the export readback use it too), it only runs when a spec is set,
        # and the result is cached on the signature of every leaf below.
        leaves = self.leaf_solid_ids()
        if ok and self.spec and not leaves:
            # "no leaves" used to mean "nothing to check", so a design with
            # NOTHING in it reported that it met a spec demanding one
            # 20x20x10 solid (measured, section 4 review 2026-09-10 — both
            # doors: a combiner that ate the only body, and striking it out).
            # A guarantee about geometry that is not there is the one thing
            # this project may never say.
            self.spec_problems = ["the design has no bodies to check against "
                                  "the spec — nothing is built"]
            return False
        if ok and self.spec and leaves:
            spec_sig = hashlib.sha1(json.dumps(
                [[sigs.get(fid) for fid in leaves], self.spec],
                sort_keys=True, default=str).encode("utf-8")).hexdigest()
            if self._spec_cache and self._spec_cache[0] == spec_sig:
                self.spec_problems = list(self._spec_cache[1])
                return not self.spec_problems
            try:
                spec_obj = self._spec_obj()
            except Exception as e:
                self.spec_problems = [f"spec is malformed: {e!r}"]
                return False
            self.spec_problems = inspector.verify(self.result_shape(), spec_obj)
            self._spec_cache = (spec_sig, list(self.spec_problems))
            ok = not self.spec_problems
        return ok

    def _eval(self, f: Feature):
        ins = []
        for dep in f.inputs:
            p = self._parts.get(dep)
            if p is None:
                raise ValueError(f"input '{dep}' is unavailable (failed upstream?)")
            ins.append(p)

        if f.op in CREATORS:
            return CREATORS[f.op](**self._clean(f.params))
        if f.op in MODIFIERS:
            if len(ins) != 1:
                raise ValueError(f"'{f.op}' needs exactly 1 input")
            _check_modifier_input(f.op, f.inputs[0], ins[0])
            kw = self._clean(f.params)
            if f.op in pattern.SEEDED_OPS and kw.get("seed"):
                kw.update(self._seed_parts(f, kw["seed"]))   # the seed's before / after bodies
            return MODIFIERS[f.op](ins[0], **kw)
        if f.op == "move":
            if len(ins) != 1:
                raise ValueError("'move' needs exactly 1 input")
            return Pos(*_move_offsets(f.params)) * ins[0]
        if f.op in COMBINERS:
            if len(ins) < 2:
                raise ValueError(f"'{f.op}' needs 2+ inputs")
            _check_combiner_inputs(f.op, f.inputs, ins)
            return COMBINERS[f.op](ins)
        raise ValueError(f"unknown op '{f.op}'")

    @staticmethod
    def _clean(params: dict) -> dict:
        """JSON round-trips tuples into lists; blocks accept lists fine, but
        convert point lists' inner items to tuples for safety."""
        out = {}
        for k, v in params.items():
            if (isinstance(v, list) and v and isinstance(v[0], (list, tuple))):
                out[k] = [tuple(item) for item in v]
            else:
                out[k] = v
        return out

    def _spec_obj(self) -> inspector.Spec:
        return inspector.spec_from_dict(self.spec)

    def consumed_ids(self) -> set[str]:
        """Ids swallowed by a downstream feature — what should NOT be shown on
        its own (the viewport's bodies and floating sketches both filter on
        this).

        Face-reference ops (sketch_on_face, extrude_face) do NOT consume their
        body input — they only point at a face. Counting them as consumers made
        the base body vanish as soon as a face sketch on it was extruded.

        Neither does a SUPPRESSED (struck-out) feature: its geometry is gone,
        so whatever it used must come back on screen. A struck-out logo cut
        kept "consuming" the case body, so the moment the next extrude made a
        new leaf, the whole body vanished from the viewport (reported
        2026-09-01: "the whole back body vanished"). But a suppressed node IS
        a pass-through to its first input during rebuild — so an ACTIVE
        feature consuming a struck id really consumes whatever that id
        resolves to, and the resolution must follow the chain."""
        by_id = {f.id: f for f in self.features}
        return {self._live_source(dep, by_id) for f in self.features
                if not f.suppressed and f.op not in sk.FACE_REFERENCE_OPS
                for dep in f.inputs}

    def _live_source(self, dep: str, by_id: dict | None = None) -> str:
        """The id whose solid `dep` actually hands downstream.

        A struck node is a pass-through to its first input during rebuild, so
        its OWN (cleared) volume and piece count are the wrong thing to read
        about it -- follow the chain to the feature that really built the
        body. ONE copy of the walk: consumed_ids, _check_pieces and
        _check_idle_booleans each had their own."""
        by_id = by_id if by_id is not None else {f.id: f for f in self.features}
        seen = set()
        while (dep in by_id and by_id[dep].suppressed
               and by_id[dep].inputs and dep not in seen):
            seen.add(dep)
            dep = by_id[dep].inputs[0]
        return dep

    def leaf_solid_ids(self) -> list[str]:
        """Ids of every built SOLID body that no downstream feature consumes —
        the bodies that should be VISIBLE in the viewport. Multiple leaves are
        normal mid-build (a base plate and a wall before they are fused); the
        old viewport showed only the last one, so positioning a second body was
        blind. The last leaf is the result; the rest render as ghosts."""
        consumed = self.consumed_ids()
        out = []
        for f in self.features:
            if f.suppressed or f.id in consumed:
                continue
            part = self._parts.get(f.id)
            if part is None or f.op in sk.SKETCH_PRODUCERS or sk.is_sketch(part):
                continue    # sketches render separately; failed parts flag themselves
            out.append(f.id)
        return out

    def _heal_stranding_cuts(self) -> list[str]:
        """Tick `through` on extrude tools whose cut strands material.

        Only ever applied when it is PROVEN to be the fix: the cut must have
        left more pieces than it was given, and switching the tool to
        through-all must bring the count back to what it was. That test is what
        makes this safe to do automatically — a cut that was MEANT to sever a
        part stays severed when the tool is made longer, so it is never
        "healed", and a pocket (a cut that legitimately stops inside) never
        strands anything and so is never touched.

        Returns the ids of the tools it changed."""
        fixed: list[str] = []
        by_id = {f.id: f for f in self.features}
        for f in self.features:
            if f.op != "cut" or f.suppressed or not f.pieces or f.pieces <= 1:
                continue
            base = self._parts.get(f.inputs[0]) if f.inputs else None
            if base is None:
                continue
            base_pieces = n_solids(base)
            if base_pieces is None or f.pieces <= base_pieces:
                continue                       # already in pieces, or unchanged
            for tid in f.inputs[1:]:
                t = by_id.get(tid)
                # "through" ABSENT means nobody has decided — that is the
                # script-generated case this exists for. Present means the user
                # decided, either way, and an explicit False is them saying no:
                # the warning tells them to untick it for the old behaviour, so
                # re-ticking it here would make that advice a lie.
                if (t is None or t.op != "extrude" or t.suppressed
                        or "through" in t.params):
                    continue
                # The proof below is computed for THIS cut only, so a tool
                # some other feature ALSO uses must be left alone: ticking
                # `through` on a shared prism deepened the other cut by
                # 3600 mm3 without testing it and without saying so
                # (measured, section 4 review 2026-09-10 — and
                # designs/cam-cover-plaque already shares a tool prism
                # between two combiners).
                if sum(1 for x in self.features
                       if not x.suppressed and tid in (x.inputs or [])) > 1:
                    continue
                # A probe is a full extrude PLUS a boolean, and its answer is
                # a pure function of the geometry it asks about. A cut that
                # was MEANT to sever never passes the test below, and nothing
                # writes `through` for it, so the probe ran again on every
                # single rebuild — 13.0 ms against 0.1 ms on a four-feature
                # design where every other feature is a cache hit (section 2
                # review, 2026-09-10). The memo rides the cut's own content
                # signature, so any real change upstream asks again.
                memo = (self._sigs.get(f.id) or "", tid)
                if memo in self._heal_tried:
                    continue
                try:
                    probe = sk.extrude_sketch(
                        **{**self._clean(t.params),
                           "sketch": self._parts.get(t.inputs[0]),
                           "through": True})
                    trial = base
                    for other in f.inputs[1:]:
                        trial = trial - (probe if other == tid
                                         else self._parts.get(other))
                except Exception:
                    self._remember_heal_failed(memo)
                    continue
                # The piece COUNT alone is not proof. Since the offset
                # method (2026-08-27) cuts run DOWNWARD from a face, so
                # through-all reaches 2m INTO the part instead of out of it --
                # it drills clean through, which also lands on "1 piece" while
                # destroying the part (and on a vacuum table a through hole
                # breaks the job loose). So require that the heal removed only
                # the STRANDED lumps: the healed volume must match the current
                # volume minus everything that is not the main body.
                cur = self._parts.get(f.id)
                if cur is None:
                    self._remember_heal_failed(memo)
                    continue
                lumps = sorted((sv.volume for sv in cur.solids()), reverse=True)
                stranded = sum(lumps[1:])
                want = cur.volume - stranded
                if n_solids(trial) == base_pieces and                         trial.volume >= want - max(1e-6, 1e-9 * want):
                    t.params["through"] = True     # the design is now correct,
                    fixed.append(tid)              # not merely reported on
                else:
                    self._remember_heal_failed(memo)
        if fixed:
            self._mark_stale()
        return fixed

    def _remember_heal_failed(self, memo: tuple) -> None:
        """This through-all probe has been tried on this exact geometry and
        did not help, so it never needs running again for it."""
        self._heal_tried[memo] = True
        while len(self._heal_tried) > CACHE_MAX:
            self._heal_tried.pop(next(iter(self._heal_tried)))   # oldest out

    def _check_pieces(self) -> list:
        """Name the feature that broke the part into pieces.

        A feature is called out when its solid has MORE lumps than the body it
        was built from: that is the moment a boss stopped touching the part, or
        a cut severed it. Legitimately multi-body designs (an assembly, two
        plates fused apart) still report — the count is the point, and it is
        never an error, because "two pieces" is sometimes exactly what the user
        wants. It just must not be silent."""
        notes = []
        by_id = {x.id: x for x in self.features}

        def built_from(dep: str):
            return by_id.get(self._live_source(dep, by_id))

        for f in self.features:
            if f.suppressed or f.pieces is None or f.pieces <= 1:
                continue
            # Only BODY-shaping features can "break the part": an extrude of a
            # sketch holding 8 pilot circles is 8 prisms by design, and warning
            # about it buried the real signal (esp32-remote reported a dozen
            # notes, all of them tool prisms doing exactly their job).
            if f.op not in COMBINERS and f.op not in MODIFIERS:
                continue
            if f.op in sk.SKETCH_PRODUCERS or f.op in ("extrude", "revolve",
                                                       "loft", "sweep"):
                continue
            # A pattern's COPY form (no `seed`) exists to produce `count`
            # SEPARATE bodies, so N pieces is the number the user typed, not
            # a part that fell apart. 16 designs in the library were each
            # being told "something in it no longer touches the rest" — the
            # exact false signal the exclusion above exists to prevent. With
            # a seed the op edits ONE body, so it keeps the check.
            if (f.op in ("linear_pattern", "polar_pattern")
                    and not f.params.get("seed")):
                continue
            base = None
            for dep in f.inputs:                # the body it was built from
                d = built_from(dep)
                if d is not None and d.pieces:
                    base = d.pieces
                    break
            if base is not None and f.pieces <= base:
                continue                        # it was already in pieces
            notes.append(
                f"'{f.id}' ({f.op}) leaves the part in {f.pieces} separate "
                f"pieces" + (f" (its input was {base})" if base else "") +
                " — something in it no longer touches the rest. Not an error "
                "if you meant it; a detached boss or a cut right through "
                "usually is not.")
        return notes

    def _check_idle_booleans(self) -> list:
        """Name a cut that removed NOTHING — or a join that added nothing.

        The tool body is consumed by the boolean whether it reached the target
        or not, so a tool that misses simply DISAPPEARS from the viewport while
        the body is untouched and every row stays green (measured: the cut's
        volume 4000.0 against its input's 4000.0, and not one warning).
        Fusion refuses the operation outright; the tree is allowed to keep it,
        but it may not keep it quietly.

        The JOIN half is the same silence through the Extrude tool's own door:
        a picked face pulled 4 mm INTO the body and left at the default Join
        fuses a prism that is already inside it — plate 24 000, prism 9 600,
        join 24 000 mm3, three green rows, nothing said (measured 2026-09-11,
        section 7 review). extrude.js now switches such a pull to Cut, but an
        explicit Join, the AI and the MCP path all still reach here."""
        notes = []
        by_id = {x.id: x for x in self.features}
        for f in self.features:
            if f.suppressed or f.op not in ("cut", "fuse") or f.volume is None \
                    or not f.inputs:
                continue
            base = by_id.get(self._live_source(f.inputs[0], by_id))
            if base is None or not base.volume or base.volume <= 0:
                continue
            if abs(f.volume - base.volume) > 0.01:      # both are 2dp-rounded
                continue
            if f.op == "cut":
                notes.append(
                    f"'{f.id}' (cut) removed no material — its tool "
                    f"{_name_list(f.inputs[1:])} does not reach "
                    f"'{f.inputs[0]}'. Move or lengthen the tool, or remove "
                    f"the cut.")
            else:
                notes.append(
                    f"'{f.id}' (join) added no material — "
                    f"{_name_list(f.inputs[1:])} is already inside "
                    f"'{f.inputs[0]}'. To take that shape OUT of the body make "
                    f"it a Cut; to add material, pull it the other way.")
        return notes

    def _check_dangling(self):
        """A leaf body that is NOT the displayed result can be a silent trap —
        chaining a modifier to the wrong upstream feature quietly drops the real
        part from the result while every status stays green. Name the strays.
        (Two leaves mid-build, e.g. base + wall before a fuse, are legitimate
        and now BOTH render — but until they are combined the earlier ones are
        still 'not the result', so we flag them so the state is never silent.)"""
        self.warnings = self._check_pieces() + self._check_idle_booleans()
        # what the ops wanted the user to hear (a taper that ended at its tip):
        # here, so the AI, MCP and API paths see it — not only the browser panel
        for f in self.features:
            for note in (f.notes or []):
                self.warnings.append(f"'{f.id}': {note}")
        rf = self._result_feature()
        if rf is None:
            return
        for fid in self.leaf_solid_ids():
            if fid == rf.id:
                continue
            # informational, not an error: separate bodies are everyday CAD
            # (Fusion's Bodies folder) — the note exists so an ACCIDENTAL
            # stray (chained from the wrong feature) is never silent
            self.warnings.append(
                f"'{fid}' and '{rf.id}' are separate bodies — normal while "
                f"modeling. Use Extrude's Join/Cut (or a fuse/cut feature) "
                f"to combine them, or remove '{fid}' if it was unintended.")

    # -- results --------------------------------------------------------------
    def _result_feature(self) -> Feature | None:
        """The feature whose part result() returns (rollback-aware)."""
        seen_bar = self.rollback is None
        for f in reversed(self.features):
            if not seen_bar:
                seen_bar = f.id == self.rollback
                if not seen_bar:
                    continue
            part = self._parts.get(f.id)
            if (not f.suppressed and part is not None
                    and f.op not in sk.SKETCH_PRODUCERS
                    and not sk.is_sketch(part)):
                return f
        return None

    def result(self):
        """The final SOLID — the last built, non-suppressed, non-sketch feature
        (respects the rollback bar, which stops building partway). Sketches are
        skipped: the deliverable of a design is a solid, not a 2D profile."""
        f = self._result_feature()
        return self._parts.get(f.id) if f else None

    def result_bodies(self) -> list:
        """EVERY built solid body of the design — what the export must contain.

        The one authority on "what is the design", shared by the viewport and
        the exporter so they can never disagree. It is leaf_solid_ids() turned
        into parts: a design is its unconsumed bodies, which is one solid in
        the common case and several whenever the user has a base plus a boss,
        a mirror with Join off, or a face-sketch chain (sketch_on_face does
        not consume the body it points at, so the base stays a body of its
        own). result() is the LAST of these — the tree's tail, useful for
        "the thing I just made", never for "the thing I designed".
        """
        return [p for p in (self._parts.get(fid) for fid in self.leaf_solid_ids())
                if p is not None]

    def result_shape(self):
        """The whole design as ONE shape to export or measure, or None.

        One body goes out bare — no assembly wrapper, so the everyday case is
        byte-for-byte what it always was. Several go into a Compound, which a
        STEP reader shows as N separate bodies; they are NOT fused, because
        bodies the user has not joined are not joined
        (probes/multibody_step_probe.py §3, §5).

        Exporting and measuring share this so a file can never contain
        something other than what was measured and reported.
        """
        bodies = self.result_bodies()
        if not bodies:
            return None
        return bodies[0] if len(bodies) == 1 else b3d.Compound(bodies)

    def _export_blockers(self) -> list:
        """Bodies of the design that did not build — the export is refused.

        A body of the design is any active, non-sketch feature that nothing
        downstream consumes (the same rule leaf_solid_ids() uses). If one of
        those has no built part — failed, or stale behind a rollback bar — the
        file would be handed over with a piece MISSING, which reads as "my
        edits are not in the STEP file" downstream. So it is named instead.

        Suppressed features and sketches are skipped: a struck-out feature's
        geometry is deliberately gone, and a 2D profile is not a body. A
        sketch-valued part (a moved profile) is skipped for the same reason.

        Two ways a body fails, and BOTH block (2026-09-07):

        * no part at all — the build raised, or it is stale behind a rollback
          bar. The old version walked backwards from the tail and stopped at
          the first built solid, so a failed branch sitting EARLIER than the
          tail was never noticed and its body silently vanished from the file.
        * a part that built but did not pass its health check — an empty
          solid, an open shell, a non-manifold body. rebuild() keeps the shape
          for these (only an exception nulls it), so testing `part is None`
          let them straight through: an empty cut result exported as a STEP
          holding ZERO solids and the UI called it a successful export, and in
          a multi-body design the bad body just disappeared behind plausible
          numbers. A failed feature beats a corrupt body.
        """
        consumed = self.consumed_ids()
        blockers = []
        for f in self.features:
            if (f.suppressed or f.id in consumed
                    or f.op in sk.SKETCH_PRODUCERS):
                continue
            part = self._parts.get(f.id)
            if part is not None and sk.is_sketch(part):
                continue            # a 2D profile is not a body of the design
            if part is None or f.status != "ok":
                blockers.append(f)
        return blockers

    def to_step(self, path: str) -> str:
        """Export the WHOLE FINISHED DESIGN — every body, never the transient
        build state.

        Two ways this used to hand over the wrong geometry, both fixed here:

        The rollback bar is edit plumbing — the sketch/extrude editors park
        it for isolation while they are open. Exporting while it is parked
        used to write whatever body happened to be last built (2026-08-31:
        a CAM import showed a bare cavity-cutter slab instead of the edited
        part). So a parked bar is released for the export and re-parked
        after — the restore rebuild is all cache hits — and a body that
        genuinely failed to build is refused BY NAME instead of silently
        exporting the intermediates that succeeded.

        And it exported result() — ONE body, the tree's tail — while a design
        legitimately has SEVERAL (2026-09-07: "i can see only half part of
        design and rest of them are missing"; designs/my-part-6 has four
        bodies totalling 424161.3 mm3 and the file held 585.6). Now every
        body in result_bodies() is written, as SEPARATE solids in one file,
        the way a multi-body part exports from Fusion or SolidWorks — the
        exporter does not fuse them, because bodies the user has not joined
        are not joined (probes/multibody_step_probe.py §5). One body still
        writes as a bare solid, with no assembly wrapper around it (§3).
        """
        self.exported_bodies = 0                 # never a stale count from before
        if not self._parts:
            raise RuntimeError("nothing to export — rebuild first / fix failures")
        parked = self.rollback
        if parked is not None:
            self.rollback = None
            self.rebuild()
        try:
            blockers = self._export_blockers()
            if blockers:
                what = "; ".join(
                    f"'{f.id}' ({f.problems[0]})" if f.problems else f"'{f.id}'"
                    for f in blockers)
                raise RuntimeError(
                    "cannot export: a body of the design did not build — "
                    f"{what}. Fix, strike out or delete the failed "
                    "feature(s), then export again.")
            shape = self.result_shape()
            if shape is None:
                raise RuntimeError(
                    "nothing to export — rebuild first / fix failures")
            b3d.export_step(shape, path)
            self.exported_bodies = len(self.result_bodies())   # what WAS written
            return path
        finally:
            if parked is not None:
                self.rollback = parked
                self.rebuild()

    def tree(self) -> str:
        """Render the tree the way a UI (or terminal) shows it."""
        lines = [f"{self.name}"]
        for f in self.features:
            badge = {"ok": "[OK]", "failed": "[FAIL]", "stale": "[ ? ]"}[f.status]
            sup = " (suppressed)" if f.suppressed else ""
            src = f" <- {','.join(f.inputs)}" if f.inputs else ""
            ps = ", ".join(f"{k}={v}" for k, v in f.params.items()
                           if not isinstance(v, list))
            lines.append(f"  {badge} {f.id}: {f.op}({ps}){src}{sup}")
            for p in f.problems:
                if p != "(suppressed)":
                    lines.append(f"        ! {p}")
        if self.spec:
            badge = ("[--]" if not self.spec_checked else
                     "[OK]" if not self.spec_problems else "[FAIL]")
            lines.append(f"  {badge} spec: " + ", ".join(
                f"{k}={v}" for k, v in self.spec.items() if v is not None))
            for p in self.spec_problems:
                lines.append(f"        ! {p}")
        return "\n".join(lines)

    # -- persistence: the recipe is the artifact ------------------------------
    def to_data(self) -> dict:
        """The document's intent (not its build status) as JSON-safe data."""
        return {
            "name": self.name,
            "spec": json.loads(json.dumps(self.spec)),
            "features": [{k: v for k, v in asdict(f).items()
                          if k in ("id", "op", "params", "inputs", "suppressed")}
                         for f in self.features],
        }

    @classmethod
    def from_data(cls, data: dict) -> "Document":
        doc = cls(name=data["name"], spec=data.get("spec", {}))
        # An op this build does not know is refused here, and that is the
        # SETTLED answer, not an oversight: a version restore says "cannot
        # open it -- it is still in the history" and a restored session tab
        # holding one is dropped while the others live
        # (test_version_api.py, test_session_restore.py). `op_params`
        # tolerating an unknown op is about walking the CATALOGUE without
        # raising, not a promise that the file opens. Proposed as a finding
        # in the section 2 review, 2026-09-10, and rejected on this evidence.
        for f in data["features"]:
            doc.add(f["id"], f["op"], f.get("params"), f.get("inputs"))
            doc.features[-1].suppressed = f.get("suppressed", False)
        return doc

    def save(self, path: str) -> str:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_data(), fh, indent=2)
        return path

    @classmethod
    def load(cls, path: str) -> "Document":
        with open(path, encoding="utf-8") as fh:
            return cls.from_data(json.load(fh))


# ---------------------------------------------------------------------------
# Self-test: a flange as a feature tree — build, EDIT, rebuild, save/load.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== 1. author a flange as a feature tree ===")
    doc = Document(name="flange-100")
    doc.add("body", "disc", {"radius": 50, "thickness": 10})
    doc.add("bore", "with_center_hole", {"radius": 15}, inputs=["body"])
    doc.add("bolts", "with_bolt_circle",
            {"count": 6, "bolt_radius": 4, "pitch_circle_dia": 76},
            inputs=["bore"])
    doc.spec = {"symmetry": 6, "n_solids": 1, "holes": {4.0: 6}, "tol": 0.5}

    ok = doc.rebuild()
    print(doc.tree())
    print("overall:", "PASS" if ok else "FAIL")

    print("\n=== 2. THE EDIT: bore 15 -> 12, one param, deterministic ===")
    doc.edit("bore", "radius", 12)
    print("after edit (before rebuild):")
    print(doc.tree())
    ok = doc.rebuild()
    print("after rebuild:")
    print(doc.tree())
    print("overall:", "PASS" if ok else "FAIL")

    print("\n=== 3. a BAD edit is caught and localized ===")
    doc.edit("bolts", "count", 5)          # spec demands 6 -> must FAIL
    ok = doc.rebuild()
    print(doc.tree())
    print("overall:", "PASS" if ok else "FAIL (expected)")
    doc.edit("bolts", "count", 6)          # put it back
    assert doc.rebuild()

    print("\n=== 4. save / load round-trip ===")
    doc.save("flange-100.tcad.json")
    doc2 = Document.load("flange-100.tcad.json")
    ok2 = doc2.rebuild()
    same = doc2.get("bolts").volume == doc.get("bolts").volume
    print(f"reloaded '{doc2.name}': rebuild={'PASS' if ok2 else 'FAIL'}, "
          f"volume identical: {same}")

    print("\n=== 5. deleting: strict refuses, auto repairs the history ===")
    try:
        doc.remove("body", mode="strict")
    except ValueError as e:
        print("strict remove('body') correctly refused:", e)
    probe = Document.from_data(doc.to_data())
    plan = probe.remove("bore")           # mid-chain: bolts must reconnect
    print("auto remove('bore'):", plan["summary"])
    print("bolts now built on:", probe.get("bolts").inputs)
    assert probe.rebuild(), probe.tree()

    doc.to_step("flange-100.step")
    print("\nwrote flange-100.step + flange-100.tcad.json")
