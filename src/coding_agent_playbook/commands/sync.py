"""`playbook sync` — regenerate all artifacts (SPEC §12.2 / §12.3).

Two modes:
- write (default): runs detector → renders → adapters write → stamps lockfile.
- ``--check``: re-renders into a hygienic scratch copy of the repo and compares
  against the on-disk files; exits 1 if any differ or are missing, or if any
  generated file is orphaned (specs/prK-lifecycle-hooks.md §P P2).
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import shutil
import tempfile
import tomllib
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Final

from coding_agent_playbook import __version__ as _engine_version
from coding_agent_playbook.commands._sync_scratch import ScratchCopyPolicy
from coding_agent_playbook.detector import evaluate_predicate
from coding_agent_playbook.lockfile import LockEntry, Lockfile, Provenance, compute_hash
from coding_agent_playbook.orchestrator import (
    RuleRegistryImpl,
    SyncContext,
    artifact_id_of,
    discover_adapters,
)
from coding_agent_playbook.renderer import build_environment, render_string

if TYPE_CHECKING:
    import argparse
    from collections.abc import Iterable, Mapping, Sequence

    from jinja2 import Environment

    from coding_agent_playbook.adapters.base import Adapter
    from coding_agent_playbook.detector import Facts
    from coding_agent_playbook.lockfile import ProvenanceKind
    from coding_agent_playbook.types import Prompt, Rule, Skill


# 2 = provenance on every entry (specs/prK-lifecycle-hooks.md §P P4, §B.6).
_LOCKFILE_SCHEMA = 2

_LOCKFILE_FILENAME: Final = ".coding-agent-playbook.lock"

# Filenames that are state-source-managed and must be excluded from the
# drift diff (otherwise the lockfile written by sync would itself look
# like drift). Keep this in sync with the constants in
# ``sources.filesystem.FileSystemStateSource``.
_STATE_FILES_TO_SKIP: tuple[str, ...] = (
    ".coding-agent-playbook.toml",
    ".coding-agent-playbook.local.toml",
    _LOCKFILE_FILENAME,
)

# ``sync --check`` wording for an orphan (specs/prK-lifecycle-hooks.md §P P2).
_ORPHAN_HINT: Final = "    Orphaned generated file; run 'playbook sync' to remove."


def _build_jinja_context(ctx: SyncContext) -> dict[str, object]:
    """Per SPEC §9.4: facts + project metadata + engine metadata.

    Helpers (``has_framework``, ``rule``) are registered on the env globals by
    :func:`build_environment`; the context dict carries only data fields.
    """
    context: dict[str, object] = dict(ctx.facts)
    context["project_name"] = ctx.config.project.name
    context["project_description"] = ctx.config.project.description
    context.update(dict(ctx.config.user_choices))
    context["engine_version"] = ctx.config.engine_version or _engine_version
    return context


def _render_rule_body(rule: Rule, context: dict[str, object], env: Environment) -> Rule:
    """Re-emit a Rule with ``body`` set to the Jinja-rendered output.

    Non-templated rules pass through verbatim. The template/body split lets
    callers re-render from ``template_body`` again (e.g. for inline
    inclusion from a prompt with a different context).
    """
    if rule.is_templated:
        rendered = render_string(rule.template_body, dict(context), env=env)
        return dataclasses.replace(rule, body=rendered)
    return rule


def _render_prompt_body(prompt: Prompt, context: dict[str, object], env: Environment) -> Prompt:
    """Render a prompt's body through Jinja, masking ``input_variables`` so
    the opencode placeholder substitution can still find them (SPEC §9.7 +
    the ``prompt_opencode_command`` contract in renderer.py)."""
    if not prompt.is_templated:
        return prompt
    safe_context = dict(context)
    # Per SPEC §9.7 / renderer's opencode contract: input_variables names
    # must not appear in the Jinja context, or {{ var }} placeholders get
    # expanded before the format-time substitution maps them to $ARGUMENTS.
    for var in prompt.frontmatter.input_variables or []:
        name = var.get("name") if isinstance(var, dict) else None
        if name and name in safe_context:
            del safe_context[name]
    rendered = render_string(prompt.template_body, safe_context, env=env)
    return dataclasses.replace(prompt, body=rendered)


@dataclasses.dataclass(frozen=True)
class SyncResult:
    """Everything one :func:`_run_sync` pass produced.

    ``written`` keeps every adapter-returned path in dispatch order
    (duplicates included, so the summary count is unchanged); ``provenance``
    maps each *resolved* written path to its origin; ``removed`` lists the
    stale files ``cleanup_stale`` deleted; ``managed`` holds the scoped
    (per-JSON-element) lock entries hook-capable adapters contribute (§C.1.4),
    empty until those adapters exist.

    Example::

        result = _run_sync(ctx)
        lockfile = _build_lockfile(result.written, ctx.repo_root, "0.2.0",
                                   result.provenance, result.managed)
    """

    written: tuple[Path, ...]
    removed: tuple[Path, ...]
    provenance: Mapping[Path, Provenance]
    managed: tuple[LockEntry, ...]


class _ProvenanceRecorder:
    """Collect adapter-returned paths in dispatch order plus their provenance.

    The first writer of a path owns it. A second, *different* provenance for
    the same path (another artifact, another adapter, or a ``finalize``
    result) makes it ``kind="composite"`` (§P P4).
    """

    def __init__(self) -> None:
        self.written: list[Path] = []
        self.provenance: dict[Path, Provenance] = {}

    def record(self, paths: Iterable[Path], provenance: Provenance) -> None:
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


def _dispatch_to_adapters(
    adapters: Mapping[str, Adapter],
    rules: Sequence[Rule],
    prompts: Sequence[Prompt],
    skills: Sequence[Skill],
    repo_root: Path,
) -> _ProvenanceRecorder:
    """Run every adapter's ``write_*`` calls then ``finalize``, tagging each
    returned path with the artifact (or composite output) that produced it.

    Provenance is recorded by wrapping the calls, so the adapter return type
    (``list[Path]``) is unchanged. ``adapters`` maps the entry-point name to
    the instance, e.g. ``{"continue": ContinueAdapter()}``.
    """
    recorder = _ProvenanceRecorder()
    for name, adapter in adapters.items():
        for rule in rules:
            recorder.record(
                adapter.write_rule(rule, repo_root), _artifact_provenance("rule", rule, name)
            )
        for prompt in prompts:
            recorder.record(
                adapter.write_prompt(prompt, repo_root),
                _artifact_provenance("prompt", prompt, name),
            )
        for skill in skills:
            recorder.record(
                adapter.write_skill(skill, repo_root), _artifact_provenance("skill", skill, name)
            )
        recorder.record(adapter.finalize(repo_root), Provenance(kind="composite", adapter=name))
    return recorder


def _repo_relative(path: Path, repo_root: Path) -> str:
    """Posix path of resolved ``path`` relative to ``repo_root`` (absolute if outside)."""
    try:
        return path.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _whole_file_entry(path: Path, repo_root: Path, origin: Provenance | None) -> LockEntry | None:
    """Whole-file entry for resolved ``path``; ``None`` if it is unreadable.
    A path with no recorded origin gets the v1 unknown provenance (``kind=""``)."""
    try:
        content = path.read_bytes()
    except OSError:
        return None
    rel = _repo_relative(path, repo_root)
    if origin is None:
        return LockEntry(path=rel, sha256=compute_hash(content), bytes=len(content))
    return LockEntry.from_provenance(rel, content, origin)


def _build_lockfile(
    written: Sequence[Path],
    repo_root: Path,
    engine_version: str,
    provenance: Mapping[Path, Provenance],
    managed: Sequence[LockEntry],
) -> Lockfile:
    """Stamp a schema-2 lockfile: one provenance-bearing whole-file entry per
    written path, sorted by path; a path owned element-wise by ``managed``
    scoped entries gets no whole-file entry, and those entries are appended
    instead (§B.6, §C.1.4). ``provenance`` is keyed by resolved path.

    Example: ``_build_lockfile(r.written, root, "0.2.0", r.provenance, r.managed)``.
    """
    scoped_paths = {entry.path for entry in managed}
    entries: list[LockEntry] = []
    for path in sorted({p.resolve() for p in written}):
        entry = _whole_file_entry(path, repo_root, provenance.get(path))
        if entry is not None and entry.path not in scoped_paths:
            entries.append(entry)
    entries.extend(managed)
    # RFC 3339 Zulu timestamp for the lockfile per SPEC §14.4
    rendered_at = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return Lockfile(
        schema_version=_LOCKFILE_SCHEMA,
        engine_version=engine_version,
        rendered_at=rendered_at,
        entries=entries,
    )


def _filter_applies_if[T: "Rule | Prompt"](
    artifacts: list[T],
    facts: Facts,
    repo_root: Path,
) -> list[T]:
    """Apply :func:`evaluate_predicate` to each artifact and drop the ones
    whose ``applies_if`` evaluates to False. Empty predicate → always pass.
    """
    kept: list[T] = []
    for artifact in artifacts:
        predicate = artifact.frontmatter.applies_if or {}
        if not predicate or evaluate_predicate(predicate, facts, repo_root=repo_root):
            kept.append(artifact)
    return kept


def _filter_skills(skills: list[Skill]) -> list[Skill]:
    """Skills are unconditional in v1 (no ``applies_if`` in the SKILL.md
    schema). Returned unchanged; kept as a hook for v2 to filter on a
    ``conditions:`` extension without churning the call site."""
    return list(skills)


def _resolve_repo_root(args: argparse.Namespace) -> Path:
    raw = getattr(args, "repo_root", None)
    if raw is None:
        return Path.cwd()
    return Path(raw)


def _cleanup_stale(
    adapters: Mapping[str, Adapter], written: Sequence[Path], repo_root: Path
) -> tuple[Path, ...]:
    """Run every adapter's ``cleanup_stale`` after *all* adapters finalized."""
    resolved_written: set[Path] = {p.resolve() for p in written}
    removed: list[Path] = []
    for adapter in adapters.values():
        removed.extend(adapter.cleanup_stale(resolved_written, repo_root))
    return tuple(removed)


