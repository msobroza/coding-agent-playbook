"""`playbook sync` — regenerate all artifacts (SPEC §12.2 / §12.3).

Three modes:
- write (default): runs detector → renders → adapters write → settles output
  an earlier sync left behind (``_sync_orphans``, both ``[output] commit``
  settings — the only deletion policy for stale skill output) → stamps the
  schema-2 lockfile with each entry's provenance (``_sync_lockfile``), then
  applies the ``[output] commit`` policy: ``commit = false`` (default) keeps
  the managed ``.gitignore`` block current and warns about generated paths git
  still tracks; ``commit = true`` removes the block.
- ``--check``: re-renders into an empty scratch dir and compares against the
  on-disk files (plus, for ``commit = false``, the managed block); exits 1 on
  drift, including every **orphan** write mode would delete
  (specs/prK-lifecycle-hooks.md §P P2).
- ``--check-staged``: re-renders into an empty scratch dir and exits 1 if any
  staged path is generated output (the ``commit = false`` pre-commit guard).

Both check modes decide skill-dir ownership against the real tree, so they skip
exactly the skill dirs write mode skips. Write mode installs the leftover policy
around its render, so a file/folder swap inside a skill dir displaces only what
that policy would delete (``_prior_output.judging_leftovers_with``).

Every mode first refuses to run when a configured overlay package fails to
import or ships no ``resources/`` directory, or a bundled-plugin name matches no
``catalog/plugins/<leaf>/`` (``_sync_preflight``) — rendering without it would
silently drop the org rules and un-ignore their output. A config the engine
would misread fails even earlier, while loading
(:class:`~coding_agent_playbook.config.schema.ConfigError`). Write mode and
``--check`` then run the full ``playbook validate`` rule set, the hook trust
contract H1-H21 included (:func:`~coding_agent_playbook.commands.validate.sync_gate_errors`),
and exit 1 on any finding, printing its ``FAIL`` lines to stderr and writing
nothing (§P P8, §B.5). Validate's warnings print as ``warning:`` lines, and a
``[hooks]`` / ``[guardrails]`` table in ``.local.toml`` is only one of them
here (§B.1). ``--check-staged`` is the pre-commit hot path and is not gated,
except that a prompt still calling the removed ``rule()`` fails with validate's
message (D15) instead of a jinja2 traceback. A template the Jinja sandbox
rejects aborts every mode with exit 1, naming the source file, before any
adapter writes (specs/prK-lifecycle-hooks.md §P P1); so does a skill whose
composed description cannot fit 300 characters, naming it.

Hooks (§C.1.3, ``_sync_hooks``): every mode renders the on hooks through the
adapters (each told the real repo and the prior lockfile) plus the sync-level
``guard_config.json`` and script copies. ``.claude/settings.json`` is a shared
output: merged against the real file even into the ``--check`` scratch dir,
and never whole-file locked, gitignored or flagged as staged output. The
launcher, the OpenCode shim and (hooks or not) the Claude Code rules file are
written whole, so every mode first refuses (exit 1, naming the file) a user
file or a symlink at a path it is about to write, and a symlinked or
hard-linked ``.claude/CLAUDE.md`` stub. A write stopped by something in the way
(a dangling symlink such as ``.claude/commands -> ../tools/cc``, a file where an
output directory goes, a directory, FIFO or socket where an output file goes)
exits 1 naming it, never a traceback or a hang (``_output_blockers``). Write mode then pins the interpreter,
says when OpenCode must restart (the shim's lock entry changed), and asks the
TTY-only trust questions.
"""

from __future__ import annotations

