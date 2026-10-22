"""One render pass: a sandboxed environment, a rule registry and the Jinja context.

``playbook sync`` (``sync.render``), ``playbook render`` (``commands.render``) and
the eval runner (``evals.prompting``) each open one :class:`RenderSession` per
pass, so the three cannot diverge: the session filters the rules by
``applies_if`` once, and its registry holds only the rules it kept
(specs/prT-package-layout.md section 9 AC.3). A template the sandbox rejects
raises ``rendering.jinja.TemplateSecurityError`` naming its file (prK §P1).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import coding_agent_playbook as _engine
from coding_agent_playbook.artifacts.identity import template_source
from coding_agent_playbook.config.layout import resolve_layout
from coding_agent_playbook.detector.predicate import filter_applies_if
from coding_agent_playbook.rendering.jinja import build_environment, render_sandboxed
from coding_agent_playbook.rendering.prompt_rule_delivery import includes_rules_appendix
from coding_agent_playbook.rendering.rule_registry import RuleRegistryImpl
from coding_agent_playbook.skills.capabilities import framework_role_map
from coding_agent_playbook.skills.membership import active_skill_ids

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from jinja2 import Environment

    from coding_agent_playbook.artifacts.hook import Hook
    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill
    from coding_agent_playbook.config.model import Config
    from coding_agent_playbook.detector.facts import Facts
    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook

#: What :meth:`RenderSession.open` does with an ``applies_if`` validate would reject.
type MalformedPredicate = Literal["raise", "omit"]


@dataclass(frozen=True, slots=True, kw_only=True)
class TemplateContext:
    """The Jinja context every artifact body renders with (SPEC §9.4).

    Example::

        TemplateContext.for_config(ctx.config, ctx.facts).as_dict()["project_name"]
    """

    facts: Facts
    project_name: str
    project_description: str = ""
    engine_version: str
    user_choices: Mapping[str, object] = field(default_factory=dict)
    overrides: Mapping[str, object] = field(default_factory=dict)
    # The resolved document layout (D71): every key, its configured path or D60 default.
    layout: Mapping[str, str] = field(default_factory=lambda: resolve_layout({}))

    @classmethod
    def for_config(cls, config: Config, facts: Facts) -> TemplateContext:
        """Sync and ``playbook render``: ``[project]``, ``user_choices``, the pinned or installed version.

        Example: ``for_config(config, facts).engine_version`` -> the ``[engine] version`` pin, else the installed version.
        """
        return cls(
            facts=facts,
            project_name=config.project.name,
            project_description=config.project.description,
            # Read only when the config pins none: the installed version costs an
            # importlib.metadata lookup (the root package resolves it lazily).
            engine_version=config.engine_version or _engine.__version__,
            user_choices=config.user_choices,
            layout=resolve_layout(config.layout),
        )

    def as_dict(self) -> dict[str, object]:
        """facts, then project, then user_choices, then engine_version and layout, then overrides.

        Later wins, so a fact or a user choice cannot shadow ``layout`` (D71).

        Example: ``TemplateContext(facts={}, project_name="demo", engine_version="1").as_dict()``.
        """
        return {
            **self.facts,
            "project_name": self.project_name,
            "project_description": self.project_description,
            **self.user_choices,
            "engine_version": self.engine_version,
            "layout": dict(self.layout),
            **self.overrides,
        }


class RenderSession:
    """One sandboxed environment and one applies_if-filtered rule registry per render pass.

    Example::

        session = RenderSession.open(ctx.rules_resolved,
                                     TemplateContext.for_config(ctx.config, ctx.facts),
                                     repo_root=ctx.repo_root)
        rules = session.render_rules()
    """

    def __init__(self, rules: list[Rule], context: TemplateContext, env: Environment) -> None:
        """Hold what :meth:`open` built; call :meth:`open` instead."""
        self._rules = rules
        self._context = context.as_dict()
        self._env = env
        # RS-D8: an included rule renders with the facts only, never the full context.
        self._registry = RuleRegistryImpl(rules, context.facts, env)

    @classmethod
    def open(
        cls,
        rules: Sequence[Rule],
        context: TemplateContext,
        *,
        repo_root: Path,
        on_malformed_predicate: MalformedPredicate = "raise",
        skills: Sequence[Skill] = (),
        framework: str | None = None,
    ) -> RenderSession:
        """Filter ``rules`` by ``applies_if`` once; build the environment and the registry from them.

        ``repo_root`` anchors ``has_file``. A predicate ``playbook validate`` would
        reject raises ``ValueError``, unless ``on_malformed_predicate="omit"``:
        ``playbook render`` runs no validate gate, so it drops that rule instead.
        ``skills`` (the merged skills) and ``framework`` (the enabled framework's
        layer) feed ``framework_skill(role)``, ``skill_active(name)`` (D74) and
        ``rule_active(rule_id)`` (prU D73); without them every role is ``""`` and
        no skill, nor any rule a skill owns, is active, which is what
        eval-sample prompts see (``evals.prompting._sample_session``).

        Example: ``RenderSession.open([], context, repo_root=repo).render_rule(rule)``.
        """
        kept = _applicable(rules, context.facts, repo_root, on_malformed_predicate)
        env = build_environment([])
        # SPEC §9.4: has_framework and has_ml_dep read the facts from the globals.
        env.globals["_facts"] = dict(context.facts)
        env.globals["_framework_roles"] = framework_role_map(skills, framework)
        active_skills = active_skill_ids(skills, rules, kept)
        env.globals["_active_skills"] = active_skills
        env.globals["_active_rules"] = _reachable_rule_ids(kept, active_skills)
        return cls(kept, context, env)

    @property
    def registry(self) -> RuleRegistryImpl:
        """The applicable rules only; a ``RuleRegistry`` and a ``SkillReferenceIndex`` (#54).

        Example: ``discover_adapters(config, rule_registry=session.registry)``.
        """
        return self._registry

    def render_rules(self) -> list[Rule]:
        """Every applicable rule with its body rendered, in input order (sync, skill references).

        Example: ``[rule.body for rule in session.render_rules()]``.
        """
        return [self.render_rule(rule) for rule in self._rules]

    def render_rule(self, rule: Rule) -> Rule:
        """``rule`` rendered whatever its ``applies_if`` (``playbook render <rule-id>``).

        Example: ``session.render_rule(rule).body`` -> ``"Project demo ..."``.
        """
        if not rule.is_templated:
            return rule
        body = self._render(rule.template_body, self._context, template_source(rule))
        return dataclasses.replace(rule, body=body)

    def render_prompt(self, prompt: Prompt) -> Prompt:
        """The body rendered with ``input_variables`` names masked, for an adapter's format.

        Example: ``render_for(path, session.render_prompt(prompt).body, "prompt_continue", ...)``.
        """
        if not prompt.is_templated:
            return prompt
        context = _without_input_variables(self._context, prompt)
        body = self._render(prompt.template_body, context, template_source(prompt))
        return dataclasses.replace(prompt, body=body)

    def check_inclusions(self, prompts: Sequence[Prompt]) -> None:
        """Render each included rule once now, so a sandbox violation raises before any write.

        The Continue and agent_harness adapters repeat this very render inside
        ``write_prompt``, after earlier files are on disk; each id once (D15).

        Example: ``session.check_inclusions(rendered_prompts)``.
        """
        for prompt in prompts:
            for rule_id in dict.fromkeys(prompt.frontmatter.includes_rules):
                self._registry.render_for_inclusion(rule_id, {})

    def render_hook_body(self, hook: Hook) -> str:
        """``HOOK.md`` verbatim, or ``HOOK.md.j2`` rendered; ``rule()`` is undefined (H19).

        Only the body renders; frontmatter, handler commands and scripts never do
        (L7). A violation names the hook's file, or its id without one.

        Example: ``session.render_hook_body(hook)`` -> ``"Guard demo.\\n"``.
        """
        if not hook.is_templated:
            return hook.body
        source = str(hook.source_path) if hook.source_path is not None else hook.frontmatter.id
        return self._render(hook.template_body, self._context, source)

    def with_hook_body(self, hook: ResolvedHook) -> ResolvedHook:
        """``hook`` with its rendered body; a hook built in memory passes through.

        Example: ``resolve_sync_hooks(ctx, session.with_hook_body)``.
        """
        if hook.definition is None:
            return hook
        return hook.with_rendered_body(self.render_hook_body(hook.definition))

    def prompt_text(self, prompt: Prompt) -> str:
        """The eval runner's text: the body with the full context, plus the Reference rules section.

        Unlike :meth:`render_prompt` nothing is masked: the invocation's input
        variables are in the context (``TemplateContext.overrides``). The text is
        what Continue gets (D22): the eval scratch repo has no skill to point at.

        Example: ``session.prompt_text(prompt)`` -> ``"Review src/x.py.\\n\\n## Reference rules…"``.
        """
        body = prompt.template_body
        if prompt.is_templated:
            body = self._render(body, self._context, template_source(prompt))
        return body + includes_rules_appendix(prompt.frontmatter.includes_rules, self._registry)

    def _render(self, template: str, context: dict[str, object], source: str) -> str:
        """``template`` through the session's sandbox; a violation names ``source``."""
        return render_sandboxed(template, context, env=self._env, source=source)


def _applicable(
    rules: Sequence[Rule], facts: Facts, repo_root: Path, on_malformed: MalformedPredicate
) -> list[Rule]:
    """``rules`` that pass ``filter_applies_if``, in order; see :meth:`RenderSession.open`."""
    if on_malformed == "raise":
        return filter_applies_if(list(rules), facts, repo_root)
    # One rule at a time, so a malformed predicate drops its own rule only.
    return [rule for rule in rules if _passes_unless_malformed(rule, facts, repo_root)]


def _reachable_rule_ids(kept: Sequence[Rule], active_skills: frozenset[str]) -> frozenset[str]:
    """Ids ``rule_active`` reports: a kept rule with no skill, or whose skill renders (prU D73).

    A pointer to a rule whose skill is dropped would send the reader nowhere.
    """
    return frozenset(
        rule.frontmatter.id
        for rule in kept
        if rule.frontmatter.skill is None or rule.frontmatter.skill in active_skills
    )


def _passes_unless_malformed(rule: Rule, facts: Facts, repo_root: Path) -> bool:
    """Whether ``rule`` passes ``filter_applies_if``; ``False`` where its predicate raises."""
    try:
        return bool(filter_applies_if([rule], facts, repo_root))
    except ValueError:
        return False


def _without_input_variables(context: dict[str, object], prompt: Prompt) -> dict[str, object]:
    """``context`` minus the names of ``prompt``'s ``input_variables``.

    The OpenCode format maps each ``{{ <name> }}`` left in the rendered body to
    ``$ARGUMENTS`` (SPEC §9.7), so a fact or choice of the same name must not
    expand it first.
    """
    names = {
        name
        for var in prompt.frontmatter.input_variables or []
        if isinstance(var, dict) and (name := var.get("name"))
    }
    return {key: value for key, value in context.items() if key not in names}
