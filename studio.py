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
import os
import re
import webbrowser
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import build123d as b3d
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_SurfaceType
from OCP.TopAbs import TopAbs_Orientation, TopAbs_ShapeEnum
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

import author
import blocks
import imgtrace
import sketch as sketchlib
import sketch_trim as trimlib
import sketch_snap as snaplib
from document import Document
from samples import SAMPLES, sample_flange, sample_impeller, sample_compressor  # noqa: F401 (re-export for tests)

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
MESH_PATH = ROOT / "_studio_mesh.stl"
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


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


# ---------------------------------------------------------------------------
# Multi-document state: one entry per open tab
# ---------------------------------------------------------------------------

STATE: dict = {"docs": {}, "active": None, "seq": 0}
MAX_HISTORY = 25
MAX_TABS = 12


def _new_tab(doc: Document) -> str:
    """Open a document in a new tab and make it active."""
    STATE["seq"] += 1
    tid = f"t{STATE['seq']}"
    STATE["docs"][tid] = {"doc": doc, "ok": False, "rebuild_ms": None,
                          "history": []}
    STATE["active"] = tid
    return tid


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
    mutation (edit/add/remove/suppress/spec)."""
    e = _entry()
    e["history"].append(e["doc"].to_data())
    del e["history"][:-MAX_HISTORY]


def _rebuild_and_mesh() -> None:
    import time
    e = _entry()
    t0 = time.perf_counter()
    e["ok"] = e["doc"].rebuild()
    e["rebuild_ms"] = round((time.perf_counter() - t0) * 1000)
    part = e["doc"].result()
    if part is not None:
        try:
            b3d.export_stl(part, str(MESH_PATH))
        except Exception:
            pass


def _tabs_json() -> list[dict]:
    return [{"id": tid, "name": e["doc"].name, "ok": e["ok"],
             "active": tid == STATE["active"]}
            for tid, e in STATE["docs"].items()]


def _doc_json() -> dict:
    e = _entry()
    doc = e["doc"]
    return {
        "name": doc.name,
        "ok": e["ok"],
        "rebuild_ms": e["rebuild_ms"],
        "can_undo": len(e["history"]) > 0,
        "rollback": doc.rollback,
        "spec": doc.spec,
        "spec_problems": doc.spec_problems,
        "warnings": doc.warnings,
        "tabs": _tabs_json(),
        "active_tab": STATE["active"],
        "features": [{
            "id": f.id, "op": f.op, "params": f.params, "inputs": f.inputs,
            "status": f.status, "problems": f.problems, "volume": f.volume,
            "suppressed": f.suppressed,
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
- If the request is not a single-parameter edit, explain briefly via "answer"."""


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

class EditReq(BaseModel):
    feature_id: str
    param: str
    value: object


class ParamsReq(BaseModel):
    feature_id: str
    params: dict           # set several params at once, one rebuild


class FaceReq(BaseModel):
    face_center: list
    face_normal: list | None = None
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


class RemoveReq(BaseModel):
    feature_id: str


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
    # geometry is cached inside the Document — no rebuild needed on switch
    part = _doc().result()
    if part is not None:
        try:
            b3d.export_stl(part, str(MESH_PATH))
        except Exception:
            pass
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