def _run_sync(ctx: SyncContext, *, predicate_root: Path | None = None) -> SyncResult:
    """Internal helper: render + dispatch + cleanup, returning one
    :class:`SyncResult`. Used by both write mode and ``--check`` (the latter
    compares ``written`` with on-disk content and reports ``removed`` as orphans).

    ``predicate_root`` is where ``applies_if: has_file`` paths are looked up
    (default ``ctx.repo_root``). ``--check`` passes the real repo so a path its
    scratch copy leaves out (``.env``, ``build/``) never changes the rule set.
    """
    root = ctx.repo_root if predicate_root is None else predicate_root
    rules = _filter_applies_if(ctx.rules_resolved, ctx.facts, root)
    prompts = _filter_applies_if(ctx.prompts_resolved, ctx.facts, root)
    skills = _filter_skills(ctx.skills_resolved)

    base_env = build_environment([], is_prompt_context=False)
    base_env.globals["_facts"] = dict(ctx.facts)
    base_context = _build_jinja_context(ctx)

    # Render rule bodies first (their template_body may also be re-rendered
    # by the registry when a prompt asks to inline them).
    rendered_rules = [_render_rule_body(rule, base_context, base_env) for rule in rules]

    registry = RuleRegistryImpl(rendered_rules, ctx.facts, base_env)
    prompt_env = build_environment([], is_prompt_context=True, rule_registry=registry)
    prompt_env.globals["_facts"] = dict(ctx.facts)
    rendered_prompts = [_render_prompt_body(p, base_context, prompt_env) for p in prompts]

    # Re-discover adapters with the rule_registry plumbed in so the
    # includes_rules appendix can resolve through the registry.
    adapters = discover_adapters(ctx.config, rule_registry=registry)
    ctx.adapters = adapters

    recorder = _dispatch_to_adapters(
        adapters, rendered_rules, rendered_prompts, skills, ctx.repo_root
    )
    removed = _cleanup_stale(adapters, recorder.written, ctx.repo_root)
    return SyncResult(
        written=tuple(recorder.written),
        removed=removed,
        provenance=dict(recorder.provenance),
        managed=(),
    )


