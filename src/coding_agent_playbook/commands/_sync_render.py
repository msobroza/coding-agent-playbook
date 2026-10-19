"""Jinja rendering of the canonical artifacts for ``playbook sync`` / ``render`` (SPEC §9.4).

Every template a sync executes runs here, **before any adapter writes**: rule
bodies, prompt bodies, every rule a prompt lists in ``includes_rules``
(pre-rendered — the Continue and agent_harness adapters repeat that render for
their ``## Reference rules`` appendix inside ``write_prompt``, after earlier
files are on disk), and the advisory body of every on hook (resolved
by ``_sync_hooks``, specs/prK-lifecycle-hooks.md §C.1.3). So a template the Jinja
sandbox rejects aborts the sync with nothing written and the offending file
named (:class:`~coding_agent_playbook.renderer.TemplateSecurityError`,
specs/prK-lifecycle-hooks.md §P1).

Skills are composed here too (``skills.membership.compose_skills``, ADR 0001): a
skill with a ``playbook:`` block gets its active member rules, rendered by the
same pass as every other rule, and is dropped when none of them passes
``applies_if``; any other skill passes through unchanged. Each composed skill's
description is composed here once as well, so one that cannot fit 300 characters
aborts the sync with nothing written (:class:`SkillDescriptionOverflowError`).
The ``playbook-guardrails`` skill is split off and composed from the on hooks'
guardrail text (``hook_policy.guardrails_skill``, D6), for the adapters that
write it.
"""

from __future__ import annotations

import dataclasses
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook import __version__ as _engine_version
from coding_agent_playbook.artifacts.identity import template_source
from coding_agent_playbook.commands._sync_hooks import SyncHooks, resolve_sync_hooks
from coding_agent_playbook.detector.predicate import filter_applies_if
from coding_agent_playbook.hook_policy.guardrails_skill import (
    compose_guardrails_skill,
    split_guardrails_skill,
)
from coding_agent_playbook.renderer import (
    TemplateSecurityError,
    build_environment,
    render_sandboxed,
)
from coding_agent_playbook.rule_registry import build_prompt_environment
from coding_agent_playbook.skills.document import DescriptionOverflowError, emitted_frontmatter
from coding_agent_playbook.skills.membership import compose_skills, undelivered_member_warning
from coding_agent_playbook.skills.naming import skill_id_of

if TYPE_CHECKING:
    from collections.abc import Sequence

    from jinja2 import Environment

    from coding_agent_playbook.artifacts.hook import Hook
    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill
    from coding_agent_playbook.hook_policy import ResolvedHook
    from coding_agent_playbook.rule_registry import RuleRegistryImpl
    from coding_agent_playbook.validation.context import SyncContext


@dataclass(frozen=True)
class RenderedArtifacts:
    """The applicable artifacts with their bodies rendered, ready for the adapters.

    ``registry`` resolves ``includes_rules`` for the adapters: the skill
    reference of each rule for Claude Code and OpenCode commands, its text for
    the Continue and agent_harness appendix (already rendered once per included
    rule, so the adapters' repeat cannot fail).
    ``hooks`` holds the ``[hooks]`` policy and the on hooks, bodies rendered.
    ``skills`` are composed: each carries its active member rules as
    ``member_references``, while ``rules`` still holds every active rule.
    ``guardrails_skill`` is the ``playbook-guardrails`` skill composed from the
    on hooks (``None`` without one), kept out of ``skills`` so only the adapters
    that write it receive it (D6).

    Example::

        rendered = render_artifacts(ctx)
        adapters = discover_adapters(ctx.config, rule_registry=rendered.registry)
    """

    rules: list[Rule]
    prompts: list[Prompt]
    skills: list[Skill]
    registry: RuleRegistryImpl
    hooks: SyncHooks = field(default_factory=SyncHooks)
    guardrails_skill: Skill | None = None


class SkillDescriptionOverflowError(ValueError):
    """A composed skill whose description cannot fit 300 chars even with one Covers name.

    Raised by :func:`render_artifacts` before any adapter writes. ``subject``
    names the skill as ``playbook validate`` does (``skills/<id> (<package>)``);
    ``overflow`` is the :class:`DescriptionOverflowError` with the text and its
    length. Validate's V11 refuses such a skill in write and ``--check`` mode;
    ``--check-staged`` skips validate, so there only this check stops it.

    Example::

        except SkillDescriptionOverflowError as exc:
            print(exc.subject, exc.overflow.length)
    """

    def __init__(self, subject: str, overflow: DescriptionOverflowError) -> None:
        self.subject = subject
        self.overflow = overflow
        super().__init__(f"{subject}: {overflow}")


def build_jinja_context(ctx: SyncContext) -> dict[str, object]:
    """Per SPEC §9.4: facts + project metadata + engine metadata.

    Helpers (``has_framework``, ``has_ml_dep``) are registered on the env globals
    by :func:`build_environment`; the context dict carries only data fields.
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
    callers re-render from ``template_body`` again (e.g. for a prompt's
    ``## Reference rules`` appendix). A sandbox violation
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

    Renders ``template_body`` through ``env``, the sandboxed base environment:
    ``rule()`` is undefined there, so a body cannot include a rule (H19). Only
    the body renders; frontmatter, handler commands and scripts never do (L7).
    A sandbox violation raises :class:`TemplateSecurityError` naming the hook's
    file (its id without one).

    Example::

        hook = resolved.with_rendered_body(render_hook_body(resolved.definition, ctx, env))
    """
    if not hook.is_templated:
        return hook.body
    source = str(hook.source_path) if hook.source_path is not None else hook.frontmatter.id
    return render_sandboxed(hook.template_body, dict(context), env=env, source=source)


