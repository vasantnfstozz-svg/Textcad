---
name: debug-studio
description: Diagnosis playbook for TextCAD Studio problems — server won't start, MCP disconnected, geometry check failures, UI showing stale code. Load when anything is broken or behaving unexpectedly.
---

# Debugging TextCAD — known failure modes and where to look

## Where the evidence lives
- **Studio server output**: the background task's output file (shown when the
  task was launched). Python buffers stdout when redirected — use `python -u`
  if you need live output.
- **MCP server log**: `%APPDATA%\Claude\logs\mcp-server-textcad.log` — the
  actual traceback for any "Server disconnected" in Claude Desktop.
- **No server needed for API debugging**: use FastAPI's TestClient
  (`from fastapi.testclient import TestClient; TestClient(studio.app)`) —
  the whole API works in-process (see tests/test_api.py fixtures).

## Known failure modes (all hit before, all real)
1. **Port 8123 in use (WinError 10048)** — an old `python studio.py` is still
   alive. Find/stop it before relaunching.
2. **Two Pythons** — Desktop/PATH may resolve `python` to 3.12; everything is
   installed in `C:\Python314\python.exe`. Use absolute paths in configs.
3. **MCP "Server disconnected"** — module missing (wrong python) OR something
   printed to stdout (stdout IS the protocol). Keep geometry calls inside
   `_quiet()` in mcp_server.py.
4. **UI shows old behavior after a JS change** — browser cache. Bump
   `main.js?v=N` in index.html and hard-refresh (Ctrl+F5).
5. **Sphere-bearing solids "not manifold"** — build123d 0.11 false negative;
   inspector.health already tolerates it (checks for GeomType.SPHERE faces).
6. **`setx` env var invisible** — processes inherit VS Code's env from before
   setx. Read via registry: `[Environment]::GetEnvironmentVariable(name,"User")`
   in PowerShell or `studio._user_env()` in Python.
7. **Boss/extrude "not working"** — usually the new body isn't FUSED with the
   base (line contact ≠ fusion; result() shows the last solid only). Check
   n_solids in inspector.measure.
8. **Model returns empty viewport** — a bare sketch has no volume; sketches
   ship separately in /api/model's `sketches` list (unconsumed only).

## Diagnosis discipline
Read the actual log/traceback BEFORE forming a fix. Reproduce via TestClient
or a scratch script. Add a regression test for every real bug fixed.
