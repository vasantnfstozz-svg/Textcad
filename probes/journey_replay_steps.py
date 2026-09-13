"""Replay a bug folder's RECORDED STEPS verbatim against a fresh server.

`tests/journeys.py --replay` needs `before.tcad.json`, and a folder filed by
`write_crash` has none: the process was gone before it could be written. But
`journey.json` holds every request in order, so the crash can be reached again
without paying for the random walk. -> the step that dies, printed as it goes.

    python probes/journey_replay_steps.py bugs/<folder> [--upto N]
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder")
    ap.add_argument("--upto", type=int, default=0, help="stop after this step number")
    a = ap.parse_args()
    rec = json.loads((Path(a.folder) / "journey.json").read_text(encoding="utf-8"))
    src = rec.get("file")
    from tests.journeys import load_document, make_client
    studio, client = make_client()
    doc = load_document(Path(src) if src else None)
    studio._new_tab(doc, source="replay")
    studio._rebuild_and_mesh()
    print(f"opened {src}: {len(doc.features)} features", flush=True)
    for s in rec.get("steps") or []:
        n = s.get("n")
        if a.upto and n > a.upto:
            break
        url, method, body = s.get("url"), s.get("method", "POST"), s.get("body")
        if not url:
            continue
        print(f"  #{n} {s.get('kind')} {s.get('op') or ''} -> {method} {url}", flush=True)
        t0 = time.perf_counter()
        r = client.get(url) if method == "GET" else client.post(url, json=body or {})
        ms = round((time.perf_counter() - t0) * 1000)
        print(f"     {r.status_code} {ms} ms", flush=True)
    print("replay finished without dying", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
