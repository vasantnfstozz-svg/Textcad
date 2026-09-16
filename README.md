# TextCAD — a robust text-to-CAD system

> **Historical document (July 2026).** This README describes the original
> command-line prototype (`generate.py` writing build123d code) and a
> long-fixed API-key blocker. The product today is **TextCAD Studio**, the
> feature-tree web app. Start with [CLAUDE.md](CLAUDE.md) for the map and the
> rules, [ARCHITECTURE.md](ARCHITECTURE.md) for how it works, and
> [LAUNCH-PLAN.md](LAUNCH-PLAN.md) for what is being built now. The founding
> idea below — mistakes must never reach the user — is unchanged.
>
> **To just run it on a fresh computer:** double-click `run-textcad.cmd`. It
> finds Python, installs what is missing the first time, and opens Studio in
> your browser. What TextCAD is built on, and under which licences, is in
> [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).

This is a working prototype that turns a natural-language description into a
validated, machinable CAD model (a STEP file). It was built step by step; this
document is the full context so development can continue in **Claude Code**
inside VS Code.

---

## 1. What we're building and why

The goal is a **text-to-CAD** system: you type "a 100mm flange with 6 bolt
holes" and get a real CAD solid you can machine from. The long-term target is
parts driven by engineering math — the motivating example is a **centrifugal
compressor / impeller**, where the geometry comes from calculations (blade
count, blade angles, hub and shroud curves, tip radius).

The core problem we're solving: naive text-to-CAD takes **3–4 attempts** to get
a correct part, because the model makes mistakes you only see after it renders.
This system is designed so **mistakes never reach the user** — they are caught
automatically and repaired in a loop.

---

## 2. The key architectural decision: code generation, not tool-calling

There are two ways an LLM can drive CAD:

- **Tool-calling** — the model calls discrete operations one at a time
  ("make box", "add hole") against a live kernel. Good for simple parts and
  interactive click-and-tweak editing. It struggles with long, math-heavy parts
  because error accumulates over a long chain of calls and there is no clean
  "re-run with new parameters".
- **Code generation** — the model writes a small program; the program runs and
  the geometry falls out. This is what we chose.

For a compressor (hundreds of operations, deeply parametric, and we already
*have* the calculations), code generation wins clearly. It's precise, it's
re-runnable with new parameters, and — most important — **code is checkable**:
if it's wrong, it fails loudly instead of silently making broken geometry. That
"fail loudly" property is the foundation of the whole robustness design.

This is the same approach Zoo (KittyCAD) uses with their KCL language. We use
an open Python stack instead of adopting their cloud engine.

---

## 3. The stack

- **OpenCASCADE (OCCT)** — the geometry kernel. Battle-tested industrial
  B-Rep/NURBS engine. This is the "oracle" that decides whether a solid is
  valid. Robustness comes from here, not from trusting the LLM.
- **build123d** — a Pythonic layer on top of OpenCASCADE. This is the language
  the LLM writes. Chosen over CadQuery because it's explicit and readable
  (plain variables, no hidden fluent state), which is easier for an LLM to get
  right and for us to validate.