def execute(repo_root: Path, *, check: bool = False) -> int:
    """Execute the sync pipeline.

    Programmatic entry point used by ``playbook init`` (to fire a sync after
    writing the config) and by tests that want to skip the argparse
    plumbing. The CLI's :func:`run` wrapper simply parses flags and
    forwards to here.
    """
    ctx = SyncContext.from_repo(repo_root)
    if check:
        return _run_check(ctx)
    result = _run_sync(ctx)

    lockfile = _build_lockfile(
        result.written,
        ctx.repo_root,
        ctx.config.engine_version,
        result.provenance,
        result.managed,
    )
    ctx.state_source.save_lockfile(lockfile)

    print(f"Summary: {len(result.written)} files written, {len(result.removed)} removed")
    return 0


def run(args: argparse.Namespace) -> int:
    """Dispatch to write mode or ``--check`` mode."""
    return execute(repo_root=_resolve_repo_root(args), check=bool(getattr(args, "check", False)))


def _run_check(ctx: SyncContext) -> int:
    """``playbook sync --check``: render into a scratch copy, then report drift.

    Exits 0 (no drift) or 1. Drift is a generated file that differs from, or is
    missing in, the real repo, plus every orphan (:func:`_orphan_drift`). The
    full sync runs against the copy so adapters write freely and the real tree
    is never touched. The copy is hygienic (:class:`ScratchCopyPolicy`): no VCS,
    environments, caches, build outputs, secrets or links leaving the repo.
    Because those are detector inputs, facts and ``has_file`` predicates come
    from the real repo, so the scratch run renders the same artifact set.
    """
    scratch_dir = Path(tempfile.mkdtemp(prefix="playbook-sync-check-"))
    try:
        scratch = scratch_dir / "repo"
        policy = ScratchCopyPolicy(ctx.repo_root)
        shutil.copytree(ctx.repo_root, scratch, symlinks=False, ignore=policy)
        scratch_ctx = SyncContext.from_repo(scratch, facts=ctx.facts)
        # ``cleanup_stale`` runs inside the copy: ``removed`` is exactly the set
        # of stale generated files a real sync would delete, i.e. orphans.
        result = _run_sync(scratch_ctx, predicate_root=ctx.repo_root)
        drift = _content_drift(result.written, scratch, ctx.repo_root)
        drift += _orphan_drift(result, scratch, ctx, policy)
        return _report_drift(drift)
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


