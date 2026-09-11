"""
generate.py — text-to-CAD generator with a TWO-layer repair loop.

Layer 1 (engine.py) : catches broken code + invalid geometry.
Layer 2 (check.py)  : catches "valid but WRONG" parts vs a ground-truth Spec.

MODEL SELECTION (automatic, checked in this order):
  * GEMINI_API_KEY set     -> Google Gemini   (free tier)
  * ANTHROPIC_API_KEY set  -> Claude
  * neither                -> offline FakeModel
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
import os
import re
import engine
import inspector
import blocks

if TYPE_CHECKING:
    import check                  # only for the Spec annotation of text_to_cad


SYSTEM_PROMPT = (
    "You write build123d Python scripts. Output ONLY code, no markdown, no prose.\n"
    "Assign the final part to a variable named `result`.\n"
    "\n"
    "PREFER these verified helper functions. They are ALREADY DEFINED in your "
    "script's global namespace — do NOT write any import for them and do NOT "
    "redefine them; just call them directly (you cannot get their geometry "
    "wrong, so compose from them whenever they fit):\n"
    f"{blocks.api_summary()}\n"
    "\n"
    "They return build123d `Part` objects you can combine with + (union), "
    "- (subtract), and & (intersect), and position with `Pos(x, y, z) * part`.\n"
    "Use polar_pattern(feature, count) to build N-fold symmetric parts so the "
    "symmetry is correct by construction.\n"
    "You may still use raw build123d API when no helper fits. Keep geometry "
    "simple if unsure."
)


# ---------------------------------------------------------------------------
# Models — each exposes generate(messages) -> str. The loop doesn't care which.
# ---------------------------------------------------------------------------

class FakeModel:
    """Offline stand-in: fails on attempt 1, fixes itself on attempt 2."""
    def generate(self, messages: list[dict]) -> str:
        transcript = " ".join(m["content"] for m in messages)
        failed = "TypeError" in transcript or "invalid" in transcript
        base = (
            "with BuildPart() as p:\n"
            "    Cylinder(radius=50, height=10)\n"
            "    with Locations((0, 0)):\n"
            "        Hole(radius=15)\n"
            "    with PolarLocations(radius=38, count=6):\n"
            "        Hole(radius=4)\n"
        )
        if not failed:
            return base + "    p.part.is_valid()   # BUG: property, not method\n" + "result = p\n"
        return base + "result = p\n"


class GeminiModel:
    """Google Gemini. Key passed in from the environment, never stored here."""
    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        from google import genai
        self.genai = genai
        self.client = genai.Client(api_key=api_key)
        self.model = model

    @staticmethod
    def _to_contents(messages: list[dict]):
        """Map our messages to Gemini's format: assistant->model, drop system."""
        out = []
        for m in messages:
            if m["role"] == "system":
                continue
            role = "model" if m["role"] == "assistant" else "user"
            out.append({"role": role, "parts": [{"text": m["content"]}]})
        return out

    def generate(self, messages: list[dict]) -> str:
        from google.genai import types
        system = next(m["content"] for m in messages if m["role"] == "system")
        resp = self.client.models.generate_content(
            model=self.model,
            contents=self._to_contents(messages),
            config=types.GenerateContentConfig(
                system_instruction=system, max_output_tokens=2000, temperature=0,
            ),
        )
        return resp.text or ""


class OpenRouterModel:
    """OpenRouter (OpenAI-compatible). Key from the environment, never stored here.

    Its message format is identical to ours, so no mapping is needed.
    Pick any free model from https://openrouter.ai/models (filter: Free) and put
    its id here. Free ids end in ':free'. Code-capable ones work best.
    """
    def __init__(self, api_key: str, model: str | None = None):
        from openai import OpenAI
        # Model can be set from the terminal via OPENROUTER_MODEL (no file edit).
        model = model or os.environ.get(
            "OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324")
        # A REQUEST clock as well as the job's. Without one the SDK waits its
        # own 10-minute default (times its retries) on a stalled connection,
        # and a chat job's tab is read-only for every second of that.
        self.client = OpenAI(api_key=api_key, timeout=120.0, max_retries=2,
                             base_url="https://openrouter.ai/api/v1")
        self.model = model
        print(f"[OpenRouter model: {model}]")

    def generate(self, messages: list[dict]) -> str:
        # 8000: a decomposed HISTORY tree (many sketches with path entities)
        # regularly exceeds the old 2000 cap — truncation surfaced as
        # baffling "unterminated string" JSON errors the model can't fix
        resp = self.client.chat.completions.create(
            model=self.model, messages=messages, max_tokens=8000, temperature=0,
        )
        return resp.choices[0].message.content or ""


class AnthropicModel:
    """Claude. Key passed in from the environment, never stored here."""
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-5"):
        from anthropic import Anthropic
        self.client = Anthropic(api_key=api_key)
        self.model = model

    def generate(self, messages: list[dict]) -> str:
        system = next(m["content"] for m in messages if m["role"] == "system")
        turns = [{"role": m["role"], "content": m["content"]}
                 for m in messages if m["role"] != "system"]
        resp = self.client.messages.create(
            model=self.model, max_tokens=8000, system=system, messages=turns,
        )
        return "".join(b.text for b in resp.content if b.type == "text")