import contextlib
import shutil
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook._symlinks import real_path
from coding_agent_playbook.adapters._owned_files import UserOwnedFileError
from coding_agent_playbook.adapters._prior_output import judging_leftovers_with
from coding_agent_playbook.adapters._skill_writer import deciding_ownership_against
from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.adapters.claude_settings import SettingsMergeError
from coding_agent_playbook.commands import (
    _output_blockers,
    _sync_hooks,
    _sync_orphans,
    _sync_output,
    _sync_preflight,
)
from coding_agent_playbook.commands._output_locations import OutputLocations
from coding_agent_playbook.commands._sync_hook_local import SyncHookDeps
from coding_agent_playbook.commands._sync_lockfile import (
    ProvenanceRecorder,
    SyncResult,
    build_lockfile,
    dispatch_to_adapters,
)
from coding_agent_playbook.commands._sync_render import (
    SkillDescriptionOverflowError,
    render_artifacts,
    report_description_overflow,
    report_sandbox_violation,
)
from coding_agent_playbook.commands._validate_prompts import check_prompt_rule_calls
from coding_agent_playbook.commands._validation import report_validation_errors
from coding_agent_playbook.commands.validate import sync_gate_errors
from coding_agent_playbook.git_client import SubprocessGitClient
from coding_agent_playbook.gitignore import LOCKFILE_NAME, ignore_entries
from coding_agent_playbook.guard_config import SYNC_OUTPUT_LOCATIONS
from coding_agent_playbook.orchestrator import (
    SyncContext,
    discover_adapters,
    installed_output_locations,
)
from coding_agent_playbook.renderer import TemplateSecurityError

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable, Iterator, Sequence

    from coding_agent_playbook.commands._validation import ValidationError
    from coding_agent_playbook.git_client import GitClient
    from coding_agent_playbook.lockfile.model import Lockfile

    #: The validate gate's signature: every finding for ``ctx`` (none = go on).
    ValidateFn = Callable[[SyncContext], Sequence[ValidationError]]

# What "the lockfile cannot be read" looks like: tomllib.TOMLDecodeError and
# lockfile.model.LockfileFormatError are ValueErrors; the rest guard third-party sources.
_UNREADABLE_LOCKFILE: tuple[type[Exception], ...] = (OSError, ValueError, KeyError, TypeError)

# Printed last when the sandbox or the validate gate stops a sync before any write.
_ABORT_OUTCOME = "playbook sync aborted; no files were written."


def _resolve_repo_root(args: argparse.Namespace) -> Path:
    raw = getattr(args, "repo_root", None)
    if raw is None:
        return Path.cwd()
    return Path(raw)


def _render_into(
    ctx: SyncContext, output_root: Path, prior: Lockfile | None
) -> tuple[ProvenanceRecorder, _sync_hooks.SyncHooks]:
    """Render every applicable artifact through the enabled adapters into ``output_root``.

    Inputs — ``applies_if`` file checks, skill sources, config, the co-owned
    ``settings.json`` — are read from the real repo through ``ctx``; only the
    writes go to ``output_root``. So ``--check`` modes render into an empty
    scratch dir without copying the working tree. Every template runs, and a
    ``settings.json`` the merge would refuse, a user file where an
    engine-owned file (the launcher, the OpenCode shim, the Claude Code rules
    file) goes, or a symlinked or hard-linked ``.claude/CLAUDE.md`` is
    rejected, before the first write. Returns the written paths with their
    provenance, and the hooks.
    """
    rendered = render_artifacts(ctx)
    _sync_hooks.check_settings_readable(ctx, rendered.hooks, prior)
    # Re-discover adapters with the rule_registry plumbed in so the
    # includes_rules appendix can resolve through the registry.
    adapters = discover_adapters(ctx.config, rule_registry=rendered.registry)
    ctx.adapters = adapters
    _sync_hooks.check_runtime_outputs_owned(ctx.repo_root, adapters, rendered.hooks)
    recorder = dispatch_to_adapters(
        adapters,
        rendered.rules,
        rendered.prompts,
        rendered.skills,
        output_root,
        hooks=rendered.hooks.dispatch(
            ctx.repo_root, prior, guardrails_skill=rendered.guardrails_skill
        ),
    )
    _sync_hooks.write_runtime_outputs(
        ctx, rendered.hooks, output_root, recorder, prompts=rendered.prompts, rules=rendered.rules
    )
    return recorder, rendered.hooks