def render_artifacts(ctx: SyncContext) -> RenderedArtifacts:
    """Filter by ``applies_if``, run every template a sync needs and compose skills; write nothing.

    Inputs (``applies_if`` file checks included) are read from the real repo
    through ``ctx``. Raises :class:`TemplateSecurityError` (or, for a malformed
    ``[hooks]`` table, ``_sync_hooks.HookPolicyError``, and for a composed
    description over 300 chars, :class:`SkillDescriptionOverflowError`) before
    any adapter has written a file. Skills come from
    ``skills.membership.compose_skills``; when member rules are active but no
    enabled adapter delivers them, one ``warning:`` line goes to stderr (E12:
    there is no fallback).

    Example::

        rendered = render_artifacts(SyncContext.from_repo(repo))
    """
    rules = filter_applies_if(ctx.rules_resolved, ctx.facts, ctx.repo_root)
    prompts = filter_applies_if(ctx.prompts_resolved, ctx.facts, ctx.repo_root)
    base_env = build_environment([])
    base_env.globals["_facts"] = dict(ctx.facts)
    base_context = build_jinja_context(ctx)
    # Render rule bodies first (their template_body may also be re-rendered
    # by the registry when a prompt asks to inline them).
    rendered_rules = [render_rule_body(rule, base_context, base_env) for rule in rules]
    registry, prompt_env = build_prompt_environment(rendered_rules, ctx.facts)
    rendered_prompts = [render_prompt_body(p, base_context, prompt_env) for p in prompts]
    _prerender_inclusions(rendered_prompts, registry)
    hooks = resolve_sync_hooks(ctx, lambda hook: _with_body(hook, base_context, base_env))
    composed = compose_skills(ctx.skills_resolved, ctx.rules_resolved, rendered_rules)
    skills, authored_guardrails = split_guardrails_skill(composed)
    _check_composed_descriptions(skills)
    _warn_undelivered_members(ctx, skills)
    return RenderedArtifacts(
        rules=rendered_rules,
        prompts=rendered_prompts,
        skills=skills,
        registry=registry,
        hooks=hooks,
        guardrails_skill=compose_guardrails_skill(authored_guardrails, hooks.resolved),
    )


def _check_composed_descriptions(skills: Sequence[Skill]) -> None:
    """Compose the description of every skill with members now, before any write.

    The writers compose it again inside ``write_skill``; that is deterministic,
    so it cannot raise once this pass has not. Without this pass an overflow
    escaped mid-dispatch, after earlier adapters had written and with no
    lockfile saved.
    """
    for skill in skills:
        if skill.member_references:
            _compose_description_of(skill)


def _compose_description_of(skill: Skill) -> None:
    """Compose ``skill``'s emitted frontmatter; wrap an overflow with the skill's name."""
    try:
        emitted_frontmatter(skill)
    except DescriptionOverflowError as exc:
        subject = f"skills/{skill_id_of(skill)} ({skill.source_package})"
        raise SkillDescriptionOverflowError(subject, exc) from exc


def _warn_undelivered_members(ctx: SyncContext, skills: list[Skill]) -> None:
    """Print the undelivered-member warning when no enabled adapter delivers member rules.

    ``ctx.adapters`` is populated by ``SyncContext.from_config``; the sync
    re-discovers the same adapters with a rule registry afterwards, and
    ``delivers_member_rules`` is a class attribute, so either set answers alike.
    """
    warning = undelivered_member_warning(ctx.adapters.values(), skills)
    if warning is not None:
        print(warning, file=sys.stderr)


def _with_body(hook: ResolvedHook, context: dict[str, object], env: Environment) -> ResolvedHook:
    """``hook`` with its ``HOOK.md.j2`` body rendered (a hook built in memory has none)."""
    if hook.definition is None:
        return hook
    return hook.with_rendered_body(render_hook_body(hook.definition, context, env))


def _prerender_inclusions(prompts: list[Prompt], registry: RuleRegistryImpl) -> None:
    """Run each ``includes_rules`` appendix render once, now, before any write.

    The Continue and agent_harness adapters render the appendix inside
    ``write_prompt`` with the very same call (``render_for_inclusion(rule_id,
    {})``) — after AGENTS.md and earlier commands are on disk. Running it here
    first makes a sandbox violation in an included rule abort the sync with
    nothing written. Every prompt with ``includes_rules`` gets the appendix
    there, each id once (D15).
    """
    for prompt in prompts:
        for rule_id in dict.fromkeys(prompt.frontmatter.includes_rules):
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


def report_description_overflow(exc: SkillDescriptionOverflowError, *, outcome: str) -> int:
    """Print ``error: skills/<id> (<package>): <detail>`` and ``error: <outcome>``; return 1.

    Both lines go to stderr; the detail carries the shortest text and its length.

    Example::

        return report_description_overflow(exc, outcome="playbook sync aborted.")
    """
    print(f"error: {exc}", file=sys.stderr)
    print(f"error: {outcome}", file=sys.stderr)
    return 1


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
