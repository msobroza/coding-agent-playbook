"""The protected set: which paths ``playbook sync`` owns, read from ``guard_config.json`` (specs/prK-hook-pack.md §E.1).

:func:`protected_paths` turns the rendered ``sentinel`` and ``protected``
tables into a :class:`ProtectedSet`; :func:`classify` decides one
``NormalizedPath`` against it. Shared by guard-generated-outputs and, in later
K5 steps, control-plane-guard (the scoped rows) and the ``drift`` stage.

The set comes only from the lockfile rows and the adapters' output dirs that
sync rendered: nothing is rendered and nothing is spawned here. The order of
:func:`classify` is the §E.1 policy:

1. outside the repo, only installed resources count (``resource_roots``,
   resolved through ``machine.json``; a root inside a worktree, such as an
   editable install, is engine authoring and stays editable);
2. a path that does not exist yet is a creation, which always passes;
3. the lockfile itself, then the hook artifacts (user-owned guardrail files);
4. a lock row is authoritative and needs no read (SKILL.md and copied skill
   files carry no sentinel); a path whose rows are all scoped is left to
   control-plane-guard;
5. the handler's ``extra_protected`` globs;
6. last, a file under an output dir carrying the sentinel at its anchored
   position (``generated_output.sentinel.file_has_sentinel``), never read when
   it is a symlink, on a secret path or when it is not a regular file.

Stdlib, ``hook_runtime``, the zero-import ``generated_output.sentinel`` and the stdlib-only
``catalog.roots`` module (a leaf) only (§D.1).
"""

from __future__ import annotations

import os
import stat
import sys
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook.generated_output.sentinel import SENTINEL, file_has_sentinel
from coding_agent_playbook.hook_runtime.config.reader import Malformed, TableReader
from coding_agent_playbook.hook_runtime.config.schema import (
    HOOKS_OUTPUT_DIR,
    LOCKFILE_REL,
    RESOURCE_ROOT_ID_FORMAT,
)
from coding_agent_playbook.hook_runtime.dispatch.paths import fold_key
from coding_agent_playbook.hook_runtime.globs import GlobSet, compile_globs

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig
    from coding_agent_playbook.hook_runtime.config.pin import MachinePins
    from coding_agent_playbook.hook_runtime.dispatch.paths import NormalizedPath

__all__ = [
    "DEFAULT_HOOK_ARTIFACTS",
    "ENGINE_RESOURCES_ID",
    "HitKind",
    "ProtectedEntry",
    "ProtectedHit",
    "ProtectedSet",
    "SentinelReader",
    "classify",
    "protected_paths",
]

#: The engine's own layer (its bundled ``catalog/core/``); resolvable without
#: ``machine.json``, from this package. The id keeps its ``resources`` spelling
#: (``hooks.guard_config.resource_roots.resource_root_ids`` formats the same way).
ENGINE_RESOURCES_ID: Final = RESOURCE_ROOT_ID_FORMAT.format(package="coding_agent_playbook")
#: Used when ``guard_config.json`` predates the table (``guard_config.HOOK_ARTIFACTS``);
#: kept apart from the writer's copy until a schema decision retires it (GC-D7, F-G1).
DEFAULT_HOOK_ARTIFACTS: Final = (
    HOOKS_OUTPUT_DIR,
    ".claude/hooks/playbook/",
    ".opencode/plugins/playbook-hooks.js",
)

type HitKind = Literal["lockfile", "hook_artifact", "entry", "extra", "sentinel", "resource"]
#: ``(realpath, sentinel) -> bool``: whether the file carries the sentinel at its anchor.
type SentinelReader = Callable[[str, str], bool]


