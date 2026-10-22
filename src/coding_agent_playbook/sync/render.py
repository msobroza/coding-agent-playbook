"""The render step of ``playbook sync`` (SPEC §9.4): one render session, then skills.

Every template a sync executes runs here, through one
:class:`~coding_agent_playbook.rendering.session.RenderSession`, **before any
adapter writes**: rule bodies, prompt bodies, every rule a prompt lists in
``includes_rules`` (pre-rendered — the Continue and agent_harness adapters
repeat that render for their ``## Reference rules`` appendix inside
``write_prompt``, after earlier files are on disk), and the advisory body of
every on hook (resolved by ``_hook_outputs``, specs/prK-lifecycle-hooks.md
§C.1.3). So a template the Jinja sandbox rejects aborts the sync with nothing
written and the offending file named
(:class:`~coding_agent_playbook.rendering.jinja.TemplateSecurityError`,
specs/prK-lifecycle-hooks.md §P1).

Skills are composed here too (``skills.membership.compose_skills``, ADR 0001): a
skill with a ``playbook:`` block gets its active member rules, rendered by the
same pass as every other rule, and is dropped when none of them passes
``applies_if``; any other skill passes through unchanged. Each composed skill's
description is composed here once as well, so one that cannot fit 300 characters
aborts the sync with nothing written (:class:`SkillDescriptionOverflowError`).
The ``playbook-guardrails`` skill is split off and composed from the on hooks'
guardrail text (``hooks.guardrails_skill``, D6), for the adapters that
write it.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.config.framework import enabled_framework
from coding_agent_playbook.detector.predicate import filter_applies_if
from coding_agent_playbook.hooks.guardrails_skill import (
    compose_guardrails_skill,
    split_guardrails_skill,
)
from coding_agent_playbook.rendering.session import RenderSession, TemplateContext
from coding_agent_playbook.skills.document import DescriptionOverflowError, emitted_frontmatter
from coding_agent_playbook.skills.membership import compose_skills, undelivered_member_warning
from coding_agent_playbook.skills.naming import skill_id_of
from coding_agent_playbook.skills.sections import section_impacts
from coding_agent_playbook.sync._hook_outputs import SyncHooks, resolve_sync_hooks

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill
    from coding_agent_playbook.rendering.jinja import TemplateSecurityError
    from coding_agent_playbook.rendering.rule_registry import RuleRegistryImpl
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


def render_artifacts(ctx: SyncContext) -> RenderedArtifacts:
    """Filter by ``applies_if``, run every template a sync needs and compose skills; write nothing.

    Inputs (``applies_if`` file checks included) are read from the real repo
    through ``ctx``. Raises :class:`TemplateSecurityError` (or, for a malformed
    ``[hooks]`` table, ``_hook_outputs.HookPolicyError``, and for a composed
    description over 300 chars, :class:`SkillDescriptionOverflowError`) before
    any adapter has written a file. Skills come from
    ``skills.membership.compose_skills``; when member rules are active but no
    enabled adapter delivers them, one ``warning:`` line goes to stderr (E12:
    there is no fallback).

    Example::

        rendered = render_artifacts(SyncContext.from_repo(repo))
    """
    context = TemplateContext.for_config(ctx.config, ctx.facts)
    session = RenderSession.open(
        ctx.rules_resolved,
        context,
        repo_root=ctx.repo_root,
        skills=ctx.skills_resolved,
        framework=enabled_framework(ctx.config.layers_enabled),
        impacts=section_impacts(ctx.skills_resolved, ctx.rules_resolved),
    )
    prompts = filter_applies_if(ctx.prompts_resolved, ctx.facts, ctx.repo_root)
    rendered_rules = session.render_rules()
    rendered_prompts = [session.render_prompt(prompt) for prompt in prompts]
    session.check_inclusions(rendered_prompts)
    hooks = resolve_sync_hooks(ctx, session.with_hook_body)
    composed = compose_skills(ctx.skills_resolved, ctx.rules_resolved, rendered_rules)
    skills, authored_guardrails = split_guardrails_skill(composed)
    _check_composed_descriptions(skills)
    _warn_undelivered_members(ctx, skills)
    return RenderedArtifacts(
        rules=rendered_rules,
        prompts=rendered_prompts,
        skills=skills,
        registry=session.registry,
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