def _report_drift(drift: Sequence[str]) -> int:
    """Print the drift lines (or the all-clear) and return the exit code."""
    if not drift:
        print("No drift detected.")
        return 0
    print("Drift detected:")
    for entry in drift:
        print(entry)
    return 1


def _scratch_relative(path: Path, scratch_real: Path) -> Path:
    """``path`` (inside the scratch copy) relative to the resolved scratch root."""
    return path.resolve().relative_to(scratch_real)


def _content_drift(written: Sequence[Path], scratch: Path, repo_root: Path) -> list[str]:
    """Drift lines for scratch-generated files that differ from, or are missing
    in, ``repo_root``; state-source files (config, lockfile) are skipped."""
    scratch_real = scratch.resolve()
    drift: list[str] = []
    for path in written:
        rel = _scratch_relative(path, scratch_real)
        if rel.name in _STATE_FILES_TO_SKIP:
            continue
        line = _compare_generated(path, repo_root / rel, rel.as_posix())
        if line is not None:
            drift.append(line)
    return drift


def _compare_generated(generated: Path, actual: Path, rel: str) -> str | None:
    """One drift line when ``actual`` is missing or differs from ``generated``."""
    if not actual.is_file():
        return f"  {rel}\n    Missing on disk; run 'playbook sync' to create."
    if actual.read_bytes() != generated.read_bytes():
        return (
            f"  {rel}\n"
            "    Generated content differs from on-disk content.\n"
            "    Run 'playbook sync' to regenerate."
        )
    return None


def _orphan_drift(
    result: SyncResult, scratch: Path, ctx: SyncContext, policy: ScratchCopyPolicy
) -> list[str]:
    """Drift lines for orphans, each path once, sorted.

    An orphan is a generated file the scratch sync's ``cleanup_stale`` removed
    (sentinel-tagged, no longer produced), or a lockfile orphan
    (:func:`_lockfile_orphans`) — the only record for files that cannot carry a
    sentinel (``SKILL.md``, copied skill scripts). An unreadable lockfile (e.g.
    merge-conflict markers) is reported as drift instead of a traceback.
    """
    scratch_real = scratch.resolve()
    orphans = {_scratch_relative(p, scratch_real).as_posix() for p in result.removed}
    try:
        lockfile = ctx.state_source.load_lockfile()
    except (tomllib.TOMLDecodeError, KeyError) as exc:
        unreadable = (
            f"  {_LOCKFILE_FILENAME}\n    Unreadable lockfile ({type(exc).__name__}: {exc}); "
            "run 'playbook sync' to rewrite it."
        )
        return [*_orphan_lines(orphans), unreadable]
    regenerated = {_scratch_relative(p, scratch_real).as_posix() for p in result.written}
    orphans |= _lockfile_orphans(lockfile, regenerated, ctx.repo_root, policy)
    return _orphan_lines(orphans)


def _orphan_lines(orphans: Iterable[str]) -> list[str]:
    return [f"  {rel}\n{_ORPHAN_HINT}" for rel in sorted(orphans)]


def _lockfile_orphans(
    lockfile: Lockfile | None,
    regenerated: set[str],
    repo_root: Path,
    policy: ScratchCopyPolicy,
) -> set[str]:
    """Paths of prior whole-file lock entries the scratch sync did not
    regenerate whose file still exists in ``repo_root``.

    Scoped entries (``json:<pointer>``) are skipped: their file is shared with
    the user and never deleted (§B.6). So are paths the scratch copy left out
    (``policy.covers``), which the scratch run could not judge.
    """
    if lockfile is None:
        return set()
    return {
        entry.path
        for entry in lockfile.entries
        if not entry.scope
        and entry.path not in regenerated
        and not policy.covers(entry.path)
        and _is_repo_file(repo_root, entry.path)
    }


def _is_repo_file(repo_root: Path, rel: str) -> bool:
    """Whether lockfile path ``rel`` names an existing file inside ``repo_root``
    (absolute and ``..`` paths never do)."""
    pure = PurePosixPath(rel)
    if pure.is_absolute() or ".." in pure.parts:
        return False
    return (repo_root / pure).is_file()
