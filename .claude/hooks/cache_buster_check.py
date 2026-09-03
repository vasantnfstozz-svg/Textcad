"""Stop hook: a frontend change must bump main.js?v= in static/index.html.

A long-open browser tab keeps running the JavaScript it downloaded; only a new
version number in index.html makes Ctrl+F5 fetch the new code. Forgetting the
bump is the number one cause of "I fixed it but you still see the old
behaviour". If files under static/ are modified (uncommitted) and the version
line in index.html is not among the changes, Claude is told before it stops.
`stop_hook_active` guards against an endless loop.
"""
import json
import os
import subprocess
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    data = {}
if data.get("stop_hook_active"):
    sys.exit(0)
root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def git(*args):
    try:
        return subprocess.run(["git", *args], cwd=root, capture_output=True,
                              text=True, timeout=20).stdout
    except Exception:
        return ""


changed = set(git("diff", "--name-only", "HEAD", "--", "static/").split())
changed |= set(git("ls-files", "--others", "--exclude-standard", "--", "static/").split())
frontend = sorted(f for f in changed if f != "static/index.html")
if not frontend:
    sys.exit(0)
index_diff = git("diff", "HEAD", "--", "static/index.html")
if any(line.startswith("+") and "main.js?v=" in line for line in index_diff.splitlines()):
    sys.exit(0)
print(json.dumps({
    "decision": "block",
    "reason": (f"Frontend files changed ({', '.join(frontend)}) but main.js?v= in "
               f"static/index.html was not bumped. Read the CURRENT value in "
               f"static/index.html and raise it by one, so the user's browser loads "
               f"the new code (CLAUDE.md frontend rule). If these are another "
               f"session's uncommitted changes, say so and stop."),
}))
sys.exit(0)
