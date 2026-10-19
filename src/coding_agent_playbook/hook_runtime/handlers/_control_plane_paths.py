"""Which control-plane row a written path falls under (specs/prK-hook-pack.md §E.1, §E.0.5).

The ``control_plane`` table of ``guard_config.json`` holds the engine
constants :data:`CONTROL_PLANE` (``config.schema``; sync renders them; an
overlay may only add rows, through the guard's ``extra_paths`` config key, L2).
:func:`load_plane` reads it with the ``protected`` and ``precommit`` tables;
:func:`route_of` names the row one ``NormalizedPath`` belongs to, first match
wins:

1. ``state``: anything under ``<git dir>/playbook-hooks`` (the interpreter
   pin, ``machine.json``, the Stop and session state), any worktree's;
2. outside the repository: the user's ``${CLAUDE_CONFIG_DIR:-~/.claude}/settings*.json``
   and the main checkout's ``settings.local.json`` (``settings``), then the
   user-local trust store's directory (``trust_store``);
3. in the repository: the hook artifacts (``protected.hook_artifacts``), the
   settings, config, MCP, OpenCode and pre-commit files, ``playbook/hooks/``,
   overlay ``src/*/resources/hooks/`` and engine ``catalog/{core,plugins/*}/hooks/``
   sources, plugin carriers, then the
   ``hooks:`` frontmatter carriers (markdown only);
4. the ``extra_paths`` rows.

Both candidate ``settings.local.json`` locations are guarded (the worktree's
and the main checkout's, which Claude Code ≥ 2.1.211 reads for a linked
worktree): over-matching is the safe direction.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook.hook_runtime.config.protected import protected_paths
from coding_agent_playbook.hook_runtime.config.reader import TableReader
from coding_agent_playbook.hook_runtime.config.schema import (
    CONTROL_PLANE,
    PolicyKeys,
)
from coding_agent_playbook.hook_runtime.escape import settings_files
from coding_agent_playbook.hook_runtime.globs import GlobSet, compile_globs
from coding_agent_playbook.hook_runtime.paths import fold_key
from coding_agent_playbook.hook_runtime.state import STATE_DIR_NAME

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig
    from coding_agent_playbook.hook_runtime.config.protected import ProtectedSet
    from coding_agent_playbook.hook_runtime.event import RepoInfo
    from coding_agent_playbook.hook_runtime.paths import NormalizedPath

__all__ = ["ControlPlane", "RouteKind", "load_plane", "route_of"]

type RouteKind = Literal[
    "state",
    "trust_store",
    "settings",
    "hook_artifact",
    "config",
    "local_config",
    "mcp",
    "opencode_config",
    "precommit",
    "hook_source",
    "plugin_carrier",
    "frontmatter_carrier",
    "extra",
]


#: In-repo rows after the hook artifacts, in match order: (route, table key).
_REPO_ROWS: Final[tuple[tuple[RouteKind, str], ...]] = (
    ("settings", "settings"),
    ("config", "config"),
    ("local_config", "local_config"),
    ("mcp", "mcp"),
    ("opencode_config", "opencode_config"),
    ("precommit", "precommit"),
    ("hook_source", "hook_sources"),
    ("plugin_carrier", "plugin_carriers"),
    ("frontmatter_carrier", "frontmatter_carriers"),
)
#: The ``toml_<row>`` table keys, in ``PolicyKeys`` field order.
_POLICY_ROWS: Final = ("deny", "ask", "ask_removals", "ask_additions", "loosening")
_GLOB_CHARS: Final = frozenset("*?[")


@dataclass(frozen=True, slots=True)
class _Row:
    """One routing row: exact folded keys plus globs."""

    kind: RouteKind
    exact: frozenset[str]
    globs: GlobSet

    def matches(self, key: str) -> bool:
        return key in self.exact or self.globs.matches(key)


@dataclass(frozen=True, slots=True, kw_only=True)
class _Outside:
    """What locates the guarded files outside the repository; read only for such a path."""

    repo: RepoInfo
    env: Mapping[str, str]
    home: str
    project_dir: str
    user_settings: tuple[str, ...]

    def route(self, real: str, platform: str) -> RouteKind | None:
        """``settings`` for a Claude settings file Claude loads, ``trust_store`` for the store."""
        user_dir = self.env.get("CLAUDE_CONFIG_DIR") or os.path.join(self.home, ".claude")
        files = [
            *settings_files(self.repo, project_dir=self.project_dir, env=self.env, home=self.home),
            *(Path(user_dir) / name for name in self.user_settings),
        ]
        if real in {_real_key(path, platform) for path in files}:
            return "settings"
        trust = _trust_dir(self.env, self.home, platform)
        return "trust_store" if real == trust or real.startswith(f"{trust}/") else None


@dataclass(frozen=True, slots=True, kw_only=True)
class ControlPlane:
    """The control-plane rows of one dispatch, keys folded for ``platform``.

    ``rows`` are the in-repo rows in match order (``extra`` last);
    ``state_bases`` are the folded git dirs whose ``playbook-hooks`` is guarded.
    """

    rows: tuple[_Row, ...]
    outside: _Outside
    state_bases: tuple[str, ...]
    protected: ProtectedSet
    policy_keys: PolicyKeys
    precommit_ids: tuple[str, ...]
    platform: str


def load_plane(
    cfg: GuardConfig,
    repo: RepoInfo,
    *,
    env: Mapping[str, str],
    home: str | None,
    platform: str,
    project_dir: str,
    extra: Iterable[str] = (),
) -> ControlPlane:
    """The :class:`ControlPlane` of ``cfg`` for ``repo``; ``extra`` are ``extra_paths`` globs.

    A malformed table raises ``Malformed`` (a ``ValueError``): the guard's
    failure policy then asks.

    Example::

        >>> route_of(load_plane(cfg, repo, env={}, home="/h", platform="linux",
        ...                     project_dir="/r"), npath)  # doctest: +SKIP
        'settings'
    """
    root = TableReader(dict(cfg.tables), "")
    table = root.child("control_plane")
    pset = protected_paths(cfg, platform=platform)
    home_dir = home or os.path.expanduser("~")

    def strings(name: str) -> tuple[str, ...]:
        return table.strings(name, CONTROL_PLANE[name])

    rows = (
        _Row("hook_artifact", frozenset(), pset.hook_artifacts),
        *(_row(kind, strings(name), platform) for kind, name in _REPO_ROWS),
        _row("extra", tuple(extra), platform, home=home_dir),  # ~/ rows reach user files
    )
    outside = _Outside(
        repo=repo,
        env=env,
        home=home_dir,
        project_dir=project_dir,
        user_settings=strings("user_settings"),
    )
    git_dirs = (fold_key(repo.git_dir, platform), fold_key(repo.common_dir, platform))
    return ControlPlane(
        rows=rows,
        outside=outside,
        state_bases=tuple(dict.fromkeys(git_dirs)),
        protected=pset,
        policy_keys=PolicyKeys(*(strings(f"toml_{row}") for row in _POLICY_ROWS)),
        precommit_ids=root.child("precommit").strings("playbook_hook_ids", ()),
        platform=platform,
    )


def route_of(plane: ControlPlane, npath: NormalizedPath) -> RouteKind | None:
    """The control-plane row ``npath`` falls under, or ``None`` for any other path.

    Example::

        >>> route_of(plane, normalize_path(".mcp.json", ...))  # doctest: +SKIP
        'mcp'
    """
    real = fold_key(npath.realpath, plane.platform)
    if _in_state_dir(real, plane.state_bases, plane.platform):
        return "state"
    if npath.repo_rel is None:
        return _outside_route(plane, real)
    key = npath.key
    for row in plane.rows:
        if row.matches(key) and (row.kind != "frontmatter_carrier" or key.endswith(".md")):
            return row.kind
    return None


def _outside_route(plane: ControlPlane, real: str) -> RouteKind | None:
    found = plane.outside.route(real, plane.platform)
    if found is not None:
        return found
    return "extra" if plane.rows[-1].matches(real) else None


def _in_state_dir(real: str, bases: Iterable[str], platform: str) -> bool:
    """Whether ``real`` lies in a ``playbook-hooks`` dir under one of the git dirs."""
    name = fold_key(STATE_DIR_NAME, platform)
    for base in bases:
        if real.startswith(f"{base}/") and name in real[len(base) + 1 :].split("/"):
            return True
    return False


def _trust_dir(env: Mapping[str, str], home: str, platform: str) -> str:
    """The folded real directory of the user-local trust store (§B.4)."""
    from coding_agent_playbook.security.trust import default_trust_store_path

    path = default_trust_store_path(environ=env, platform=platform, home=Path(home))
    return _real_key(path.parent, platform)


def _row(kind: RouteKind, patterns: Iterable[str], platform: str, home: str | None = None) -> _Row:
    """A bare name is an exact key (repo root only); anything else is a glob."""
    listed = tuple(patterns)
    exact = [p for p in listed if not p.endswith("/") and not _GLOB_CHARS & set(p)]
    globs = [p for p in listed if p not in exact]
    return _Row(
        kind,
        frozenset(fold_key(p, platform) for p in exact),
        compile_globs(globs, platform=platform, home=home),
    )


def _real_key(path: str | os.PathLike[str], platform: str) -> str:
    return fold_key(os.path.realpath(path), platform)
