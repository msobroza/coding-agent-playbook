"""`playbook sync` — regenerate all artifacts (SPEC §12.2 / §12.3).

Three modes:
- write (default): runs detector → renders → adapters write → settles output
  an earlier sync left behind (``_sync_orphans``, both ``[output] commit``
  settings — the only deletion policy for stale skill output) → stamps the
  lockfile, then applies the ``[output] commit`` policy: ``commit = false``
  (default) keeps the managed ``.gitignore`` block current and warns about
  generated paths git still tracks; ``commit = true`` removes the block.
- ``--check``: re-renders into an empty scratch dir and compares against the
  on-disk files (plus, for ``commit = false``, the managed block); exits 1 on
  drift.
- ``--check-staged``: re-renders into an empty scratch dir and exits 1 if any
  staged path is generated output (the ``commit = false`` pre-commit guard).

Both check modes decide skill-dir ownership against the real tree, so they skip
exactly the skill dirs write mode skips. Write mode installs the leftover policy
around its render, so a file/folder swap inside a skill dir displaces only what
that policy would delete (``_prior_output.judging_leftovers_with``).

Every mode first refuses to run when a configured overlay package is not
importable (``_sync_preflight``) — rendering without it would silently drop
the org rules and un-ignore their output.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as _dt
import shutil
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook import __version__ as _engine_version
from coding_agent_playbook.adapters._prior_output import judging_leftovers_with
from coding_agent_playbook.adapters._skill_writer import deciding_ownership_against
from coding_agent_playbook.commands import _sync_orphans, _sync_output, _sync_preflight
from coding_agent_playbook.commands._output_locations import OutputLocations
from coding_agent_playbook.detector import evaluate_predicate
from coding_agent_playbook.git_client import SubprocessGitClient
from coding_agent_playbook.gitignore import LOCKFILE_NAME, ignore_entries
from coding_agent_playbook.lockfile import LockEntry, Lockfile, compute_hash
from coding_agent_playbook.orchestrator import (
    RuleRegistryImpl,
    SyncContext,
    discover_adapters,
    installed_output_locations,
)
from coding_agent_playbook.renderer import build_environment, render_string

if TYPE_CHECKING:
    import argparse
    from collections.abc import Iterator, Sequence

    from jinja2 import Environment

    from coding_agent_playbook.detector import Facts
    from coding_agent_playbook.git_client import GitClient
    from coding_agent_playbook.types import Prompt, Rule, Skill


_LOCKFILE_SCHEMA = 1


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


def _build_lockfile(
    written_paths: list[Path],
    repo_root: Path,
    engine_version: str,
    carried: Sequence[LockEntry] = (),
) -> Lockfile:
    """Hash every written file into a new :class:`Lockfile`.

    ``carried`` are the kept orphans (``_sync_orphans``): output an earlier sync
    wrote that is still engine-owned, so their old entries ride along unchanged.
    """
    entries: list[LockEntry] = []
    for path in sorted({p.resolve() for p in written_paths}):
        try:
            content = path.read_bytes()
        except OSError:
            continue
        try:
            rel = path.resolve().relative_to(repo_root.resolve())
        except ValueError:
            rel = path
        entries.append(
            LockEntry(
                path=rel.as_posix(),
                sha256=compute_hash(content),
                bytes=len(content),
            )
        )
    entries.extend(sorted(carried, key=lambda entry: entry.path))
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


def _render_into(ctx: SyncContext, output_root: Path) -> list[Path]:
    """Render every applicable artifact through the enabled adapters into ``output_root``.

    Inputs — ``applies_if`` file checks, skill sources, config — are read from
    the real repo through ``ctx``; only the adapters' writes go to
    ``output_root``. So ``--check`` modes render into an empty scratch dir
    without copying the working tree. Returns the written paths.
    """
    rules = _filter_applies_if(ctx.rules_resolved, ctx.facts, ctx.repo_root)
    prompts = _filter_applies_if(ctx.prompts_resolved, ctx.facts, ctx.repo_root)
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

    written: list[Path] = []
    for adapter in adapters.values():
        for rule in rendered_rules:
            written.extend(adapter.write_rule(rule, output_root))
        for prompt in rendered_prompts:
            written.extend(adapter.write_prompt(prompt, output_root))
        for skill in skills:
            written.extend(adapter.write_skill(skill, output_root))
        written.extend(adapter.finalize(output_root))
    return written


def _run_sync(
    ctx: SyncContext, policy: _sync_orphans.LeftoverPolicy
) -> tuple[list[Path], list[Path]]:
    """Write mode's render: write into the repo, then let each adapter remove its
    own stale files (pruning directories that leaves empty). Returns
    ``(written, removed)``; ``removed`` includes files a file/folder swap displaced.

    The render runs under ``policy``, so a skill-dir file/folder swap displaces
    only what the leftover policy itself would delete.
    """
    with judging_leftovers_with(policy.may_delete):
        written = _render_into(ctx, ctx.repo_root)
    resolved_written: set[Path] = {p.resolve() for p in written}
    removed: list[Path] = []
    for adapter in ctx.adapters.values():
        removed.extend(adapter.cleanup_stale(resolved_written, ctx.repo_root))
    policy.locations.prune_emptied(removed, ctx.repo_root)
    return written, [*removed, *policy.displaced]


def execute(
    repo_root: Path,
    *,
    check: bool = False,
    check_staged: bool = False,
    git: GitClient | None = None,
) -> int:
    """Execute the sync pipeline in write, ``--check`` or ``--check-staged`` mode.

    Programmatic entry point used by ``playbook init`` (to fire a sync after
    writing the config) and by tests that want to skip the argparse plumbing.
    ``git`` defaults to :class:`SubprocessGitClient`; tests inject a fake.

    Example::

        >>> execute(Path("."), check=True)  # doctest: +SKIP
        0
    """
    if check and check_staged:
        raise ValueError("execute(): check and check_staged are mutually exclusive, got both True")
    git_client = git if git is not None else SubprocessGitClient()
    ctx = SyncContext.from_repo(repo_root)
    if check_staged and ctx.config.commit_output:
        return 0  # the staged-output guard is a no-op under committed output
    if not _environment_ready(ctx):
        return 1
    if check_staged:
        return _run_check_staged(ctx, git_client)
    if check:
        return _run_check(ctx, git_client)
    return _run_write(ctx, git_client)


def run(args: argparse.Namespace) -> int:
    """Dispatch the parsed ``playbook sync`` flags to :func:`execute`."""
    return execute(
        repo_root=_resolve_repo_root(args),
        check=bool(getattr(args, "check", False)),
        check_staged=bool(getattr(args, "check_staged", False)),
    )


def _environment_ready(ctx: SyncContext) -> bool:
    """Refuse (``False``) when an overlay is unimportable; warn on missing adapters."""
    missing = _sync_preflight.missing_overlays(ctx.config.overlays_enabled)
    if missing:
        _sync_preflight.report_missing_overlays(missing)
        return False
    absent = _missing_adapters(ctx)
    if absent:
        _sync_preflight.warn_missing_adapters(absent)
    return True


def _missing_adapters(ctx: SyncContext) -> list[str]:
    """Enabled adapter names with no installed entry point."""
    return _sync_preflight.missing_adapters(ctx.config.adapters_enabled, ctx.adapters)


def _run_write(ctx: SyncContext, git: GitClient) -> int:
    """Write mode: render + write + settle leftovers + lockfile, then the ``[output]`` policy.

    Under either ``commit`` setting, earlier output this render did not rewrite
    (orphans) is settled first: pristine, untracked ones are deleted, the rest
    stay owned — carried in the lockfile (and, for ``commit = false``, kept in
    the managed block, so they never become committable). ``.gitignore`` is a
    user file: never in ``written``, hashed, or cleaned up.
    """
    commit = ctx.config.commit_output
    policy = _leftover_policy(ctx, git)
    written, removed = _run_sync(ctx, policy)
    plan = policy.plan(written)
    removed.extend(policy.delete(plan.delete))
    policy.prune_vanished()
    lockfile = _build_lockfile(written, ctx.repo_root, ctx.config.engine_version, plan.keep)
    ctx.state_source.save_lockfile(lockfile)
    kept = _sync_orphans.entry_paths(plan.keep, ctx.repo_root)
    try:
        status = _sync_output.update_gitignore(ctx.repo_root, [*written, *kept], commit=commit)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if status:
        print(status)
    if commit:
        _sync_output.report_kept_leftovers(ctx.repo_root, kept)
    else:
        _sync_output.warn_tracked_output(ctx.repo_root, [*written, *kept], git)
    print(f"Summary: {len(written)} files written, {len(removed)} removed")
    return 0


def _previous_lockfile(ctx: SyncContext) -> Lockfile | None:
    """The last sync's lockfile (the ownership record), ``None`` if absent or unreadable."""
    try:
        return ctx.state_source.load_lockfile()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"warning: ignoring unreadable {LOCKFILE_NAME}: {exc}", file=sys.stderr)
        return None