- **An LLM** (currently Anthropic's Claude via API) — writes the build123d
  code. Any strong code model works; no fine-tuning needed to start.

Rejected: OpenSCAD / SolidPython — mesh/STL output only, cannot export STEP,
cannot machine from it.

---

## 4. The pipeline

```
natural language
   -> LLM writes build123d code
   -> engine.run_script executes it        [LAYER 1: valid geometry?]
   -> check.verify measures the solid       [LAYER 2: the RIGHT part?]
   -> (any failure) feed the error back to the LLM and retry (up to 3x)
   -> export STEP
```

Two walls a part must clear before it reaches the user:

- **Layer 1 (engine.py)** — catches broken code (bad API, syntax) and invalid
  geometry (self-intersections, empty booleans). The kernel is the judge.
- **Layer 2 (check.py)** — catches "valid but WRONG": a perfectly good solid
  that doesn't match the spec (e.g. 5 bolt holes when 6 were required). This is
  where the *engineering intelligence* lives, and where the compressor
  calculations plug in.

Both failures feed back into the same repair loop, so the model self-corrects.

---

## 5. The files

| File | Role |
|------|------|
| `engine.py`   | The verified core / "oracle". Takes a build123d script string, executes it safely, returns a structured result, exports STEP. Never raises. **Do not modify casually.** |
| `check.py`    | The domain checker (Layer 2). Measures a finished solid (bounding box, volume, hole count) and compares against a ground-truth `Spec`. Returns human-readable mismatches. |
| `generate.py` | The generator. Calls the LLM, runs the two-layer loop, feeds errors back, retries. Auto-selects real Claude vs an offline fake model. |

### Contracts (important for Claude Code)

`engine.run_script(code: str, step_path: str | None = None) -> RunResult`
- The script string **must** assign its final solid to a variable named `result`.
- `RunResult` fields: `ok: bool`, `stage: str` ("ok" | "exec" | "geometry"),
  `error: str | None`, `volume: float | None`, `step_path: str | None`.

`check.Spec(size=(X,Y,Z), holes={radius: count}, tol=0.5)`
- All fields optional; use `None` for a bbox axis you don't want to check.

`check.verify(step_path: str, spec: Spec) -> list[str]`
- Empty list == the part is correct. Otherwise, a list of mismatch strings.

`generate.text_to_cad(prompt, model=None, spec=None, max_attempts=3, step_path="generated.step") -> GenResult`

---

## 6. What works right now (verified)

- `engine.py` correctly passes a good script, catches a broken-API script at the
  `exec` stage, and catches impossible geometry at the `geometry` stage.
- `check.py` passes a correct 6-hole flange and flags a 5-hole one as wrong.
- `generate.py` runs the full two-layer loop end to end with the offline fake
  model: fails on a rigged bad script, repairs itself, passes both layers,
  writes `generated.step`. The STEP file opens correctly in real CAD software.

---

## 7. Current blocker (needs fixing next)

The live Claude API call raises an error. The last line of the traceback was cut
off, but it is one of three (in order of likelihood):

1. **400 – credit balance too low.** A new API key often has $0. The API needs
   its own credits, separate from the Claude Team subscription. Fix: add a few
   dollars in console.anthropic.com -> Billing.
2. **401 – authentication error.** Bad or mistyped key. Re-copy it from the
   console and re-set the environment variable.
3. **404 – model not found.** The account may not have access to
   `claude-opus-4-8`. Fix: change the default model in `AnthropicModel.__init__`
   to a model the account has (e.g. a current Sonnet).

**Action for Claude Code:** run `python generate.py "..."`, read the FULL last
line of the traceback, and apply the matching fix above.

---

## 8. How to run

```
# one-time: install deps
pip install build123d anthropic

# set the API key for THIS terminal session (never hardcode it in a file)
$env:ANTHROPIC_API_KEY = "sk-ant-...your-key..."   # PowerShell / Windows

# run
python generate.py "a 100mm flange with a center bore and 6 bolt holes"
```

If the key is picked up, output starts with `[using REAL Claude ...]`. With no
key set, it falls back to the offline fake model automatically.

---

## 9. Gotchas learned (save yourself the debugging)

- In build123d 0.11.x, `is_valid` is a **property**, not a method — write
  `solid.is_valid`, not `solid.is_valid()`. (This was the first hallucination
  the engine caught.)
- The API key goes in the **environment variable**, never in the code file, and
  must be set in the **same terminal** the script runs in.
- `$env:...` only lasts for that terminal session. Use `setx` to persist it,
  then open a new terminal.
- Hole-counting in `check.py` is a heuristic (it counts cylindrical faces by
  radius). It works well for prismatic parts like flanges. Robust feature
  recognition for arbitrary geometry is a deeper problem for later.

---

## 10. Roadmap / next steps

- **Part 4 — compressor domain checks (the big one).** Extend `check.py` with
  turbomachinery measurements: blade count, hub diameter, blade angle, tip
  radius. Feed real calculated values in as the `Spec`. This is the direct path
  to the compressor goal and where the system stops being a toy.
- **Live viewer.** Install the OCP CAD Viewer VS Code extension to see parts
  render live inside the editor as they're generated.
- **Visual feedback loop.** Render the built part to an image and feed it back
  to the model so it can catch its own visual mistakes (a second kind of
  Layer 2).
- **Prompt quality.** Improve the system prompt so the model writes better
  build123d on the first try, reducing repair rounds.

---

## For Claude Code: where to start

1. Fix the API blocker in Section 7 (run it, read the last traceback line).
2. Once a live part builds, confirm the two-layer loop by setting the spec in
   `generate.py` to something the model must work for (e.g. `holes={4: 8}` while
   the prompt asks for 6) and watch Layer 2 drive a repair.
3. Then start Part 4: this needs real compressor calculation values from the
   user before it's meaningful — ask for them.
