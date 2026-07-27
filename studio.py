"""
studio.py — TextCAD Studio: the local web app.

Run:  python studio.py   ->  opens http://127.0.0.1:8123 in your browser.

Three panels: chat (talk to the designer), feature tree (click a parameter to
edit it), 3D viewer. Every edit — spoken or clicked — flows through the SAME
path: Document.edit() -> deterministic rebuild through verified blocks ->
per-node health + spec verification. The LLM never regenerates a design during
an edit; it only points at (feature, parameter, value). Nothing else can change.
"""

from __future__ import annotations
import json
import os
import re
import webbrowser
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

import build123d as b3d

import meanline
import author
from document import Document

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
MESH_PATH = ROOT / "_studio_mesh.stl"

app = FastAPI(title="TextCAD Studio")


# ---------------------------------------------------------------------------
# Samples — demo-ready designs
# ---------------------------------------------------------------------------

def sample_flange() -> Document:
    doc = Document(name="flange-100")
    doc.add("body", "disc", {"radius": 50, "thickness": 10})
    doc.add("bore", "with_center_hole", {"radius": 15}, inputs=["body"])
    doc.add("bolts", "with_bolt_circle",
            {"count": 6, "bolt_radius": 4, "pitch_circle_dia": 76},
            inputs=["bore"])
    doc.spec = {"symmetry": 6, "n_solids": 1, "holes": {4.0: 6}, "tol": 0.5}
    return doc


def sample_impeller() -> Document:
    """The 7-blade curved impeller as an editable feature tree."""
    doc = Document(name="impeller-7")
    doc.add("hub_body", "revolve_profile",
            {"points": [[0, 0], [22, 0], [22, 3], [10, 28], [0, 28]]})
    doc.add("hub", "with_center_hole", {"radius": 6}, inputs=["hub_body"])
    doc.add("blade", "curved_blade",
            {"inner_radius": 9, "outer_radius": 40, "inlet_angle_deg": 30,
             "exit_angle_deg": 55, "height": 26, "thickness": 2.5})
    doc.add("blades_raw", "polar_pattern", {"count": 7}, inputs=["blade"])
    doc.add("shroud_cutter", "revolve_profile",
            {"points": [[8, 26], [40, 10], [48, 10], [48, 60], [8, 60]]})
    doc.add("blades", "cut", inputs=["blades_raw", "shroud_cutter"])
    doc.add("impeller", "fuse", inputs=["hub", "blades"])
    doc.spec = {"symmetry": 7, "n_solids": 1, "tip_radius": 40.0, "tol": 0.5}
    return doc


def sample_compressor() -> Document:
    """Physics-designed compressor: meanline calc -> feature tree. Heavier to
    rebuild (13 curved blades) — expect a minute or two per rebuild."""
    d = meanline.design(meanline.Duty(mass_flow=0.5, pressure_ratio=3.0,
                                      rpm=45000))
    t, L = d.backplate_thk, d.axial_length
    r_in = round(0.75 * d.inducer_hub_radius, 2)
    thk = round(max(0.02 * d.tip_radius, 1.5), 2)
    big = t + L + 50.0
    doc = Document(name=f"compressor-PR3-{d.blade_count}blades")
    doc.add("hub_body", "revolve_profile",
            {"points": [[0, 0], [d.tip_radius, 0], [d.tip_radius, t],
                        [d.inducer_hub_radius, t + L], [0, t + L]]})
    doc.add("hub", "with_center_hole", {"radius": d.bore_radius},
            inputs=["hub_body"])
    doc.add("blade", "curved_blade",
            {"inner_radius": r_in, "outer_radius": d.tip_radius,
             "inlet_angle_deg": d.beta1_deg, "exit_angle_deg": d.beta2_deg,
             "height": L, "thickness": thk})
    doc.add("blade_up", "move", {"z": t}, inputs=["blade"])
    doc.add("blades_raw", "polar_pattern", {"count": d.blade_count},
            inputs=["blade_up"])
    doc.add("shroud_cutter", "revolve_profile",
            {"points": [[r_in - 2, t + L], [d.inducer_shroud_radius, t + L],
                        [d.tip_radius, t + d.exit_width],
                        [d.tip_radius + 15, t + d.exit_width],
                        [d.tip_radius + 15, big], [r_in - 2, big]]})
    doc.add("blades", "cut", inputs=["blades_raw", "shroud_cutter"])
    doc.add("impeller", "fuse", inputs=["hub", "blades"])
    doc.spec = {"symmetry": d.blade_count, "n_solids": 1,
                "tip_radius": d.tip_radius, "tol": 1.0}
    return doc


SAMPLES = {"flange": sample_flange, "impeller": sample_impeller,
           "compressor": sample_compressor}

STATE: dict = {"doc": None, "ok": False}


def _rebuild_and_mesh() -> None:
    doc: Document = STATE["doc"]
    STATE["ok"] = doc.rebuild()
    part = doc.result()
    if part is not None:
        try:
            b3d.export_stl(part, str(MESH_PATH))
        except Exception:
            pass


