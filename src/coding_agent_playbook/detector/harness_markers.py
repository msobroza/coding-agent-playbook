"""Which assistant harnesses a repo shows signs of, from its files alone (D79 part 2).

:data:`HARNESS_MARKERS` is the single source of truth for two consumers:
``playbook check`` prints :func:`adapter_hints` (advisory; it never fails the
command), and interactive ``playbook init`` pre-selects :func:`detected_adapters`.

Only repo files are read, never PATH: an installed binary says nothing about
what the team uses in this repo. A file the engine generated never counts as
use, so a synced repo does not look like it uses every enabled harness: callers
pass ``generated``, the paths the lockfile records (``Lockfile.recorded_paths``,
scoped entries included, since the engine may have created that file). This
layer sits below ``lockfile`` and ``config``, so it takes plain values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path


@dataclass(frozen=True)
class HarnessMarker:
    """A repo path whose user-written content shows ``harness`` is in use.

    ``path`` ending in ``/`` is a directory: any file under it counts.
    """

    harness: str
    adapter: str
    path: str


HARNESS_MARKERS: Final[tuple[HarnessMarker, ...]] = (
    HarnessMarker("Claude Code", "claude_code", "CLAUDE.md"),
    HarnessMarker("Claude Code", "claude_code", "CLAUDE.local.md"),
    HarnessMarker("Claude Code", "claude_code", ".claude/"),
    HarnessMarker("OpenCode", "opencode", "opencode.json"),
    HarnessMarker("OpenCode", "opencode", "opencode.jsonc"),
    HarnessMarker("OpenCode", "opencode", ".opencode/"),
    # Codex reads AGENTS.md and .agents/skills/, which shared_skills writes.
    HarnessMarker("Codex", "shared_skills", ".codex/"),
    HarnessMarker("Codex", "shared_skills", ".agents/"),
    HarnessMarker("Continue", "continue", ".continue/"),
)

_SYNC_AFTER: Final = "then run 'playbook sync'."


def _user_files(repo_root: Path, marker: HarnessMarker, generated: frozenset[str]) -> bool:
    """Whether ``marker`` names at least one file the engine did not generate."""
    if not marker.path.endswith("/"):
        target = repo_root / marker.path
        return target.is_file() and marker.path not in generated
    directory = repo_root / marker.path.rstrip("/")
    if not directory.is_dir():
        return False
    try:
        candidates = (p for p in directory.rglob("*") if p.is_file())
        return any(p.relative_to(repo_root).as_posix() not in generated for p in candidates)
    except OSError:
        # An unreadable tree is no evidence either way; the hint is advisory.
        return False


def _markers_found(repo_root: Path, generated: frozenset[str]) -> list[HarnessMarker]:
    return [m for m in HARNESS_MARKERS if _user_files(repo_root, m, generated)]


def detected_adapters(repo_root: Path, generated: frozenset[str]) -> list[str]:
    """The adapters whose harness markers hold user files, in table order.

    Example::

        >>> detected_adapters(repo_with_claude_md, frozenset())  # doctest: +SKIP
        ['claude_code']
    """
    return list(dict.fromkeys(m.adapter for m in _markers_found(repo_root, generated)))


def _harness_of(adapter: str) -> str:
    return next(m.harness for m in HARNESS_MARKERS if m.adapter == adapter)


def _paths_of(markers: Iterable[HarnessMarker]) -> str:
    return ", ".join(m.path for m in markers)


def _off_hint(adapter: str, found: Sequence[HarnessMarker], config_name: str) -> str:
    return (
        f"{_harness_of(adapter)} files found ({_paths_of(found)}) but the {adapter} "
        f'adapter is off: add "{adapter}" to adapters_enabled in {config_name}, '
        f"{_SYNC_AFTER}"
    )


def _unused_hint(adapter: str, config_name: str) -> str:
    harness = _harness_of(adapter)
    looked = _paths_of(m for m in HARNESS_MARKERS if m.adapter == adapter)
    return (
        f"{adapter} is enabled but the repo shows no {harness} files beyond the "
        f"engine's own output (looked for {looked}): if no one uses {harness}, remove "
        f'"{adapter}" from adapters_enabled in {config_name}, {_SYNC_AFTER}'
    )


def adapter_hints(
    repo_root: Path, enabled: Sequence[str], generated: frozenset[str], *, config_name: str
) -> list[str]:
    """Advisory lines where the enabled adapters and the repo's harness files disagree.

    One line per table adapter that is off although its markers hold user files,
    then one per enabled table adapter whose markers hold none; adapters the
    table does not know are never mentioned. ``config_name`` is the committed
    config file each fix edits (passed in: this layer sits below ``config``).

    Example::

        >>> adapter_hints(repo, ["claude_code"], frozenset(), config_name=name)  # doctest: +SKIP
        ['OpenCode files found (opencode.json) but the opencode adapter is off: ...']
    """
    found = _markers_found(repo_root, generated)
    in_use = list(dict.fromkeys(m.adapter for m in found))
    known = dict.fromkeys(m.adapter for m in HARNESS_MARKERS)
    off = [
        _off_hint(a, [m for m in found if m.adapter == a], config_name)
        for a in in_use
        if a not in enabled
    ]
    unused = [_unused_hint(a, config_name) for a in known if a in enabled and a not in in_use]
    return [*off, *unused]