@app.get("/api/mesh.stl")
def get_mesh():
    if MESH_PATH.exists():
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
MESH_MODE_FACES = 400
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

    for fi, face in rich_faces:
        try:
            verts, tris = face.tessellate(tol)
        except Exception:
            continue
        for v in verts:
            positions += [round(v.X, 4), round(v.Y, 4), round(v.Z, 4)]
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
        faces_meta.append(info)

    # In mesh mode, sampling 15k+ triangle edges would choke both server and
    # viewer (wireframe soup) — only the rich faces' edges are outlines. A
    # shared edge may appear once per face; drawing it twice is invisible.
    if mesh_mode:
        edge_list = [e for _, face in rich_faces for e in face.edges()]
    else:
        edge_list = part.edges()

    edges_meta = []
    for ei, edge in enumerate(edge_list):
        gt = str(edge.geom_type).replace("GeomType.", "")
        n = 2 if gt == "LINE" else 40
        try:
            pts = [edge @ (i / n) for i in range(n + 1)]
            poly = [[round(p.X, 4), round(p.Y, 4), round(p.Z, 4)] for p in pts]
        except Exception:
            continue
        em = {"id": ei, "type": gt, "length": round(edge.length, 2),
              "points": poly}
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
    doc = _doc()
    sketches = _sketches_json(doc)
    part = doc.result()
    result_id = doc._result_feature().id if doc._result_feature() else None

    bodies = []
    for fid in doc.leaf_solid_ids():
        gp = doc._parts.get(fid)
        if gp is None:
            continue
        try:
            bodies.append({"id": fid, "result": fid == result_id,
                           **_tagged_mesh(gp, body_id=fid)})
        except Exception:
            continue

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
        return {"positions": [], "indices": [], "faceId": [], "faces": [],
                "edges": [], "sketches": sketches, "bodies": bodies}

    return {"positions": result_mesh["positions"],
            "indices": result_mesh["indices"],
            "faceId": result_mesh["faceId"],
            "faces": result_mesh["faces"], "edges": result_mesh["edges"],
            "sketches": sketches,
            "bodies": bodies}


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
        return sketchlib.face_outline_2d(part, req.face_center, req.face_normal)
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
    return _doc_json()


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
    return {**_doc_json(), "trace_info": {**info, "feature_id": fid}}


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
    return {**_doc_json(), "import_info": {
        "feature_id": fid, "file": fname,
        "triangles": rep["output_triangles"], "bodies": rep.get("bodies"),
        "repair": repair_note,
        "size_mm": [round(bb.size.X, 2), round(bb.size.Y, 2),
                    round(bb.size.Z, 2)],
        "volume_mm3": round(part.volume, 1)}}


@app.post("/api/feature/remove")
def remove_feature(req: RemoveReq):
    _snapshot()
    try:
        _doc().remove(req.feature_id)
    except (KeyError, ValueError) as e:
        _entry()["history"].pop()
        return {"error": str(e), **_doc_json()}
    _rebuild_and_mesh()
    return _doc_json()


@app.post("/api/feature/rename")
def rename_feature(req: RenameReq):
    """Fusion's browser rename: the id is rewritten everywhere it is
    referenced (inputs, rollback bar, part cache). Geometry is untouched,
    so no rebuild — the snapshot still makes it undoable."""
    _snapshot()
    try:
        _doc().rename(req.feature_id, req.name)
    except (KeyError, ValueError) as e:
        _entry()["history"].pop()
        return {"error": str(e), **_doc_json()}
    return _doc_json()


@app.post("/api/feature/suppress")
def suppress_feature(req: SuppressReq):
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
    try:
        e["doc"] = Document.from_data(data)
    except ValueError as err:
        return {"error": f"undo failed: {err}", **_doc_json()}
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
    return {"saved": safe, **_doc_json()}


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
    """Open from the library — in a NEW tab."""
    path = DESIGNS / f"{file}.tcad.json"
    if not path.exists():
        return {"error": f"no saved design '{file}'"}
    _new_tab(Document.load(str(path)))
    _rebuild_and_mesh()
    return _doc_json()


@app.post("/api/sample/{name}")
def load_sample(name: str):
    """Open an example — in a NEW tab."""
    if name not in SAMPLES:
        return {"error": f"unknown sample '{name}'"}
    _new_tab(SAMPLES[name]())
    _rebuild_and_mesh()
    return _doc_json()


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
        _new_tab(doc)                             # AI designs open in a new tab
        _rebuild_and_mesh()
        n = len(doc.features)
        return {"reply": f"Designed \"{doc.name}\" — {n} features, all "
                         f"verified ({transcript[-1]}). Opened in a new tab; "
                         f"edit anything by clicking or asking.",
                **_doc_json()}

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
                **_doc_json()}
    return {"reply": "I couldn't map that to an editable parameter — click "
                     "the value in the tree instead.", **_doc_json()}


if __name__ == "__main__":
    import uvicorn
    # Start EMPTY (user mandate 2026-08-05: the demo flange forced a
    # primitive-tree "disc with bolts" on every launch). Samples stay
    # available under File -> Examples; saved work under File -> Open.
    _new_tab(Document(name="untitled"))
    _rebuild_and_mesh()
    url = "http://127.0.0.1:8123"
    print(f"TextCAD Studio -> {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    uvicorn.run(app, host="127.0.0.1", port=8123, log_level="warning")
