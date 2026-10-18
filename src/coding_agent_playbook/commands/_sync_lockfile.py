"""Provenance recording and lockfile stamping for ``playbook sync`` (SPEC §14.4).

Schema 2 (specs/prK-lifecycle-hooks.md §P P4, §B.6) gives every whole-file
entry its provenance — ``kind``, ``artifact_id``, ``source`` and ``adapter``.
It is recorded **without changing the adapter return type**: the dispatch
wraps each ``write_rule``/``write_prompt``/``write_skill``/``finalize`` call
and tags every path it returns. Orphans the leftover policy keeps
(``_sync_orphans``) ride along in the new lockfile with their old entries.

Hooks (specs/prK-lifecycle-hooks.md §C.1.3): every adapter first gets
``begin_sync`` with the real repo and the prior lockfile, receives
``write_hook`` after the skills and before ``finalize``, and then hands back its
scoped (per-JSON-element) lock entries. A co-owned file (an adapter's
``shared_outputs``) never gets a whole-file entry, a ``finalize`` output the
adapter declares in ``runtime_outputs`` (the launcher, the OpenCode shim) is
``kind = "runtime"`` rather than ``composite``, and a copied hook script records
its exec bit (§B.6).
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from coding_agent_playbook.lockfile import (
    LockEntry,
    Lockfile,
    Provenance,
    compute_hash,
    merge_provenance,
)
from coding_agent_playbook.orchestrator import artifact_id_of

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.adapters.base import Adapter
    from coding_agent_playbook.commands._sync_hooks import SyncHooks
    from coding_agent_playbook.hook_policy import ResolvedHook
    from coding_agent_playbook.hooks_config import HooksConfig
    from coding_agent_playbook.lockfile import ProvenanceKind
    from coding_agent_playbook.types import Prompt, Rule, Skill

#: 2 = provenance on every entry (specs/prK-lifecycle-hooks.md §P P4, §B.6).
LOCKFILE_SCHEMA = 2


@dataclass(frozen=True)
class SyncResult:
    """Everything one write-mode render produced.

    ``written`` keeps every adapter-returned path in dispatch order
    (duplicates included, so the summary count is unchanged); ``provenance``
    maps each *resolved* written path to its origin; ``removed`` lists the
    files the adapters' ``cleanup_stale`` (and a file/folder swap) deleted;
    ``managed`` holds the scoped (per-JSON-element) lock entries hook-capable
    adapters contribute (§C.1.4); ``hooks`` the hooks the render dispatched
    (``None`` when built by hand), for write mode's pins and summary.

    Example::

        result = _run_sync(ctx, policy)
        lockfile = build_lockfile(result.written, ctx.repo_root, "0.2.0",
                                  provenance=result.provenance, managed=result.managed)
    """

    written: tuple[Path, ...]
    removed: tuple[Path, ...]
    provenance: Mapping[Path, Provenance]
    managed: tuple[LockEntry, ...] = ()
    hooks: SyncHooks | None = None


@dataclass
class ProvenanceRecorder:
    """Collect adapter-returned paths in dispatch order plus their provenance.

    The first writer of a path owns it. A second, *different* provenance for
    the same path (another artifact, another adapter, or a ``finalize``
    result) makes it ``kind="composite"`` (§P P4).

    Example::

        recorder = ProvenanceRecorder()
        recorder.record(adapter.write_rule(rule, root), Provenance(kind="rule", artifact_id="x"))
    """

    written: list[Path] = field(default_factory=list)
    provenance: dict[Path, Provenance] = field(default_factory=dict)
    managed: list[LockEntry] = field(default_factory=list)

    def record(self, paths: Iterable[Path], provenance: Provenance) -> None:
        """Append ``paths`` and tag each (resolved) path with ``provenance``."""
        for path in paths:
            self.written.append(path)
            key = path.resolve()
            self.provenance[key] = merge_provenance(self.provenance.get(key), provenance)


def _artifact_provenance(
    kind: ProvenanceKind, artifact: Rule | Prompt | Skill, adapter_name: str
) -> Provenance:
    return Provenance(
        kind=kind,
        artifact_id=artifact_id_of(artifact),
        source=artifact.source_package,
        adapter=adapter_name,
    )


@dataclass(frozen=True)
class HookDispatch:
    """The hook inputs of one dispatch: the on hooks and what ``begin_sync`` is told.

    ``source_root`` is the real repo even when output goes to a scratch dir
    (``sync --check``); ``None`` means the output root. ``config`` is ``[hooks]``.

    Example::

        HookDispatch(hooks, ctx.repo_root, previous_lockfile, hooks_cfg)
    """

    hooks: Sequence[ResolvedHook] = ()
    source_root: Path | None = None
    prior_lock: Lockfile | None = None
    config: HooksConfig | None = None


def dispatch_to_adapters(
    adapters: Mapping[str, Adapter],
    rules: Sequence[Rule],
    prompts: Sequence[Prompt],
    skills: Sequence[Skill],
    output_root: Path,
    *,
    hooks: HookDispatch | None = None,
) -> ProvenanceRecorder:
    """Run every adapter's ``begin_sync``, ``write_*`` calls and ``finalize`` into ``output_root``,
    tagging each returned path with the artifact (or composite output) that produced it.

    ``adapters`` maps the entry-point name to the instance, e.g.
    ``{"continue": ContinueAdapter()}``. Each adapter's scoped lock entries are
    collected on ``recorder.managed`` after its ``finalize``.

    Example::

        recorder = dispatch_to_adapters(adapters, rules, prompts, skills, repo_root,
                                        hooks=HookDispatch(on_hooks, repo_root, lock, cfg))
    """
    plan = hooks if hooks is not None else HookDispatch()
    recorder = ProvenanceRecorder()
    for name, adapter in adapters.items():
        adapter.begin_sync(
            plan.source_root or output_root, plan.prior_lock, hooks_config=plan.config
        )
        _write_artifacts(recorder, name, adapter, (rules, prompts, skills), output_root)
        for hook in plan.hooks:
            recorder.record(adapter.write_hook(hook, output_root), _hook_provenance(hook, name))
        _record_finalize(recorder, name, adapter, output_root)
        recorder.managed.extend(adapter.managed_lock_entries())
    return recorder


def _record_finalize(
    recorder: ProvenanceRecorder, name: str, adapter: Adapter, output_root: Path
) -> None:
    """``finalize`` output: ``runtime`` for a declared ``runtime_outputs`` file, else ``composite``."""
    runtime = frozenset(type(adapter).runtime_outputs)
    for path in adapter.finalize(output_root):
        declared = _spelled_relative(path, output_root) in runtime
        kind: ProvenanceKind = "runtime" if declared else "composite"
        recorder.record([path], Provenance(kind=kind, adapter=name))


def _spelled_relative(path: Path, root: Path) -> str:
    """``path`` relative to ``root`` as spelled, POSIX (``""`` outside it): a symlinked
    output dir must not hide a declared runtime file, so nothing is resolved."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return ""


