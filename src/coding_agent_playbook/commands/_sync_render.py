"""Jinja rendering of the canonical artifacts for ``playbook sync`` / ``render`` (SPEC §9.4).

Every template a sync executes runs here, **before any adapter writes**: rule
bodies, prompt bodies, and every rule a prompt inlines through
``includes_rules`` (pre-rendered — adapters repeat that render inside
``write_prompt``, after earlier files are on disk). So a template the Jinja
sandbox rejects aborts the sync with nothing written and the offending file
named (:class:`~coding_agent_playbook.renderer.TemplateSecurityError`,
specs/prK-lifecycle-hooks.md §P1).
"""

from __future__ import annotations

import dataclasses
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook import __version__ as _engine_version
from coding_agent_playbook.detector import evaluate_predicate
from coding_agent_playbook.orchestrator import RuleRegistryImpl, template_source
from coding_agent_playbook.renderer import (
    TemplateSecurityError,
    appendix_rule_ids,
    build_environment,
    render_sandboxed,
)

if TYPE_CHECKING:
    from jinja2 import Environment

    from coding_agent_playbook.detector import Facts
    from coding_agent_playbook.orchestrator import SyncContext
    from coding_agent_playbook.types import Hook, Prompt, Rule, Skill


@dataclass(frozen=True)
class RenderedArtifacts:
    """The applicable artifacts with their bodies rendered, ready for the adapters.

    ``registry`` resolves ``includes_rules`` for the adapters (already
    exercised once per included rule, so the adapters' repeat cannot fail).

    Example::

        rendered = render_artifacts(ctx)
        adapters = discover_adapters(ctx.config, rule_registry=rendered.registry)
    """

    rules: list[Rule]
    prompts: list[Prompt]
    skills: list[Skill]
    registry: RuleRegistryImpl


def build_jinja_context(ctx: SyncContext) -> dict[str, object]:
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


def render_rule_body(rule: Rule, context: dict[str, object], env: Environment) -> Rule:
    """Re-emit a Rule with ``body`` set to the Jinja-rendered output.

    Non-templated rules pass through verbatim. The template/body split lets
    callers re-render from ``template_body`` again (e.g. for inline
    inclusion from a prompt with a different context). A sandbox violation
    raises :class:`TemplateSecurityError` naming the rule's source file.
    """
    if not rule.is_templated:
        return rule
    rendered = render_sandboxed(
        rule.template_body, dict(context), env=env, source=template_source(rule)
    )
    return dataclasses.replace(rule, body=rendered)


def render_prompt_body(prompt: Prompt, context: dict[str, object], env: Environment) -> Prompt:
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
    rendered = render_sandboxed(
        prompt.template_body, safe_context, env=env, source=template_source(prompt)
    )
    return dataclasses.replace(prompt, body=rendered)


def render_hook_body(hook: Hook, context: dict[str, object], env: Environment) -> str:
    """The advisory body of ``hook``: ``HOOK.md`` verbatim, ``HOOK.md.j2`` rendered (§C.1.3).

    Renders ``template_body`` through ``env``, the sandboxed *base* environment
    (``is_prompt_context=False``): ``rule()`` is undefined there, so a body
    cannot include a rule (H19). Only the body renders; frontmatter, handler
    commands and scripts never do (L7). A sandbox violation raises
    :class:`TemplateSecurityError` naming the hook's file (its id without one).

    Example::

        hook = resolved.with_rendered_body(render_hook_body(resolved.definition, ctx, env))
    """
    if not hook.is_templated:
        return hook.body
    source = str(hook.source_path) if hook.source_path is not None else hook.frontmatter.id
    return render_sandboxed(hook.template_body, dict(context), env=env, source=source)


def filter_applies_if[T: "Rule | Prompt"](
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


def filter_skills(skills: list[Skill]) -> list[Skill]:
    """Skills are unconditional in v1 (no ``applies_if`` in the SKILL.md
    schema). Returned unchanged; kept as a hook for v2 to filter on a
    ``conditions:`` extension without churning the call site."""
    return list(skills)


def render_artifacts(ctx: SyncContext) -> RenderedArtifacts:
    """Filter by ``applies_if`` and run every template a sync needs; write nothing.

    Inputs (``applies_if`` file checks included) are read from the real repo
    through ``ctx``. Raises :class:`TemplateSecurityError` before any adapter
    has written a file.

    Example::

        rendered = render_artifacts(SyncContext.from_repo(repo))
    """
    rules = filter_applies_if(ctx.rules_resolved, ctx.facts, ctx.repo_root)
    prompts = filter_applies_if(ctx.prompts_resolved, ctx.facts, ctx.repo_root)
    base_env = build_environment([], is_prompt_context=False)
    base_env.globals["_facts"] = dict(ctx.facts)
    base_context = build_jinja_context(ctx)
    # Render rule bodies first (their template_body may also be re-rendered
    # by the registry when a prompt asks to inline them).
    rendered_rules = [render_rule_body(rule, base_context, base_env) for rule in rules]
    registry = RuleRegistryImpl(rendered_rules, ctx.facts, base_env)
    prompt_env = build_environment([], is_prompt_context=True, rule_registry=registry)
    prompt_env.globals["_facts"] = dict(ctx.facts)
    rendered_prompts = [render_prompt_body(p, base_context, prompt_env) for p in prompts]
    _prerender_inclusions(rendered_prompts, registry)
    return RenderedArtifacts(
        rules=rendered_rules,
        prompts=rendered_prompts,
        skills=filter_skills(ctx.skills_resolved),
        registry=registry,
    )


def _prerender_inclusions(prompts: list[Prompt], registry: RuleRegistryImpl) -> None:
    """Run each ``includes_rules`` appendix render once, now, before any write.

    The adapters render the appendix inside ``write_prompt`` with the very
    same call (``render_for_inclusion(rule_id, {})``) — after AGENTS.md and
    earlier commands are on disk. Running it here first makes a sandbox
    violation in an included rule abort the sync with nothing written.
    """
    for prompt in prompts:
        for rule_id in appendix_rule_ids(prompt.frontmatter.includes_rules, prompt.body):
            registry.render_for_inclusion(rule_id, {})


def report_sandbox_violation(exc: TemplateSecurityError, repo_root: Path, *, outcome: str) -> int:
    """Print ``exc`` to stderr, naming its file relative to ``repo_root``; return 1.

    ``outcome`` is the second error line (e.g. ``"playbook sync aborted; no
    files were written."``). Inputs are read in place, so the source path is
    always a real-tree path and never a scratch directory.

    Example::

        return report_sandbox_violation(exc, ctx.repo_root, outcome="playbook render aborted.")
    """
    detail = f"template rejected by the Jinja sandbox: {exc.detail}"
    return report_template_error(exc.source, detail, repo_root, outcome=outcome)


def report_template_error(source: str, detail: str, repo_root: Path, *, outcome: str) -> int:
    """Print ``error: <source>: <detail>`` and ``error: <outcome>`` to stderr; return 1.

    An absolute ``source`` is shown relative to ``repo_root``; anything else
    (an artifact id) is shown as given.

    Example::

        return report_template_error(str(hook.source_path), "'rule' is undefined", repo_root,
                                     outcome="playbook render aborted.")
    """
    path = Path(source)
    shown = _repo_relative(path, repo_root) if path.is_absolute() else source
    print(f"error: {shown}: {detail}", file=sys.stderr)
    print(f"error: {outcome}", file=sys.stderr)
    return 1


def _repo_relative(path: Path, repo_root: Path) -> str:
    """POSIX ``path`` relative to ``repo_root`` (both resolved); unchanged if outside."""
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
