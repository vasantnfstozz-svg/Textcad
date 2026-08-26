"""history.py — the per-design version tree (P1 of VERSION-TREE-PLAN.md).

Storage only. No HTTP, no UI, no Document import: this layer moves JSON in and
out of disk and knows the shape of a version tree, nothing else. That is
deliberate — everything above it is plumbing, and this is the part that has to
be right.

Layout, one sidecar directory per design:

    designs/esp32-remote.tcad.json      # the CURRENT design, untouched by us
    designs/esp32-remote.history/
        index.json                      # the tree: nodes, parents, labels, star
        v1.json.gz                      # a Document.to_data() payload
        v2.json.gz

A directory rather than one big file, for two reasons that both bite in
practice: appending a version must not rewrite the whole history, and one
corrupt snapshot must not take the other twenty with it.

Snapshots are gzipped. Measured on the real library, not assumed: feature-tree
JSON compresses 12-19x (cam-cover-plaque 198 KB -> 10.4 KB), so a design's
entire history costs less than one raw copy of it.

Four invariants worth stating out loud, because the tests exist to pin them:

1. **A version is only recorded when the content hash changes** (compared
   against its parent). Re-opening a design, or an edit that lands back on the
   same numbers, must never pad the tree. The whole feature exists because too
   many near-identical things made the real one hard to find; a version list
   that grows on no-ops would just be the tab explosion in a new costume.
2. **Editing from an old version BRANCHES.** `parent` defaults to `current`, so
   restoring v3 and saving makes a child of v3 and leaves v4..v10 reachable.
   A history that truncated on restore would silently destroy the newer work.
3. **The snapshot is written before the index.** A crash in between leaves an
   orphaned `.json.gz` — garbage, but harmless. The other order would leave the
   index promising a version whose payload does not exist.
4. **A broken index is never overwritten.** Writes refuse and say why; the
   snapshots are still on disk and `repair()` rebuilds an index from them.
   Silently starting a fresh index would throw away recoverable versions.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import shutil
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = 1
INDEX = "index.json"
SUFFIX = ".history"
_VID = re.compile(r"^v(\d+)$")


class HistoryError(Exception):
    """A history on disk is unusable, described in words a user can act on."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def content_hash(data: dict) -> str:
    """Hash of a design's INTENT. Canonical separators and sorted keys so that
    re-serialising the same design can never look like a change."""
    blob = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return "sha1:" + hashlib.sha1(blob.encode("utf-8")).hexdigest()


def _write_atomic(path: Path, blob: bytes) -> None:
    """Write via temp + os.replace, which is a genuine atomic overwrite on
    Windows too (probed, not assumed). A half-written index.json would cost the
    user every version they have."""
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(blob)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


@dataclass
class Version:
    """One node of the tree. `spec` and `rebuildable` are whatever the caller
    measured — this layer stores them, it does not compute geometry."""
    id: str
    parent: str | None = None
    created: str = ""
    label: str = ""
    source: str = ""
    hash: str = ""
    features: int = 0
    spec: dict = field(default_factory=dict)
    commit: str | None = None
    rebuildable: bool | None = None

    @classmethod
    def from_data(cls, d: dict) -> "Version":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