def _run_sync(ctx: SyncContext, policy: _sync_orphans.LeftoverPolicy) -> SyncResult:
    """Write mode's render: write into the repo, then let each adapter remove its
    own stale files (pruning directories that leaves empty).

    The render runs under ``policy``, so a skill-dir file/folder swap displaces
    only what the leftover policy itself would delete; ``removed`` includes
    those displaced files.
    """
    with judging_leftovers_with(policy.may_delete):
        recorder, hooks = _render_into(ctx, ctx.repo_root, policy.previous)
    resolved_written: set[Path] = {p.resolve() for p in recorder.written}
    removed: list[Path] = []
    for adapter in ctx.adapters.values():
        removed.extend(adapter.cleanup_stale(resolved_written, ctx.repo_root))
    policy.locations.prune_emptied(removed, ctx.repo_root)
    return SyncResult(
        written=tuple(recorder.written),
        removed=(*removed, *policy.displaced),
        provenance=dict(recorder.provenance),
        managed=tuple(recorder.managed),
        hooks=hooks,
    )


def execute(
    repo_root: Path,
    *,
    check: bool = False,
    check_staged: bool = False,
    git: GitClient | None = None,
    validate: ValidateFn = sync_gate_errors,
    hook_deps: SyncHookDeps | None = None,
) -> int:
    """Execute the sync pipeline in write, ``--check`` or ``--check-staged`` mode.

    Programmatic entry point used by ``playbook init`` (to fire a sync after
    writing the config) and by tests that want to skip the argparse plumbing.
    ``git`` defaults to :class:`SubprocessGitClient`; tests inject a fake.
    Write and ``--check`` mode first run ``validate`` (the ``playbook
    validate`` rule set; tests inject a fake). ``hook_deps`` holds write
    mode's machine-local hook seams (pins, trust store, TTY); tests inject
    fakes. Returns 1, having written nothing, on any validate finding, when a
    template is rejected by the Jinja sandbox, when a skill's composed
    description cannot fit 300 characters, when ``settings.json`` is
    not valid JSON, or when a user file (or a symlink) holds the path of the
    launcher, the OpenCode shim or the Claude Code rules file, or when
    ``.claude/CLAUDE.md`` is a symlink, a hard link or not a regular file.
    Returns 1 too, without a traceback, naming the entry, when a write is stopped
    by something in the way in the repo: a dangling symlink (``.claude/commands
    -> ../tools/cc``), a file where an output directory goes, or a directory,
    FIFO or socket where an output file goes.

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
    if not check_staged and not _passes_validation(ctx, validate):
        return 1
    try:
        if check_staged:
            return _run_check_staged(ctx, git_client)
        if check:
            return _run_check(ctx, git_client)
        return _run_write(ctx, git_client, hook_deps or SyncHookDeps())
    except TemplateSecurityError as exc:
        return report_sandbox_violation(exc, ctx.repo_root, outcome=_ABORT_OUTCOME)
    except SkillDescriptionOverflowError as exc:
        return report_description_overflow(exc, outcome=_ABORT_OUTCOME)
    except SettingsMergeError as exc:
        return _sync_hooks.report_settings_error(exc, check=check or check_staged)
    except UserOwnedFileError as exc:
        return _sync_hooks.report_owned_file_error(exc, check=check or check_staged)
    except _sync_hooks.HookPolicyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        # A write stopped by something in the way (a dangling link, a file where an
        # output dir goes, a dir, FIFO or socket where an output file goes): name
        # it instead of a traceback. Any other OSError (EACCES, ENOSPC, a bug) keeps its traceback.
        blocker = _output_blockers.blocker_in(exc, ctx.repo_root)
        if blocker is None:
            raise
        return _output_blockers.report_blocker(blocker, check=check or check_staged)


def run(args: argparse.Namespace) -> int:
    """Dispatch the parsed ``playbook sync`` flags to :func:`execute`."""
    return execute(
        repo_root=_resolve_repo_root(args),
        check=bool(getattr(args, "check", False)),
        check_staged=bool(getattr(args, "check_staged", False)),
    )


def _environment_ready(ctx: SyncContext) -> bool:
    """Refuse (``False``) when an overlay is unusable; warn on missing adapters."""
    unusable = _sync_preflight.unusable_overlays(ctx.config.overlays_enabled)
    if unusable:
        _sync_preflight.report_unusable_overlays(unusable)
        return False
    absent = _missing_adapters(ctx)
    if absent:
        _sync_preflight.warn_missing_adapters(absent)
    return True


def _passes_validation(ctx: SyncContext, validate: ValidateFn) -> bool:
    """Run the validate gate; on findings print them and the abort line to stderr.

    Any rendering of content ``playbook validate`` rejects — an unknown
    ``applies_if`` fact, a broken eval-task reference, an invalid Agent Skill
    — is refused before the first write (prK §P P8b, OQ-4). ``--check-staged``,
    the ``commit = false`` pre-commit hot path, comes here only with the
    ``rule()`` call check (D15).
    """
    errors = validate(ctx)
    if not errors:
        return True
    report_validation_errors(errors, sys.stderr)
    print(_ABORT_OUTCOME, file=sys.stderr)
    return False


def _missing_adapters(ctx: SyncContext) -> list[str]:
    """Enabled adapter names with no installed entry point."""
    return _sync_preflight.missing_adapters(ctx.config.adapters_enabled, ctx.adapters)


def _run_write(ctx: SyncContext, git: GitClient, hook_deps: SyncHookDeps) -> int:
    """Write mode: render + write + settle leftovers + lockfile, then the ``[output]`` policy.

    Under either ``commit`` setting, earlier output this render did not rewrite
    (orphans) is settled first: pristine, untracked ones are deleted, the rest
    stay owned — carried in the lockfile (and, for ``commit = false``, kept in
    the managed block, so they never become committable). ``.gitignore`` is a
    user file: never in ``written``, hashed, or cleaned up.
    """
    commit = ctx.config.commit_output
    policy = _leftover_policy(ctx, git, _previous_lockfile(ctx))
    result = _run_sync(ctx, policy)
    written = list(result.written)
    plan = policy.plan(written)
    removed = [*result.removed, *policy.delete(plan.delete)]
    policy.prune_vanished()
    shared = _sync_output.shared_outputs(ctx.adapters)
    lockfile = build_lockfile(
        written,
        ctx.repo_root,
        ctx.config.engine_version,
        provenance=result.provenance,
        managed=result.managed,
        carried=plan.keep,
        shared=shared,
    )
    ctx.state_source.save_lockfile(lockfile)
    kept = _sync_orphans.entry_paths(plan.keep, ctx.repo_root)
    owned = _sync_output.without_shared([*written, *kept], ctx.repo_root, shared)
    try:
        status = _sync_output.update_gitignore(ctx.repo_root, owned, commit=commit)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if status:
        print(status)
    if commit:
        _sync_output.report_kept_leftovers(ctx.repo_root, kept)
    else:
        _sync_output.warn_tracked_output(ctx.repo_root, owned, git)
    print(f"Summary: {len(written)} files written, {len(removed)} removed")
    restart = _sync_hooks.opencode_restart_notice(policy.previous, lockfile)
    _sync_hooks.finish_write(
        ctx, result.hooks or _sync_hooks.SyncHooks(), hook_deps, restart_notice=restart
    )
    return 0


def _previous_lockfile(ctx: SyncContext) -> Lockfile | None:
    """The last sync's lockfile (the ownership record), ``None`` if absent or unreadable."""
    try:
        return ctx.state_source.load_lockfile()
    except _UNREADABLE_LOCKFILE as exc:
        print(f"warning: ignoring unreadable {LOCKFILE_NAME}: {exc}", file=sys.stderr)
        return None


