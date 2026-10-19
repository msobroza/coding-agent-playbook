"""`playbook render <id>` — render a single artifact to stdout for debugging
(SPEC §12.7).

Supports ``--format <fmt>`` (defaults to the artifact's natural format),
``--show-source`` (template path + overrides), and ``--show-rules`` (for
prompts, lists each ``includes_rules`` id with its applies_if outcome and its
delivery: the owning skill and reference, or always loaded). A hook id
renders ``hook_advisory`` by default, or ``hook_claude_settings``
(specs/prK-lifecycle-hooks.md §C.4.1).
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2.exceptions import UndefinedError

from coding_agent_playbook.detector.predicate import evaluate_predicate
from coding_agent_playbook.orchestrator import SyncContext, artifact_id_of, template_source
from coding_agent_playbook.renderer import (
    BUILTIN_FORMATS,
    FORMAT_ALIASES,
    TemplateSecurityError,
    build_environment,
    render_for,
)
from coding_agent_playbook.rule_registry import build_prompt_environment, skill_reference_of
from coding_agent_playbook.sync.render import (
    build_jinja_context,
    render_hook_body,
    render_prompt_body,
    render_rule_body,
    report_sandbox_violation,
    report_template_error,
)
from coding_agent_playbook.types import Hook, Prompt, Rule, Skill

if TYPE_CHECKING:
    import argparse


_RULE_FORMATS = {"continue_rule", "claude_md_section", "agents_md_section"}
_PROMPT_FORMATS = {"prompt_continue", "prompt_claude_command", "prompt_opencode_command"}
_HOOK_FORMATS = {"hook_advisory", "hook_claude_settings"}
#: Formats valid per artifact kind (skills render as prompts).
_KIND_FORMATS = {
    "rule": ("rules", _RULE_FORMATS),
    "prompt": ("prompts", _PROMPT_FORMATS),
    "skill": ("prompts", _PROMPT_FORMATS),
    "hook": ("hooks", _HOOK_FORMATS),
}

# Any of the four artifact dataclasses can come back from _find_artifact.
_Artifact = Rule | Prompt | Skill | Hook


class PromptBodyUndefinedError(Exception):
    """A prompt body named something its Jinja context lacks, such as the removed ``rule()``.

    Raised only for the prompt's own body, so ``playbook render`` names that
    file; an undefined name inside an included rule's template keeps its traceback.

    Example::

        PromptBodyUndefinedError("playbook/prompts/x.md.j2", "'rule' is undefined")
    """

    def __init__(self, source: str, detail: str) -> None:
        super().__init__(f"{source}: {detail}")
        self.source = source
        self.detail = detail


def _find_artifact(ctx: SyncContext, artifact_id: str) -> tuple[str | None, _Artifact | None]:
    """Locate an artifact by ID across rules/prompts/skills. Returns
    ``(kind, artifact)`` or ``(None, None)``.
    """
    for rule in ctx.rules_resolved:
        if rule.frontmatter.id == artifact_id:
            return "rule", rule
    for prompt in ctx.prompts_resolved:
        if prompt.frontmatter.id == artifact_id:
            return "prompt", prompt
    for skill in ctx.skills_resolved:
        skill_id = (
            skill.frontmatter.get("id", "skill") if isinstance(skill.frontmatter, dict) else None
        )
        if skill_id == artifact_id:
            return "skill", skill
    for hook in ctx.hooks_resolved:
        if hook.frontmatter.id == artifact_id:
            return "hook", hook
    return None, None


def _resolve_format(fmt: str | None, kind: str) -> str:
    """Apply :data:`FORMAT_ALIASES` and default to a sensible format."""
    if fmt is None:
        return {
            "rule": "continue_rule",
            "prompt": "prompt_continue",
            "skill": "prompt_continue",
            "hook": "hook_advisory",
        }[kind]
    return FORMAT_ALIASES.get(fmt, fmt)


def _format_error(kind: str, resolved_format: str) -> str | None:
    """Why ``resolved_format`` cannot render a ``kind`` artifact, or None when it can."""
    label, formats = _KIND_FORMATS[kind]
    if resolved_format in formats:
        return None
    return (
        f"format {resolved_format!r} not valid for {label}; "
        f"use one of: {', '.join(sorted(formats))}"
    )


def _show_source(artifact: _Artifact, kind: str, ctx: SyncContext) -> str:
    """Print provenance per SPEC §12.7: template path, format flavour,
    overlay losers (if any), enabled adapters, and the evaluated
    ``applies_if`` outcome against the current facts.
    """
    lines: list[str] = []
    template_path = getattr(artifact, "source_path", None)
    if template_path is None:
        # In-memory artifact (no on-disk source). Fall back to the source
        # package name with an explicit marker so the line still tells the
        # user *where* it conceptually came from.
        source_package = getattr(artifact, "source_package", "<unknown>")
        lines.append(f"Template:  {source_package}/(in-memory)")
    else:
        lines.append(f"Template:  {template_path}")
    is_templated = getattr(artifact, "is_templated", False)
    lines.append(f"Format:    {'.md.j2 (Jinja-templated)' if is_templated else '.md (verbatim)'}")
    relevant = [
        c
        for c in ctx.overlay_collisions
        if c.kind == kind and c.artifact_id == artifact_id_of(artifact)
    ]
    if relevant:
        losers = ", ".join(relevant[0].losers)
        lines.append(f"Overrides: {losers}")
    adapters = sorted(ctx.adapters.keys())
    lines.append(f"Adapters:  {', '.join(adapters)}")
    # Final line: SPEC §12.7 surfaces the predicate outcome under the
    # current facts so the user can see at a glance whether `playbook sync`
    # would emit this artifact.
    frontmatter = artifact.frontmatter
    predicate: dict[str, object] = {}
    if hasattr(frontmatter, "applies_if"):
        predicate = dict(frontmatter.applies_if or {})
    elif isinstance(frontmatter, dict):
        raw = frontmatter.get("applies_if") or {}
        if isinstance(raw, dict):
            predicate = dict(raw)
    if predicate:
        try:
            evaluated = evaluate_predicate(predicate, ctx.facts, repo_root=ctx.repo_root)
        except ValueError:
            evaluated = False
    else:
        evaluated = True
    lines.append(f"applies_if evaluated: {evaluated}")
    return "\n".join(lines)


def _rule_applies(rule: Rule, ctx: SyncContext) -> bool:
    """Whether ``rule``'s ``applies_if`` holds for the repo; a malformed predicate does not.

    The one predicate rule of ``playbook render``: an empty predicate holds, and
    ``evaluate_predicate``'s ``ValueError`` (a predicate validate would reject) reads as
    false, as ``--show-rules`` has always printed it. ``detector.predicate.filter_applies_if``
    is not reused because it raises there, and render has no validate gate to run first.

    Example: ``_rule_applies(rule, SyncContext.from_repo(repo))`` -> ``False`` without fastapi.
    """
    predicate = rule.frontmatter.applies_if or {}
    if not predicate:
        return True
    try:
        return evaluate_predicate(predicate, ctx.facts, repo_root=ctx.repo_root)
    except ValueError:
        return False


def _show_rules(prompt: Prompt, ctx: SyncContext) -> str:
    """The ``--show-rules`` listing: each included id with its gate and its delivery (D15).

    Example line: ``  - pytest  (coding_agent_playbook, applies_if=True -> skill
    python-testing, references/pytest.md)``.
    """
    rule_index = {rule.frontmatter.id: rule for rule in ctx.rules_resolved}
    lines = [f"Prompt:    {prompt.frontmatter.id}", "includes_rules:"]
    if not prompt.frontmatter.includes_rules:
        lines.append("  (none)")
        return "\n".join(lines)
    for rule_id in prompt.frontmatter.includes_rules:
        rule = rule_index.get(rule_id)
        if rule is None:
            lines.append(f"  - {rule_id}  (UNKNOWN)")
            continue
        applies = _rule_applies(rule, ctx)
        marker = _delivery(rule) if applies else "OMITTED"
        lines.append(f"  - {rule_id}  ({rule.source_package}, applies_if={applies} -> {marker})")
    return "\n".join(lines)


def _delivery(rule: Rule) -> str:
    """Where an applicable included rule reaches a Claude Code or OpenCode command.

    Its skill reference, ``always loaded`` for an always rule, or ``no skill`` for
    a scoped rule that names none (``playbook validate`` rejects one, V1).
    """
    reference = skill_reference_of(rule)
    if reference is not None:
        return f"skill {reference.skill_id}, {reference.path}"
    return "always loaded" if rule.frontmatter.scope == "always" else "no skill"


def _render_rule(ctx: SyncContext, rule: Rule, resolved_format: str) -> str:
    base_env = build_environment([])
    base_env.globals["_facts"] = dict(ctx.facts)
    context = build_jinja_context(ctx)
    rendered = render_rule_body(rule, context, base_env)
    return render_for(
        rendered.source_path or Path("inline"),
        rendered.body,
        resolved_format,
        frontmatter=dataclasses.asdict(rendered.frontmatter),
    )


def _render_prompt(ctx: SyncContext, prompt: Prompt, resolved_format: str) -> str:
    """``prompt`` in ``resolved_format``: the pointer block for commands, the appendix for Continue.

    Raises :class:`PromptBodyUndefinedError` naming the prompt when its own
    body uses an undefined name (a leftover ``rule()`` call, a typo).
    """
    base_env = build_environment([])
    base_env.globals["_facts"] = dict(ctx.facts)
    context = build_jinja_context(ctx)
    # Only applicable rules enter the registry, as sync delivers them (SPEC §6.2.5);
    # the prompt itself renders whatever its own applies_if.
    rendered_rules = [
        render_rule_body(rule, context, base_env)
        for rule in ctx.rules_resolved
        if _rule_applies(rule, ctx)
    ]
    registry, prompt_env = build_prompt_environment(rendered_rules, ctx.facts)
    try:
        rendered_prompt = render_prompt_body(prompt, context, prompt_env)
    except UndefinedError as exc:
        raise PromptBodyUndefinedError(template_source(prompt), str(exc)) from exc
    return render_for(
        rendered_prompt.source_path or Path("inline"),
        rendered_prompt.body,
        resolved_format,
        frontmatter=dataclasses.asdict(rendered_prompt.frontmatter),
        rule_registry=registry,
        skill_references=registry,
    )


def _render_hook(ctx: SyncContext, hook: Hook, resolved_format: str) -> str:
    """The hook's advisory markdown, or its Claude registration JSON (§C.4.1).

    Only the body renders, in the sandboxed base environment, where ``rule()``
    is undefined (H19); both formats read the declared frontmatter.
    """
    base_env = build_environment([])
    base_env.globals["_facts"] = dict(ctx.facts)
    body = render_hook_body(hook, build_jinja_context(ctx), base_env)
    return render_for(
        hook.source_path or Path("inline"),
        body,
        resolved_format,
        frontmatter=hook.frontmatter.to_mapping(),
    )


def _render_artifact(ctx: SyncContext, kind: str, artifact: _Artifact, resolved_format: str) -> str:
    if kind == "hook":
        assert isinstance(artifact, Hook)
        return _render_hook(ctx, artifact, resolved_format)
    if kind == "rule":
        assert isinstance(artifact, Rule)
        return _render_rule(ctx, artifact, resolved_format)
    if kind == "prompt":
        assert isinstance(artifact, Prompt)
        return _render_prompt(ctx, artifact, resolved_format)
    # skills degrade to prompts for render purposes
    assert isinstance(artifact, Skill)
    return _render_prompt(ctx, artifact.to_prompt(), resolved_format)


def run(args: argparse.Namespace) -> int:
    repo_root = Path(getattr(args, "repo_root", None) or Path.cwd())
    artifact_id = args.id
    ctx = SyncContext.from_repo(repo_root)
    kind, artifact = _find_artifact(ctx, artifact_id)
    if artifact is None or kind is None:
        print(f"no artifact matching id {artifact_id!r}", file=sys.stderr)
        return 1

    if getattr(args, "show_source", False):
        print(_show_source(artifact, kind, ctx))
        return 0

    if getattr(args, "show_rules", False):
        if kind != "prompt":
            print(
                f"--show-rules only valid for prompts; {artifact_id!r} is a {kind}",
                file=sys.stderr,
            )
            return 1
        assert isinstance(artifact, Prompt)
        print(_show_rules(artifact, ctx))
        return 0

    resolved_format = _resolve_format(getattr(args, "format", None), kind)
    if resolved_format not in BUILTIN_FORMATS:
        valid = ", ".join(sorted(BUILTIN_FORMATS | set(FORMAT_ALIASES.keys())))
        print(f"unknown format {resolved_format!r}; valid: {valid}", file=sys.stderr)
        return 1
    problem = _format_error(kind, resolved_format)
    if problem is not None:
        print(problem, file=sys.stderr)
        return 1

    try:
        print(_render_artifact(ctx, kind, artifact, resolved_format))
    except TemplateSecurityError as exc:
        # Every applicable rule renders here, so one escaping template anywhere
        # names its file instead of dumping a traceback (prK §P1).
        return report_sandbox_violation(exc, ctx.repo_root, outcome="playbook render aborted.")
    except PromptBodyUndefinedError as exc:
        # A prompt that still calls the removed rule() (D15): name the file.
        return report_template_error(
            exc.source, exc.detail, ctx.repo_root, outcome="playbook render aborted."
        )
    except UndefinedError as exc:
        if not isinstance(artifact, Hook):
            raise
        # A hook body cannot call rule() (H19): name the file, not a traceback.
        source = str(artifact.source_path or artifact.frontmatter.id)
        return report_template_error(
            source, str(exc), ctx.repo_root, outcome="playbook render aborted."
        )
    return 0
