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
import hashlib
import json
import os
import re

import build123d as b3d
from build123d import Pos

import blocks
import inspector
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

# modifiers: exactly one upstream Part + numeric/string params
MODIFIERS = {
    "with_center_hole": blocks.with_center_hole,
    "with_bolt_circle": blocks.with_bolt_circle,
    "polar_pattern": blocks.polar_pattern,
    "rotate": blocks.rotate,
    "mirror": blocks.mirror_copy,
    "scale": blocks.scale_uniform,
    "linear_pattern": blocks.linear_pattern,
    "fillet": blocks.fillet_edges,
    "chamfer": blocks.chamfer_edges,
    "shell": blocks.shell_out,
    "extrude": sk.extrude_sketch,       # sketch -> solid
    "extrude_face": sk.extrude_face,    # solid's picked face -> prism (boss/pocket)
    "revolve": sk.revolve_sketch,       # sketch -> solid
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
    return sk.loft_sketches(parts)

COMBINERS = {"fuse": _fuse, "cut": _cut, "intersect": _intersect,
             "loft": _loft}

KNOWN_OPS = set(CREATORS) | set(MODIFIERS) | set(COMBINERS) | {"move"}

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


DELETE_MODES = ("auto", "cascade", "strict")

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
FILE_BACKED_OPS = {"import_stl"}

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


@dataclass
class Document:
    """An editable, savable, rebuildable design."""
    name: str
    features: list[Feature] = field(default_factory=list)
    spec: dict = field(default_factory=dict)   # inspector.Spec fields, JSON-safe
    spec_problems: list = field(default_factory=list)
    warnings: list = field(default_factory=list)  # non-fatal honesty flags
    rollback: str | None = None    # SolidWorks-style bar: build only up to this id
    _parts: dict = field(default_factory=dict, repr=False)   # id -> Part cache
    _cache: dict = field(default_factory=lambda: _SHARED_CACHE, repr=False)
    _spec_cache: tuple = field(default=None, repr=False)     # (sig, problems)
    _geom_version: str = field(default="", repr=False)       # what is drawable

    # -- authoring ----------------------------------------------------------
    def add(self, id: str, op: str, params: dict | None = None,
            inputs: list[str] | None = None) -> "Document":
        if op not in KNOWN_OPS:
            raise ValueError(f"unknown op '{op}' — allowed: {sorted(KNOWN_OPS)}")
        if any(f.id == id for f in self.features):
            raise ValueError(f"duplicate feature id '{id}'")
        for dep in (inputs or []):
            if not any(f.id == dep for f in self.features):
                raise ValueError(f"feature '{id}' references unknown input '{dep}'")
        self.features.append(Feature(id=id, op=op, params=params or {},
                                     inputs=list(inputs or [])))
        return self

    # -- editing (THE point of the tree) -------------------------------------
    def edit(self, feature_id: str, param: str, value) -> None:
        """Change ONE parameter of ONE named node. Nothing else can change."""
        f = self.get(feature_id)
        if param not in f.params:
            raise KeyError(f"feature '{feature_id}' has no parameter '{param}' "
                           f"(has: {list(f.params)})")
        f.params[param] = value
        self._mark_stale()

    def get(self, feature_id: str) -> Feature:
        for f in self.features:
            if f.id == feature_id:
                return f
        raise KeyError(f"no feature named '{feature_id}'")

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
        if self.rollback == old:
            self.rollback = new
        if old in self._parts:
            self._parts[new] = self._parts.pop(old)

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
            dependents = [f.id for f in self.features if feature_id in f.inputs]
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
                if len(ins) < _min_inputs(f.op) or (f.op == "cut" and not base_ok):
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
        fuse has no tool slot."""
        def has_live_consumer(fid, swept):
            for f in self.features:
                if f.id in gone or f.id in swept:
                    continue
                if fid in rewired.get(f.id, f.inputs):
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
            if f is not None:                # its own feeders may now be idle
                queue += [d for d in f.inputs
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

    def _cache_put(self, sig: str, part, problems, volume) -> None:
        self._cache[sig] = (part, list(problems), volume)
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
                continue
            if self.rollback is not None and f.id == self.rollback:
                past_bar = True     # build this one, stop after
            if f.suppressed:
                f.status, f.problems, f.volume = "ok", ["(suppressed)"], None
                if f.inputs:
                    self._parts[f.id] = self._parts.get(f.inputs[0])
                continue
            hit = self._cache_get(sigs[f.id])
            if hit is not None:
                # identical inputs -> identical geometry: skip the build AND
                # the health check, which together are most of a rebuild
                part, problems, volume = hit
                f.problems, f.volume = list(problems), volume
                f.status = "ok" if not problems else "failed"
                self._parts[f.id] = part
                if f.status == "failed":
                    ok = False
                continue
            try:
                part = self._eval(f)
                # 2D result: check area, not solid health. Classified by OP as
                # well as type — disjoint entities compose into a Compound that
                # is not a Sketch instance, and solid-checking a 2D profile
                # produced false "empty solid" failures on correct designs.
                if f.op in sk.SKETCH_PRODUCERS or sk.is_sketch(part):
                    area = getattr(part, "area", 0.0)
                    f.problems = [] if area > 0 else ["sketch is empty"]
                    f.volume = None
                    f.status = "ok" if not f.problems else "failed"
                else:
                    f.problems = inspector.health(part)
                    f.volume = round(part.volume, 2)
                    f.status = "ok" if not f.problems else "failed"
                self._parts[f.id] = part
                self._cache_put(sigs[f.id], part, f.problems, f.volume)
            except Exception as e:
                f.status, f.problems, f.volume = "failed", [repr(e)], None
                self._parts[f.id] = None
                # cache the FAILURE too: a broken parameter must not cost a
                # full re-evaluation on every rebuild while the user fixes it
                self._cache_put(sigs[f.id], None, f.problems, None)
            if f.status == "failed":
                ok = False

        # A fingerprint of what the viewport would draw. The UI skips refetching
        # and re-rendering the model when this has not moved — opening and
        # closing a sketch without touching anything changes nothing, and used
        # to cost a full re-tessellation plus a multi-megabyte transfer.
        self._geom_version = hashlib.sha1(json.dumps(
            [[f.id, sigs.get(f.id), f.suppressed] for f in self.features]
            + [self.rollback], default=str).encode("utf-8")).hexdigest()

        self._check_dangling()
        self.spec_problems = []
        if self.rollback is not None:
            self.spec_problems = ["(spec not checked while rolled back)"]
            return ok
        if ok and self.spec and self.result() is not None:
            rf = self._result_feature()
            spec_sig = hashlib.sha1(json.dumps(
                [sigs.get(rf.id if rf else ""), self.spec],
                sort_keys=True, default=str).encode("utf-8")).hexdigest()
            if self._spec_cache and self._spec_cache[0] == spec_sig:
                self.spec_problems = list(self._spec_cache[1])
                return not self.spec_problems
            try:
                spec_obj = self._spec_obj()
            except Exception as e:
                self.spec_problems = [f"spec is malformed: {e!r}"]
                return False
            self.spec_problems = inspector.verify(self.result(), spec_obj)
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
            return MODIFIERS[f.op](ins[0], **self._clean(f.params))
        if f.op == "move":
            if len(ins) != 1:
                raise ValueError("'move' needs exactly 1 input")
            p = f.params
            return Pos(float(p.get("x", 0)), float(p.get("y", 0)),
                       float(p.get("z", 0))) * ins[0]
        if f.op in COMBINERS:
            if len(ins) < 2:
                raise ValueError(f"'{f.op}' needs 2+ inputs")
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

    def leaf_solid_ids(self) -> list[str]:
        """Ids of every built SOLID body that no downstream feature consumes —
        the bodies that should be VISIBLE in the viewport. Multiple leaves are
        normal mid-build (a base plate and a wall before they are fused); the
        old viewport showed only the last one, so positioning a second body was
        blind. The last leaf is the result; the rest render as ghosts.

        Face-reference ops (sketch_on_face, extrude_face) do NOT consume their
        body input — they only point at a face. Counting them as consumers made
        the base body vanish as soon as a face sketch on it was extruded."""
        consumed = {dep for f in self.features
                    if f.op not in sk.FACE_REFERENCE_OPS
                    for dep in f.inputs}
        out = []
        for f in self.features:
            if f.suppressed or f.id in consumed:
                continue
            part = self._parts.get(f.id)
            if part is None or f.op in sk.SKETCH_PRODUCERS or sk.is_sketch(part):
                continue    # sketches render separately; failed parts flag themselves
            out.append(f.id)
        return out

    def _check_dangling(self):
        """A leaf body that is NOT the displayed result can be a silent trap —
        chaining a modifier to the wrong upstream feature quietly drops the real
        part from the result while every status stays green. Name the strays.
        (Two leaves mid-build, e.g. base + wall before a fuse, are legitimate
        and now BOTH render — but until they are combined the earlier ones are
        still 'not the result', so we flag them so the state is never silent.)"""
        self.warnings = []
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

    def to_step(self, path: str) -> str:
        part = self.result()
        if part is None:
            raise RuntimeError("nothing to export — rebuild first / fix failures")
        b3d.export_step(part, path)
        return path

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
            badge = "[OK]" if not self.spec_problems else "[FAIL]"
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
