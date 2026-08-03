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
4. **UI shows old behavior after a JS change** — browser cache. The server now
   sends no-cache headers for `/` and `/static/*`; one Ctrl+F5 clears anything
   cached from before that fix.
4b. **Feature fails with "unexpected keyword argument"** — the SERVER process
   is running old backend code (Python doesn't hot-reload; new frontend sends
   params the old backend doesn't know). Symptom pattern: red TypeError in the
   tree, viewport missing the solid. Fix: restart the server — or launch with
   `python dev.py` (uvicorn reload=True) so backend edits auto-restart it.
   Freeing a stuck port works via `netstat -ano | findstr :PORT` + `taskkill
   /PID <pid> /F`.
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
9. **Taper works one way but not the other on a picked face** — the face's
   outline contains a straight BSPLINE seam edge (left by fusing a tapered /
   lofted body). build123d's tapered extrude offsets that wire with
   `BRepOffsetAPI_MakeOffset`, which for ONE offset sign silently returns a
   degenerate wire (a 4-edge rectangle came back as 1 edge), and `make_loft`
   then dies — `Standard_NoSuchObject`, or a 0xC0000005 access violation that
   kills the whole server. `sketch._straighten_face` rebuilds such edges as
   LINEs (fixing it), `_taper_offset_problem` pre-checks the offset so OCCT is
   never handed the garbage. If a NEW op offsets wires, it needs the same two
   guards. Diagnose with: print `[e.geom_type.name for e in
   face.outer_wire().edges()]` — a non-LINE entry on a visually straight edge
   is the tell.

## Diagnosis discipline
Read the actual log/traceback BEFORE forming a fix. Reproduce via TestClient
or a scratch script. Add a regression test for every real bug fixed.
