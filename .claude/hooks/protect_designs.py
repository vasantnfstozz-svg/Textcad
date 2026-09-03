"""PreToolUse hook (Edit|Write): the user's design library is not edited by hand.

Blocks direct edits to designs/<slug>.tcad.json, designs/<slug>.history/** and
the live session file. Twice this project nearly rewrote a design under an open
Studio tab (the stale-tab trap) and once a test overwrote a library file.
Designs change through the app (or a generator script run through the shell),
never through a text edit. Frozen copies under tests/fixtures/ stay editable.
"""
import json
import re
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)                       # a hook must never break a tool call
path = ((data.get("tool_input") or {}).get("file_path") or "").replace("\\", "/")
rules = (
    (r"(^|/)designs/[^/]+\.tcad\.json$", "a design file in the library"),
    (r"(^|/)designs/[^/]+\.history(/|$)", "a design's version history"),
    (r"(^|/)\.studio-session[^/]*\.json$", "the live Studio session file"),
)
for pattern, what in rules:
    if re.search(pattern, path):
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": (
                f"{path} is {what} — the user's work. It is never edited by hand "
                f"(a Studio tab may hold it: editing the file underneath is the "
                f"stale-tab trap). Change designs through the app's API, or run "
                f"the design's generator script; test data belongs in tests/fixtures/."),
        }}))
        break
sys.exit(0)