def _doc_json() -> dict:
    doc: Document = STATE["doc"]
    return {
        "name": doc.name,
        "ok": STATE["ok"],
        "spec": doc.spec,
        "spec_problems": doc.spec_problems,
        "features": [{
            "id": f.id, "op": f.op, "params": f.params, "inputs": f.inputs,
            "status": f.status, "problems": f.problems, "volume": f.volume,
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
To design a NEW part from scratch (user describes a part to create, not a
change to the current one): {"action":"create","description":"<the user's full requirement, restated precisely>"}
To answer a question:  {"action":"answer","text":"..."}

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
# API
# ---------------------------------------------------------------------------

class EditReq(BaseModel):
    feature_id: str
    param: str
    value: object


class ChatReq(BaseModel):
    message: str


class NewReq(BaseModel):
    name: str = "untitled"


class FeatureReq(BaseModel):
    id: str
    op: str
    params: dict = {}
    inputs: list[str] = []


class RemoveReq(BaseModel):
    feature_id: str


class SuppressReq(BaseModel):
    feature_id: str
    suppressed: bool


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/doc")
def get_doc():
    return _doc_json()


@app.get("/api/mesh.stl")
def get_mesh():
    if MESH_PATH.exists():
        return Response(MESH_PATH.read_bytes(), media_type="model/stl")
    return Response(status_code=404)


@app.get("/api/ops")
def get_ops():
    """The legal operation catalog — feeds the UI's Add Feature dialog."""
    return author.op_catalog()


@app.post("/api/new")
def new_design(req: NewReq):
    STATE["doc"] = Document(name=req.name or "untitled")
    STATE["ok"] = False
    if MESH_PATH.exists():
        MESH_PATH.unlink()
    return _doc_json()


@app.post("/api/feature/add")
def add_feature(req: FeatureReq):
    doc: Document = STATE["doc"]
    try:
        doc.add(req.id, req.op, req.params, req.inputs)
    except ValueError as e:
        return {"error": str(e), **_doc_json()}
    _rebuild_and_mesh()
    return _doc_json()


@app.post("/api/feature/remove")
def remove_feature(req: RemoveReq):
    doc: Document = STATE["doc"]
    try:
        doc.remove(req.feature_id)
    except (KeyError, ValueError) as e:
        return {"error": str(e), **_doc_json()}
    _rebuild_and_mesh()
    return _doc_json()


@app.post("/api/feature/suppress")
def suppress_feature(req: SuppressReq):
    doc: Document = STATE["doc"]
    try:
        doc.get(req.feature_id).suppressed = req.suppressed
    except KeyError as e:
        return {"error": str(e), **_doc_json()}
    doc._mark_stale()
    _rebuild_and_mesh()
    return _doc_json()


@app.post("/api/sample/{name}")
def load_sample(name: str):
    if name not in SAMPLES:
        return {"error": f"unknown sample '{name}'"}
    STATE["doc"] = SAMPLES[name]()
    _rebuild_and_mesh()
    return _doc_json()


@app.post("/api/edit")
def edit(req: EditReq):
    doc: Document = STATE["doc"]
    try:
        doc.edit(req.feature_id, req.param, req.value)
    except (KeyError, ValueError) as e:
        return {"error": str(e), **_doc_json()}
    _rebuild_and_mesh()
    return _doc_json()


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
        STATE["doc"] = doc
        _rebuild_and_mesh()
        n = len(doc.features)
        return {"reply": f"Designed \"{doc.name}\" — {n} features, all "
                         f"verified ({transcript[-1]}). It's now in the tree; "
                         f"edit anything by clicking or asking.",
                **_doc_json()}

    for _ in range(2):                       # one repair retry, same philosophy
        if intent.get("action") != "edit":
            return {"reply": intent.get("text", "…"), **_doc_json()}
        doc: Document = STATE["doc"]
        try:
            doc.edit(intent["feature_id"], intent["param"], intent["value"])
        except (KeyError, ValueError) as e:
            intent = chat_intent(req.message, feedback=str(e))
            continue
        _rebuild_and_mesh()
        state = "PASS" if STATE["ok"] else "FAILED verification"
        return {"reply": f"Set {intent['feature_id']}.{intent['param']} = "
                         f"{intent['value']} — rebuilt: {state}.",
                **_doc_json()}
    return {"reply": "I couldn't map that to an editable parameter — click "
                     "the value in the tree instead.", **_doc_json()}


@app.post("/api/export")
def export_step():
    doc: Document = STATE["doc"]
    path = str(ROOT / f"{doc.name}.step")
    try:
        doc.to_step(path)
        return {"path": path}
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    import uvicorn
    STATE["doc"] = sample_flange()
    _rebuild_and_mesh()
    url = "http://127.0.0.1:8123"
    print(f"TextCAD Studio -> {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    uvicorn.run(app, host="127.0.0.1", port=8123, log_level="warning")