def _leftover_policy(
    ctx: SyncContext, git: GitClient, previous: Lockfile | None
) -> _sync_orphans.LeftoverPolicy:
    """The leftover policy for this run: ``previous`` (the last sync's lockfile),
    bounded by every installed adapter's declared output locations.

    With an enabled adapter missing, its output cannot be judged stale: keep all.
    The sync-level hook outputs (``guard_config.json``, copied scripts) belong to
    no adapter, so their location joins explicitly (§B.6).
    """
    locations = OutputLocations.declared(
        [*installed_output_locations(), *SYNC_OUTPUT_LOCATIONS], ctx.repo_root
    )
    return _sync_orphans.LeftoverPolicy(
        previous=previous,
        repo_root=ctx.repo_root,
        git=git,
        keep_all=bool(_missing_adapters(ctx)),
        locations=locations,
    )


@contextlib.contextmanager
def _rendered_scratch(
    ctx: SyncContext, prior: Lockfile | None
) -> Iterator[tuple[Path, list[Path]]]:
    """Render into an empty throwaway directory; yield ``(scratch_root, written)``.

    Nothing from the working tree is copied (inputs are read in place through
    ``ctx``), so a dangling symlink, an unreadable data directory, a socket, a
    secret file or a large ``.venv`` can neither crash, slow nor leak into the
    pre-commit guard, and the real tree is never written. The only source bytes
    the render copies are skills' ``scripts/``/``references/``, which refuse
    secret paths and links leaving the skill (``_skill_sources``). The scratch root
    carries the repo's directory name so name-derived content (``HARNESS.md``)
    renders identically, and skill-dir ownership is decided against the real
    tree (write-mode parity).
    """
    scratch_dir = Path(tempfile.mkdtemp(prefix="playbook-sync-check-"))
    try:
        scratch = scratch_dir / (ctx.repo_root.resolve().name or "repo")
        scratch.mkdir()
        # Skill-dir ownership is a property of the real tree, not the empty
        # scratch: skip exactly the dirs write mode would skip (SPEC §12.3).
        with deciding_ownership_against(ctx.repo_root):
            written = _render_into(ctx, scratch, prior)[0].written
        yield scratch, written
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


