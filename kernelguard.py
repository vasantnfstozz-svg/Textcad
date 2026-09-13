"""kernelguard.py — the kernel calls that can kill the process run somewhere else.

WHY. OpenCASCADE segfaults. Not on nonsense, but on the user's own parts, in
one click, with no exception any `except` can ever see (an access violation is
not an exception — the process is simply gone). The overnight journey run of
2026-09-13 filed four of them, and the measurements that followed say no
geometric bound fences any of them:

  * `fillet` on the EIGHT flat rims of a sliver body dies with 0xC0000005 at
    every radius from 0.05 to 0.5 and refuses politely at 0.8 and up; any ONE
    of those rims alone never crashes, and all 53 edges at once never crash
    either (my-part-8 seed 46791; probes/fillet_crash_sweep.py,
    probes/fillet_crash_bisect.py).
  * `shell {thickness 1.1, open "bottom"}` on the oneplus case dies, while 0.2
    builds and 2.0 refuses cleanly — the window is NOT monotonic in thickness
    (probes/shell_open_face_crash.py).
  * a CLOSED `shell` of 1.9 on the pump impeller's three lumps dies at every
    thickness from 0.8 to 2.9, and the SAME shell built at the previous z; the
    edit moved one lump by 14 mm3 and left every bounding box identical
    (probes/shell_third_crash.py).
  * `shell` OUTSIDE on a box-clipped ball dies from 1.2 mm up, and no bound
    applies to GROWING a body at all (probes/shell_thick_wall_sweep.py).

Four bodies, three shapes of crash. Shell's own review spent three rounds on
geometric guards and TWICE ended up refusing correct geometry, so the answer
here is not another bound.

HOW. One WARM worker process holds build123d imported and answers jobs over a
pipe. The body crosses as a .brep file. If the worker dies, the parent turns
the death into a plain sentence, records it, and starts a fresh worker; if the
worker is still working past the budget, it is killed and the wait becomes a
sentence. The server lives either way, and the feature goes red like any other
refusal.

WARM on purpose: a fresh python that imports build123d costs 10-30 SECONDS on
this machine (measured, probes/sidecar_cost.py), so a process per call would
put that on every fillet. The worker starts once; only its DEATH costs a
restart, and that restart runs in the background so the next click is warm.

WHAT CROSSES. Never a shape object, and never a name the child has to resolve
for itself. Two reasons, both measured:

  * build123d filters shell openings with `[o for o in openings if o in
    solid.faces()]` and `Shape.__eq__` is `IsSame` — a Face belonging to any
    other instance of the same solid is dropped SILENTLY, so a body meant to
    be open would come back a closed hollow, all green, wrong part.
  * a re-resolve in the child could land on a DIFFERENT edge or face, which
    turns a crash into silent wrong geometry. That is strictly worse: a crash
    costs one step, a wrong body reaches the user.

So the parent resolves the picks — that has never crashed — and sends INDICES
plus a FINGERPRINT of each picked shape. The child takes `part.edges()[i]`,
measures it, and refuses if it does not match the fingerprint. The .brep round
trip is proven to preserve edge and face ORDER and geometry exactly on six
bodies up to 2862 edges (probes/sidecar_roundtrip.py, probes/sidecar_cost.py);
this checks it anyway, on every single call, because "proven on six bodies" is
not "true for the seventh".
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# How long ONE guarded kernel call may run before it is a hang, not work.
# Deliberately generous. The overnight run recorded a chamfer on every edge of
# a traced keychain taking 630 s and answering CORRECTLY, and one /api/edit
# spinning for 3 hours and 6 minutes with a flat working set. A tight ceiling
# would refuse the user's own keychain to catch the spin, so the ceiling sits
# above every correct answer ever measured and below any spin.
DEFAULT_BUDGET = float(os.environ.get("TEXTCAD_KERNEL_SECONDS") or 900.0)

# A cold worker imports build123d: 10-30 s measured on this machine, and a
# loaded box is slower. This is the wait for its "ready", not for any work.
READY_SECONDS = float(os.environ.get("TEXTCAD_KERNEL_READY") or 180.0)

# A ceiling on the worker's memory, GB, 0 = off. One spec symmetry boolean
# reached 44 GB on a 16 GB box on 2026-09-12 and took the laptop down with it;
# under a ceiling the kernel gets a refused allocation instead, the worker
# dies, and the user gets a sentence (tests/journeys.py runs its children the
# same way).
MEMORY_GB = float(os.environ.get("TEXTCAD_KERNEL_GB") or 6.0)

CRASH_LOG = ROOT / "bugs" / "kernel-crashes.log"

# The phrase every crash refusal carries, so the journey runner (and a grep)
# can still tell a crash from an ordinary refusal now that the process lives.
CRASH_PHRASE = "crashed the geometry kernel"
STOPPED_PHRASE = "was stopped after"


class KernelGone(ValueError):
    """The worker died, or would not stop, or came back with a shape that is
    not the one it was asked about.

    A ValueError so `Document.rebuild` paints it into the feature row like any
    other refusal. `transient` is read there too: this failure is NOT cached
    against the feature's signature, because a crash is not a broken
    parameter and the user must be able to press the same button again."""
    transient = True


def _on() -> bool:
    """Read at every call, not at import: a test that wants the raw in-process
    kernel (to spy on it, or to prove what OCCT really returns) turns the guard
    off with monkeypatch.setenv, and the user has an escape hatch."""
    return str(os.environ.get("TEXTCAD_KERNEL_GUARD", "1")).lower() \
        not in ("0", "no", "off", "false", "")


# ---------------------------------------------------------------------------
# Fingerprints — what a picked shape must still measure on the other side
# ---------------------------------------------------------------------------

def _mark(shape) -> list:
    """An edge measures by length, a face by area; build123d puts BOTH
    attributes on every Shape and returns None for the wrong one. Rounded to 6
    decimals: the round trip is exact to 9 on every body probed, and a
    different edge is never this close."""
    size = 0.0
    for attr in ("length", "area"):
        v = getattr(shape, attr, None)
        if isinstance(v, (int, float)):
            size = float(v)
            break
    c = shape.center()
    return [round(size, 6), round(c.X, 6), round(c.Y, 6), round(c.Z, 6)]


MARK_TOL = 1e-4


def _marks(shapes) -> list:
    return [_mark(s) for s in shapes]


def indices(whole: list, picked: list) -> list:
    """Where each picked shape sits in the body's own list. Identity is OCCT's
    (`IsSame`, through build123d's `__eq__`), never a geometric guess.

    Keyed by `hash(shape.wrapped)` — the same identity `blocks._shape_key` uses
    to de-duplicate picks — because a straight scan is O(picked x edges) and a
    traced outline has 2862 of them. OCCT's hash CAN collide, so every
    candidate is confirmed with `==` before it is believed."""
    by_key: dict = {}
    for i, s in enumerate(whole):
        by_key.setdefault(hash(s.wrapped), []).append(i)
    out = []
    for p in picked:
        hit = next((i for i in by_key.get(hash(p.wrapped), ()) if whole[i] == p), None)
        if hit is None:
            # The hash is a shortcut, not the rule. `edges_for` can hand back an
            # edge taken from `part.faces()[i].edges()` rather than from
            # `part.edges()`, and OCCT's hash folds in ORIENTATION where
            # `IsSame` does not — so a reversed twin of the right edge could
            # miss. Falling back to the scan the hash was avoiding costs time
            # only when it happens, and REFUSING a correct pick would be a bug
            # the user feels.
            hit = next((i for i, s in enumerate(whole) if s == p), None)
        if hit is None:
            raise KernelGone("a shape that was picked is not part of this body")
        out.append(hit)
    return out


def read_body(path: str):
    """A body back off the disk, as the kind of shape it was written as.

    `import_brep` hands back what was in the file: a Compound for a body that
    was a `Part` (however many lumps), and a BARE `Solid` for one that was a
    bare Solid — `blocks.fillet_edges` is called with both, from the tree and
    from the tests. Wrapping a bare Solid in a `Part` gives a body whose volume
    reads **0** — measured, `probes/brep_reimport_types.py`: 24000 mm3 becomes
    0.0000 — because `Part` is a Compound and a Compound's volume is the sum
    over its children, of which a TopoDS_Solid has none. (The STL import hit
    the same trap.) A Compound IS re-typed as a `Part`, because that is what
    went in and `sketch.is_sketch` and the rebuild's 2D/3D fork read the type.

    The weight check below is what found this, on the first full run of the
    fast tier. It stays because the next shape kind will not announce itself
    either."""
    from build123d import Compound, Part, import_brep
    shape = import_brep(str(path))
    return Part(shape.wrapped) if isinstance(shape, Compound) else shape


def same_weight(what: str, got: float, expected) -> None:
    """A body must weigh the same on both sides of the pipe.

    This is the one check that would catch a .brep round trip quietly changing
    a shape — a compound flattened into one lump, a transform baked in, a face
    dropped. Every body probed came back exact to nine decimals, so the
    tolerance is tight on purpose: anything looser would let real damage
    through, and a false alarm here costs one refused step, not a wrong part."""
    if expected is None:
        return
    if abs(got - expected) > max(1e-9 * abs(expected), 1e-9):
        raise KernelGone(
            f"{what} does not weigh the same on both sides of the geometry "
            f"worker ({expected:.10g} mm3 became {got:.10g} mm3), so the step "
            f"was refused rather than handing back a body that changed on the "
            f"way")


def take(shapes, picks: list, marks: list, what: str) -> list:
    """The child's half: shape number i, MEASURED against what the parent said
    it was. Shared with the parent so both sides use one rule."""
    out = []
    for i, mark in zip(picks, marks):
        if not 0 <= i < len(shapes):
            raise KernelGone(
                f"the {what} that was picked is no longer on this body "
                f"(it has {len(shapes)}), so the step was refused rather than "
                f"working on a different one")
        got = _mark(shapes[i])
        if any(abs(a - b) > MARK_TOL for a, b in zip(got, mark)):
            raise KernelGone(
                f"the {what} that was picked measures differently on the body "
                f"the geometry worker read back, so the step was refused "
                f"rather than working on a different one")
        out.append(shapes[i])
    return out


# ---------------------------------------------------------------------------
# The parent: one warm worker, and what to do when it dies
# ---------------------------------------------------------------------------

_LOCK = threading.Lock()            # one kernel workload at a time, house rule
_WORKER: "_Worker | None" = None
_SCRATCH: Path | None = None
_SEQ = 0


def _scratch() -> Path:
    global _SCRATCH
    if _SCRATCH is None:
        _SCRATCH = Path(tempfile.mkdtemp(prefix="textcad-kernel-"))
    return _SCRATCH


def _quiet_crash_dialogs() -> None:
    """Windows: no 'python.exe has stopped working' box keeping a dead worker
    alive for ever instead of letting it die. Inherited by children."""
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
        except Exception:
            pass


def _cap_memory(proc, gb: float) -> None:
    """Put the worker in a Windows Job object with a hard memory ceiling, so a
    runaway allocation is refused instead of swallowing the machine (one spec
    boolean reached 44 GB on a 16 GB box on 2026-09-12 and took the laptop
    down). Same mechanism as probes/memcap.py; silently skipped off Windows,
    and a ceiling that cannot be set never fails a build.

    Unlike tests/journeys.py's JobCap this does NOT start the child suspended:
    the gap it leaves is the microseconds before python has run a line, and a
    suspended start would have to reach into Popen's private handle. The job
    handle is deliberately kept for the life of the process rather than closed,
    because closing it would kill the worker (KILL_ON_JOB_CLOSE)."""
    if os.name != "nt" or gb <= 0:
        return
    try:
        import ctypes
        import ctypes.wintypes as wt

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class _IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in
                        ("r", "w", "o", "rt", "wt", "ot")]

        class _BASIC(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", wt.LARGE_INTEGER),
                        ("PerJobUserTimeLimit", wt.LARGE_INTEGER),
                        ("LimitFlags", wt.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wt.DWORD),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wt.DWORD),
                        ("SchedulingClass", wt.DWORD)]

        class _EXT(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", _BASIC),
                        ("IoInfo", _IO),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        job = k32.CreateJobObjectW(None, None)
        if not job:
            return
        info = _EXT()
        info.BasicLimitInformation.LimitFlags = 0x200 | 0x2000   # JOB_MEMORY | KILL_ON_CLOSE
        info.JobMemoryLimit = int(gb * (1 << 30))
        k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
        handle = getattr(proc, "_handle", None)
        if handle is not None:
            k32.AssignProcessToJobObject(job, int(handle))
        proc._textcad_job = job          # keep the handle alive with the process
    except Exception:
        pass                             # a missing ceiling must never fail a build


class _Worker:
    """A live worker process plus the two threads that read it. stderr is
    drained on its own thread on purpose: `communicate()` on the calling thread
    deadlocks exactly when the child hangs, which is the one case this exists
    for."""

    def __init__(self) -> None:
        _quiet_crash_dialogs()
        env = dict(os.environ)
        env["TEXTCAD_KERNEL_WORKER"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        self.proc = subprocess.Popen(
            [sys.executable, "-u", str(ROOT / "kernelguard.py"), "--worker"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            cwd=str(ROOT), env=env, text=True, encoding="utf-8", errors="replace")
        _cap_memory(self.proc, MEMORY_GB)
        self.lines: queue.Queue = queue.Queue()
        self.errors: deque = deque(maxlen=60)
        threading.Thread(target=self._read_out, daemon=True).start()
        threading.Thread(target=self._read_err, daemon=True).start()
        self.started = time.monotonic()
        self.ready = False

    def _read_out(self) -> None:
        try:
            for line in self.proc.stdout:
                self.lines.put(line)
        except Exception:
            pass
        self.lines.put(None)                      # EOF: the worker is gone

    def _read_err(self) -> None:
        try:
            for line in self.proc.stderr:
                self.errors.append(line.rstrip())
        except Exception:
            pass

    def answer(self, want: int, budget: float) -> dict:
        """The next JSON line carrying `want`, or a raised KernelGone. Lines
        that are not ours (a library printing to stdout) are skipped without
        spending the whole budget on one of them."""
        end = time.monotonic() + budget
        while True:
            left = end - time.monotonic()
            if left <= 0:
                raise TimeoutError
            try:
                line = self.lines.get(timeout=left)
            except queue.Empty:
                raise TimeoutError from None
            if line is None:
                raise EOFError
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("seq") == want:
                return msg

    def send(self, job: dict) -> None:
        self.proc.stdin.write(json.dumps(job) + "\n")
        self.proc.stdin.flush()

    def wait_ready(self) -> None:
        self.answer(0, READY_SECONDS)
        self.ready = True

    def stop(self) -> None:
        for step in (self.proc.kill, self.proc.wait):
            try:
                step()
            except Exception:
                pass


def _fresh_worker() -> "_Worker":
    w = _Worker()
    try:
        w.wait_ready()
    except (TimeoutError, EOFError, OSError) as e:
        w.stop()
        raise KernelGone(
            "the geometry worker would not start, so the step was refused "
            "rather than risking the app; restarting TextCAD Studio fixes "
            "this") from e
    return w


def _warm_up_soon() -> None:
    """Start the replacement in the background, so the click AFTER a crash is
    not the one that pays the 10-30 s import."""
    def go():
        global _WORKER
        with _LOCK:
            if _WORKER is None:
                try:
                    _WORKER = _fresh_worker()
                except Exception:
                    _WORKER = None
    threading.Thread(target=go, daemon=True).start()


def _facts(job: dict) -> dict:
    """The job without the parts that are noise in a log: the fingerprints, and
    the two sentences the record carries once as `said`."""
    return {k: v for k, v in job.items()
            if k not in ("marks", "crashed", "stopped")}


def _record(what: str, detail: dict, tail: list) -> None:
    """A crash still has to be findable after it has been turned into a polite
    sentence — otherwise the journey runner stops filing them and the next one
    is invisible."""
    try:
        CRASH_LOG.parent.mkdir(parents=True, exist_ok=True)
        with CRASH_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"when": time.strftime("%Y-%m-%d %H:%M:%S"),
                                 "what": what, **detail,
                                 "stderr": tail[-8:]}) + "\n")
    except Exception:
        pass


def call(kind: str, body, job: dict, budget: float | None = None):
    """Run one dangerous kernel job in the worker. Returns a build123d Part.

    Raises ValueError — the worker's own refusal sentence, unchanged — or
    KernelGone when the worker died, timed out, or read back a shape that is
    not the one it was asked about."""
    global _WORKER, _SEQ
    from build123d import export_brep

    budget = DEFAULT_BUDGET if budget is None else budget
    with _LOCK:
        _SEQ += 1
        seq = _SEQ
        here = _scratch()
        in_path = here / f"{seq}-in.brep"
        out_path = here / f"{seq}-out.brep"
        export_brep(body, str(in_path))
        # The body's own weight travels with it, and the worker weighs what it
        # read before it touches anything. The .brep round trip is exact to the
        # last decimal on every body probed — and "exact on the six we tried"
        # is not "exact on the seventh", so it is checked, not assumed. A body
        # that changed in transit must fail the step, never quietly become the
        # thing the user gets back.
        payload = dict(job, seq=seq, call=kind, volume=body.volume,
                       body=str(in_path), out=str(out_path))
        try:
            # OUTSIDE the try below on purpose: a worker that never started is
            # not a worker whose stderr and exit code can be read, and reaching
            # for them would turn a clear refusal into an AttributeError
            if _WORKER is None:
                _WORKER = _fresh_worker()
            try:
                _WORKER.send(payload)
                msg = _WORKER.answer(seq, budget)
            except (TimeoutError, EOFError, OSError) as e:
                tail = list(_WORKER.errors)
                # stop() first: a worker that has just died has not been reaped
                # yet, so poll() answers None and the log would say "unknown"
                # where 0xC0000005 is the whole point of the record
                _WORKER.stop()
                code = _WORKER.proc.poll()
                _WORKER = None
                _warm_up_soon()
                if isinstance(e, TimeoutError):
                    said = job["stopped"].replace("<minutes>", _minutes(budget))
                    _record("timeout", {"kind": kind, "seconds": budget,
                                        **_facts(job), "said": said}, tail)
                    raise KernelGone(said) from None
                _record("crash", {"kind": kind, "exit": _hex(code),
                                  **_facts(job), "said": job["crashed"]}, tail)
                raise KernelGone(job["crashed"]) from None
            if msg.get("ok"):
                out = read_body(out_path)
                same_weight("the result", out.volume, msg.get("volume"))
                return out, msg.get("notes") or []
            raise ValueError(msg.get("error") or
                             f"{kind}: the geometry worker could not finish this step")
        finally:
            for p in (in_path, out_path):
                try:
                    p.unlink()
                except OSError:
                    pass


def _hex(code: int | None) -> str:
    return "unknown" if code is None else f"{code & 0xFFFFFFFF:#010x}"


def _minutes(seconds: float) -> str:
    """The budget in the words a person would use. Minutes below 90 seconds
    read as "0.00416667 minutes", which is not a sentence anyone can act on."""
    if seconds < 90:
        return f"{round(seconds, 2):g} seconds"
    m = seconds / 60.0
    return f"{round(m, 1):g} minute" + ("" if abs(m - 1) < 0.05 else "s")


def guarded(kind: str, body, job: dict, in_process, budget: float | None = None):
    """Run `job` in the worker when the guard is on, and `in_process()` when it
    is off or the worker cannot be had. One entry point so both halves of the
    product ask the same question in the same words."""
    if not _on():
        return in_process()
    out, notes = call(kind, body, job, budget)
    if notes:
        import sketch
        for n in notes:
            sketch._note(n)
    return out


def shutdown() -> None:
    """Stop the worker (tests, and a deliberate server stop)."""
    global _WORKER
    with _LOCK:
        if _WORKER is not None:
            _WORKER.stop()
            _WORKER = None


# ---------------------------------------------------------------------------
# The worker: imports the kernel once, then answers jobs until stdin closes
# ---------------------------------------------------------------------------

def _worker_main() -> None:
    import blocks
    import sketch
    from build123d import export_brep

    def say(msg: dict) -> None:
        sys.stdout.write(json.dumps(msg) + "\n")
        sys.stdout.flush()

    say({"seq": 0, "ready": True})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            job = json.loads(line)
        except ValueError:
            continue
        seq = job.get("seq")
        try:
            part = read_body(job["body"])
            same_weight("the body", part.volume, job.get("volume"))
            sketch.drain_notes()                    # this job's notes only
            if job["call"] == "blend":
                picked = take(part.edges(), job["picks"], job["marks"], "edge")
                out = blocks.blend_after_guards(
                    job["kind"], part, picked, job["value"], job["unit"])
            elif job["call"] == "shell":
                openings = take(part.faces(), job["picks"], job["marks"], "face")
                out = sketch.shell_after_guards(
                    part, job["thickness"], job["direction"], openings, job["walls"])
            else:
                raise ValueError(f"unknown job {job['call']!r}")
            export_brep(out, job["out"])
            say({"seq": seq, "ok": True, "volume": out.volume,
                 "notes": sketch.drain_notes()})
        except Exception as e:                      # OCP errors ARE Exceptions
            sketch.drain_notes()
            say({"seq": seq, "ok": False,
                 "error": str(e) if isinstance(e, ValueError) else blocks.plain_cause(e)})


if __name__ == "__main__":
    if "--worker" in sys.argv:
        _worker_main()
    else:
        print(__doc__)
