"""Section 13 ROUND TWO — the fix commit 6b7198d read adversarially.

Round one LOOSENED a guard (lint_tree(only=)) and added a new REFUSAL
(checked_spec). This probe measures, against the user's own 50 saved designs:

 1. AUTHOR_PROMPT is byte-identical to the version before the fix.
 2. how many saved designs carry a spec key `checked_spec` now refuses.
 3. what the scoped lint still refuses and what it now lets through:
      - the AI ADDING an absolute-offset sketch once a body exists
      - the AI EDITING a user feature into the banned form
      - the AI EDITING a user feature that ALREADY breaks the lint
      - the entity limit, on an add and on an edit
 4. _MINE / _free_name across a server restart, and the "untitled" door.

Run:  C:\\Python314\\python.exe probes/s13_round2_probe.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import author                     # noqa: E402
from document import Document     # noqa: E402

DESIGNS = ROOT / "designs"
OUT = []


def say(*a):
    line = " ".join(str(x) for x in a)
    OUT.append(line)
    print(line)


# ---------------------------------------------------------------------------
# 1. AUTHOR_PROMPT byte identity
# ---------------------------------------------------------------------------
def prompt_identity(old_dir: str):
    sys.path.insert(0, old_dir)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "author_old", Path(old_dir) / "author_old.py")
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    same = old.AUTHOR_PROMPT == author.AUTHOR_PROMPT
    say(f"[1] AUTHOR_PROMPT identical to 6b7198d^: {same} "
        f"(old {len(old.AUTHOR_PROMPT)} chars, new {len(author.AUTHOR_PROMPT)})")
    if not same:
        import difflib
        for d in list(difflib.unified_diff(
                old.AUTHOR_PROMPT.splitlines(), author.AUTHOR_PROMPT.splitlines(),
                lineterm=""))[:40]:
            say("    " + d)
    # and the shared tail really is a suffix of it
    say(f"[1] TREE_PROMPT ends with AUTHOR_PROMPT's conventions verbatim: "
        f"{author.TREE_PROMPT.endswith(author._SHARED_CONVENTIONS)} ; "
        f"conventions are a real suffix of AUTHOR_PROMPT: "
        f"{author.AUTHOR_PROMPT.endswith(author._SHARED_CONVENTIONS)}")


# ---------------------------------------------------------------------------
# 2. checked_spec over the saved library
# ---------------------------------------------------------------------------
def specs_of_library():
    refused, keys_seen = [], {}
    for p in sorted(DESIGNS.glob("*.tcad.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        spec = data.get("spec") or {}
        for k in spec:
            keys_seen[k] = keys_seen.get(k, 0) + 1
        try:
            author.checked_spec(spec)
        except ValueError as e:
            refused.append((p.stem, dict(spec), str(e)[:110]))
    say(f"[2] saved designs: {len(list(DESIGNS.glob('*.tcad.json')))}; "
        f"spec keys in use: {sorted(keys_seen)}")
    say(f"[2] designs whose SAVED spec checked_spec REFUSES: {len(refused)}")
    for name, spec, msg in refused:
        say(f"       {name}: {spec} -> {msg}")
    return refused


# ---------------------------------------------------------------------------
# 3. the scoped lint
# ---------------------------------------------------------------------------
def _plate_doc():
    d = Document(name="t")
    d.add("base_sketch", "sketch",
          {"entities": [{"kind": "rectangle", "w": 40, "h": 30}], "plane": "XY"}, [])
    d.add("base", "extrude", {"amount": 10}, ["base_sketch"])
    return d


def scoped_lint():
    # (a) the AI ADDS an absolute-offset sketch once a body exists: must refuse
    d = _plate_doc()
    d.rebuild()
    authored: set[str] = set()
    base = author.lint_baseline(d.features)
    ok, text, _ = author._apply_step(
        d, {"add": {"id": "boss_sketch", "op": "sketch",
                    "params": {"entities": [{"kind": "circle", "r": 5}],
                               "plane": "XY", "offset": 10}}},
        protected=frozenset(f.id for f in d.features), keep_spec=True,
        authored=authored, baseline=base)
    say(f"[3a] AI ADDS absolute-offset sketch on a body: ok={ok} :: {text[:110]}")

    # (b) the AI EDITS ITS OWN sketch into the banned form: must refuse
    d = _plate_doc()
    d.rebuild()
    authored = set()
    base = author.lint_baseline(d.features)
    prot = frozenset(f.id for f in d.features)
    ok1, t1, _ = author._apply_step(
        d, {"add": {"id": "boss_sketch", "op": "sketch",
                    "params": {"entities": [{"kind": "circle", "r": 5}],
                               "plane": "XY"}}}, prot, True, authored, base)
    ok2, t2, _ = author._apply_step(
        d, {"edit": {"feature_id": "boss_sketch", "param": "offset",
                     "value": 10}}, prot, True, authored, base)
    say(f"[3b] AI EDITS ITS OWN sketch to absolute Z: add ok={ok1}; "
        f"edit ok={ok2} :: {t2[:110]}")

    # (c) the AI EDITS a USER sketch into the banned form: must refuse
    d = _plate_doc()
    d.add("pocket_sketch", "sketch",
          {"entities": [{"kind": "circle", "r": 5}], "plane": "XY"}, [])
    d.rebuild()
    prot = frozenset(f.id for f in d.features)
    authored = set()
    base = author.lint_baseline(d.features)
    ok, text, _ = author._apply_step(
        d, {"edit": {"feature_id": "pocket_sketch", "param": "offset",
                     "value": 10}}, prot, True, authored, base)
    say(f"[3c] AI EDITS the USER's sketch to absolute Z: ok={ok} :: {text[:140]}")

    # (d) the AI edits an UNRELATED number of a USER feature that ALREADY
    #     breaks the lint (the F2 shape): must NOT be refused for the user's
    #     own violation.
    d = _plate_doc()
    d.add("pocket_sketch", "sketch",
          {"entities": [{"kind": "circle", "r": 5}], "plane": "XY",
           "offset": 10}, [])
    d.add("pocket", "extrude", {"amount": -3}, ["pocket_sketch"])
    d.add("cut", "cut", {}, ["base", "pocket"])
    d.rebuild()
    prot = frozenset(f.id for f in d.features)
    authored = set()
    base = author.lint_baseline(d.features)
    ok, text, _ = author._apply_step(
        d, {"edit": {"feature_id": "pocket", "param": "amount",
                     "value": -4}}, prot, True, authored, base)
    say(f"[3d] AI edits 'pocket.amount' (a DIFFERENT feature, but the user's "
        f"sketch above it floats): ok={ok} :: {text[:140]}")
    ok, text, _ = author._apply_step(
        d, {"edit": {"feature_id": "pocket_sketch", "param": "entities",
                     "value": [{"kind": "circle", "r": 6}]}},
        prot, True, authored, base)
    say(f"[3e] AI edits the user's ALREADY-floating sketch's entities "
        f"(does not touch offset): ok={ok} :: {text[:160]}")

    # (f) entity limit: the AI's own add
    many = [{"kind": "circle", "r": 1, "x": i * 3, "y": 0} for i in range(11)]
    d = _plate_doc()
    d.rebuild()
    prot = frozenset(f.id for f in d.features)
    authored = set()
    base = author.lint_baseline(d.features)
    ok, text, _ = author._apply_step(
        d, {"add": {"id": "art_sketch", "op": "sketch_on_face",
                    "params": {"entities": many, "face": "top", "offset": 0},
                    "inputs": ["base"]}}, prot, True, authored, base)
    say(f"[3f] AI adds an 11-entity sketch_on_face: ok={ok} :: {text[:110]}")
    d = _plate_doc()
    d.rebuild()
    prot = frozenset(f.id for f in d.features)
    authored = set()
    base = author.lint_baseline(d.features)
    ok, text, _ = author._apply_step(
        d, {"add": {"id": "art_sketch", "op": "sketch",
                    "params": {"entities": many, "plane": "XY"}}},
        prot, True, authored, base)
    say(f"[3g] AI adds an 11-entity plain sketch: ok={ok} :: {text[:110]}")

    # (h) the AI CRAMS a user's sketch past the limit by an edit
    d = _plate_doc()
    d.add("art_sketch", "sketch",
          {"entities": [{"kind": "circle", "r": 1}], "plane": "XY"}, [])
    d.rebuild()
    prot = frozenset(f.id for f in d.features)
    authored = set()
    base = author.lint_baseline(d.features)
    ok, text, _ = author._apply_step(
        d, {"edit": {"feature_id": "art_sketch", "param": "entities",
                     "value": many}}, prot, True, authored, base)
    say(f"[3h] AI crams the user's sketch to 11 entities by edit: ok={ok} "
        f":: {text[:110]}")


# ---------------------------------------------------------------------------
# 3'. the same question against the REAL library
# ---------------------------------------------------------------------------
def library_edit_door():
    """For every saved design: does the lint, as the edit branch asks it,
    refuse an edit to a feature the USER drew that already breaks a rule?"""
    blocked, scoped_blocked = [], []
    for p in sorted(DESIGNS.glob("*.tcad.json")):
        data = json.loads(p.read_text(encoding="utf-8"))
        try:
            doc = Document.from_data(data)
        except Exception as e:                       # noqa: BLE001
            say(f"       (skipped {p.stem}: {e})")
            continue
        items = author._lint_items(doc.features, final=False)
        if not items:
            continue
        fid = items[0][0][1] if len(items[0][0]) > 1 else None
        if fid is None:
            continue
        # ROUND ONE's rule: the edit branch lints scoped to `authored | {fid}`,
        # which always holds the edited feature — so its own pre-existing
        # problem refuses the edit.
        scoped = [t for k, _, t in items if len(k) > 1 and k[1] == fid]
        if scoped:
            scoped_blocked.append((p.stem, fid, scoped[0][:80]))
        # ROUND TWO's rule: the same edit against the job's baseline.
        base = author.lint_baseline(doc.features)
        now = author._lint_since(doc.features, base, final=False)
        if now:
            blocked.append((p.stem, fid, now[0][:80]))
    n = len(list(DESIGNS.glob("*.tcad.json")))
    say(f"[3i] round ONE: saved designs where an AI EDIT to one of the user's "
        f"own features is refused for that feature's PRE-EXISTING lint "
        f"problem: {len(scoped_blocked)} of {n}")
    for name, fid, msg in scoped_blocked[:6]:
        say(f"       {name}: editing '{fid}' -> {msg}")
    say(f"[3j] round TWO (the job's baseline): {len(blocked)} of {n}")
    for name, fid, msg in blocked[:6]:
        say(f"       {name}: editing '{fid}' -> {msg}")
    return blocked


# ---------------------------------------------------------------------------
# 4. _MINE / _free_name
# ---------------------------------------------------------------------------
def mine_across_restart(tmp: Path):
    import importlib
    import mcp_server
    mcp_server.OUT = tmp
    tmp.mkdir(parents=True, exist_ok=True)
    mcp_server._MINE.clear()
    def write(n, body="{}"):
        """what build_design does: claim, write, record what was written"""
        (tmp / f"{n}.tcad.json").write_text(body, encoding="utf-8")
        if hasattr(mcp_server, "_wrote"):
            mcp_server._wrote(n)

    names = [mcp_server._free_name("t-washer")]
    write(names[0])
    # same process, the design untouched: the doorbell promise
    names.append(mcp_server._free_name("t-washer"))
    say(f"[4a] same process, twice: {names} (must be the same file)")
    # a restart: _MINE empty, the file still on disk
    chain = []
    for _ in range(4):
        mcp_server._MINE.clear()          # <- a server restart
        n = mcp_server._free_name("t-washer")
        write(n)
        chain.append(n)
    say(f"[4b] four restarts, same request each time: {chain}")
    # the 'untitled' door: the server claims it, the USER then makes one
    mcp_server._MINE.clear()
    n = mcp_server._free_name("untitled")
    write(n, '{"mine": true}')
    # ...the user opens it (the doorbell just did) and saves their own edit
    (tmp / f"{n}.tcad.json").write_text('{"THE USERS WORK": true}',
                                        encoding="utf-8")
    again = mcp_server._free_name("untitled")
    say(f"[4c] server claimed '{n}', the user then saved their own design at "
        f"that name; the server's NEXT call returns '{again}' "
        f"-> {'OVERWRITES THE USER' if again == n else 'safe'}")
    say(f"[4d] _safe_name traversal: "
        f"{[mcp_server._safe_name(s) for s in ('../../evil', '..\\\\..\\\\evil', 'a/b', 'C:/x', '...', '')]}")
    importlib.reload(mcp_server) if False else None


if __name__ == "__main__":
    old_dir = sys.argv[1] if len(sys.argv) > 1 else None
    if old_dir:
        prompt_identity(old_dir)
    specs_of_library()
    scoped_lint()
    library_edit_door()
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        mine_across_restart(Path(td) / "designs")
    print("\n--- probe done ---")
