"""The session-start briefing's anomaly probes, one small function each (specs/prK-hook-pack.md §E.1).

Each probe returns one line, or ``None`` when all is well; repo-derived
strings (paths, branch names, versions) go through ``caps.quote_data``, and
identity values are never shown at all. A probe that fails is silent: the
briefing fails open, and ``playbook-hook doctor`` is the place to dig.

Cheap by construction (the briefing has about 300 ms): no ``uv run``, no
Jinja, no ``sync --check``, no ``importlib.metadata`` (the installed engine is
read from its ``.dist-info`` directory name), and git only through the
hardened ``GitPort``. A private module: it registers no handler.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime._config_reader import read_small_file
from coding_agent_playbook.hook_runtime._lock_digest import load_toml
from coding_agent_playbook.hook_runtime.caps import quote_data
from coding_agent_playbook.hook_runtime.handlers._control_plane_toml import (
    local_policy_overrides,
)
from coding_agent_playbook.hook_runtime.handlers._drift import drift_line

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

    from coding_agent_playbook.hook_runtime.event import CanonicalEvent, RepoInfo
    from coding_agent_playbook.hook_runtime.git import GitPort
    from coding_agent_playbook.hook_runtime.handlers._drift import DriftFinding
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from coding_agent_playbook.lockfile.model import Lockfile

__all__ = [
    "COMPACT_PROBES",
    "FULL_PROBES",
    "BriefingInputs",
    "Probe",
    "installed_engine_version",
    "run_probes",
]

LOCAL_CONFIG: Final = ".coding-agent-playbook.local.toml"
#: What ``detector.detect`` reads, by presence or content (a notebook scan is too slow here).
DETECTOR_INPUTS: Final = (
    "pyproject.toml",
    "Dockerfile",
    "docker",
    ".gitlab-ci.yml",
    ".github/workflows",
)
_DIST_INFO: Final = re.compile(r"coding_agent_playbook-([^-]+)\.dist-info")
_PLACEHOLDER_EMAIL: Final = re.compile(
    r"@(example\.(com|org|net)|localhost(\.localdomain)?)$", re.I
)
_PLACEHOLDER_NAMES: Final = frozenset({"your name", "you", "user", "name", "root"})
_LOCAL_MAX_BYTES: Final = 1024 * 1024
#: An input touched in the same second as the sync is not newer (``rendered_at`` has seconds).
_MTIME_SLACK_S: Final = 1.0
_QUOTE: Final = 80


@dataclass(frozen=True, slots=True, kw_only=True)
class BriefingInputs:
    """What every probe may read: the event, the context, and what the briefing already read.

    ``lockfile`` is ``None`` when it could not be read; ``drift`` holds the
    fast-path findings (empty without a lockfile).
    """

    ev: CanonicalEvent
    ctx: HandlerContext
    repo: RepoInfo
    lockfile: Lockfile | None
    drift: tuple[DriftFinding, ...]


#: One probe: a line, or ``None`` when there is nothing to say.
type Probe = Callable[[BriefingInputs], str | None]


def run_probes(probes: Sequence[Probe], inputs: BriefingInputs) -> list[str]:
    """The line of every probe that has one, in order; a probe that raises is skipped.

    Example::

        >>> run_probes(FULL_PROBES, inputs)  # doctest: +SKIP
        ['HEAD is on the default branch "main": create a branch before committing.']
    """
    lines: list[str] = []
    for probe in probes:
        try:
            line = probe(inputs)
        except Exception:  # the briefing fails open, one probe at a time (§E.0.5)
            continue
        if line:
            lines.append(line)
    return lines


def installed_engine_version(search_path: Iterable[str] | None = None) -> str | None:
    """The version in the first ``coding_agent_playbook-<v>.dist-info`` on ``search_path``.

    Reads directory names only: ``importlib.metadata`` costs 69-190 ms (§D.1).
    Relative entries (the cwd: the agent's repo) are never searched.

    Example::

        >>> installed_engine_version(["/no/such/dir"]) is None
        True
    """
    for entry in sys.path if search_path is None else search_path:
        if not entry or not os.path.isabs(entry):
            continue
        try:
            names = sorted(os.listdir(entry))
        except OSError:
            continue  # a zip file on sys.path, or a directory gone since startup
        for name in names:
            if found := _DIST_INFO.fullmatch(name):
                return found.group(1)
    return None


# --- the probes, in briefing order ------------------------------------------------------


def drift_probe(inputs: BriefingInputs) -> str | None:
    """1. Generated outputs that drifted from the lockfile, or orphans (the fast path)."""
    return drift_line(inputs.drift) if inputs.drift else None


def engine_version_probe(inputs: BriefingInputs) -> str | None:
    """2. The installed engine is not the one that synced the outputs."""
    installed = installed_engine_version()
    if inputs.lockfile is None or installed in (None, inputs.lockfile.engine_version):
        return None
    locked = quote_data(inputs.lockfile.engine_version, 40)
    return (
        f"Engine {quote_data(installed or '', 40)} is installed but the outputs were synced "
        f"by {locked}: ask the user to run playbook sync."
    )


def detector_inputs_probe(inputs: BriefingInputs) -> str | None:
    """3. Detector inputs changed after the last sync: the applicable rules may differ."""
    if inputs.lockfile is None:
        return None
    synced = datetime.fromisoformat(inputs.lockfile.rendered_at)
    rendered = (synced if synced.tzinfo else synced.replace(tzinfo=UTC)).timestamp()
    newer = [rel for rel in DETECTOR_INPUTS if _mtime(inputs.repo, rel) > rendered + _MTIME_SLACK_S]
    if not newer:
        return None
    names = ", ".join(quote_data(rel, _QUOTE) for rel in newer)
    return (
        f"Detector inputs changed since the last sync ({names}): ask the user to run playbook sync."
    )


def local_overrides_probe(inputs: BriefingInputs) -> str | None:
    """4. ``.coding-agent-playbook.local.toml`` sets policy keys (control-plane-guard's list)."""
    try:
        data, _ = read_small_file(Path(inputs.repo.worktree_root) / LOCAL_CONFIG, _LOCAL_MAX_BYTES)
    except FileNotFoundError:
        return None
    keys = local_policy_overrides(load_toml(data))
    if not keys:
        return None
    return (
        f"{LOCAL_CONFIG} overrides policy keys ({', '.join(keys)}): "
        "the guardrails may be weaker than the committed config."
    )


def worktree_probe(inputs: BriefingInputs) -> str | None:
    """5. A linked worktree: commands must run here, never in the main checkout."""
    if not inputs.repo.is_linked_worktree:
        return None
    where = quote_data(inputs.repo.worktree_root, 160)
    return f"Linked worktree: run every command in {where}; never cd to the main checkout."


def default_branch_probe(inputs: BriefingInputs) -> str | None:
    """6. HEAD is on the default branch (``origin/HEAD``, else ``main`` / ``master``)."""
    git = inputs.ctx.git
    branch = git.symbolic_ref("HEAD")
    if branch is None or branch not in _default_branches(git):
        return None
    return f"HEAD is on the default branch {quote_data(branch, _QUOTE)}: create a branch before committing."


def identity_probe(inputs: BriefingInputs) -> str | None:
    """7. An empty or placeholder git identity; reported as such, never by value."""
    git = inputs.ctx.git
    name, email = git.config_value("user.name"), git.config_value("user.email")
    if name and email and not _placeholder(name, email):
        return None
    return (
        "Git identity: placeholder; ask the user to set user.name and user.email before committing."
    )


def network_probe(inputs: BriefingInputs) -> str | None:
    """8. The network / air-gap mode as a category (``guard_config.network``; inert until K9)."""
    table = inputs.ctx.cfg.tables.get("network")
    mode = table.get("mode") if isinstance(table, dict) else None
    return f"Network mode: {quote_data(mode, 40)}." if isinstance(mode, str) and mode else None


def escape_probe(inputs: BriefingInputs) -> str | None:
    """9. A hatch set through a settings-file ``env`` object, and therefore ignored (§D.7)."""
    names = inputs.ctx.hatches.via_settings_env
    if not names:
        return None
    return (
        f"Escape hatch {', '.join(names)} is set in a settings file env and is ignored; "
        "a deliberate override belongs in the shell that launches the agent."
    )


def pending_trust_probe(inputs: BriefingInputs) -> str | None:
    """10a. An external hook handler no user approval covers yet: it never runs."""
    external = [
        record
        for record in inputs.ctx.cfg.hooks.values()
        if any(spec.kind == "external" for spec in record.handlers.values())
    ]
    if not external or inputs.ctx.deps is None:
        return None
    from coding_agent_playbook.hook_runtime._external import approval_of
    from coding_agent_playbook.hook_runtime._ports import open_trust_store

    trust = open_trust_store(inputs.repo, inputs.ctx.deps)
    pending = [
        r.id for r in external if trust is None or not trust.allows_handler(r.id, approval_of(r))
    ]
    if not pending:
        return None
    ids = ", ".join(quote_data(hook_id, 60) for hook_id in pending)
    return (
        f"Hooks waiting for the user's trust approval: {ids} (ask the user to run playbook sync)."
    )


def machine_pins_probe(inputs: BriefingInputs) -> str | None:
    """10b. This worktree's ``machine.json`` is missing or older than the outputs."""
    from coding_agent_playbook.hook_runtime.pin import read_machine_pins

    pins = read_machine_pins(git_dir=inputs.repo.git_dir)
    locked = inputs.lockfile.engine_version if inputs.lockfile is not None else None
    stale = (
        pins is None
        or (locked is not None and pins.engine_version != locked)
        or not all(pin.unchanged() for pin in pins.tools.values())
    )
    if not stale:
        return None
    return "This worktree's machine.json is missing or stale: ask the user to run playbook sync in this worktree."


def branch_probe(inputs: BriefingInputs) -> str | None:
    """Compaction only: restate the branch (git state survives the summary this way)."""
    branch = inputs.ctx.git.symbolic_ref("HEAD")
    return f"Branch: {quote_data(branch, _QUOTE)}." if branch else "Branch: detached HEAD."


#: Every probe of a startup, resume, clear or fork, in §E.1 order.
FULL_PROBES: Final[tuple[Probe, ...]] = (
    drift_probe,
    engine_version_probe,
    detector_inputs_probe,
    local_overrides_probe,
    worktree_probe,
    default_branch_probe,
    identity_probe,
    network_probe,
    escape_probe,
    pending_trust_probe,
    machine_pins_probe,
)
#: A compaction restates only drift and git state (§E.1).
COMPACT_PROBES: Final[tuple[Probe, ...]] = (drift_probe, branch_probe)


def _default_branches(git: GitPort) -> frozenset[str]:
    remote = git.symbolic_ref("refs/remotes/origin/HEAD")
    if remote is None:
        return frozenset({"main", "master"})
    return frozenset({remote.split("/", 1)[1] if "/" in remote else remote})


def _placeholder(name: str, email: str) -> bool:
    return name.strip().lower() in _PLACEHOLDER_NAMES or bool(
        _PLACEHOLDER_EMAIL.search(email.strip())
    )


def _mtime(repo: RepoInfo, rel: str) -> float:
    """``rel``'s mtime (its own, never a link target's), or ``-inf`` when absent."""
    try:
        return os.lstat(os.path.join(repo.worktree_root, *rel.split("/"))).st_mtime
    except OSError:
        return float("-inf")
