"""The two check modes of ``playbook sync`` (SPEC §12.3): ``--check`` and ``--check-staged``.

Both render into an empty scratch directory (:func:`_rendered_scratch`) and map
what they rendered back onto the real tree, so ignore entries and orphans are
computed exactly as in write mode; neither ever writes to the repo.
``--check`` (:func:`_run_check`) reports drift: a generated file that differs or
is missing, every orphan write mode would delete, an unreadable lockfile and,
under ``[output] commit = false``, a stale managed ``.gitignore`` block.
``--check-staged`` (:func:`_run_check_staged`) fails when a staged path is
generated output. :func:`coding_agent_playbook.sync.pipeline.execute` dispatches
to them; they reuse its render, leftover policy and validate gate.
"""

from __future__ import annotations

import contextlib
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook._symlinks import real_path
from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.adapters.skill_dirs.writer import deciding_ownership_against
from coding_agent_playbook.gitignore import ignore_entries
from coding_agent_playbook.sync import _leftovers as _sync_orphans
from coding_agent_playbook.sync import _output_policy as _sync_output
from coding_agent_playbook.sync.pipeline import (
    _UNREADABLE_LOCKFILE,
    _leftover_policy,
    _passes_validation,
    _previous_lockfile,
    _render_into,
)
from coding_agent_playbook.validation import preflight as _sync_preflight
from coding_agent_playbook.validation.prompts import check_prompt_rule_calls

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from coding_agent_playbook.lockfile.model import Lockfile
    from coding_agent_playbook.sync.git_client import GitClient
    from coding_agent_playbook.validation.context import SyncContext


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