def _write_artifacts(
    recorder: ProvenanceRecorder,
    name: str,
    adapter: Adapter,
    artifacts: tuple[Sequence[Rule], Sequence[Prompt], Sequence[Skill]],
    output_root: Path,
) -> None:
    """One adapter's rules, prompts and skills, in that order."""
    rules, prompts, skills = artifacts
    for rule in rules:
        recorder.record(
            adapter.write_rule(rule, output_root), _artifact_provenance("rule", rule, name)
        )
    for prompt in prompts:
        recorder.record(
            adapter.write_prompt(prompt, output_root), _artifact_provenance("prompt", prompt, name)
        )
    for skill in skills:
        recorder.record(
            adapter.write_skill(skill, output_root), _artifact_provenance("skill", skill, name)
        )


def _hook_provenance(hook: ResolvedHook, adapter_name: str) -> Provenance:
    """A ``write_hook`` output (an advisory file): ``kind=hook`` names the hook to edit."""
    return Provenance(
        kind="hook", artifact_id=hook.id, source=hook.source_package, adapter=adapter_name
    )


def build_lockfile(
    written: Sequence[Path],
    repo_root: Path,
    engine_version: str,
    *,
    provenance: Mapping[Path, Provenance],
    managed: Sequence[LockEntry] = (),
    carried: Sequence[LockEntry] = (),
    shared: Collection[str] = (),
) -> Lockfile:
    """Stamp a schema-2 lockfile.

    One provenance-bearing whole-file entry per written path, sorted by path
    (``provenance`` is keyed by resolved path; a path without one gets the v1
    unknown provenance, ``kind=""``). A path that resolves outside ``repo_root``
    — written through an output dir linked out of the repo — gets no entry:
    the lockfile never owns output there (SPEC §4.2 step 9 releases such an
    entry), and an absolute, machine-specific path must not reach a lockfile
    that may be committed (§14.4). A path owned element-wise by ``managed``
    scoped entries, or co-owned with the user (``shared``, repo-relative), gets
    no whole-file entry; the scoped entries follow. ``carried`` are the kept
    orphans (``_sync_orphans``): output an earlier sync wrote that is still
    engine-owned, so their old entries ride along unchanged (§B.6).

    Example::

        build_lockfile(r.written, root, "0.2.0", provenance=r.provenance, carried=plan.keep)
    """
    not_whole = {entry.path for entry in managed} | set(shared)
    entries: list[LockEntry] = []
    for path in sorted({p.resolve() for p in written}):
        entry = _whole_file_entry(path, repo_root, provenance.get(path))
        if entry is not None and entry.path not in not_whole:
            entries.append(entry)
    entries.extend(managed)
    entries.extend(sorted(carried, key=lambda entry: entry.path))
    # RFC 3339 Zulu timestamp for the lockfile per SPEC §14.4
    rendered_at = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return Lockfile(
        schema_version=LOCKFILE_SCHEMA,
        engine_version=engine_version,
        rendered_at=rendered_at,
        entries=entries,
    )


def _whole_file_entry(path: Path, repo_root: Path, origin: Provenance | None) -> LockEntry | None:
    """Whole-file entry for resolved ``path``; ``None`` if it is outside the repo or unreadable."""
    rel = _repo_relative(path, repo_root)
    if rel is None:
        return None
    try:
        content = path.read_bytes()
    except OSError:
        return None
    if origin is None:
        return LockEntry(path=rel, sha256=compute_hash(content), bytes=len(content))
    entry = LockEntry.from_provenance(rel, content, origin)
    if origin.kind == "hook" and _is_executable(path):
        entry = dataclasses.replace(entry, executable=True)
    return entry


def _is_executable(path: Path) -> bool:
    """The git-style single exec bit, POSIX only (§B.6): Windows modes say nothing about it."""
    return os.name == "posix" and bool(path.stat().st_mode & 0o111)


def _repo_relative(path: Path, repo_root: Path) -> str | None:
    """POSIX resolved ``path`` relative to the resolved ``repo_root``; ``None`` outside it."""
    try:
        return path.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return None
