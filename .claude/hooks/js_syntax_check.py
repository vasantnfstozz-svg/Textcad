"""PostToolUse hook (Edit|Write): a JavaScript file under static/js must parse.

Runs `node --check` on the edited file. A syntax error is otherwise found only
when the user presses Ctrl+F5 and the whole studio fails to load, followed by a
debugging round. On failure the error is fed straight back to Claude.
"""
import json
import shutil
import subprocess
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)                       # a hook must never break a tool call
ti = data.get("tool_input") or {}
tr = data.get("tool_response") or {}
path = (ti.get("file_path") or tr.get("filePath") or "").replace("\\", "/")
if not (path.endswith(".js") and "/static/js/" in path):
    sys.exit(0)
node = shutil.which("node")
if not node:
    sys.exit(0)                       # nothing to check with; stay silent
r = subprocess.run([node, "--check", path], capture_output=True, text=True)
if r.returncode != 0:
    print(json.dumps({
        "decision": "block",
        "reason": (f"node --check failed on {path} — the studio would not load this "
                   f"file:\n{(r.stderr or r.stdout).strip()[:1500]}"),
    }))
sys.exit(0)