def _on_real_tree(written: Sequence[Path], scratch: Path, repo_root: Path) -> list[Path]:
    """Map scratch-rendered paths onto the real tree.

    Ignore entries and orphans are then computed exactly as in write mode —
    resolved through the repo's own symlinks (a symlinked ``.claude/skills``,
    say) — so the check modes and write mode always agree.
    """
    root = scratch.resolve()
    return [repo_root / path.resolve().relative_to(root) for path in written]


def _run_check(ctx: SyncContext, git: GitClient) -> int:
    """``playbook sync --check``: compare a scratch render against the repo.

    Exits 0 (no drift) or 1 (drift). Drift is a generated file that differs or
    is missing, every orphan write mode would delete (:func:`_orphans_sync_removes`),
    an unreadable lockfile, and — under ``[output] commit = false`` — a stale,
    missing or malformed managed ``.gitignore`` block. Never writes to the repo.
    """
    previous, lockfile_drift = _check_lockfile(ctx)
    with _rendered_scratch(ctx, previous) as (scratch, written):
        drift = _sync_output.file_drift(
            written,
            scratch,
            ctx.repo_root,
            shared=_sync_output.shared_outputs(ctx.adapters),
            skill_roots=_sync_output.native_skill_roots(ctx.adapters),
        )
        real_written = _on_real_tree(written, scratch, ctx.repo_root)
    stale = _stale_outputs(ctx, real_written)
    # Settled as in write mode, where cleanup_stale has already deleted ``stale``.
    plan = _leftover_policy(ctx, git, previous).plan([*real_written, *stale])
    drift.extend(_orphans_sync_removes(stale, plan, ctx.repo_root))
    drift.extend(lockfile_drift)
    if not ctx.config.commit_output:
        drift.extend(_block_drift(ctx, real_written, plan))
    return _report_drift(drift)


def _check_lockfile(ctx: SyncContext) -> tuple[Lockfile | None, list[str]]:
    """``--check``: the previous lockfile, or ``None`` plus a drift line if unreadable."""
    try:
        return ctx.state_source.load_lockfile(), []
    except _UNREADABLE_LOCKFILE as exc:
        return None, _sync_output.unreadable_lockfile_drift(exc)


