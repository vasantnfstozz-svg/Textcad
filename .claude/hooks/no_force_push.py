"""PreToolUse hook (Bash|PowerShell): a force push is the user's decision.

Blocks `git push` with --force, --force-with-lease, -f or a +refspec. A force
push rewrites the online backup; the user runs it themselves when they want it.
"""
import json
import re
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)                       # a hook must never break a tool call
cmd = (data.get("tool_input") or {}).get("command") or ""
# each shell segment on its own, so `git status && git push -f` is caught
for seg in re.split(r"[;&|\n]+", cmd):
    if re.search(r"\bgit\b.*\bpush\b", seg) and re.search(
            r"(\s--force(-with-lease)?(=\S*)?(\s|$)|\s-f(\s|$)|\s\+\S+)", seg + " "):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                "A force push rewrites the online backup and is the user's decision. "
                "Give the user the exact command to run instead."),
        }}))
        break
sys.exit(0)
