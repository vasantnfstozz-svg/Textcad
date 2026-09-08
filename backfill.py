"""backfill.py — replay git history into per-design version trees (P4).

The user asked for the version tree to cover work already done: "do this for
designs that i did from rockey baloboa keychanin to today". That history is not
lost — it is in git. Every commit that touched designs/<slug>.tcad.json is a
version of that design, and the commit subjects are descriptive enough to be
the labels ("rocky-keychain v3: slimmed silhouette (user: v2 looked fat)"), so
a backfilled tree arrives readable instead of as v1..v24.

Deliberately separate from history.py, which must not know what git is, and
from studio.py, which must not shell out. This module is the only place the two
worlds meet.

Three rules it follows:

* **Non-destructive by default.** A design whose history contains versions
  recorded from live editing is SKIPPED with a reason, never merged into or
  overwritten. Git commits are older than any live version, so appending them
  would build a chain that lies about the order things happened. `reset=True`
  exists for when the user explicitly wants git to be the only source.
* **Idempotent.** Commits already recorded (matched on sha) are skipped, so a
  second run adds only what is new — which is also how you extend a backfilled
  history after more commits land.
* **Honest about gaps.** designs/*.tcad.json was only un-ignored on 2026-08-05,
  so nothing older has blob history; a commit whose blob will not parse is
  skipped and named rather than silently dropped.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from history import History

SOURCE = "backfill:git"
_FALLBACK_GIT = r"C:\Program Files\Git\cmd\git.exe"


class BackfillError(Exception):
    """Something about git or the repo makes the replay impossible."""


def _git_exe() -> str:
    found = shutil.which("git")
    if found:
        return found
    if Path(_FALLBACK_GIT).exists():        # git is not on PATH on this machine
        return _FALLBACK_GIT
    raise BackfillError("git was not found on PATH and not at "
                        f"{_FALLBACK_GIT} — cannot read the history.")


def _git(repo: Path, *args: str) -> bytes:
    r = subprocess.run([_git_exe(), "-C", str(repo), *args],
                       capture_output=True)
    if r.returncode:
        raise BackfillError(f"git {args[0]} failed: "
                            f"{r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout


@dataclass
class Commit:
    sha: str
    when: str                # ISO-8601 UTC, the COMMIT's time not today's
    subject: str


@dataclass
class Report:
    slug: str
    status: str = "ok"       # ok | skipped | empty
    reason: str = ""
    commits: int = 0
    added: list[str] = field(default_factory=list)
    deduped: int = 0         # commits whose design was identical to the one before
    unreadable: list[str] = field(default_factory=list)

    def line(self) -> str:
        if self.status != "ok":
            return f"  {self.slug:26s} {self.status.upper()}: {self.reason}"
        bits = [f"{len(self.added)} version(s) from {self.commits} commit(s)"]
        if self.deduped:
            bits.append(f"{self.deduped} identical")
        if self.unreadable:
            bits.append(f"{len(self.unreadable)} unreadable")
        return f"  {self.slug:26s} {', '.join(bits)}"


def rel_design(slug: str) -> str:
    # git wants forward slashes regardless of platform
    return f"designs/{slug}.tcad.json"


def commits_for(repo: Path, slug: str) -> list[Commit]:
    """Oldest first: exactly the commits that touched THIS design's file.

    Two git traps, both measured on this repo rather than assumed:

    * `--reverse --follow` together return ONE commit where `--follow` alone
      returns 16 — --follow is a hack in the revision walker and does not
      compose with --reverse. So the ordering is done in Python.
    * `--follow` is not used at all. For autonomiq-sat-panel it walks git's
      rename heuristic back into sat-side-panel.tcad.json (5 commits) and on
      into isogrid-panel.tcad.json — DIFFERENT designs that each have their own
      history and their own tree. Following would import another design's
      commits under this one's name. Plain path history is 3 commits there,
      15 for esp32-remote, 24 for rocky-keychain, and those are the right
      answers. The cost is that a genuinely renamed design loses its earlier
      life; since the app has no rename and the library is keyed by filename,
      that trade is the safe one.
    """
    out = _git(repo, "log", "--format=%H|%ct|%s",
               "--", rel_design(slug)).decode("utf-8", "replace")
    found = []
    for line in out.splitlines():
        if line.count("|") < 2:
            continue
        sha, ts, subject = line.split("|", 2)
        found.append(Commit(
            sha=sha,
            when=datetime.fromtimestamp(int(ts), timezone.utc)
                         .isoformat(timespec="seconds"),
            subject=subject.strip()))
    found.reverse()                          # git lists newest first
    return found


def blob_at(repo: Path, sha: str, slug: str) -> dict:
    raw = _git(repo, "show", f"{sha}:{rel_design(slug)}")
    # a stray UTF-8 BOM would break json.loads; strip it rather than fail
    text = raw.decode("utf-8", "replace").lstrip("\ufeff")
    data = json.loads(text)
    if not isinstance(data, dict) or "features" not in data:
        raise ValueError("not a design document (no 'features')")
    return data


def library_slugs(designs_dir: Path) -> list[str]:
    """Designs present in the library right now. A slug with git history but no
    file is not backfilled: a version tree for a design you deleted would be
    clutter, and the commits are still in git if it ever comes back."""
    return sorted(p.name[:-len(".tcad.json")]
                  for p in designs_dir.glob("*.tcad.json")
                  if p.name != "examples.json")


def backfill_one(slug: str, *, repo: Path, designs_dir: Path,
                 history_root: Path, dry_run: bool = False,
                 reset: bool = False) -> Report:
    rep = Report(slug=slug)
    commits = commits_for(repo, slug)
    rep.commits = len(commits)
    if not commits:
        rep.status = "empty"
        rep.reason = ("no commits touch this design — designs/*.tcad.json was "
                      "only tracked from 2026-08-05")
        return rep

    h = History.for_design(history_root, slug)
    if h.problems():
        rep.status = "skipped"
        rep.reason = "existing history is unhealthy: " + h.problems()[0]
        return rep

    if h.exists():
        live = [v for v in h.versions() if v.source != SOURCE]
        if live and not reset:
            rep.status = "skipped"
            rep.reason = (f"{len(live)} version(s) came from live editing; git "
                          f"commits are older, so appending them would build a "
                          f"chain that lies about the order. Re-run with "
                          f"--reset to make git the only source.")
            return rep
        if live and reset and not dry_run:
            shutil.rmtree(h.path)
            h = History.for_design(history_root, slug)

    already = {v.commit for v in h.versions() if v.commit}
    todo = [c for c in commits if c.sha not in already]
    if dry_run:
        rep.added = [c.sha[:7] for c in todo]
        return rep

    h.init(slug)
    for c in todo:
        try:
            data = blob_at(repo, c.sha, slug)
        except Exception as e:
            rep.unreadable.append(f"{c.sha[:7]}: {e}")
            continue
        before = h.current()
        v = h.append(data, label=c.subject, source=SOURCE, commit=c.sha,
                     created=c.when)
        # append returns the PARENT when the design was byte-identical to it —
        # consecutive commits that changed only the .py or the preview
        if v.id == before:
            rep.deduped += 1
        else:
            rep.added.append(v.id)
    return rep


def backfill_all(*, repo: Path, designs_dir: Path, history_root: Path,
                 only: list[str] | None = None, dry_run: bool = False,
                 reset: bool = False) -> list[Report]:
    slugs = only or library_slugs(designs_dir)
    return [backfill_one(s, repo=repo, designs_dir=designs_dir,
                         history_root=history_root, dry_run=dry_run,
                         reset=reset)
            for s in slugs]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=".", help="repo root (default: cwd)")
    ap.add_argument("--only", nargs="*", metavar="SLUG",
                    help="just these designs")
    ap.add_argument("--dry-run", action="store_true",
                    help="report what WOULD be written, touch nothing")
    ap.add_argument("--reset", action="store_true",
                    help="discard live versions and rebuild from git alone")
    a = ap.parse_args()

    repo = Path(a.repo).resolve()
    designs = repo / "designs"
    if not designs.is_dir():
        print(f"no designs/ under {repo}")
        return 2

    reports = backfill_all(repo=repo, designs_dir=designs,
                           history_root=designs, only=a.only,
                           dry_run=a.dry_run, reset=a.reset)
    head = "DRY RUN — nothing written" if a.dry_run else "backfilled"
    print(f"{head}: {len(reports)} design(s) considered\n")
    for r in sorted(reports, key=lambda r: (r.status != "ok", r.slug)):
        print(r.line())
        for u in r.unreadable:
            print(f"      unreadable {u}")
    ok = [r for r in reports if r.status == "ok"]
    print(f"\n{sum(len(r.added) for r in ok)} version(s) across "
          f"{len(ok)} design(s); "
          f"{len([r for r in reports if r.status == 'skipped'])} skipped, "
          f"{len([r for r in reports if r.status == 'empty'])} with no history")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
