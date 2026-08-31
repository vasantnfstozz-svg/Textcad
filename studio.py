"""
studio.py — TextCAD Studio: the local web app (API layer).

Run:  python studio.py   ->  opens http://127.0.0.1:8123 in your browser.

The UI lives in static/ (index.html + css/ + js/ modules). This file is the
HTTP API only; the CAD brains live in the core modules (document, blocks,
sketch, inspector, author, meanline, samples).

MULTI-DOCUMENT: the server holds many open designs at once — one per UI tab.
STATE["docs"] maps tab-id -> {doc, ok, rebuild_ms, history}; STATE["active"]
names the tab every /api call operates on. New / Open / Examples / AI-create
all open a NEW tab, so the previous design stays open to switch back to.

Every edit — spoken or clicked — flows through the SAME path:
Document.edit() -> deterministic rebuild through verified blocks -> per-node
health + spec verification. The LLM never regenerates a design during an edit.
"""

from __future__ import annotations
import base64
import json
import math
import os
import re
import webbrowser
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import build123d as b3d
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.GeomAbs import GeomAbs_SurfaceType
from OCP.TopAbs import TopAbs_Orientation, TopAbs_ShapeEnum
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS
from OCP.TopTools import TopTools_IndexedDataMapOfShapeListOfShape

import author
import blocks
import imgtrace
import measure as measurelib
import sketch as sketchlib
import sketch_trim as trimlib
import sketch_snap as snaplib
from document import Document
from history import History, HistoryError, diff_snapshots
import provenance
from samples import SAMPLES, sample_flange, sample_impeller, sample_compressor  # noqa: F401 (re-export for tests)

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
MESH_PATH = ROOT / "_studio_mesh.stl"
# how much a CHAT "delete X" may take before it must be done deliberately in
# the tree instead (a pocket group is 3 features; a whole design is not)
CHAT_DELETE_LIMIT = 6
DESIGNS = ROOT / "designs"
DESIGNS.mkdir(exist_ok=True)

app = FastAPI(title="TextCAD Studio")


@app.middleware("http")
async def _no_stale_assets(request, call_next):
    """Serve the UI (index.html + every JS/CSS module) with no-cache so the
    browser NEVER runs a stale mix — a fresh main.js importing cached old
    modules was booting the app half-dead. Local dev app: correctness over
    cache. This removes the need for ?v= cache-busters entirely."""
    resp = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static"):
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


@app.middleware("http")
async def _never_die(request, call_next):
    """Turn any unhandled endpoint exception into a JSON error.

    An exception escaping an endpoint gives a bare 500 whose body the UI cannot
    read, so the app looks dead even though the server is fine -- and OCP's
    errors derive from Exception, not RuntimeError, so narrow `except` barriers
    elsewhere do not catch them. The rule this project runs on is that a
    failure must be reported, never silent and never fatal.
    """
    try:
        return await call_next(request)
    except Exception as e:                  # noqa: BLE001 - deliberate barrier
        import traceback
        traceback.print_exc()
        return JSONResponse(status_code=200, content={
            "error": f"{type(e).__name__}: {e}",
            "where": request.url.path,
            "note": "The server is still running; nothing was changed. "
                    "Undo (Ctrl+Z) if the design looks wrong.",
        })


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


# ---------------------------------------------------------------------------
# Multi-document state: one entry per open tab
# ---------------------------------------------------------------------------

STATE: dict = {"docs": {}, "active": None, "seq": 0}
MAX_HISTORY = 25
MAX_TABS = 12


def _new_tab(doc: Document, source: str | None = None,
             activate: bool = True) -> str:
    """Open a document in a new tab and make it active.

    `source` records WHERE the design came from ("file:esp32-remote",
    "sample:flange") so a later open of the same thing can reuse this tab
    instead of cloning it. Keyed on origin rather than doc.name on purpose:
    two designs can carry the same name, and renaming one must not orphan
    its tab."""
    STATE["seq"] += 1
    tid = f"t{STATE['seq']}"
    STATE["docs"][tid] = {"doc": doc, "ok": False, "rebuild_ms": None,
                          "history": [], "redo": [], "source": source,
                          "hand_edits": 0}
    if activate:
        STATE["active"] = tid
    return tid


def _find_tab(source: str) -> str | None:
    """The tab already holding this design, or None."""
    for tid, e in STATE["docs"].items():
        if e.get("source") == source:
            return tid
    return None


def _entry() -> dict:
    # Degrade gracefully: if no tab is open (fresh import / all tabs closed),
    # auto-create an empty "untitled" document instead of raising KeyError:None
    # (which 500'd /api/doc and left the UI booting half-dead with no guidance).
    if STATE["active"] is None or STATE["active"] not in STATE["docs"]:
        _new_tab(Document(name="untitled"))
    return STATE["docs"][STATE["active"]]


def _doc() -> Document:
    return _entry()["doc"]


def _snapshot() -> None:
    """Push the active design's intent onto ITS undo stack. Call BEFORE any
    mutation (edit/add/remove/suppress/spec).

    A new edit ends the redo line, exactly as in every editor: once you undo
    three steps and then do something else, the branch you undid is gone. The
    version tree is what keeps that recoverable, not this stack."""
    e = _entry()
    e["history"].append(e["doc"].to_data())
    del e["history"][:-MAX_HISTORY]
    e.setdefault("redo", []).clear()


def _rebuild_and_mesh() -> None:
    """Rebuild the active document. The STL is NOT written here.

    export_stl cost ~400 ms on every rebuild — on every parameter nudge, every
    sketch open and close — and nothing in the UI reads it: the viewport is fed
    by /api/model (JSON). It is written on demand now, when /api/mesh.stl is
    actually asked for."""
    import time
    e = _entry()
    t0 = time.perf_counter()
    e["ok"] = e["doc"].rebuild()
    e["rebuild_ms"] = round((time.perf_counter() - t0) * 1000)
    e["mesh_stale"] = True


def _tabs_json() -> list[dict]:
    return [{"id": tid, "name": e["doc"].name, "ok": e["ok"],
             "active": tid == STATE["active"]}
            for tid, e in STATE["docs"].items()]


# ---------------------------------------------------------------------------
# Version history — VERSION-TREE-PLAN.md P2
# ---------------------------------------------------------------------------
# NAMING TRAP: a tab entry's "history" key is the UNDO stack — in memory, per
# tab, capped, gone on restart. The VERSION tree below is a different thing
# living on disk under designs/<slug>.history/. Undo is for the last few
# keystrokes; versions are for putting v3 back on screen next week. Nothing
# here touches the undo stack.

def _slug_of_active() -> str | None:
    """The library slug of the active tab, or None for anything unsaved.

    A version tree is keyed to a file, so an untitled scratch design has no
    history until it is saved — "no history dir until first version"."""
    src = _entry().get("source") or ""
    return src[5:] if src.startswith("file:") else None


HISTORY_ROOT_ENV = "TEXTCAD_HISTORY_ROOT"


def _history_root() -> Path:
    """Where version histories live: beside the designs they belong to, unless
    overridden.

    The override is not a nicety. /api/open now creates <slug>.history/ as a
    side effect, so a test that merely opens flange-100 would leave a directory
    behind inside designs/ — which is tracked USER WORK. tests/conftest.py
    points this at a throwaway path for every test."""
    override = os.environ.get(HISTORY_ROOT_ENV)
    return Path(override) if override else DESIGNS


def _vhistory() -> History | None:
    slug = _slug_of_active()
    return History.for_design(_history_root(), slug) if slug else None


def _measured(e: dict) -> dict:
    """Cheap facts about the build, stored with the version so two versions can
    be compared later without rebuilding either. Nothing here may cost geometry
    work — it runs on every recorded version."""
    out: dict = {"features": len(e["doc"].features), "ok": bool(e.get("ok"))}
    try:
        f = e["doc"]._result_feature()
        if f is not None and f.volume is not None:
            out["volume"] = f.volume
    except Exception:                       # never break a save over metadata
        pass
    return out


def _hand_edit() -> None:
    """Mark that the USER changed this design by hand.

    Counted rather than flagged so the version can say how much: "manual
    changes (7 edits)" is a far better label than "saved" when the point is to
    tell the AI's work apart from the user's."""
    _entry()["hand_edits"] = _entry().get("hand_edits", 0) + 1


def _record_version(label: str, source: str) -> dict:
    """Mint a version of the active design at a MEANINGFUL moment.

    Deliberately NOT wired to /api/edit, /api/feature/params, /api/spec,
    /api/feature/suppress or /api/rollback. The user chose "meaningful moments,
    not every nudge", so a slider drag stays undo's business and then rides
    into the next recorded version along with everything else it was part of —
    history.py's hash dedupe means a save after five tweaks records ONE
    version. That IS the coalescing.

    Never raises into an endpoint. The design change already succeeded; a
    sidecar file that cannot be written must not make it look otherwise, so the
    fault is reported alongside the result instead."""
    h = _vhistory()
    if h is None:
        return {}
    e = _entry()
    hand = e.get("hand_edits", 0)
    # Hand edits that were never versioned on their own ride into this one, so
    # say so: a version recorded after the user nudged seven parameters is
    # THEIR work, whatever triggered the recording.
    if hand and source in ("save", "open"):
        label = f"manual changes ({hand} edit{'' if hand == 1 else 's'})"
        source = "manual"
    try:
        h.init(_slug_of_active() or "")
        v = h.append(e["doc"].to_data(), label=label, source=source,
                     rebuildable=bool(e.get("ok")), spec=_measured(e))
        e["hand_edits"] = 0
        return {"version": v.id}
    except HistoryError as ex:
        return {"history_error": str(ex)}


