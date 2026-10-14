"""`playbook render <id>` — render a single artifact to stdout for debugging
(SPEC §12.7).

Supports ``--format <fmt>`` (defaults to the artifact's natural format),
``--show-source`` (template path + overrides), and ``--show-rules`` (for
prompts, lists the inclusion graph with applies_if outcomes).
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.commands.sync import (
    _build_jinja_context,
    _render_prompt_body,
    _render_rule_body,
)
from coding_agent_playbook.detector import evaluate_predicate
from coding_agent_playbook.orchestrator import SyncContext, artifact_id_of, build_prompt_environment
from coding_agent_playbook.renderer import (
    BUILTIN_FORMATS,
    FORMAT_ALIASES,
    build_environment,
    render_for,
)
from coding_agent_playbook.types import Prompt, Rule, Skill

if TYPE_CHECKING:
    import argparse


_RULE_FORMATS = {"continue_rule", "claude_md_section", "agents_md_section"}
_PROMPT_FORMATS = {"prompt_continue", "prompt_claude_command", "prompt_opencode_command"}

# Either of the three artifact dataclasses can come back from _find_artifact.
_Artifact = Rule | Prompt | Skill


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
    return None, None


def _resolve_format(fmt: str | None, kind: str) -> str:
    """Apply :data:`FORMAT_ALIASES` and default to a sensible format."""
    if fmt is None:
        return {"rule": "continue_rule", "prompt": "prompt_continue", "skill": "prompt_continue"}[
            kind
        ]
    return FORMAT_ALIASES.get(fmt, fmt)


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


def _show_rules(prompt: Prompt, ctx: SyncContext) -> str:
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
        predicate = rule.frontmatter.applies_if or {}
        if not predicate:
            applies = True
        else:
            try:
                applies = evaluate_predicate(predicate, ctx.facts, repo_root=ctx.repo_root)
            except ValueError:
                applies = False
        marker = "INLINED" if applies else "OMITTED"
        lines.append(f"  - {rule_id}  ({rule.source_package}, applies_if={applies} -> {marker})")
    return "\n".join(lines)


def _render_rule(ctx: SyncContext, rule: Rule, resolved_format: str) -> str:
    base_env = build_environment([], is_prompt_context=False)
    base_env.globals["_facts"] = dict(ctx.facts)
    context = _build_jinja_context(ctx)
    rendered = _render_rule_body(rule, context, base_env)
    return render_for(
        rendered.source_path or Path("inline"),
        rendered.body,
        resolved_format,
        frontmatter=dataclasses.asdict(rendered.frontmatter),
    )


def _render_prompt(ctx: SyncContext, prompt: Prompt, resolved_format: str) -> str:
    base_env = build_environment([], is_prompt_context=False)
    base_env.globals["_facts"] = dict(ctx.facts)
    context = _build_jinja_context(ctx)
    rendered_rules = [_render_rule_body(rule, context, base_env) for rule in ctx.rules_resolved]
    registry, prompt_env = build_prompt_environment(rendered_rules, ctx.facts)
    rendered_prompt = _render_prompt_body(prompt, context, prompt_env)
    return render_for(
        rendered_prompt.source_path or Path("inline"),
        rendered_prompt.body,
        resolved_format,
        frontmatter=dataclasses.asdict(rendered_prompt.frontmatter),
        rule_registry=registry,
    )


def _render_artifact(ctx: SyncContext, kind: str, artifact: _Artifact, resolved_format: str) -> str:
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
    if kind == "rule" and resolved_format not in _RULE_FORMATS:
        print(
            f"format {resolved_format!r} not valid for rules; "
            f"use one of: {', '.join(sorted(_RULE_FORMATS))}",
            file=sys.stderr,
        )
        return 1
    if kind in ("prompt", "skill") and resolved_format not in _PROMPT_FORMATS:
        print(
            f"format {resolved_format!r} not valid for prompts; "
            f"use one of: {', '.join(sorted(_PROMPT_FORMATS))}",
            file=sys.stderr,
        )
        return 1

    print(_render_artifact(ctx, kind, artifact, resolved_format))
    return 0