def _leftover_policy(ctx: SyncContext, git: GitClient) -> _sync_orphans.LeftoverPolicy:
    """The leftover policy for this run: the previous lockfile, bounded by every
    installed adapter's declared output locations.

    With an enabled adapter missing, its output cannot be judged stale: keep all.
    """
    locations = OutputLocations.declared(installed_output_locations(), ctx.repo_root)
    return _sync_orphans.LeftoverPolicy(
        previous=_previous_lockfile(ctx),
        repo_root=ctx.repo_root,
        git=git,
        keep_all=bool(_missing_adapters(ctx)),
        locations=locations,
    )


@contextlib.contextmanager
def _rendered_scratch(ctx: SyncContext) -> Iterator[tuple[Path, list[Path]]]:
    """Render into an empty throwaway directory; yield ``(scratch_root, written)``.

    Nothing from the working tree is copied (inputs are read in place through
    ``ctx``), so a dangling symlink, an unreadable data directory, a socket or a
    large ``.venv`` can neither crash nor slow the pre-commit guard, and the
    real tree is never written. The scratch root carries the repo's directory
    name so name-derived content (``HARNESS.md``) renders identically, and
    skill-dir ownership is decided against the real tree (write-mode parity).
    """
    scratch_dir = Path(tempfile.mkdtemp(prefix="playbook-sync-check-"))
    try:
        scratch = scratch_dir / (ctx.repo_root.resolve().name or "repo")
        scratch.mkdir()
        # Skill-dir ownership is a property of the real tree, not the empty
        # scratch: skip exactly the dirs write mode would skip (SPEC §12.3).
        with deciding_ownership_against(ctx.repo_root):
            written = _render_into(ctx, scratch)
        yield scratch, written
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


