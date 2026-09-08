"""PostToolUse hook (Edit|Write): a Python file must pass Ruff's crash-class rules.

Runs `ruff check` with only the rules whose every hit is a certain runtime error
or a statement that cannot be right: E9 (syntax), F63 (bad comparisons such as
`is` with a literal), F7 (break/continue/return outside their block), F82
(undefined names, locals read before assignment) and PLE (pylint errors). The
broader ship-time set lives in ruff.toml; it stays out of the hook so an import
written before its first use does not nag mid-edit. A hit comes straight back
to Claude, the way the JS syntax check does.
"""
import importlib.util
import json
import subprocess
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)                       # a hook must never break a tool call
ti = data.get("tool_input") or {}
tr = data.get("tool_response") or {}
path = (ti.get("file_path") or tr.get("filePath") or "").replace("\\", "/")
if not path.endswith(".py"):
    sys.exit(0)
if importlib.util.find_spec("ruff") is None:
    sys.exit(0)                       # nothing to check with; stay silent
r = subprocess.run([sys.executable, "-m", "ruff", "check", "--no-cache",
                    "--select", "E9,F63,F7,F82,PLE", "--output-format", "concise",
                    path], capture_output=True, text=True)
if r.returncode != 0:
    print(json.dumps({
        "decision": "block",
        "reason": (f"ruff found a certain error in {path} (an undefined name, a "
                   f"syntax error, or a statement that cannot be right):\n"
                   f"{(r.stdout or r.stderr).strip()[:1500]}"),
    }))
sys.exit(0)