def _stale_outputs(ctx: SyncContext, real_written: Sequence[Path]) -> list[Path]:
    """Files the enabled adapters' ``cleanup_stale`` would delete on the real tree (read-only).

    An adapter written against the pre-v0.16 contract overrides ``cleanup_stale``
    but not ``stale_outputs`` (SPEC §10.1): the check cannot know what its
    cleanup deletes, so it is skipped with a warning rather than reporting
    orphans its own cleanup may never remove (a drift no sync could clear).
    """
    resolved = {real_path(path) for path in real_written}  # may pass through a user's loop
    stale: list[Path] = []
    for name, adapter in ctx.adapters.items():
        if _has_legacy_cleanup(adapter):
            _sync_preflight.warn_legacy_cleanup(name)
            continue
        stale.extend(adapter.stale_outputs(resolved, ctx.repo_root))
    return stale


def _has_legacy_cleanup(adapter: Adapter) -> bool:
    """True when ``adapter`` customizes ``cleanup_stale`` without ``stale_outputs``."""
    cls = type(adapter)
    return (
        cls.cleanup_stale is not Adapter.cleanup_stale
        and cls.stale_outputs is Adapter.stale_outputs
    )


def _orphans_sync_removes(
    stale: Sequence[Path], plan: _sync_orphans.OrphanPlan, repo_root: Path
) -> list[str]:
    """Drift lines for every orphan ``playbook sync`` would delete, each once, sorted.

    Those are the sentinel-tagged files ``cleanup_stale`` removes and the
    lockfile orphans the leftover policy deletes (pristine, untracked, in a
    declared location) — notably a removed skill's ``SKILL.md`` and copied
    scripts. Leftovers the policy keeps (edited, tracked, an adapter missing)
    stay owned by design and are not drift, so the hint is always true.
    """
    removable = [*stale, *_sync_orphans.entry_paths(plan.delete, repo_root)]
    return _sync_output.orphan_drift(removable, repo_root)


def _report_drift(drift: Sequence[str]) -> int:
    """Print the drift lines (or the all-clear) and return the exit code."""
    if not drift:
        print("No drift detected.")
        return 0
    print("Drift detected:")
    for entry in drift:
        print(entry)
    return 1


def _block_drift(
    ctx: SyncContext, real_written: list[Path], plan: _sync_orphans.OrphanPlan
) -> list[str]:
    """``--check``: the managed block vs. what write mode would write (incl. kept orphans)."""
    owned = [*real_written, *_sync_orphans.entry_paths(plan.keep, ctx.repo_root)]
    return _sync_output.gitignore_drift(ctx.repo_root, _ignore_entries(ctx, owned))


def _ignore_entries(ctx: SyncContext, owned: Sequence[Path]) -> list[str]:
    """The managed-block entries for ``owned``, minus the adapters' shared outputs."""
    shared = _sync_output.shared_outputs(ctx.adapters)
    return ignore_entries(_sync_output.without_shared(owned, ctx.repo_root, shared), ctx.repo_root)


def _run_check_staged(ctx: SyncContext, git: GitClient) -> int:
    """``playbook sync --check-staged``: fail when generated output is staged.

    Exit 0 outside a git repo or with nothing staged (fast path: no render).
    Exit 1 on a prompt that still calls ``rule()``. Otherwise render into a
    scratch dir and exit 1 listing every staged path covered by an entry for
    this render's output *or* any earlier output still on disk (every orphan
    in the previous lockfile, pristine or not).
    """
    staged = git.staged_paths(ctx.repo_root)
    if not staged:
        return 0
    # Rendering a leftover rule() call (D15) raises a bare UndefinedError; refuse it
    # with the section 7.5 message, as the validate gate does for the other modes.
    if not _passes_validation(ctx, lambda c: check_prompt_rule_calls(c.prompts_resolved)):
        return 1
    previous = _previous_lockfile(ctx)
    with _rendered_scratch(ctx, previous) as (scratch, written):
        real_written = _on_real_tree(written, scratch, ctx.repo_root)
    orphans = _sync_orphans.find_orphans(previous, real_written, ctx.repo_root)
    owned = [*real_written, *_sync_orphans.entry_paths(orphans, ctx.repo_root)]
    offenders = _sync_output.staged_generated_paths(staged, _ignore_entries(ctx, owned))
    if not offenders:
        return 0
    _sync_output.report_staged_output(offenders, ctx.repo_root)
    return 1