@dataclass(frozen=True, slots=True)
class ProtectedEntry:
    """One ``protected.entries`` row: a lock entry's path and provenance.

    ``kind`` is ``""`` for a v1 entry (unknown provenance); ``sha256`` is set
    only on a scoped row (one managed JSON element).

    Example: ``ProtectedEntry(".claude/CLAUDE.md", "composite")``.
    """

    path: str
    kind: str
    artifact_id: str = ""
    source: str = ""
    scope: str = ""
    sha256: str = ""


@dataclass(frozen=True, slots=True)
class ProtectedHit:
    """Why one path is protected: ``path`` is repo-relative (absolute for a resource).

    ``entry`` is the whole-file lock row for an ``entry`` hit, else ``None``.

    Example: ``ProtectedHit(path="AGENTS.md", kind="sentinel")``.
    """

    path: str
    kind: HitKind
    entry: ProtectedEntry | None = None


@dataclass(frozen=True, slots=True, kw_only=True)
class ProtectedSet:
    """The protected set of one dispatch, keys folded for ``platform``.

    ``rows`` maps a folded repo-relative key to its lock rows; ``output_dirs``
    are folded (``x/`` a directory, else one file); ``resource_roots`` are
    absolute real paths outside any worktree check (that is :func:`classify`'s).
    """

    sentinel: str
    rows: Mapping[str, tuple[ProtectedEntry, ...]]
    output_dirs: tuple[str, ...]
    hook_artifacts: GlobSet
    extra: GlobSet
    secret_paths: GlobSet
    resource_roots: tuple[str, ...]
    platform: str

    def scoped(self, key: str) -> tuple[ProtectedEntry, ...]:
        """The scoped rows of folded ``key`` (control-plane-guard's managed elements)."""
        return tuple(row for row in self.rows.get(key, ()) if row.scope)


def protected_paths(
    cfg: GuardConfig,
    machine: MachinePins | None = None,
    *,
    platform: str = sys.platform,
    extra: Iterable[str] = (),
) -> ProtectedSet:
    """The :class:`ProtectedSet` of ``cfg``'s ``sentinel`` / ``protected`` tables.

    ``machine`` resolves the ``pkg:`` resource ids (``None``: only the engine's,
    from this package); ``extra`` are the handler's ``extra_protected`` globs.
    A malformed table raises ``Malformed`` (a ``ValueError``): the guard's
    failure policy then asks.

    Example::

        >>> protected_paths(cfg, platform="darwin").rows[".claude/claude.md"]  # doctest: +SKIP
        (ProtectedEntry(path='.claude/CLAUDE.md', kind='composite', ...),)
    """
    root = TableReader(dict(cfg.tables), "")
    table = root.child("protected")
    rows: dict[str, list[ProtectedEntry]] = {}
    for entry in _entries(table):
        rows.setdefault(fold_key(entry.path, platform), []).append(entry)
    return ProtectedSet(
        sentinel=root.text("sentinel", SENTINEL),
        rows=MappingProxyType({key: tuple(found) for key, found in rows.items()}),
        output_dirs=tuple(fold_key(d, platform) for d in table.strings("output_dirs", ())),
        hook_artifacts=compile_globs(
            table.strings("hook_artifacts", DEFAULT_HOOK_ARTIFACTS), platform=platform
        ),
        extra=compile_globs(extra, platform=platform),
        secret_paths=cfg.secret_paths,
        resource_roots=_resource_roots(table.strings("resource_roots", ()), machine),
        platform=platform,
    )