def _on_real_tree(written: Sequence[Path], scratch: Path, repo_root: Path) -> list[Path]:
    """Map scratch-rendered paths onto the real tree.

    Ignore entries are then computed exactly as in write mode — resolved through
    the repo's own symlinks (a symlinked ``.claude/skills``, say) — so the check
    modes and write mode always agree on the managed block.
    """
    root = scratch.resolve()
    return [repo_root / path.resolve().relative_to(root) for path in written]


def _run_check(ctx: SyncContext, git: GitClient) -> int:
    """``playbook sync --check``: compare a scratch render against the repo.

    Exits 0 (no drift) or 1 (drift). Under ``[output] commit = false`` a
    stale, missing or malformed managed ``.gitignore`` block is drift too.
    Never writes to the repo.
    """
    with _rendered_scratch(ctx) as (scratch, written):
        drift = _sync_output.file_drift(written, scratch, ctx.repo_root)
        real_written = _on_real_tree(written, scratch, ctx.repo_root)
    if not ctx.config.commit_output:
        drift.extend(_block_drift(ctx, real_written, git))
    if drift:
        print("Drift detected:")
        for entry in drift:
            print(entry)
        return 1
    print("No drift detected.")
    return 0


def _block_drift(ctx: SyncContext, real_written: list[Path], git: GitClient) -> list[str]:
    """``--check``: the managed block vs. what write mode would write (incl. kept orphans)."""
    plan = _leftover_policy(ctx, git).plan(real_written)
    owned = [*real_written, *_sync_orphans.entry_paths(plan.keep, ctx.repo_root)]
    return _sync_output.gitignore_drift(ctx.repo_root, ignore_entries(owned, ctx.repo_root))


def _run_check_staged(ctx: SyncContext, git: GitClient) -> int:
    """``playbook sync --check-staged``: fail when generated output is staged.

    Exit 0 outside a git repo or with nothing staged (fast path: no render).
    Otherwise render into a scratch dir and exit 1 listing every staged path
    covered by an entry for this render's output *or* any earlier output still
    on disk (every orphan in the previous lockfile, pristine or not).
    """
    staged = git.staged_paths(ctx.repo_root)
    if not staged:
        return 0
    with _rendered_scratch(ctx) as (scratch, written):
        real_written = _on_real_tree(written, scratch, ctx.repo_root)
    orphans = _sync_orphans.find_orphans(_previous_lockfile(ctx), real_written, ctx.repo_root)
    owned = [*real_written, *_sync_orphans.entry_paths(orphans, ctx.repo_root)]
    offenders = _sync_output.staged_generated_paths(staged, ignore_entries(owned, ctx.repo_root))
    if not offenders:
        return 0
    _sync_output.report_staged_output(offenders, ctx.repo_root)
    return 1
