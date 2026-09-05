"""OCCT SEGFAULTS on a real design — the reason the Fillet tool never probes a
value the user did not type (P4 review, 2026-09-04).

The shipped tool answered a refused radius by BISECTING for "the largest that
would fit": ~10 more fillet builds at radii nobody asked for. On the user's own
esp32-remote (254 faces, 609 edges) that is not merely slow —

    radius 4.0 on the "top" edge group -> a clean ValueError (the kernel refuses)
    radius 2.0 on the same edges       -> SIGSEGV, exit 139

so being helpful about the refusal at 4 would have killed studio.py and every
unsaved tab with it. No try/except can catch a segfault: the only safe rule is
that the kernel is called once, with the value the user typed.

This probe is the evidence, kept runnable. It CRASHES the interpreter by
design — run it in its own process, never inside the test suite:

    PYTHONPATH=. C:\\Python314\\python.exe probes\\fillet_segfault_probe.py 4      -> refusal
    PYTHONPATH=. C:\\Python314\\python.exe probes\\fillet_segfault_probe.py 2.0    -> exit 139

The user can still type 2.0 themselves. Since 2026-09-05 that costs one step,
not the session: `python studio.py` runs supervise.py, which relaunches the
server child after a crash the OS reported, with every tab as of the last
COMPLETED request (the session file is the checkpoint), and the UI says what
happened. tests/test_supervisor.py uses this very fillet as its startup-crash
case (a saved design whose rebuild segfaults comes back unbuilt).
"""
import json
import sys

import blocks
from document import Document

FIXTURE = "tests/fixtures/esp32-remote.tcad.json"


def main(radius: float, group: str = "top") -> None:
    doc = Document.from_data(json.load(open(FIXTURE, encoding="utf-8")))
    doc.rebuild()
    part = doc.result()
    edges = blocks.edges_for(part, group)
    print(f"{FIXTURE}: {len(part.faces())} faces, {len(part.edges())} edges; "
          f"'{group}' selects {len(edges)}", flush=True)
    print(f"fillet at radius {radius} ...", flush=True)
    try:
        out = blocks._b3d_fillet(edges, radius=radius)
        print(f"  built, volume {out.volume:.1f}", flush=True)
    except Exception as e:                      # OCP errors are Exception
        print(f"  clean refusal: {type(e).__name__}: {str(e)[:90]}", flush=True)
    print("survived — this radius is safe on this body", flush=True)


if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 2.0,
         sys.argv[2] if len(sys.argv) > 2 else "top")
