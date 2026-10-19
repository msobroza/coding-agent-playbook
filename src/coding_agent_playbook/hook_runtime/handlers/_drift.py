"""The drift fast path, shared by the ``drift`` Stop stage and the session-start briefing (specs/prK-hook-pack.md §E.1).

About 0.1 s and stdlib-only, never a render:

- ``lockfile.drift.drift_entries``: every whole-file entry hashed against disk,
  every scoped ``json:<pointer>`` entry matched by its canonical hash; secret
  paths are never read;
- the orphan scan: files under ``protected.output_dirs`` (each enabled
  adapter's ``_output_directories()`` plus the composite singletons) that
  carry the sentinel at its anchored position but are not in the lockfile.
  That is exactly what ``playbook sync --check`` reports through the adapters'
  ``stale_outputs``; ``.claude/skills`` is lockfile-only since the leftover
  policy (#25), so a sentinel ``SKILL.md`` missing from the lockfile is the
  user's and is never scanned. Links and secret paths are never opened.

What the fast path cannot see (a lockfile orphan whose canonical source was
deleted) needs a render: :func:`sync_check_findings` parses the ``playbook
sync --check`` child the stage runs for that. The lockfile is read with
``tomllib`` here, on ``stop`` and ``session_start`` only (§D.1 branch-local row).
"""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.generated_output.sentinel import file_has_sentinel
from coding_agent_playbook.hook_runtime.caps import quote_data
from coding_agent_playbook.hook_runtime.config.lock_digest import MAX_LOCK_BYTES, load_toml
from coding_agent_playbook.hook_runtime.config.protected import protected_paths
from coding_agent_playbook.hook_runtime.config.reader import read_small_file
from coding_agent_playbook.hook_runtime.config.schema import LOCKFILE_REL
from coding_agent_playbook.hook_runtime.paths import fold_key
from coding_agent_playbook.lockfile.drift import drift_entries
from coding_agent_playbook.lockfile.model import Lockfile

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig
    from coding_agent_playbook.hook_runtime.config.protected import ProtectedSet
    from coding_agent_playbook.lockfile.drift import DriftItem

__all__ = [
    "DRIFT_ADVICE",
    "DriftFinding",
    "drift_fast_path",
    "drift_line",
    "drift_summary",
    "hook_artifact_drift",
    "lockfile_findings",
    "read_lockfile",
    "sync_check_findings",
]

DRIFT_ADVICE: Final = "Run playbook validate && playbook sync before finishing."
#: The file list of a drift line stops near this many characters, then says how many more.
_LIST_CHARS: Final = 120
_PATH_CHARS: Final = 80
#: An output dir holding more files than this is not scanned further (a bound, not a verdict).
_MAX_SCAN_FILES: Final = 5000
_DRIFT_REPORT: Final = "Drift detected:"
#: How ``sync --check`` names what stopped it before any drift report (``Cannot verify <path>: …``).
_CANNOT_VERIFY: Final = "Cannot verify "
_WHAT: Final = {
    "missing": "missing",
    "hash_mismatch": "hash mismatch",
    "mode_mismatch": "mode mismatch",
    "managed_missing": "managed entry missing",
    "managed_edited": "managed entry edited",
    "unreadable": "unreadable",
}


@dataclass(frozen=True, slots=True)
class DriftFinding:
    """One drifted or orphaned output: its repo-relative ``path`` and ``what`` is wrong.

    Example: ``DriftFinding(".continue/rules/10-x.md", "hash mismatch")``.
    """

    path: str
    what: str


def read_lockfile(root: str) -> Lockfile:
    """``<root>/.coding-agent-playbook.lock``, parsed; raises ``OSError`` or ``ValueError``.

    Example::

        >>> read_lockfile("/repo").engine_version  # doctest: +SKIP
        '0.2.0'
    """
    data, _ = read_small_file(Path(root) / LOCKFILE_REL, MAX_LOCK_BYTES)
    return Lockfile.from_dict(load_toml(data))


def drift_fast_path(root: str, cfg: GuardConfig, *, platform: str) -> list[DriftFinding]:
    """The fast-path findings of the repository at ``root``; raises when the lockfile is unreadable.

    Example::

        >>> drift_fast_path("/repo", cfg, platform="linux")  # doctest: +SKIP
        []
    """
    return lockfile_findings(root, cfg, read_lockfile(root), platform=platform)


def lockfile_findings(
    root: str, cfg: GuardConfig, lockfile: Lockfile, *, platform: str
) -> list[DriftFinding]:
    """Drifted lock entries, then orphans, for an already-read ``lockfile``.

    Example::

        >>> lockfile_findings("/repo", cfg, lockfile, platform="linux")  # doctest: +SKIP
        [DriftFinding(path='.claude/commands/old.md', what='orphan')]
    """
    pset = protected_paths(cfg, platform=platform)

    def secret(rel: str) -> bool:
        return pset.secret_paths.matches(fold_key(rel, platform))

    items = drift_entries(lockfile, Path(root), skip=secret)
    found = [_finding(item) for item in items]
    found.extend(DriftFinding(rel, "orphan") for rel in orphan_outputs(root, pset, lockfile))
    return found