def _doc_json() -> dict:
    e = _entry()
    doc = e["doc"]
    return {
        "name": doc.name,
        "ok": e["ok"],
        "rebuild_ms": e["rebuild_ms"],
        "can_undo": len(e["history"]) > 0,
        "can_redo": len(e.get("redo") or []) > 0,
        "rollback": doc.rollback,
        "geom_version": getattr(doc, "_geom_version", ""),
        # lumps in the displayed result: 2 means the design is not one part
        "result_pieces": (doc._result_feature().pieces
                          if doc._result_feature() else None),
        # separate BODIES on screen (Fusion's Bodies folder), counted properly
        # instead of inferred from how many warnings happen to exist
        "bodies": len(doc.leaf_solid_ids()),
        "spec": doc.spec,
        "spec_problems": doc.spec_problems,
        "warnings": doc.warnings,
        "tabs": _tabs_json(),
        "active_tab": STATE["active"],
        "features": [{
            "id": f.id, "op": f.op, "params": f.params, "inputs": f.inputs,
            "status": f.status, "problems": f.problems, "volume": f.volume,
            "suppressed": f.suppressed, "pieces": f.pieces,
        } for f in doc.features],
    }


# ---------------------------------------------------------------------------
# Chat intent — the LLM's ONLY power here is pointing at (feature, param, value)
# ---------------------------------------------------------------------------