def pick_model():
    if os.environ.get("OPENROUTER_API_KEY"):
        print("[using OpenRouter — key found in environment]\n")
        return OpenRouterModel(api_key=os.environ["OPENROUTER_API_KEY"])
    if os.environ.get("GEMINI_API_KEY"):
        print("[using Google Gemini — key found in environment]\n")
        return GeminiModel(api_key=os.environ["GEMINI_API_KEY"])
    if os.environ.get("ANTHROPIC_API_KEY"):
        print("[using Claude — key found in environment]\n")
        return AnthropicModel(api_key=os.environ["ANTHROPIC_API_KEY"])
    print("[no API key found — using offline FakeModel]\n")
    return FakeModel()


# ---------------------------------------------------------------------------
# Helpers + the two-layer loop
# ---------------------------------------------------------------------------

def _strip_fences(text: str) -> str:
    text = re.sub(r"^```(?:python)?\s*", "", text.strip())
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _describe_spec(spec: "inspector.Spec") -> str:
    parts = []
    if spec.size:
        dims = " x ".join(f"{v}mm" if v is not None else "?" for v in spec.size)
        parts.append(f"overall bounding box {dims}")
    if spec.volume is not None:
        parts.append(f"volume ~{spec.volume}mm^3")
    for r, c in spec.holes.items():
        parts.append(f"{c} holes of radius {r}mm")
    if spec.symmetry is not None:
        parts.append(f"{spec.symmetry}-fold rotational symmetry about the Z axis")
    if spec.tip_radius is not None:
        parts.append(f"maximum radial reach from the Z axis exactly "
                     f"{spec.tip_radius}mm (tip radius)")
    if spec.n_solids is not None:
        parts.append(f"exactly {spec.n_solids} solid body(ies)")
    return "; ".join(parts)


def _show_in_viewer(step_path: str) -> None:
    """Push the generated part to the OCP CAD Viewer panel in VS Code.
    Silently does nothing if the viewer/extension isn't available."""
    try:
        import build123d as b3d
        from ocp_vscode import show
        show(b3d.import_step(step_path))
        print("    (sent to OCP CAD Viewer)")
    except Exception as e:
        print(f"    (viewer not shown: {e})")


@dataclass
class GenResult:
    ok: bool
    attempts: int
    result: engine.RunResult
    code: str
    history: list[dict] = field(default_factory=list)


def text_to_cad(prompt: str, model=None, spec: "check.Spec | None" = None,
                max_attempts: int = 3, step_path: str = "generated.step") -> GenResult:
    model = model or pick_model()

    user_msg = prompt
    if spec is not None:
        user_msg += f"\n\nThe part MUST satisfy: {_describe_spec(spec)}."

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ]
    last_run, last_code = None, ""

    for attempt in range(1, max_attempts + 1):
        code = _strip_fences(model.generate(messages))
        last_code = code
        messages.append({"role": "assistant", "content": code})

        run = engine.run_script(code, step_path=step_path,
                                extra_globals=blocks.EXPORTS)
        last_run = run
        print(f"--- attempt {attempt} --- stage={run.stage} ok={run.ok}")

        if not run.ok:
            err = (run.error or "").strip().splitlines()[-1]
            print(f"    LAYER 1 FAILED ({run.stage}): {err}")
            print("    --- code it wrote ---\n" +
                  "\n".join("    " + ln for ln in code.splitlines()))
            messages.append({"role": "user", "content":
                "That script failed with this error:\n"
                f"{run.error}\nReturn corrected build123d code only."})
            continue

        # Layer 1.5: spec-free health. Runs even with NO spec, so free-play parts
        # are still protected against leaky/non-manifold, multi-body, or
        # degenerate solids the kernel's basic checks let slip through.
        problems = inspector.health(run.step_path)
        if problems:
            print(f"    HEALTH FAILED: {problems}")
            print("    --- code it wrote ---\n" +
                  "\n".join("    " + ln for ln in code.splitlines()))
            messages.append({"role": "user", "content":
                "The solid is unsound:\n"
                + "\n".join(f"- {p}" for p in problems)
                + "\nFix the script so it produces one clean, watertight solid. "
                  "Return code only."})
            continue

        if spec is not None:
            fails = inspector.verify(run.step_path, spec)
            if fails:
                print(f"    LAYER 2 FAILED (wrong part): {fails}")
                print("    --- code it wrote ---\n" +
                      "\n".join("    " + ln for ln in code.splitlines()))
                messages.append({"role": "user", "content":
                    "The geometry is valid but does not match the requirement:\n"
                    + "\n".join(f"- {f}" for f in fails)
                    + "\nFix the script so it matches. Return code only."})
                continue
            print("    LAYER 2 PASSED: part matches spec.")

        print(f"    SUCCESS: valid solid, volume={run.volume}, wrote {run.step_path}")
        _show_in_viewer(run.step_path)
        return GenResult(True, attempt, run, code, messages)

    print(f"--- gave up after {max_attempts} attempts ---")
    return GenResult(False, max_attempts, last_run, last_code, messages)


if __name__ == "__main__":
    import sys
    prompt = " ".join(sys.argv[1:]) or "a 100mm flange with a center bore and 6 bolt holes"
    print(f"PROMPT: {prompt}\n")
    spec = inspector.Spec(size=(100, 100, 10), holes={4: 6}, symmetry=6,
                          n_solids=1, tol=0.5)
    text_to_cad(prompt, spec=spec)
