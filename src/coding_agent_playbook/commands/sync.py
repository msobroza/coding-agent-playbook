"""`cap sync` — regenerate all artifacts (SPEC §12.2 / §12.3).

Two modes:
- write (default): runs detector → renders → adapters write → stamps lockfile.
- ``--check``: re-renders in memory and compares against the on-disk files;
  exits 1 if any differ or are missing.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook import __version__ as _engine_version
from coding_agent_playbook.detector import evaluate_predicate
from coding_agent_playbook.lockfile import LockEntry, Lockfile, compute_hash
from coding_agent_playbook.orchestrator import (
    RuleRegistryImpl,
    SyncContext,
    discover_adapters,
)
from coding_agent_playbook.renderer import build_environment, render_string

if TYPE_CHECKING:
    import argparse

    from jinja2 import Environment

    from coding_agent_playbook.detector import Facts
    from coding_agent_playbook.types import Prompt, Rule, Skill


_LOCKFILE_SCHEMA = 1

# Filenames that are state-source-managed and must be excluded from the
# drift diff (otherwise the lockfile written by sync would itself look
# like drift). Keep this in sync with the constants in
# ``sources.filesystem.FileSystemStateSource``.
_STATE_FILES_TO_SKIP: tuple[str, ...] = (
    ".coding-agent-playbook.toml",
    ".coding-agent-playbook.local.toml",
    ".coding-agent-playbook.lock",
)


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


def _build_lockfile(written_paths: list[Path], repo_root: Path, engine_version: str) -> Lockfile:
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
    return Lockfile(
        schema_version=_LOCKFILE_SCHEMA,
        engine_version=engine_version,
        rendered_at=_dt.datetime.now(_dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
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


def _run_sync(ctx: SyncContext) -> tuple[list[Path], list[Path]]:
    """Internal helper: render + dispatch + cleanup. Returns ``(written,
    removed)``. Used by both write mode and ``--check`` (the latter only
    inspects ``written`` against on-disk content)."""
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
            written.extend(adapter.write_rule(rule, ctx.repo_root))
        for prompt in rendered_prompts:
            written.extend(adapter.write_prompt(prompt, ctx.repo_root))
        for skill in skills:
            written.extend(adapter.write_skill(skill, ctx.repo_root))
        written.extend(adapter.finalize(ctx.repo_root))

    resolved_written: set[Path] = {p.resolve() for p in written}
    removed: list[Path] = []
    for adapter in adapters.values():
        removed.extend(adapter.cleanup_stale(resolved_written, ctx.repo_root))
    return written, removed


def run(args: argparse.Namespace) -> int:
    """Dispatch to write mode or ``--check`` mode."""
    repo_root = _resolve_repo_root(args)
    ctx = SyncContext.from_repo(repo_root)
    if getattr(args, "check", False):
        return _run_check(ctx)
    written, removed = _run_sync(ctx)

    lockfile = _build_lockfile(written, ctx.repo_root, ctx.config.engine_version)
    ctx.state_source.save_lockfile(lockfile)

    print(f"Summary: {len(written)} files written, {len(removed)} removed")
    return 0


def _run_check(ctx: SyncContext) -> int:
    """``cap sync --check``: render in a parallel scratch tree, compare bytes
    against the consumer repo. Exits 0 (no drift) or 1 (drift detected).

    Implementation choice: we run the full sync against a temporary mirror of
    the consumer repo so adapters can write freely without mutating the real
    tree, then diff the rendered output against on-disk content. This avoids
    duplicating render logic.
    """
    import shutil
    import tempfile

    # ``_STATE_FILES_TO_SKIP`` is the module-local constant tuple of files
    # owned by the StateSource (config + lockfile) — those are never
    # written by adapters, so they must be excluded from the drift diff.
    # See the constant's docstring above for the rationale.

    scratch_dir = Path(tempfile.mkdtemp(prefix="cap-sync-check-"))
    try:
        scratch = scratch_dir / "repo"
        shutil.copytree(ctx.repo_root, scratch, symlinks=False)
        scratch_ctx = SyncContext.from_repo(scratch)
        # In --check mode we still run the full sync (including
        # ``cleanup_stale``) inside the scratch tree. That's intentional:
        # we need the cleanup pass to populate the "removed" set for
        # comparison, and since the work happens against a copy the real
        # repo is untouched.
        written, _ = _run_sync(scratch_ctx)

        drift: list[str] = []
        for path in written:
            rel = path.resolve().relative_to(scratch.resolve())
            if rel.name in _STATE_FILES_TO_SKIP:
                continue
            actual_path = ctx.repo_root / rel
            scratch_bytes = path.read_bytes()
            if not actual_path.is_file():
                drift.append(f"  {rel.as_posix()}\n    Missing on disk; run 'cap sync' to create.")
                continue
            actual_bytes = actual_path.read_bytes()
            if actual_bytes != scratch_bytes:
                drift.append(
                    f"  {rel.as_posix()}\n"
                    "    Generated content differs from on-disk content.\n"
                    "    Run 'cap sync' to regenerate."
                )

        if drift:
            print("Drift detected:")
            for entry in drift:
                print(entry)
            return 1
        print("No drift detected.")
        return 0
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)