def orphan_outputs(root: str, pset: ProtectedSet, lockfile: Lockfile) -> list[str]:
    """Sentinel-tagged files under the output dirs that no lock entry owns, scan order.

    Example::

        >>> orphan_outputs("/repo", pset, lockfile)  # doctest: +SKIP
        ['.claude/commands/old.md']
    """
    owned = {fold_key(entry.path, pset.platform) for entry in lockfile.entries}
    found: list[str] = []
    for rel in _candidates(root, pset.output_dirs):
        key = fold_key(rel, pset.platform)
        if key in owned or pset.secret_paths.matches(key):
            continue
        path = os.path.join(root, *rel.split("/"))
        if _regular(path) and file_has_sentinel(path, sentinel=pset.sentinel):
            found.append(rel)
    return found


def hook_artifact_drift(findings: Sequence[DriftFinding], cfg: GuardConfig, platform: str) -> bool:
    """Whether a finding is a hook artifact (launcher, shim, copied script): the runtime itself.

    Example::

        >>> hook_artifact_drift([DriftFinding(".claude/hooks/playbook/launch.sh", "hash mismatch")],
        ...                     cfg, "linux")  # doctest: +SKIP
        True
    """
    artifacts = protected_paths(cfg, platform=platform).hook_artifacts
    return any(artifacts.matches(fold_key(f.path.split("#", 1)[0], platform)) for f in findings)


def drift_summary(findings: Sequence[DriftFinding]) -> str:
    """``Playbook drift: "<path>" (<what>), ....``, the list cut near 120 characters.

    Example::

        >>> drift_summary([DriftFinding("AGENTS.md", "hash mismatch")])
        'Playbook drift: "AGENTS.md" (hash mismatch).'
    """
    shown: list[str] = []
    for finding in findings:
        item = f"{quote_data(finding.path, _PATH_CHARS)} ({finding.what})"
        if shown and sum(len(s) + 2 for s in shown) + len(item) > _LIST_CHARS:
            break
        shown.append(item)
    hidden = len(findings) - len(shown)
    more = f" and {hidden} more" if hidden else ""
    return f"Playbook drift: {', '.join(shown)}{more}."


def drift_line(findings: Sequence[DriftFinding]) -> str:
    """The one combined drift line (§E.1): the summary, then what to run.

    Example::

        >>> drift_line([DriftFinding("AGENTS.md", "missing")]).endswith(DRIFT_ADVICE)
        True
    """
    return f"{drift_summary(findings)} {DRIFT_ADVICE}"


def sync_check_findings(stdout: bytes) -> list[DriftFinding]:
    """The paths a failed ``playbook sync --check`` lists; ``ValueError`` when it names none.

    Each drift entry starts with a two-space ``  <path>`` line; its explanation
    lines are indented further. A check stopped before any drift report by
    something in the way (a file where an output directory goes, a symlinked
    rules file, an unparsable ``settings.json``) prints ``Cannot verify <path>:
    <reason>.`` instead: that path is a ``cannot verify`` finding, not a crash.

    Example::

        >>> sync_check_findings(b"Drift detected:\\n  AGENTS.md\\n    Run sync.\\n")
        [DriftFinding(path='AGENTS.md', what='out of sync')]
    """
    lines = stdout.decode("utf-8", errors="replace").splitlines()
    if _DRIFT_REPORT in lines:
        paths = [line[2:] for line in lines if line.startswith("  ") and not line.startswith("   ")]
        return [DriftFinding(path, "out of sync") for path in paths] or [
            DriftFinding("playbook sync --check", "drift")
        ]
    refused = [_refused_path(line) for line in lines if line.startswith(_CANNOT_VERIFY)]
    if not refused:
        raise ValueError("playbook sync --check failed without a drift report")
    return [DriftFinding(path, "cannot verify") for path in refused]


def _refused_path(line: str) -> str:
    """``<path>`` of a ``Cannot verify <path>: <reason>.`` line (the command when unnamed)."""
    path = line[len(_CANNOT_VERIFY) :].split(": ", 1)[0].strip()
    return path or "playbook sync --check"


def _finding(item: DriftItem) -> DriftFinding:
    path = f"{item.path}#{item.pointer}" if item.pointer else item.path
    return DriftFinding(path, _WHAT[item.kind])


def _candidates(root: str, output_dirs: Sequence[str]) -> Iterator[str]:
    """Repo-relative paths under each output dir (``x/``) or the singleton file itself, bounded."""
    seen = 0
    for entry in output_dirs:
        if not entry.endswith("/"):
            yield entry
            continue
        top = os.path.join(root, *entry.rstrip("/").split("/"))
        if os.path.islink(top) or not os.path.isdir(top):
            continue
        for dirpath, _dirs, files in os.walk(top):  # never follows a linked directory
            base = os.path.relpath(dirpath, root).replace(os.sep, "/")
            for name in sorted(files):
                seen += 1
                if seen > _MAX_SCAN_FILES:
                    return
                yield f"{base}/{name}"


def _regular(path: str) -> bool:
    """A regular file, not a link (the engine never writes one) nor a FIFO that would block."""
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False