def _user_env(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    try:                                   # VS Code's env may predate setx
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
            return winreg.QueryValueEx(k, name)[0]
    except Exception:
        return None


INTENT_PROMPT = """You are the edit assistant inside TextCAD Studio, a
parametric CAD tool. You will be given the current design's feature tree as
JSON and a user message. Respond with ONLY a JSON object, no prose:

To edit one parameter: {"action":"edit","feature_id":"...","param":"...","value":<number-or-list>}
To delete a feature:   {"action":"delete","feature_id":"..."}
To design a NEW object from scratch (user describes something to create, not a
change to the current one): {"action":"create","description":"<the user's full requirement, restated precisely>"}
To answer a question:  {"action":"answer","text":"..."}

NEVER refuse or answer that an object cannot be designed — ANY object request
(a car, a rocket, a chair, a cartoon character) routes to "create"; the design
engine will build a stylized approximation if the shape is organic/complex.

Rules:
- "feature_id" MUST be exactly one of the "id" values in the tree, and "param"
  MUST be a key of that feature's "params". NEVER invent names.
- Map the user's vocabulary onto the actual tree. E.g. if the user says "bore"
  and the tree has a with_center_hole feature named "hub", the bore is
  hub.radius. "Blade count" is usually a polar_pattern's "count".
- All lengths are mm, angles deg; convert if the user implies otherwise.
- "delete" is for "remove/delete/get rid of <feature>". Pick the feature the
  user MEANS: a pocket the user names is usually the cut/extrude feature, not
  its sketch. Dependent features are repaired automatically, so never refuse a
  delete because something downstream uses it.
- If the request is not a single-parameter edit or a delete, explain briefly
  via "answer"."""


def _make_model():
    key = _user_env("OPENROUTER_API_KEY")
    if not key:
        return None
    from generate import OpenRouterModel
    return OpenRouterModel(
        api_key=key,
        model=_user_env("OPENROUTER_MODEL") or "anthropic/claude-sonnet-4.5")


def chat_intent(message: str, feedback: str | None = None) -> dict:
    doc_json = json.dumps(_doc_json()["features"])
    model = _make_model()
    if model:
        try:
            user = f"FEATURE TREE:\n{doc_json}\n\nUSER: {message}"
            if feedback:
                user += (f"\n\nYour previous intent FAILED: {feedback}\n"
                         "Pick a feature_id and param that actually exist above.")
            raw = model.generate([
                {"role": "system", "content": INTENT_PROMPT},
                {"role": "user", "content": user},
            ])
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
            return json.loads(raw)
        except Exception as e:
            return {"action": "answer",
                    "text": f"(model unavailable: {e}) Try clicking a value "
                            f"in the tree to edit it directly."}
    # offline fallback: "set <feature> <param> to <value>"
    m = re.search(r"(?:set|change|make)\s+(\w+)[ .](\w+)\s+(?:to\s+)?(-?[\d.]+)",
                  message, re.I)
    if m:
        return {"action": "edit", "feature_id": m.group(1),
                "param": m.group(2), "value": float(m.group(3))}
    return {"action": "answer",
            "text": "No API key found — use: set <feature> <param> to <value>, "
                    "or click a value in the tree."}


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class VersionReq(BaseModel):
    id: str | None = None            # None = unpin, for the star


class LabelReq(BaseModel):
    id: str
    label: str = ""


class EditReq(BaseModel):
    feature_id: str
    param: str
    value: object


class ParamsReq(BaseModel):
    feature_id: str
    params: dict           # set several params at once, one rebuild


class FaceReq(BaseModel):
    # a face is named EITHER by geometry (a real pick) or by direction (the
    # authoring path — face="top"/"bottom"/"+x"/...); requiring face_center
    # made every named-face sketch un-editable (422 before the JSON was read)
    face_center: list | None = None
    face_normal: list | None = None
    face: str | None = None
    offset: float = 0.0                 # the sketch plane's offset off the face
    feature_id: str | None = None       # which BODY the face belongs to


class TrimReq(BaseModel):
    entities: list
    piece: str | None = None


class SnapReq(BaseModel):
    plane: str = "XY"
    offset: float = 0.0


class ChatReq(BaseModel):
    message: str


class NewReq(BaseModel):
    name: str = "untitled"


class FeatureReq(BaseModel):
    id: str
    op: str
    params: dict = {}
    inputs: list[str] = []


class TracePngReq(BaseModel):
    png_base64: str                  # data-URL or bare base64 of a PNG/JPG
    feature_id: str = "traced-image"
    height_mm: float = 50.0
    plane: str = "XY"
    offset: float = 0.0
    tol_mm: float = 0.15
    min_channel_mm: float = 0.0      # end-mill pre-fill; 0 = off
    connect_pieces: bool = False     # weld disjoint art into one piece


class ImportStlReq(BaseModel):
    stl_base64: str                  # data-URL or bare base64 of the .stl
    feature_id: str = "imported-stl"
    scale: float = 1.0               # 1 = STL units are mm


class FaceFeatureReq(BaseModel):
    """A face the user picked in the viewport, as the tagged mesh describes it.
    `face` is the face's index on that body (the mesh's faceId), `center`+`area`
    let the backend notice a stale index after a rebuild, `point` is the raycast
    hit (the best interior sample)."""
    body: str | None = None
    face: int | None = None
    point: list | None = None
    center: list | None = None
    area: float | None = None


class MeasureSel(BaseModel):
    """One viewport selection: a face or edge index on a body, as the tagged
    mesh handed them out."""
    body: str | None = None
    kind: str = "face"
    id: int | None = None


class MeasureReq(BaseModel):
    """Measure one selection (`b` omitted) or between two."""
    a: MeasureSel
    b: MeasureSel | None = None


class MeasureProbeReq(MeasureReq):
    """A dimension-line drag: `point` rides selection `on` (a raycast hit on
    its face) and the answer is the live distance to the other selection."""
    point: list
    on: str = "a"


class MeasureSetReq(MeasureReq):
    """Drive the geometry FROM the measured number: make this dimension
    `value`.

    A DRIVEN dimension (a diameter) writes its one param. A DERIVED one (the
    gap between two independent features) is changed by MOVING one side, and
    `side` says which: "auto" lets tree order decide (the later feature moves,
    because the earlier one is almost always stock or a datum), "a"/"b" is the
    user's explicit choice."""
    value: float
    side: str = "auto"


class RemoveReq(BaseModel):
    feature_id: str
    mode: str = "auto"          # auto (repair the history) | cascade | strict
    dry_run: bool = False       # just report the plan, change nothing


class RenameReq(BaseModel):
    feature_id: str
    name: str


class SuppressReq(BaseModel):
    feature_id: str
    suppressed: bool


class SpecReq(BaseModel):
    spec: dict


class RollbackReq(BaseModel):
    feature_id: str | None = None


class TabReq(BaseModel):
    id: str


# ---------------------------------------------------------------------------
# Pages + document data
# ---------------------------------------------------------------------------

@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/doc")
def get_doc():
    return _doc_json()


# ---------------------------------------------------------------------------
# Document tabs
# ---------------------------------------------------------------------------

@app.get("/api/tabs")
def get_tabs():
    return {"tabs": _tabs_json(), "active_tab": STATE["active"]}


@app.post("/api/tabs/switch")
def switch_tab(req: TabReq):
    if req.id not in STATE["docs"]:
        return {"error": f"no tab '{req.id}'", **_doc_json()}
    STATE["active"] = req.id
    # geometry is cached inside the Document — no rebuild needed on switch,
    # and the STL is written only if something asks for /api/mesh.stl
    _entry()["mesh_stale"] = True
    return _doc_json()


@app.post("/api/tabs/close")
def close_tab(req: TabReq):
    if req.id not in STATE["docs"]:
        return {"error": f"no tab '{req.id}'", **_doc_json()}
    del STATE["docs"][req.id]
    if not STATE["docs"]:                       # never zero tabs
        _new_tab(Document(name="untitled"))
        _rebuild_and_mesh()
    elif STATE["active"] == req.id or STATE["active"] not in STATE["docs"]:
        STATE["active"] = next(reversed(STATE["docs"]))
    return _doc_json()


@app.post("/api/new")
def new_design(req: NewReq):
    """New design = a NEW TAB; the current design stays open."""
    if len(STATE["docs"]) >= MAX_TABS:
        return {"error": f"too many open tabs (max {MAX_TABS}) — close some",
                **_doc_json()}
    _new_tab(Document(name=req.name or "untitled"))
    _rebuild_and_mesh()
    if MESH_PATH.exists():
        MESH_PATH.unlink()
    return _doc_json()


# ---------------------------------------------------------------------------
# Geometry for the viewport
# ---------------------------------------------------------------------------

def _ensure_mesh_file() -> bool:
    """Write _studio_mesh.stl if the current result has not been exported yet."""
    e = _entry()
    if not e.get("mesh_stale", True) and MESH_PATH.exists():
        return True
    part = e["doc"].result()
    if part is None:
        return False
    try:
        b3d.export_stl(part, str(MESH_PATH))
        e["mesh_stale"] = False
        return True
    except Exception:
        return False


@app.get("/api/mesh.stl")
def get_mesh():
    if _ensure_mesh_file() and MESH_PATH.exists():
        return Response(MESH_PATH.read_bytes(), media_type="model/stl")
    return Response(status_code=404)


def _sketch_mesh_data(p) -> dict | None:
    """Tessellation of one built Sketch: triangle fill + edge outlines."""
    positions, indices = [], []
    base = 0
    try:
        for face in p.faces():
            verts, tris = face.tessellate(0.3)
            for v in verts:
                positions += [round(v.X, 4), round(v.Y, 4), round(v.Z, 4)]
            for t in tris:
                indices += [base + t[0], base + t[1], base + t[2]]
            base += len(verts)
        outlines = []
        for edge in p.edges():
            gt = str(edge.geom_type).replace("GeomType.", "")
            n = 2 if gt == "LINE" else 24
            pts = [edge @ (i / n) for i in range(n + 1)]
            outlines.append([[round(q.X, 4), round(q.Y, 4), round(q.Z, 4)]
                             for q in pts])
    except Exception:
        return None
    return {"positions": positions, "indices": indices, "outlines": outlines}


def _sketches_json(doc: Document) -> list[dict]:
    """Unconsumed sketches, tessellated so the viewport can SHOW them as
    floating 2D profiles (like Fusion). Consumed sketches (already extruded /
    revolved / lofted) are hidden to keep the view clean."""
    consumed = {i for f in doc.features for i in f.inputs}
    out = []
    for f in doc.features:
        if f.suppressed or f.id in consumed:
            continue
        p = doc._parts.get(f.id)
        if p is None or not sketchlib.is_sketch(p):
            continue
        m = _sketch_mesh_data(p)
        if m is None:
            continue
        out.append({"id": f.id, **m})
    return out


def _plain_mesh(part, tol: float) -> dict:
    """Bare position/index mesh of a solid (no face tagging). Kept for callers
    that only need a silhouette; bodies in /api/model are fully tagged now."""
    positions, indices, base = [], [], 0
    for face in part.faces():
        try:
            verts, tris = face.tessellate(tol)
        except Exception:
            continue
        for v in verts:
            positions += [round(v.X, 3), round(v.Y, 3), round(v.Z, 3)]
        for t in tris:
            indices += [base + t[0], base + t[1], base + t[2]]
        base += len(verts)
    return {"positions": positions, "indices": indices}


def _mesh_tol(part, denom: float = 900.0, floor: float = 0.05) -> float:
    try:
        bb = part.bounding_box()
        return max((bb.size.X + bb.size.Y + bb.size.Z) / denom, floor)
    except Exception:
        return 0.2


# Bodies with more faces than this are treated as imported triangle meshes:
# their raw triangle faces merge into ONE pickable "MESH" face (id -1) and
# skip BRepMesh entirely. Probed on a 10k-triangle sphere: the classic
# per-face path takes 25-50s PER REQUEST vs ~2s for the fast path — and 10k
# individual face-meta entries are useless for picking anyway. Real BREP
# faces on such a body (e.g. a cylinder wall cut into an imported mesh) still
# get the classic individually-tagged treatment.
# One triangulation for the whole solid, instead of meshing every face on its
# own. Per-face tessellation cost 8.8 s on esp32-remote's 254 faces and
# 2.5 s more to sample its edges; the shared mesh does both in well under a
# second AND is better geometry: independently meshed faces do not share the
# nodes along their common edges, so the shell is full of hairline cracks.
MESH_LINEAR_TOL = None          # set per part by _mesh_tol()
MESH_ANGULAR_TOL = 0.35         # rad; ~37 segments around the smallest hole in
                                # esp32-remote, measured, not guessed

MESH_MODE_FACES = 400

# Tessellation cache, process-wide. Triangulating esp32-remote's result body
# costs ~2.2 s; the Part objects themselves are shared by the document rebuild
# cache, so the same geometry reaching a second tab (or the same design opened
# twice) is the SAME shape and must not be re-triangulated. Keyed by the OCCT
# shape, and the entry keeps the Part alive so the key cannot be recycled.
_MESH_CACHE: dict = {}
_MESH_CACHE_MAX = 24
MESH_FACE_ID = -1


def _triangle_pts(face) -> list | None:
    """The 3 corner points of a pure-triangle face wound to its OUTWARD
    normal, or None for anything richer. Pure OCP — no BRepMesh.

    Winding must come from the plane axis + orientation flag: the raw vertex
    walk order is NOT reliable (probed on a lib3mf sphere: 296 of 1258
    triangles came out inverted, which backface-culls them into holes)."""
    pts, seen = [], set()
    vexp = TopExp_Explorer(face.wrapped, TopAbs_ShapeEnum.TopAbs_VERTEX)
    while vexp.More():
        p = BRep_Tool.Pnt_s(TopoDS.Vertex_s(vexp.Current()))
        key = (round(p.X(), 6), round(p.Y(), 6), round(p.Z(), 6))
        if key not in seen:
            if len(pts) == 3:
                return None
            seen.add(key)
            pts.append(key)
        vexp.Next()
    if len(pts) != 3:
        return None
    surf = BRepAdaptor_Surface(face.wrapped)
    if surf.GetType() != GeomAbs_SurfaceType.GeomAbs_Plane:
        return None                # 3-vertex CURVED face — classic path
    ax = surf.Plane().Axis().Direction()
    nx, ny, nz = ax.X(), ax.Y(), ax.Z()
    if face.wrapped.Orientation() == TopAbs_Orientation.TopAbs_REVERSED:
        nx, ny, nz = -nx, -ny, -nz
    (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = pts
    cx = (y1 - y0) * (z2 - z0) - (z1 - z0) * (y2 - y0)
    cy = (z1 - z0) * (x2 - x0) - (x1 - x0) * (z2 - z0)
    cz = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)
    if cx * nx + cy * ny + cz * nz < 0:
        pts = [pts[0], pts[2], pts[1]]
    return pts


def _shape_key(shape):
    """Identity of a TopoDS shape, usable as a dict key.

    hash() of a TopoDS_Shape is its underlying TShape, which is exactly the
    identity we want and costs 1.5 us. (The first version also appended
    `TShape().This()` for safety: that call takes 1.3 MILLIseconds, and the
    1218 of them were 2.3 of the 3.2 s this function spent. Probed on
    esp32-remote: the hash alone is unique across all 609 edges of a part and
    stable across re-queries, and the key is only ever used within one part.)"""
    return hash(getattr(shape, "wrapped", shape))


def _face_triangles(face, tol):
    """(vertices, triangles) for one face out of the SHARED triangulation.

    Falls back to meshing the face alone if it has no triangulation (a face
    BRepMesh refused). Triangle winding follows the face's orientation: a
    REVERSED face's nodes wind the other way, and getting this wrong turns the
    part inside out under backface culling."""
    tf = face.wrapped
    loc = TopLoc_Location()
    tri = BRep_Tool.Triangulation_s(tf, loc)
    if tri is None:
        try:
            verts, tris = face.tessellate(tol)
            return [(v.X, v.Y, v.Z) for v in verts], tris
        except Exception:
            return None, None
    trsf = loc.Transformation()
    ident = loc.IsIdentity()
    verts = []
    for i in range(1, tri.NbNodes() + 1):
        p = tri.Node(i)
        if not ident:
            p = p.Transformed(trsf)
        verts.append((p.X(), p.Y(), p.Z()))
    reversed_face = tf.Orientation() == TopAbs_Orientation.TopAbs_REVERSED
    tris = []
    for i in range(1, tri.NbTriangles() + 1):
        a, b, c = tri.Triangle(i).Get()
        if reversed_face:
            b, c = c, b
        tris.append((a - 1, b - 1, c - 1))
    return verts, tris


def _edge_polylines(part) -> dict:
    """Every edge's polyline, taken from the shared triangulation.

    Sampling each edge's curve instead cost 2.5 s on esp32-remote (609 edges,
    41 points each); this is the mesh's own discretisation, already computed."""
    out = {}
    try:
        emap = TopTools_IndexedDataMapOfShapeListOfShape()
        TopExp.MapShapesAndAncestors_s(part.wrapped,
                                       TopAbs_ShapeEnum.TopAbs_EDGE,
                                       TopAbs_ShapeEnum.TopAbs_FACE, emap)
    except Exception:
        return out
    for i in range(1, emap.Extent() + 1):
        edge = TopoDS.Edge_s(emap.FindKey(i))
        hosts = emap.FindFromIndex(i)
        picks = [hosts.First()] if hosts.Extent() == 1 else [hosts.First(),
                                                             hosts.Last()]
        for pick in picks:
            try:
                f = TopoDS.Face_s(pick)
                loc = TopLoc_Location()
                tri = BRep_Tool.Triangulation_s(f, loc)
                if tri is None:
                    continue
                pot = BRep_Tool.PolygonOnTriangulation_s(edge, tri, loc)
                if pot is None:
                    continue
                trsf, ident = loc.Transformation(), loc.IsIdentity()
                nodes = pot.Nodes()
                poly = []
                for k in range(1, nodes.Length() + 1):
                    p = tri.Node(nodes.Value(k))
                    if not ident:
                        p = p.Transformed(trsf)
                    poly.append([round(p.X(), 4), round(p.Y(), 4),
                                 round(p.Z(), 4)])
                if len(poly) >= 2:
                    out[_shape_key(edge)] = poly
                break
            except Exception:
                continue
    return out


def _tagged_mesh(part, body_id: str | None = None) -> dict:
    """Face-tagged mesh of ONE solid: triangles carry the index of the OCCT
    face they came from, plus per-face and per-edge metadata for picking.

    Every visible body goes through this, not just the displayed result — a
    body you can see but cannot click is a trap (and a body rendered as a grey
    ghost reads as "it disappeared", which is exactly what users report)."""
    tol = _mesh_tol(part)
    positions, indices, face_ids, faces_meta = [], [], [], []
    base = 0
    all_faces = part.faces()
    mesh_mode = len(all_faces) > MESH_MODE_FACES
    rich_faces = list(enumerate(all_faces))     # faces that get full tagging

    if mesh_mode:
        rich_faces, tri_count = [], 0
        for fi, face in enumerate(all_faces):
            pts = _triangle_pts(face)
            if pts is None:
                rich_faces.append((fi, face))
                continue
            for p in pts:
                positions += [round(p[0], 4), round(p[1], 4), round(p[2], 4)]
                face_ids.append(MESH_FACE_ID)
            indices += [base, base + 1, base + 2]
            base += 3
            tri_count += 1
        if tri_count:
            try:
                area = round(part.area, 2)
            except Exception:
                area = None
            info = {"id": MESH_FACE_ID, "type": "MESH", "planar": False,
                    "area": area, "triangles": tri_count}
            if body_id is not None:
                info["body"] = body_id
            faces_meta.append(info)

    # Triangulate the whole solid ONCE; every face then reads its own slice of
    # that mesh. Faces keep their own vertex ranges (face_ids stays per-vertex,
    # which is what picking needs) but the triangles come from a single
    # consistent mesh.
    if rich_faces:
        try:
            BRepMesh_IncrementalMesh(part.wrapped, tol, False,
                                     MESH_ANGULAR_TOL, True)
        except Exception:
            pass

    for fi, face in rich_faces:
        verts, tris = _face_triangles(face, tol)
        if verts is None:
            continue
        for v in verts:
            positions += [round(v[0], 4), round(v[1], 4), round(v[2], 4)]
            face_ids.append(fi)
        for t in tris:
            indices += [base + t[0], base + t[1], base + t[2]]
        base += len(verts)
        gt = str(face.geom_type).replace("GeomType.", "")
        info = {"id": fi, "type": gt, "area": round(face.area, 2)}
        if body_id is not None:
            info["body"] = body_id          # which body this face belongs to
        # FLAT test is geometric, not by surface type: taper/loft/sweep make dead-
        # flat walls stored as BSPLINE/BEZIER/EXTRUSION that are still sketchable
        # and extrudable. `planar` drives face selection in the UI.
        try:
            info["planar"] = gt == "PLANE" or sketchlib.face_plane(face) is not None
        except Exception:
            info["planar"] = gt == "PLANE"
        try:
            c = face.center()
            info["center"] = [round(c.X, 2), round(c.Y, 2), round(c.Z, 2)]
            n = face.normal_at(c)
            info["normal"] = [round(n.X, 3), round(n.Y, 3), round(n.Z, 3)]
        except Exception:
            pass
        if gt == "CYLINDER":
            try:
                info["radius"] = round(face.radius, 2)
            except Exception:
                pass
            # The AXIS, not center(): a cylinder's center() lies ON the surface
            # (probed 2026-08-27 — a r=5 bore at the origin reports x=-5), so
            # labelling a hole's position from it is wrong by one radius.
            try:
                ax = face.axis_of_rotation
                info["axis"] = [round(ax.direction.X, 4),
                                round(ax.direction.Y, 4),
                                round(ax.direction.Z, 4)]
                info["axis_at"] = [round(ax.position.X, 4),
                                   round(ax.position.Y, 4),
                                   round(ax.position.Z, 4)]
            except Exception:
                pass
        # FULL circular boundaries of this face, largest first — an annular
        # face's outer and inner radii, a hole's rim on a floor. The user reads
        # a washer face as "outer dia / inner dia" (request 2026-08-31), not as
        # an area. Corner-fillet arcs are PARTIAL circles and excluded: someone
        # asking "what is this bore" does not mean the corner radius.
        try:
            radii = []
            for fe in face.edges():
                if str(fe.geom_type).replace("GeomType.", "") != "CIRCLE":
                    continue
                r = float(fe.radius)
                if abs(float(fe.length) - 2 * math.pi * r) > max(1e-6, 1e-4 * r):
                    continue                     # an arc, not a full circle
                if not any(abs(r - q) < 1e-6 for q in radii):
                    radii.append(r)
            if radii:
                info["circles"] = sorted((round(r, 4) for r in radii),
                                         reverse=True)
        except Exception:
            pass
        faces_meta.append(info)

    # In mesh mode, sampling 15k+ triangle edges would choke both server and
    # viewer (wireframe soup) — only the rich faces' edges are outlines. A
    # shared edge may appear once per face; drawing it twice is invisible.
    if mesh_mode:
        edge_list = [e for _, face in rich_faces for e in face.edges()]
    else:
        edge_list = part.edges()

    edges_meta = []
    edge_polys = _edge_polylines(part) if not mesh_mode else {}
    for ei, edge in enumerate(edge_list):
        gt = str(edge.geom_type).replace("GeomType.", "")
        # the polyline the shared mesh already computed for this edge: it costs
        # nothing and follows the triangles exactly, so outlines sit on the
        # silhouette instead of floating beside it
        poly = edge_polys.get(_shape_key(edge))
        if poly is None:
            n = 2 if gt == "LINE" else 24
            try:
                pts = [edge @ (i / n) for i in range(n + 1)]
                poly = [[round(p.X, 4), round(p.Y, 4), round(p.Z, 4)]
                        for p in pts]
            except Exception:
                continue
        em = {"id": ei, "type": gt, "length": round(edge.length, 2),
              "points": poly}
        # a round edge carries its DIAMETER, so clicking the line of a circle
        # can read one out with no round trip. arc_center only: edge.center()
        # is a point on the circle, not its centre (probed 2026-08-27).
        if gt == "CIRCLE":
            try:
                em["radius"] = round(edge.radius, 4)
                c = edge.arc_center
                em["arc_center"] = [round(c.X, 4), round(c.Y, 4), round(c.Z, 4)]
            except Exception:
                pass
        if body_id is not None:
            em["body"] = body_id
        edges_meta.append(em)

    return {"positions": positions, "indices": indices, "faceId": face_ids,
            "faces": faces_meta, "edges": edges_meta}


@app.get("/api/model")
def get_model():
    """EVERY visible body, each face-tagged for picking, plus unconsumed
    sketches as 2D profiles.

    `bodies` lists every unconsumed solid — including the displayed result,
    flagged `result: true` — so the viewport can draw them all as real solids.
    They used to be drawn as translucent grey ghosts with only the result
    solid: extruding a second sketch made the FIRST body a ghost, which reads
    exactly like "my box went blank / disappeared". Fusion shows every body in
    the Bodies folder as a real, clickable solid.

    The top-level positions/indices/faceId/faces/edges keys still describe the
    RESULT body, so older callers keep working."""
    e = _entry()
    doc = e["doc"]
    # The response is 3+ MB of triangles; re-serialising it for a viewport that
    # already has this exact geometry is pure waste. Keyed by the document's
    # geometry fingerprint, so any real change misses the cache.
    version = getattr(doc, "_geom_version", "")
    cached = e.get("model_json")
    if version and cached and cached[0] == version:
        return Response(content=cached[1], media_type="application/json")

    sketches = _sketches_json(doc)
    part = doc.result()
    result_id = doc._result_feature().id if doc._result_feature() else None

    # Tessellation is the single most expensive thing in a viewport refresh
    # (2.3-3.2 s for esp32-remote). The document's rebuild cache hands back the
    # SAME Part object when a feature's inputs did not change, so identity is a
    # sound cache key: same object -> same triangles.
    bodies = []
    for fid in doc.leaf_solid_ids():
        gp = doc._parts.get(fid)
        if gp is None:
            continue
        key = (fid, hash(gp.wrapped))
        hit = _MESH_CACHE.get(key)
        if hit is not None and hit[0].wrapped.IsSame(gp.wrapped):
            tagged = hit[1]
        else:
            try:
                tagged = _tagged_mesh(gp, body_id=fid)
            except Exception:
                continue
            _MESH_CACHE[key] = (gp, tagged)
            while len(_MESH_CACHE) > _MESH_CACHE_MAX:
                _MESH_CACHE.pop(next(iter(_MESH_CACHE)))
        bodies.append({"id": fid, "result": fid == result_id, **tagged})

    result_mesh = next((b for b in bodies if b["result"]), None)
    if result_mesh is None and part is not None:
        # a result that is not a leaf (shouldn't happen) — tag it anyway
        try:
            result_mesh = {"id": result_id, "result": True,
                           **_tagged_mesh(part, body_id=result_id)}
            bodies.append(result_mesh)
        except Exception:
            result_mesh = None
    if result_mesh is None:
        payload = {"positions": [], "indices": [], "faceId": [], "faces": [],
                   "edges": [], "sketches": sketches, "bodies": bodies}
    else:
        payload = {"positions": result_mesh["positions"],
                   "indices": result_mesh["indices"],
                   "faceId": result_mesh["faceId"],
                   "faces": result_mesh["faces"],
                   "edges": result_mesh["edges"],
                   "sketches": sketches,
                   "bodies": bodies}
    body = json.dumps(payload).encode("utf-8")
    if version:
        e["model_json"] = (version, body)
    return Response(content=body, media_type="application/json")


@app.get("/api/sketch-mesh/{feature_id}")
def get_sketch_mesh(feature_id: str):
    """Tessellation of ONE sketch feature — consumed or not — so the tree can
    highlight a selected sketch in the viewport (feature-mesh only does
    solids; a consumed sketch isn't in /api/model's sketches at all)."""
    p = _doc()._parts.get(feature_id)
    if p is None or not sketchlib.is_sketch(p):
        return {"error": "not a built sketch"}
    m = _sketch_mesh_data(p)
    if m is None:
        return {"error": "tessellation failed"}
    return {"id": feature_id, **m}


@app.get("/api/feature-mesh/{feature_id}.stl")
def get_feature_mesh(feature_id: str):
    """Mesh of ONE feature's own solid — lets the UI highlight in 3D what a
    selected tree node actually contributes."""
    part = _doc()._parts.get(feature_id)
    if part is None:
        return Response(status_code=404)
    path = ROOT / "_studio_feature.stl"
    try:
        b3d.export_stl(part, str(path))
        return Response(path.read_bytes(), media_type="model/stl")
    except Exception:
        return Response(status_code=404)


# ---------------------------------------------------------------------------
# Editing the active design
# ---------------------------------------------------------------------------

@app.post("/api/edit")
def edit(req: EditReq):
    _hand_edit()
    _snapshot()
    try:
        _doc().edit(req.feature_id, req.param, req.value)
    except (KeyError, ValueError) as e:
        _entry()["history"].pop()
        return {"error": str(e), **_doc_json()}
    _rebuild_and_mesh()
    return _doc_json()


@app.post("/api/face-outline")
def face_outline(req: FaceReq):
    """The picked face's boundary (outer + holes) projected into its plane's
    local 2D — so the sketch editor can show the selected surface as reference
    geometry. Resolves the face by GEOMETRY on the body it was picked from
    (feature_id), falling back to the result solid; with several bodies visible
    the result is not necessarily the one you clicked."""
    part = None
    if req.feature_id:
        part = _doc()._parts.get(req.feature_id)
    if part is None:
        part = _doc().result()
    if part is None:
        return {"outer": [], "holes": [], "planar": False,
                "error": "no solid to sketch on"}
    try:
        return sketchlib.face_outline_2d(part, req.face_center, req.face_normal,
                                         face=req.face, offset=req.offset)
    except Exception as e:
        return {"outer": [], "holes": [], "planar": False, "error": str(e)}


@app.post("/api/sketch/snap")
def sketch_snap_points(req: SnapReq):
    """Geometry of the visible bodies that is COINCIDENT with the sketch plane,
    in the plane's own 2D coords: corners / edge midpoints / circle centres /
    where an edge pierces the plane, plus the in-plane edges as polylines so
    the sketcher can draw what is snappable. Fetched once when a sketch opens."""
    doc = _doc()
    parts = {fid: doc._parts.get(fid) for fid in doc.leaf_solid_ids()}
    try:
        return snaplib.snap_geometry(parts, req.plane, req.offset)
    except (KeyError, ValueError) as e:
        return {"points": [], "edges": [], "error": str(e)}


@app.post("/api/sketch/trim/pieces")
def sketch_trim_pieces(req: TrimReq):
    """Split every entity outline at its crossings with the others — the
    hoverable trim segments. Stateless: works on the entity list sent by the
    open sketch editor, not on the document."""
    try:
        return {"pieces": trimlib.trim_pieces(req.entities)}
    except (KeyError, ValueError) as e:
        return {"pieces": [], "error": str(e)}


@app.post("/api/sketch/trim/apply")
def sketch_trim_apply(req: TrimReq):
    """Delete one trim piece and return the rebuilt entity list."""
    try:
        return trimlib.trim_apply(req.entities, req.piece or "")
    except (KeyError, ValueError) as e:
        return {"error": str(e)}


@app.post("/api/feature/params")
def edit_params(req: ParamsReq):
    """Set several params of one feature in a single rebuild — used by the
    sketch editor (reopen a committed sketch, redraw, save all entities)."""
    _hand_edit()
    _snapshot()
    try:
        f = _doc().get(req.feature_id)
        for k, v in req.params.items():
            f.params[k] = v
        _doc()._mark_stale()
    except (KeyError, ValueError) as e:
        _entry()["history"].pop()
        return {"error": str(e), **_doc_json()}
    _rebuild_and_mesh()
    return _doc_json()


@app.post("/api/feature/add")
def add_feature(req: FeatureReq):
    _snapshot()
    try:
        _doc().add(req.id, req.op, req.params, req.inputs)
    except ValueError as e:
        _entry()["history"].pop()
        return {"error": str(e), **_doc_json()}
    _rebuild_and_mesh()
    return {**_record_version(f"{req.op} added", f"tool:{req.op}"),
            **_doc_json()}


@app.post("/api/trace-png")
def trace_png(req: TracePngReq):
    """Upload an image, get a SKETCH feature holding its traced outline —
    then Extrude / Revolve / Cut it like any hand-drawn sketch."""
    _snapshot()
    try:
        data = base64.b64decode(req.png_base64.split(",")[-1])
        ents, info = imgtrace.image_to_entities(
            data, req.height_mm, req.tol_mm, req.min_channel_mm,
            connect_pieces=req.connect_pieces)
        fid, n = req.feature_id, 2
        while any(f.id == fid for f in _doc().features):
            fid = f"{req.feature_id}-{n}"
            n += 1
        _doc().add(fid, "sketch",
                   {"plane": req.plane, "offset": req.offset,
                    "entities": ents}, [])
    except Exception as e:        # decode/trace errors -> honest message
        _entry()["history"].pop()
        return {"error": str(e), **_doc_json()}
    _rebuild_and_mesh()
    return {**_record_version(f"traced {fid}", "tool:trace_png"),
            **_doc_json(), "trace_info": {**info, "feature_id": fid}}


class ImportStepReq(BaseModel):
    step_base64: str
    feature_id: str = "imported-step"
    scale: float = 1.0


@app.post("/api/import-step")
def import_step_file(req: ImportStepReq):
    """Upload a STEP file, get an import_step feature holding it as exact BREP
    bodies. The point (user request 2026-08-31): a design EXPORTED from here
    must come back in losslessly — cylinders stay round, no mesh, no repair.
    Same shape as /api/import-stl: the file lands in imports/ so the tree
    stays a small JSON recipe that rebuilds from disk."""
    _snapshot()
    saved_new = None
    try:
        data = base64.b64decode(req.step_base64.split(",")[-1])
        blocks.IMPORTS_DIR.mkdir(exist_ok=True)
        stem = re.sub(r"[^\w-]+", "-", req.feature_id).strip("-")[:40] or "imported"
        fname, n = f"{stem}.step", 2
        # same name + same bytes -> reuse the file; different bytes -> suffix
        while (blocks.IMPORTS_DIR / fname).exists()                 and (blocks.IMPORTS_DIR / fname).read_bytes() != data:
            fname, n = f"{stem}-{n}.step", n + 1
        if not (blocks.IMPORTS_DIR / fname).exists():
            (blocks.IMPORTS_DIR / fname).write_bytes(data)
            saved_new = blocks.IMPORTS_DIR / fname
        # validate BEFORE adding a feature — a bad file must not leave a
        # broken node in the tree
        part = blocks.import_step(fname, req.scale)
        fid, n = req.feature_id, 2
        while any(f.id == fid for f in _doc().features):
            fid = f"{req.feature_id}-{n}"
            n += 1
        _doc().add(fid, "import_step", {"file": fname, "scale": req.scale}, [])
    except Exception as e:        # decode/read errors -> honest message
        _entry()["history"].pop()
        if saved_new is not None:
            try:
                saved_new.unlink()
            except OSError:
                pass
        return {"error": str(e), **_doc_json()}
    _rebuild_and_mesh()
    bb = part.bounding_box()
    solids = part.solids()
    return {**_record_version(f"imported {fname}", "tool:import_step"),
            **_doc_json(), "import_info": {
        "feature_id": fid, "file": fname, "bodies": len(solids),
        "size_mm": [round(bb.size.X, 2), round(bb.size.Y, 2),
                    round(bb.size.Z, 2)],
        "volume_mm3": round(part.volume, 1)}}


@app.post("/api/import-stl")
def import_stl_file(req: ImportStlReq):
    """Upload an STL from an outside source, get an import_stl feature holding
    it as a solid body — then Move / Cut / Fuse it like any other body. The
    file is saved into imports/ so the feature tree stays a small JSON recipe
    that rebuilds from disk."""
    _snapshot()
    saved_new = None
    try:
        data = base64.b64decode(req.stl_base64.split(",")[-1])
        blocks.IMPORTS_DIR.mkdir(exist_ok=True)
        stem = re.sub(r"[^\w-]+", "-", req.feature_id).strip("-")[:40] or "imported"
        fname, n = f"{stem}.stl", 2
        # same name + same bytes -> reuse the file; different bytes -> suffix
        while (blocks.IMPORTS_DIR / fname).exists() \
                and (blocks.IMPORTS_DIR / fname).read_bytes() != data:
            fname, n = f"{stem}-{n}.stl", n + 1
        if not (blocks.IMPORTS_DIR / fname).exists():
            (blocks.IMPORTS_DIR / fname).write_bytes(data)
            saved_new = blocks.IMPORTS_DIR / fname
        # validate BEFORE adding a feature — a bad file must not leave a
        # broken node in the tree (this also primes the read cache)
        part = blocks.import_stl(fname, req.scale)
        fid, n = req.feature_id, 2
        while any(f.id == fid for f in _doc().features):
            fid = f"{req.feature_id}-{n}"
            n += 1
        _doc().add(fid, "import_stl", {"file": fname, "scale": req.scale}, [])
    except Exception as e:        # decode/read/mesh errors -> honest message
        _entry()["history"].pop()
        if saved_new is not None:
            try:
                saved_new.unlink()
            except OSError:
                pass
        return {"error": str(e), **_doc_json()}
    _rebuild_and_mesh()
    rep = blocks.import_stl_report(fname)
    repair_note = None
    if rep.get("repaired"):
        steps = []
        if rep.get("healed_wall_triangles"):
            steps.append(f"merged {rep['healed_wall_triangles']} coincident "
                         "wall triangles")
        if rep.get("remeshed_bodies"):
            steps.append(f"remeshed {rep['remeshed_bodies']} defective "
                         "bod" + ("y" if rep["remeshed_bodies"] == 1 else "ies"))
        if rep["output_triangles"] < rep["input_triangles"]:
            steps.append(f"decimated {rep['input_triangles']:,} → "
                         f"{rep['output_triangles']:,} triangles")
        repair_note = "auto-repaired: " + ", ".join(steps) if steps else None
    bb = part.bounding_box()
    return {**_record_version(f"imported {fname}", "tool:import_stl"),
            **_doc_json(), "import_info": {
        "feature_id": fid, "file": fname,
        "triangles": rep["output_triangles"], "bodies": rep.get("bodies"),
        "repair": repair_note,
        "size_mm": [round(bb.size.X, 2), round(bb.size.Y, 2),
                    round(bb.size.Z, 2)],
        "volume_mm3": round(part.volume, 1)}}


@app.post("/api/face-feature")
def face_feature(req: FaceFeatureReq):
    """WHICH FEATURE MADE THIS FACE (Fusion's Find in Timeline).

    Read-only: no snapshot, no rebuild, no document mutation — it walks the
    per-feature solids already cached from the last rebuild. Deliberately does
    NOT return the document (a 79-feature payload per click is waste); the
    frontend only needs the attribution."""
    try:
        return provenance.attribute_face(
            _doc(), body_id=req.body, face_index=req.face, point=req.point,
            center=req.center, area=req.area)
    except Exception as e:                  # OCP errors are NOT RuntimeError
        return {"feature": None, "reason": f"attribution failed: {e!r}"}


@app.post("/api/measure")
def measure_selection(req: MeasureReq):
    """HOW WIDE / HOW FAR / HOW THICK (Fusion's Measure).

    Read-only, like /api/face-feature: no snapshot, no rebuild, no document
    mutation — it measures the solids already cached from the last rebuild, and
    deliberately does NOT return the document (the payload per click would be
    the whole tree). Errors come back as {"error": ...} rather than a 500, so
    the readout can say why instead of going blank (rule 7)."""
    return measurelib.measure(_doc(), req.a.model_dump(),
                              req.b.model_dump() if req.b else None)


def _revert_last() -> bool:
    """Undo the snapshot this request pushed, without touching the redo stack.

    Used when a measure-driven edit fails its own verification: the user asked
    for a dimension and did not get it, so the design goes back exactly as it
    was rather than being left mid-change. Deliberately NOT the /api/undo path,
    because this was never a state the user chose to be in — offering to redo
    into it would be offering to redo into a mistake."""
    e = _entry()
    if not e["history"]:
        return False
    data = e["history"].pop()
    old = e["doc"]
    try:
        e["doc"] = Document.from_data(data)
    except ValueError:
        e["history"].append(data)      # put it back; better than losing it
        return False
    e["doc"]._cache = old._cache
    e["doc"]._spec_cache = old._spec_cache
    _rebuild_and_mesh()
    return True


@app.post("/api/measure/probe")
def measure_probe(req: MeasureProbeReq):
    """SLIDE THE MEASUREMENT (the draggable dimension line).

    Read-only like /api/measure — a probe per pointermove must never snapshot,
    rebuild, or touch the document. The value is the kernel's own minimum
    distance from the dragged point to the other selection, so the live number
    is exact, not a mesh approximation."""
    if req.b is None:
        return {"error": "probing needs two selections"}
    return measurelib.probe(_doc(), req.a.model_dump(), req.b.model_dump(),
                            req.point, req.on)


@app.post("/api/measure/set")
def measure_set(req: MeasureSetReq):
    """TYPE A DIMENSION AND THE MODEL FOLLOWS (the editable half of Measure).

    Two kinds of change, and never a guess between them:

      * a DRIVEN dimension — one that maps to a single param, like a bore's
        diameter mapping to a circle entity's radius — writes that param;
      * a DERIVED one — the gap between two independent features, a number
        stored nowhere — is changed by MOVING one side, with `side` naming
        which. Tree order picks the default (the later feature moves; the
        earlier is almost always stock or a datum) and the user can override
        it. Anything that is neither is refused with a reason.

    The write is planned before anything is touched, so a refusal leaves the
    document byte-identical. Afterwards the SAME selection is measured again and
    the achieved value reported next to the requested one: house rule 3, never
    trust, always measure. Writing a param is not proof the geometry moved."""
    plan = measurelib.plan_set(_doc(), req.a.model_dump(),
                               req.b.model_dump() if req.b else None,
                               req.value, req.side)
    if "error" in plan:
        return {**plan, **_doc_json()}
    _hand_edit()
    _snapshot()
    try:
        measurelib.write(_doc(), plan)
        _doc()._mark_stale()
    except (KeyError, ValueError, IndexError, TypeError) as e:
        _entry()["history"].pop()          # the plan never landed
        return {"error": f"could not apply that: {e}", **_doc_json()}
    _rebuild_and_mesh()
    # VERIFY: re-measure the same pick and say what the model actually became
    after = measurelib.measure(_doc(), req.a.model_dump(),
                               req.b.model_dump() if req.b else None)
    achieved = after.get("value")
    # The re-measure reuses the SAME face indices, and those are array
    # positions that a rebuild can reorder. So agreeing on a number is not
    # enough: if the pick now measures a different KIND of thing, the indices
    # went stale and this verification is about some other geometry entirely.
    same_kind = after.get("kind") == plan.get("kind")
    ok = (achieved is not None and same_kind
          and abs(float(achieved) - float(req.value)) <= 1e-4)
    out = {k: plan[k] for k in
           ("driver", "move", "requested", "param", "was") if k in plan}
    out.update({"achieved": achieved, "verified": ok})
    if not ok:
        # REVERT. The requested dimension is not what the model came out as, so
        # the edit did something other than what was asked — most often because
        # translating a profile that far pushes it outside the part and changes
        # the topology. Leaving that behind with only a warning means handing
        # the user a wrecked part and hoping they read the note, which is the
        # opposite of this project's whole point. Put it back and say so.
        why = ("the same pick now reads as "
               f"{after.get('kind') or 'nothing measurable'} instead of "
               f"{plan.get('kind')}"
               if not same_kind else
               f"the model came out at "
               + (f"{achieved:g} mm" if achieved is not None else "something else"))
        out["reverted"] = _revert_last()
        out["warning"] = (
            f"asked for {req.value:g} mm but {why} — "
            + ("nothing was changed" if out["reverted"] else
               "the edit could not be undone automatically; press Ctrl+Z"))
    return {**out, **_doc_json()}


@app.post("/api/feature/remove")
def remove_feature(req: RemoveReq):
    """Delete a feature. `dry_run` returns the PLAN only, so the UI can show
    what else goes with it and ask first; the same call without dry_run then
    applies exactly that plan. The returned "remove_plan" is what the user is
    told -- a delete never quietly takes more than the node they clicked."""
    if req.dry_run:
        try:
            plan = _doc().remove_plan(req.feature_id, req.mode)
        except (KeyError, ValueError) as e:
            return {"error": str(e), **_doc_json()}
        return {**_doc_json(), "remove_plan": plan}
    _snapshot()
    try:
        plan = _doc().remove(req.feature_id, req.mode)
    except (KeyError, ValueError) as e:
        _entry()["history"].pop()
        return {"error": str(e), **_doc_json()}
    _rebuild_and_mesh()
    if not _doc().features and MESH_PATH.exists():
        MESH_PATH.unlink()                  # last feature gone -> empty viewport
    return {**_record_version(f"deleted {req.feature_id}", "tool:delete"),
            **_doc_json(), "remove_plan": plan}


@app.post("/api/feature/rename")
def rename_feature(req: RenameReq):
    """Fusion's browser rename: the id is rewritten everywhere it is
    referenced (inputs, rollback bar, part cache). Geometry is untouched,
    so no rebuild — the snapshot still makes it undoable."""
    _hand_edit()
    _snapshot()
    try:
        _doc().rename(req.feature_id, req.name)
    except (KeyError, ValueError) as e:
        _entry()["history"].pop()
        return {"error": str(e), **_doc_json()}
    return _doc_json()


@app.post("/api/feature/suppress")
def suppress_feature(req: SuppressReq):
    _hand_edit()
    _snapshot()
    try:
        _doc().get(req.feature_id).suppressed = req.suppressed
    except KeyError as e:
        _entry()["history"].pop()
        return {"error": str(e), **_doc_json()}
    _doc()._mark_stale()
    _rebuild_and_mesh()
    return _doc_json()


@app.post("/api/spec")
def set_spec(req: SpecReq):
    """Edit the design's requirements — the legitimate way to change intent
    (e.g. actually wanting 9 blades) instead of fighting the verifier."""
    known = {"size", "volume", "holes", "n_solids", "symmetry", "tip_radius",
             "com", "require_manifold", "tol", "vol_tol"}
    _hand_edit()
    _snapshot()
    doc = _doc()
    doc.spec = {k: v for k, v in req.spec.items()
                if k in known and v is not None}
    doc._mark_stale()
    _rebuild_and_mesh()
    return _doc_json()


@app.post("/api/undo")
def undo():
    e = _entry()
    if not e["history"]:
        return {"error": "nothing to undo", **_doc_json()}
    data = e["history"].pop()
    old_doc = e["doc"]
    try:
        rebuilt = Document.from_data(data)
    except ValueError as err:
        return {"error": f"undo failed: {err}", **_doc_json()}
    # what we are leaving becomes the thing redo puts back
    e.setdefault("redo", []).append(old_doc.to_data())
    del e["redo"][:-MAX_HISTORY]
    e["doc"] = rebuilt
    # The rebuild cache is process-wide (content-addressed), so the restored
    # document already inherits it; this keeps the link explicit for a document
    # that was given a private cache.
    e["doc"]._cache = old_doc._cache
    e["doc"]._spec_cache = old_doc._spec_cache
    _rebuild_and_mesh()
    return _doc_json()


@app.post("/api/redo")
def redo():
    """Step forward again after an undo.

    User (2026-08-26): "whatever i am doing in that manual design, it can be
    easily undo and redo in that feature tree". Undo alone makes trying
    something out a one-way trip -- you can retreat but not return, so people
    stop experimenting."""
    e = _entry()
    if not e.get("redo"):
        return {"error": "nothing to redo", **_doc_json()}
    data = e["redo"].pop()
    old_doc = e["doc"]
    try:
        rebuilt = Document.from_data(data)
    except ValueError as err:
        return {"error": f"redo failed: {err}", **_doc_json()}
    e["history"].append(old_doc.to_data())      # ...and redo is undoable again
    del e["history"][:-MAX_HISTORY]
    e["doc"] = rebuilt
    e["doc"]._cache = old_doc._cache
    e["doc"]._spec_cache = old_doc._spec_cache
    _rebuild_and_mesh()
    return _doc_json()


@app.post("/api/rollback")
def rollback(req: RollbackReq):
    """Drag the rollback bar: feature_id = build only up to there;
    null = back to full build. A view, not an edit — no history entry."""
    doc = _doc()
    doc.rollback = req.feature_id
    doc._mark_stale()
    _rebuild_and_mesh()
    return _doc_json()


# ---------------------------------------------------------------------------
# Library, samples, export
# ---------------------------------------------------------------------------

@app.post("/api/save")
def save_design():
    doc = _doc()
    safe = re.sub(r"[^\w\-]+", "-", doc.name).strip("-") or "untitled"
    path = DESIGNS / f"{safe}.tcad.json"
    doc.save(str(path))
    # bind this tab to the file it just wrote (it may not have had a source, or
    # may have been saved under a new name) so opening that design later comes
    # back HERE instead of cloning the tab
    _entry()["source"] = f"file:{safe}"
    # AFTER the source is bound, so a first-ever save starts the history under
    # the name it was just written as
    return {"saved": safe, **_record_version("saved", "save"), **_doc_json()}


@app.get("/api/versions")
def get_versions():
    """The design's version tree. Separate from /api/doc on purpose: the index
    grows with every version and /api/doc is answered on every keystroke."""
    h = _vhistory()
    if h is None:
        return {"versions": [], "current": None, "starred": None,
                "problems": [], "unsaved": True,
                "note": "this design has no history yet — save it once and its "
                        "versions start being recorded"}
    return {"versions": [asdict(v) for v in h.versions()],
            "current": h.current(), "starred": h.starred(),
            "problems": h.problems(), "design_id": h.design_id,
            "name": h.name, "tree": h.tree_lines(), "unsaved": False}


@app.get("/api/versions/diff")
def version_diff(target: str, base: str | None = None):
    """What changed in one version, against its parent by default.

    On demand rather than precomputed for the whole list: answering it means
    decompressing two snapshots, and the panel refreshes whenever the document
    changes. The same reason problems() is shallow."""
    h = _vhistory()
    if h is None:
        return {"error": "this design has no history yet — save it once first"}
    try:
        v = h.get(target)
        frm = base or v.parent
        if frm is None:
            return {"target": target, "base": None, "added": [], "removed": [],
                    "changed": [], "spec_changed": False, "renamed": None,
                    "summary": "the first version — nothing before it to "
                               "compare against"}
        out = diff_snapshots(h.snapshot(frm), h.snapshot(target))
    except HistoryError as e:
        return {"error": str(e)}
    return {"target": target, "base": frm, **out}


@app.post("/api/versions/restore")
def restore_version(req: VersionReq):
    """Put an old version back on screen, in THIS tab.

    Three things it deliberately does not do:
      * it does not write designs/<slug>.tcad.json — the user's saved design
        stays as it is until they explicitly save (their decision);
      * it does not truncate the tree — set_current() moves the marker, so the
        NEXT edit branches off this version and v4..v10 survive;
      * it does not lose what was on screen — the outgoing state goes on the
        undo stack, so restoring is undoable like anything else.
    """
    h = _vhistory()
    if h is None:
        return {"error": "this design has no history yet — save it once first",
                **_doc_json()}
    if not req.id:
        return {"error": "which version? pass an id like 'v3'", **_doc_json()}
    try:
        snap = h.snapshot(req.id)
    except HistoryError as e:
        return {"error": str(e), **_doc_json()}
    try:
        fresh = Document.from_data(snap)
    except Exception as e:
        # A version recorded before an op was renamed cannot be rebuilt by this
        # build. It STAYS in the tree as a record: refusing to open it is far
        # better than dropping it, and far better than a 500.
        return {"error": f"{req.id} was recorded by an older build and this one "
                         f"cannot open it ({e}). It is still in the history — "
                         f"nothing was changed.", **_doc_json()}
    e = _entry()
    _snapshot()                                  # restoring is undoable
    e["doc"] = fresh
    _rebuild_and_mesh()
    out = {"restored": req.id}
    try:
        h.set_current(req.id)
    except HistoryError as ex:
        out["history_error"] = str(ex)
    return {**out, **_doc_json()}


@app.post("/api/versions/star")
def star_version(req: VersionReq):
    """Pin the one version the user actually means, or unpin with id=null.

    This is the answer to "we do not know which is my intended design".
    Recency cannot answer it — v10 is not automatically better than v7 — so
    exactly one version per design carries the mark."""
    h = _vhistory()
    if h is None:
        return {"error": "this design has no history yet — save it once first"}
    try:
        h.star(req.id)
    except HistoryError as e:
        return {"error": str(e)}
    return {"starred": h.starred()}


@app.post("/api/versions/label")
def label_version(req: LabelReq):
    """Rename a version. Auto-labels say what happened ("saved", "extrude
    added"); this is how a version gets called "the one for the mill"."""
    h = _vhistory()
    if h is None:
        return {"error": "this design has no history yet — save it once first"}
    try:
        h.relabel(req.id, req.label)
    except HistoryError as e:
        return {"error": str(e)}
    return {"labelled": req.id, "label": req.label}


@app.get("/api/examples")
def get_examples():
    """The curated gallery: the designs actually built in this tool, grouped.

    Read from designs/examples.json so the list is data, not code — adding a
    design to the gallery is an edit to that file. Entries whose .tcad.json has
    gone are dropped rather than shown as dead tiles, and the feature count is
    taken from the file itself so it cannot drift from the catalog."""
    cat = DESIGNS / "examples.json"
    if not cat.exists():
        return {"groups": []}
    try:
        data = json.loads(cat.read_text(encoding="utf-8"))
    except Exception as e:
        return {"groups": [], "error": f"examples.json is malformed: {e}"}
    groups = []
    for g in data.get("groups", []):
        designs = []
        for d in g.get("designs", []):
            path = DESIGNS / f"{d.get('file', '')}.tcad.json"
            if not path.exists():
                continue
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
                feats = doc.get("features", [])
            except Exception:
                continue
            designs.append({**d,
                            "name": doc.get("name", d["file"]),
                            "features": len(feats),
                            "preview": (DESIGNS /
                                        f"{d['file']}-preview.png").exists()})
        if designs:
            groups.append({"group": g.get("group", ""),
                           "blurb": g.get("blurb", ""), "designs": designs})
    return {"groups": groups}


@app.get("/api/design-preview/{file}")
def design_preview(file: str):
    """Thumbnail for a gallery tile. designs/ is not statically served (it holds
    the user's work, not web assets), so previews come through here."""
    safe = re.sub(r"[^\w\-]", "", file)
    png = DESIGNS / f"{safe}-preview.png"
    if not png.exists():
        return Response(status_code=404)
    return Response(content=png.read_bytes(), media_type="image/png")


@app.get("/api/designs")
def list_designs():
    out = []
    for p in sorted(DESIGNS.glob("*.tcad.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            out.append({"file": p.stem.replace(".tcad", ""),
                        "name": data.get("name", p.stem),
                        "features": len(data.get("features", []))})
        except Exception:
            continue
    return out


@app.post("/api/open/{file}")
def open_design(file: str):
    """Open from the library, REUSING this design's tab if it already has one.

    This used to make a new tab every time, unconditionally. The design loop is
    "regenerate the script -> POST /api/open/<name> -> look at it in 3D", so ten
    iterations left ten identically-named tabs and no way to tell which was
    which (user, 2026-08-26: "we do not know which is my intended design").

    The FILE is the source of truth here, so a tab whose design has moved on is
    reloaded rather than left stale — that refresh is the entire point of the
    loop. The state the tab held is pushed onto its undo stack first, so
    reloading can never silently discard unsaved work.

    If the file matches what the tab already shows, only the switch happens: a
    97-feature design costs ~45 s to rebuild and it would buy nothing."""
    path = DESIGNS / f"{file}.tcad.json"
    if not path.exists():
        return {"error": f"no saved design '{file}'"}
    fresh = Document.load(str(path))
    tid = _find_tab(f"file:{file}")
    if tid is None:
        _new_tab(fresh, source=f"file:{file}")
        _rebuild_and_mesh()
        return {"tab_reused": False, "reloaded": False,
                **_record_version(f"opened {file}", "open"), **_doc_json()}
    e = STATE["docs"][tid]
    STATE["active"] = tid
    if e["doc"].to_data() == fresh.to_data():
        e["mesh_stale"] = True
        return {"tab_reused": True, "reloaded": False, **_doc_json()}
    e["history"].append(e["doc"].to_data())
    del e["history"][:-MAX_HISTORY]
    e["doc"] = fresh
    _rebuild_and_mesh()
    # the OUTGOING tab state is deliberately NOT recorded: it was never saved,
    # the undo stack already holds it, and minting versions for scratch states
    # is the version-explosion the user ruled out
    return {"tab_reused": True, "reloaded": True,
            **_record_version("reloaded from disk", "open"), **_doc_json()}


@app.post("/api/sample/{name}")
def load_sample(name: str):
    """Open a built-in example, reusing its tab if it is already open.

    No reload branch here, unlike a library design: a sample has no file that
    can move on, so an already-open one is simply switched to, edits and all.
    Clicking Flange twice must not give you two flanges, and must not throw
    away what you did to the first one either. File > New gets a clean one."""
    if name not in SAMPLES:
        return {"error": f"unknown sample '{name}'"}
    tid = _find_tab(f"sample:{name}")
    if tid is not None:
        STATE["active"] = tid
        STATE["docs"][tid]["mesh_stale"] = True
        return {"tab_reused": True, **_doc_json()}
    _new_tab(SAMPLES[name](), source=f"sample:{name}")
    _rebuild_and_mesh()
    return {"tab_reused": False, **_doc_json()}


@app.get("/api/sketch/kinds")
def sketch_kinds():
    """Which dimensions each sketch shape has, so the feature tree can offer
    real editable fields (width/height/diameter) instead of a JSON blob."""
    return sketchlib.entity_schema()


@app.get("/api/ops")
def get_ops():
    """The legal operation catalog — feeds the UI's Add Feature dialog."""
    return author.op_catalog()


@app.post("/api/export")
def export_step():
    doc = _doc()
    path = str(ROOT / f"{doc.name}.step")
    try:
        doc.to_step(path)
        return {"path": path}
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@app.post("/api/chat")
def chat(req: ChatReq):
    intent = chat_intent(req.message)

    if intent.get("action") == "create":
        model = _make_model()
        if model is None:
            return {"reply": "Designing from scratch needs an API key "
                             "(OPENROUTER_API_KEY).", **_doc_json()}
        doc, transcript = author.author_design(
            intent.get("description") or req.message, model)
        if doc is None:
            return {"reply": "I couldn't produce a verified design:\n"
                             + "\n".join(transcript), **_doc_json()}
        # A NEW design goes in a NEW tab and must NOT steal the one the user is
        # working in (user, 2026-08-26: "even my current tab is being taken for
        # that design ... that should not disturb other tabs"). Authoring takes
        # a while, and yanking the viewport away mid-edit loses their place.
        was = STATE["active"]
        tid = _new_tab(doc, activate=True)
        _rebuild_and_mesh()                       # build it while it is active
        n = len(doc.features)
        if was in STATE["docs"] and was != tid:
            STATE["active"] = was                 # ...then hand the tab back
        return {"reply": f"Designed \"{doc.name}\" — {n} features, all "
                         f"verified ({transcript[-1]}). It is waiting in its "
                         f"own tab; your current design is untouched. Click "
                         f"the \"{doc.name}\" tab when you want it.",
                "new_tab": tid, **_doc_json()}

    if intent.get("action") == "delete":
        fid = intent.get("feature_id")
        if not fid:
            return {"reply": "Which feature should I delete? Name it as it "
                             "appears in the tree.", **_doc_json()}
        try:                                 # look before leaping (dry run)
            plan = _doc().remove_plan(fid)
        except (KeyError, ValueError) as e:
            return {"reply": f"I could not delete that: {e}", **_doc_json()}
        if len(plan["deleted"]) > CHAT_DELETE_LIMIT:
            # a chat message is a poor place to approve a demolition: show the
            # damage and make the user do it deliberately in the tree
            return {"reply": f"I did NOT touch the design: '{fid}' is holding "
                             f"up most of it. {plan['summary']} If you really "
                             f"want that, click the x on '{fid}' in the tree "
                             f"and confirm.",
                    "remove_plan": plan, **_doc_json()}
        _snapshot()
        try:
            plan = _doc().remove(fid)
        except (KeyError, ValueError) as e:
            _entry()["history"].pop()
            return {"reply": f"I could not delete that: {e}", **_doc_json()}
        _rebuild_and_mesh()
        state = "PASS" if _entry()["ok"] else "FAILED verification"
        said = plan["summary"].replace("Delete ", "Deleted ", 1)
        return {"reply": f"{said} Rebuilt: {state}. Undo (Ctrl+Z) "
                         f"puts it all back.",
                **_record_version(f"AI deleted {fid}", "ai"),
                "remove_plan": plan, **_doc_json()}

    for _ in range(2):                       # one repair retry, same philosophy
        if intent.get("action") != "edit":
            return {"reply": intent.get("text", "…"), **_doc_json()}
        _snapshot()
        try:
            _doc().edit(intent["feature_id"], intent["param"], intent["value"])
        except (KeyError, ValueError) as e:
            _entry()["history"].pop()
            intent = chat_intent(req.message, feedback=str(e))
            continue
        _rebuild_and_mesh()
        state = "PASS" if _entry()["ok"] else "FAILED verification"
        return {"reply": f"Set {intent['feature_id']}.{intent['param']} = "
                         f"{intent['value']} — rebuilt: {state}.",
                **_record_version(
                    f"AI set {intent['feature_id']}.{intent['param']}"
                    f" = {intent['value']}", "ai"),
                **_doc_json()}
    return {"reply": "I couldn't map that to an editable parameter — click "
                     "the value in the tree instead.", **_doc_json()}


if __name__ == "__main__":
    import socket
    import uvicorn
    # Start EMPTY (user mandate 2026-08-05: the demo flange forced a
    # primitive-tree "disc with bolts" on every launch). Samples stay
    # available under File -> Examples; saved work under File -> Open.
    _new_tab(Document(name="untitled"))
    _rebuild_and_mesh()
    port = int(os.environ.get("TEXTCAD_PORT", "8123"))
    url = f"http://127.0.0.1:{port}"

    # Refuse to start a SECOND server on a port that already answers. On
    # Windows two processes can both bind one port and replies then come from
    # whichever bound last, which makes the app behave at random -- reads as
    # "the server crashed" while a stale process quietly serves old code.
    probe = socket.socket()
    probe.settimeout(0.4)
    already = probe.connect_ex(("127.0.0.1", port)) == 0
    probe.close()
    if already:
        print(f"Something is already serving {url}.")
        print("That is probably TextCAD Studio -- just open the tab.")
        print("If it is stuck, close it first, or pick another port:")
        print(f"  set TEXTCAD_PORT=8124 && python studio.py")
        raise SystemExit(3)

    print(f"TextCAD Studio -> {url}")
    # new=2 asks for a TAB in the existing window rather than a new window, and
    # TEXTCAD_NO_BROWSER skips it entirely (user: "always keep one webbrowser,
    # just open a new tab"). Restarting the server should not pile up windows.
    if os.environ.get("TEXTCAD_NO_BROWSER") != "1":
        try:
            webbrowser.open(url, new=2)
        except Exception:
            pass
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