class History:
    """The version tree of one design, backed by a directory."""

    # -- construction ------------------------------------------------------

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._data: dict | None = None
        self._problems: list[str] = []
        self._load()

    @classmethod
    def for_design(cls, designs_dir: str | Path, slug: str) -> "History":
        return cls(Path(designs_dir) / f"{slug}{SUFFIX}")

    # -- disk --------------------------------------------------------------

    def _blank(self, name: str = "") -> dict:
        return {"schema": SCHEMA, "design_id": "d_" + uuid.uuid4().hex[:12],
                "name": name, "current": None, "starred": None, "versions": []}

    def _load(self) -> None:
        """Never raises. A history that cannot be read reports itself through
        `problems()` and behaves as empty for READS; writes refuse separately,
        so a corrupt index is never quietly replaced."""
        self._problems = []
        idx = self.path / INDEX
        if not idx.exists():
            # "no index" and "the index vanished from under real snapshots" are
            # very different situations and must not read the same. The second
            # is recoverable data loss, so say so instead of reporting an empty
            # history and letting the user believe there was never anything.
            orphans = sorted(self.path.glob("v*.json.gz"))
            if orphans:
                self._problems.append(
                    f"{idx} is missing but {len(orphans)} version snapshot(s) "
                    f"are still in {self.path.name} — History.repair() rebuilds "
                    f"an index from them.")
            self._data = None
            return
        try:
            data = json.loads(idx.read_text(encoding="utf-8"))
        except Exception as e:
            self._problems.append(
                f"{idx} is unreadable ({e}). The version snapshots are still "
                f"on disk — History.repair() rebuilds the index from them.")
            self._data = None
            return
        if not isinstance(data, dict) or "versions" not in data:
            self._problems.append(f"{idx} is not a history index (no "
                                  f"'versions'). Nothing was changed.")
            self._data = None
            return
        got = data.get("schema")
        if got != SCHEMA:
            self._problems.append(
                f"{idx} is schema {got!r}, this build understands {SCHEMA}. "
                f"Refusing to touch it rather than risk mangling it.")
            self._data = None
            return
        self._data = data

    def _save(self, data: dict | None = None) -> None:
        """Persist, THEN adopt. Every writer builds a new index dict and hands
        it here; `self._data` only advances once the bytes are down. Mutating in
        place first would leave a live History disagreeing with its own disk
        after a failed write — the kind of split-brain that is invisible until
        it has already cost the user a version."""
        payload = self._data if data is None else data
        self.path.mkdir(parents=True, exist_ok=True)
        _write_atomic(self.path / INDEX,
                      json.dumps(payload, indent=2).encode("utf-8"))
        self._data = payload

    def _require(self) -> dict:
        """The index, or a clear refusal. Called by every write."""
        if self._data is None and self._problems:
            raise HistoryError(" ".join(self._problems))
        if self._data is None:
            raise HistoryError(f"no history at {self.path} — call init() first")
        return self._data

    # -- state -------------------------------------------------------------

    def exists(self) -> bool:
        return self._data is not None

    def problems(self, deep: bool = False) -> list[str]:
        """Plain-language faults. Empty when the history is healthy. Callers
        should surface these verbatim: a wrong explanation is worse than none,
        and 'no versions yet' must never be shown for 'the file is corrupt'.

        `deep` also DECOMPRESSES every snapshot to prove it is readable, which
        is O(whole history) — 100 versions of a big design is megabytes of gzip.
        The UI polls this whenever the document changes, so it asks for the
        shallow check: a missing file is caught by a stat, and a snapshot that
        is present but corrupt is caught the moment it is opened, where
        `snapshot()` already raises a message naming it. Paying to re-verify
        every version on every keystroke would be the wrong trade."""
        out = list(self._problems)
        if self._data is not None:
            for v in self._versions():
                p = self._snap_path(v.id)
                if not p.exists():
                    out.append(f"{v.id} is listed but its snapshot {p.name} is "
                               f"missing — that version cannot be opened.")
                elif deep and not self._readable(v.id):
                    out.append(f"{v.id}'s snapshot {p.name} is corrupt — the "
                               f"other versions are unaffected.")
        return out

    def init(self, name: str = "") -> "History":
        """Create an empty history. Existing ones are left exactly as they are
        (this is called on every save, so it must be idempotent)."""
        if self._data is None and not self._problems:
            self._data = self._blank(name)
            self._save()
        return self

    @property
    def design_id(self) -> str | None:
        return self._data.get("design_id") if self._data else None

    @property
    def name(self) -> str | None:
        return self._data.get("name") if self._data else None

    def current(self) -> str | None:
        return self._data.get("current") if self._data else None

    def starred(self) -> str | None:
        return self._data.get("starred") if self._data else None

    # -- reading versions --------------------------------------------------

    def _versions(self) -> list[Version]:
        if self._data is None:
            return []
        return [Version.from_data(d) for d in self._data["versions"]]

    def versions(self) -> list[Version]:
        """Creation order — v1, v2, … regardless of branching. Branch shape
        lives in `parent`, never in the numbering."""
        return sorted(self._versions(),
                      key=lambda v: int(_VID.match(v.id).group(1))
                      if _VID.match(v.id) else 0)

    def get(self, vid: str) -> Version:
        for v in self._versions():
            if v.id == vid:
                return v
        raise HistoryError(f"no version '{vid}' in {self.path.name}")

    def _snap_path(self, vid: str) -> Path:
        return self.path / f"{vid}.json.gz"

    def _readable(self, vid: str) -> bool:
        try:
            self._read_snap(vid)
            return True
        except Exception:
            return False

    def _read_snap(self, vid: str) -> dict:
        with gzip.open(self._snap_path(vid), "rt", encoding="utf-8") as fh:
            return json.load(fh)

    def snapshot(self, vid: str) -> dict:
        """The stored `Document.to_data()` payload for one version."""
        self.get(vid)                                  # existence first
        p = self._snap_path(vid)
        if not p.exists():
            raise HistoryError(f"{vid} is listed in {self.path.name} but its "
                               f"snapshot {p.name} is gone — it cannot be "
                               f"opened. The other versions are unaffected.")
        try:
            return self._read_snap(vid)
        except Exception as e:
            raise HistoryError(f"{vid}'s snapshot {p.name} is corrupt ({e}). "
                               f"The other versions are unaffected.") from e

    # -- tree shape --------------------------------------------------------

    def children(self, vid: str | None) -> list[str]:
        return [v.id for v in self.versions() if v.parent == vid]

    def roots(self) -> list[str]:
        return self.children(None)

    def ancestors(self, vid: str) -> list[str]:
        """Root-first path down to `vid`, excluding itself."""
        chain, seen = [], set()
        cur = self.get(vid).parent
        while cur is not None and cur not in seen:
            seen.add(cur)
            chain.append(cur)
            try:
                cur = self.get(cur).parent
            except HistoryError:                       # dangling parent ref
                break
        return list(reversed(chain))

    def leaves(self) -> list[str]:
        return [v.id for v in self.versions() if not self.children(v.id)]

    def branch_points(self) -> list[str]:
        """Versions with more than one child — where the user went back and
        took a different path."""
        return [v.id for v in self.versions() if len(self.children(v.id)) > 1]

    def tree_lines(self) -> list[str]:
        """Readable dump, for debugging and for the tests to assert against."""
        out: list[str] = []

        def walk(vid: str, depth: int) -> None:
            v = self.get(vid)
            marks = ("*" if vid == self.current() else " ") + \
                    ("★" if vid == self.starred() else " ")
            out.append(f"{marks} {'  ' * depth}{vid}  {v.label}".rstrip())
            for c in self.children(vid):
                walk(c, depth + 1)

        for r in self.roots():
            walk(r, 0)
        return out

    # -- writing -----------------------------------------------------------

    def _next_id(self, data: dict) -> str:
        used = [int(m.group(1)) for m in
                (_VID.match(d["id"]) for d in data["versions"]) if m]
        return f"v{max(used, default=0) + 1}"

    def append(self, snapshot: dict, *, label: str = "", source: str = "",
               parent: str | None = None, use_current_as_parent: bool = True,
               spec: dict | None = None, commit: str | None = None,
               rebuildable: bool | None = None,
               created: str | None = None) -> Version:
        """Record a version and make it current.

        Returns the version now holding this content. If it is identical to the
        parent it would hang off, **nothing is written** and the parent comes
        back — invariant 1. Callers wanting to know whether they created
        anything compare the returned id against `current()` beforehand.

        `parent` defaults to `current()`, which is what makes restore-then-edit
        branch instead of truncate (invariant 2).
        """
        data = self._require()
        if parent is None and use_current_as_parent:
            parent = data.get("current")
        if parent is not None:
            self.get(parent)                           # refuse dangling parents

        h = content_hash(snapshot)
        if parent is not None and self.get(parent).hash == h:
            return self.get(parent)

        vid = self._next_id(data)
        v = Version(id=vid, parent=parent, created=created or _now(),
                    label=label, source=source, hash=h,
                    features=len(snapshot.get("features", [])),
                    spec=spec or {}, commit=commit, rebuildable=rebuildable)

        # snapshot FIRST, then the index (invariant 3)
        self.path.mkdir(parents=True, exist_ok=True)
        _write_atomic(self._snap_path(vid), gzip.compress(
            json.dumps(snapshot, separators=(",", ":")).encode("utf-8"), 6))
        self._save({**data,
                    "versions": data["versions"] + [asdict(v)],
                    "current": vid,
                    "name": data.get("name") or snapshot.get("name", "") or ""})
        return v

    def set_current(self, vid: str) -> None:
        """Move the 'you are here' marker. The next append branches from it."""
        data = self._require()
        self.get(vid)
        self._save({**data, "current": vid})

    def star(self, vid: str | None) -> None:
        """Pin the one version the user actually wants (or None to unpin).

        This is the point of the feature. "Which is my intended design?" is not
        answered by recency — v10 is not automatically better than v7 — so
        exactly one version per design can be marked, and nothing else may
        claim that slot."""
        data = self._require()
        if vid is not None:
            self.get(vid)
        self._save({**data, "starred": vid})

    def relabel(self, vid: str, label: str) -> None:
        data = self._require()
        self.get(vid)
        self._save({**data, "versions": [
            {**d, "label": label} if d["id"] == vid else d
            for d in data["versions"]]})

    def rename(self, new_slug: str) -> "History":
        """Follow a design that was renamed, so its history does NOT fork.

        The directory is keyed by slug, so a rename has to move it; the
        `design_id` stays put, which is what keeps the identity stable."""
        data = self._require()
        target = self.path.with_name(f"{new_slug}{SUFFIX}")
        if target == self.path:
            return self
        if target.exists():
            raise HistoryError(f"{target.name} already exists — refusing to "
                               f"merge two histories.")
        shutil.move(str(self.path), str(target))
        self.path = target
        self._save({**data, "name": new_slug})
        return self

    # -- recovery ----------------------------------------------------------

    def repair(self) -> list[str]:
        """Rebuild a lost or unreadable index from the snapshots still on disk.

        Deliberately separate from `_load`: guessing is fine when the user asks
        for it and unacceptable as a silent fallback. Ordering is by version
        number and the chain is made linear — the real parent links are gone
        with the index, and inventing branches would be a lie. Returns notes on
        what was assumed."""
        snaps = sorted(self.path.glob("v*.json.gz"),
                       key=lambda p: int(_VID.match(p.name.split(".")[0])
                                         .group(1)))
        if not snaps:
            raise HistoryError(f"nothing to repair in {self.path} — no "
                               f"v*.json.gz snapshots found")
        keep = self._data or self._blank()
        notes, versions, prev = [], [], None
        for p in snaps:
            vid = p.name.split(".")[0]
            try:
                with gzip.open(p, "rt", encoding="utf-8") as fh:
                    snap = json.load(fh)
            except Exception as e:
                notes.append(f"{vid}: snapshot unreadable ({e}) — left out")
                continue
            versions.append(asdict(Version(
                id=vid, parent=prev,
                created=datetime.fromtimestamp(
                    p.stat().st_mtime, timezone.utc).isoformat(
                        timespec="seconds"),
                label="(recovered)", source="repair",
                hash=content_hash(snap),
                features=len(snap.get("features", [])))))
            prev = vid
        self._save({**keep, "schema": SCHEMA, "versions": versions,
                    "current": prev, "starred": None,
                    "design_id": keep.get("design_id")
                    or "d_" + uuid.uuid4().hex[:12]})
        self._problems = []
        notes.append(f"rebuilt {len(versions)} versions as a linear chain — "
                     f"original branch links were lost with the index")
        return notes
