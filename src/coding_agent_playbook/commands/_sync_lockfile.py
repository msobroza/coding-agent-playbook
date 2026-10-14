"""Provenance recording and lockfile stamping for ``playbook sync`` (SPEC §14.4).

Schema 2 (specs/prK-lifecycle-hooks.md §P P4, §B.6) gives every whole-file
entry its provenance — ``kind``, ``artifact_id``, ``source`` and ``adapter``.
It is recorded **without changing the adapter return type**: the dispatch
wraps each ``write_rule``/``write_prompt``/``write_skill``/``finalize`` call
and tags every path it returns. Orphans the leftover policy keeps
(``_sync_orphans``) ride along in the new lockfile with their old entries.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from coding_agent_playbook.lockfile import LockEntry, Lockfile, Provenance, compute_hash
from coding_agent_playbook.orchestrator import artifact_id_of

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.adapters.base import Adapter
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
    adapters contribute (§C.1.4), empty until those adapters exist.

    Example::

        result = _run_sync(ctx, policy)
        lockfile = build_lockfile(result.written, ctx.repo_root, "0.2.0",
                                  provenance=result.provenance, managed=result.managed)
    """

    written: tuple[Path, ...]
    removed: tuple[Path, ...]
    provenance: Mapping[Path, Provenance]
    managed: tuple[LockEntry, ...] = ()


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

    def record(self, paths: Iterable[Path], provenance: Provenance) -> None:
        """Append ``paths`` and tag each (resolved) path with ``provenance``."""
        for path in paths:
            self.written.append(path)
            key = path.resolve()
            previous = self.provenance.get(key)
            if previous is None or previous == provenance:
                self.provenance[key] = provenance
            else:
                self.provenance[key] = _composite_of(previous, provenance)


def _composite_of(first: Provenance, second: Provenance) -> Provenance:
    """Provenance of a path with two different writers: the adapter survives
    only when both writers agree on it."""
    adapter = first.adapter if first.adapter == second.adapter else ""
    return Provenance(kind="composite", adapter=adapter)


def _artifact_provenance(
    kind: ProvenanceKind, artifact: Rule | Prompt | Skill, adapter_name: str
) -> Provenance:
    return Provenance(
        kind=kind,
        artifact_id=artifact_id_of(artifact),
        source=artifact.source_package,
        adapter=adapter_name,
    )


def dispatch_to_adapters(
    adapters: Mapping[str, Adapter],
    rules: Sequence[Rule],
    prompts: Sequence[Prompt],
    skills: Sequence[Skill],
    output_root: Path,
) -> ProvenanceRecorder:
    """Run every adapter's ``write_*`` calls then ``finalize`` into ``output_root``,
    tagging each returned path with the artifact (or composite output) that produced it.

    ``adapters`` maps the entry-point name to the instance, e.g.
    ``{"continue": ContinueAdapter()}``.

    Example::

        recorder = dispatch_to_adapters(adapters, rules, prompts, skills, repo_root)
    """
    recorder = ProvenanceRecorder()
    for name, adapter in adapters.items():
        for rule in rules:
            recorder.record(
                adapter.write_rule(rule, output_root), _artifact_provenance("rule", rule, name)
            )
        for prompt in prompts:
            recorder.record(
                adapter.write_prompt(prompt, output_root),
                _artifact_provenance("prompt", prompt, name),
            )
        for skill in skills:
            recorder.record(
                adapter.write_skill(skill, output_root), _artifact_provenance("skill", skill, name)
            )
        recorder.record(adapter.finalize(output_root), Provenance(kind="composite", adapter=name))
    return recorder


def build_lockfile(
    written: Sequence[Path],
    repo_root: Path,
    engine_version: str,
    *,
    provenance: Mapping[Path, Provenance],
    managed: Sequence[LockEntry] = (),
    carried: Sequence[LockEntry] = (),
) -> Lockfile:
    """Stamp a schema-2 lockfile.

    One provenance-bearing whole-file entry per written path, sorted by path
    (``provenance`` is keyed by resolved path; a path without one gets the v1
    unknown provenance, ``kind=""``). A path owned element-wise by ``managed``
    scoped entries gets no whole-file entry; those entries follow. ``carried``
    are the kept orphans (``_sync_orphans``): output an earlier sync wrote that
    is still engine-owned, so their old entries ride along unchanged (§B.6).

    Example::

        build_lockfile(r.written, root, "0.2.0", provenance=r.provenance, carried=plan.keep)
    """
    scoped_paths = {entry.path for entry in managed}
    entries: list[LockEntry] = []
    for path in sorted({p.resolve() for p in written}):
        entry = _whole_file_entry(path, repo_root, provenance.get(path))
        if entry is not None and entry.path not in scoped_paths:
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
    """Whole-file entry for resolved ``path``; ``None`` if it is unreadable."""
    try:
        content = path.read_bytes()
    except OSError:
        return None
    rel = _repo_relative(path, repo_root)
    if origin is None:
        return LockEntry(path=rel, sha256=compute_hash(content), bytes=len(content))
    return LockEntry.from_provenance(rel, content, origin)


def _repo_relative(path: Path, repo_root: Path) -> str:
    """POSIX resolved ``path`` relative to the resolved ``repo_root`` (as is if outside)."""
    try:
        return path.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