def classify(
    pset: ProtectedSet, npath: NormalizedPath, *, read_sentinel: SentinelReader | None = None
) -> ProtectedHit | None:
    """Why ``npath`` is protected, or ``None`` when an edit of it may proceed.

    ``read_sentinel`` defaults to ``generated_output.sentinel.file_has_sentinel``;
    it is called only for an existing regular file under an output dir, never
    through a symlink or on a secret path.

    Example::

        >>> classify(pset, normalize_path("AGENTS.md", ...)).kind  # doctest: +SKIP
        'entry'
    """
    if npath.repo_rel is None:
        return _resource_hit(pset, npath)
    if not npath.exists:
        return None  # creating a new path passes (§E.1)
    rel, key = npath.repo_rel, npath.key
    if key == fold_key(LOCKFILE_REL, pset.platform):
        return ProtectedHit(rel, "lockfile")
    if pset.hook_artifacts.matches(key):
        return ProtectedHit(rel, "hook_artifact")
    rows = pset.rows.get(key, ())
    whole = next((row for row in rows if not row.scope), None)
    if whole is not None:
        return ProtectedHit(rel, "entry", whole)
    if rows:
        return None  # only managed JSON elements: control-plane-guard owns them
    if pset.extra.matches(key):
        return ProtectedHit(rel, "extra")
    reader = read_sentinel or _read_sentinel
    if _sentinel_candidate(pset, npath) and reader(npath.realpath, pset.sentinel):
        return ProtectedHit(rel, "sentinel")
    return None


def _entries(table: TableReader) -> list[ProtectedEntry]:
    raw = table.table.get("entries", [])
    if not isinstance(raw, list):
        raise Malformed(table.key("entries"), "expected a list of objects", raw)
    return [_entry(TableReader(row, f"{table.key('entries')}[{i}]")) for i, row in enumerate(raw)]


def _entry(row: TableReader) -> ProtectedEntry:
    return ProtectedEntry(
        path=row.text("path"),
        kind=row.text("kind", ""),
        artifact_id=row.text("artifact_id", ""),
        source=row.text("source", ""),
        scope=row.text("scope", ""),
        sha256=row.text("sha256", ""),
    )


def _resource_roots(ids: Iterable[str], machine: MachinePins | None) -> tuple[str, ...]:
    """Each ``pkg:`` id's real path on this machine; an unresolvable id protects nothing."""
    known = dict(machine.resource_roots) if machine is not None else {}
    if ENGINE_RESOURCES_ID not in known:
        known[ENGINE_RESOURCES_ID] = _engine_layer_dir()
    found = (known.get(resource_id) for resource_id in ids)
    return tuple(dict.fromkeys(os.path.realpath(path) for path in found if path))


def _engine_layer_dir() -> str:
    """This package's ``catalog/core/``, or ``""`` (protects nothing) when the catalog is missing.

    The ``catalog.roots`` module is a stdlib-only leaf (``pathlib``, which the dispatcher
    already loads), so the hot path stays import-light (§D.1).
    """
    from coding_agent_playbook.catalog.roots import (
        CatalogMissingError,
        engine_layer_root,
    )

    try:
        return str(engine_layer_root())
    except CatalogMissingError:
        return ""


def _resource_hit(pset: ProtectedSet, npath: NormalizedPath) -> ProtectedHit | None:
    """An installed engine/overlay resource is always denied, created or not (§E.1)."""
    key = npath.key
    for root in pset.resource_roots:
        folded = fold_key(root, pset.platform).rstrip("/")
        if key == folded or key.startswith(f"{folded}/"):
            return ProtectedHit(npath.realpath, "resource")
    return None


def _sentinel_candidate(pset: ProtectedSet, npath: NormalizedPath) -> bool:
    """Whether the anchored-sentinel read may open ``npath`` at all.

    A linked file is never read (the engine never writes one), as in the
    adapters' scan; a linked *directory* above it (a project under darwin's
    ``/tmp``) is fine, since ``key`` already comes from the real path.
    """
    key = npath.key
    in_output = any(
        key.startswith(entry) if entry.endswith("/") else key == entry for entry in pset.output_dirs
    )
    if not in_output or os.path.islink(npath.path) or pset.secret_paths.matches(key):
        return False
    try:
        return stat.S_ISREG(os.lstat(npath.realpath).st_mode)  # a FIFO would block open()
    except OSError:
        return False


def _read_sentinel(path: str, sentinel: str) -> bool:
    return file_has_sentinel(path, sentinel=sentinel)
