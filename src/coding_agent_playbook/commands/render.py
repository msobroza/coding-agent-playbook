"""`cap render <id>` — render a single artifact to stdout for debugging
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
from coding_agent_playbook.orchestrator import RuleRegistryImpl, SyncContext
from coding_agent_playbook.renderer import (
    BUILTIN_FORMATS,
    FORMAT_ALIASES,
    build_environment,
    render_for,
)

if TYPE_CHECKING:
    import argparse

    from coding_agent_playbook.types import Prompt, Rule


_RULE_FORMATS = {"continue_rule", "claude_md_section", "agents_md_section"}
_PROMPT_FORMATS = {"prompt_continue", "prompt_claude_command", "prompt_opencode_command"}


def _find_artifact(ctx: SyncContext, artifact_id: str):  # type: ignore[no-untyped-def]
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
        skill_id = skill.frontmatter.get("id", "skill") if isinstance(skill.frontmatter, dict) else None
        if skill_id == artifact_id:
            return "skill", skill
    return None, None


def _resolve_format(fmt: str | None, kind: str) -> str:
    """Apply :data:`FORMAT_ALIASES` and default to a sensible format."""
    if fmt is None:
        return {"rule": "continue_rule", "prompt": "prompt_continue", "skill": "prompt_continue"}[kind]
    return FORMAT_ALIASES.get(fmt, fmt)


def _show_source(artifact, kind: str, ctx: SyncContext) -> str:  # type: ignore[no-untyped-def]
    """Print provenance (template path, applicable adapters, overlay losers)."""
    lines = []
    template_path = getattr(artifact, "source_path", None)
    if template_path is None:
        lines.append("Template:  (inline / not on disk)")
    else:
        lines.append(f"Template:  {template_path}")
    is_templated = getattr(artifact, "is_templated", False)
    lines.append(f"Format:    {'.md.j2 (Jinja-templated)' if is_templated else '.md (verbatim)'}")
    relevant = [c for c in ctx.overlay_collisions if c.kind == kind and c.artifact_id == _artifact_id(artifact)]
    if relevant:
        losers = ", ".join(relevant[0].losers)
        lines.append(f"Overrides: {losers}")
    adapters = sorted(ctx.adapters.keys())
    lines.append(f"Adapters:  {', '.join(adapters)}")
    return "\n".join(lines)


def _artifact_id(artifact) -> str:  # type: ignore[no-untyped-def]
    frontmatter = getattr(artifact, "frontmatter")
    if hasattr(frontmatter, "id"):
        return frontmatter.id
    return frontmatter.get("id", "skill")


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


def _render_artifact(ctx: SyncContext, kind: str, artifact, resolved_format: str) -> str:  # type: ignore[no-untyped-def]
    base_env = build_environment([], is_prompt_context=False)
    base_env.globals["_facts"] = dict(ctx.facts)
    context = _build_jinja_context(ctx)
    if kind == "rule":
        rendered = _render_rule_body(artifact, context, base_env)
        return render_for(
            rendered.source_path or Path("inline"),
            rendered.body,
            resolved_format,
            frontmatter=dataclasses.asdict(rendered.frontmatter),
        )
    if kind == "prompt":
        # Build the registry against the full resolved rules so {{ rule() }}
        # calls still work in --format prompt_*.
        rendered_rules = [_render_rule_body(rule, context, base_env) for rule in ctx.rules_resolved]
        registry = RuleRegistryImpl(rendered_rules, ctx.facts, base_env)
        prompt_env = build_environment([], is_prompt_context=True, rule_registry=registry)
        prompt_env.globals["_facts"] = dict(ctx.facts)
        rendered = _render_prompt_body(artifact, context, prompt_env)
        return render_for(
            rendered.source_path or Path("inline"),
            rendered.body,
            resolved_format,
            frontmatter=dataclasses.asdict(rendered.frontmatter),
            rule_registry=registry,
        )
    # skills degrade to prompts for render purposes
    promoted = artifact.to_prompt()
    return _render_artifact(ctx, "prompt", promoted, resolved_format)


def run(args: argparse.Namespace) -> int:
    repo_root = Path(getattr(args, "repo_root", None) or Path.cwd())
    artifact_id = args.id
    ctx = SyncContext.from_repo(repo_root)
    kind, artifact = _find_artifact(ctx, artifact_id)
    if artifact is None:
        print(f"no artifact matching id {artifact_id!r}", file=sys.stderr)
        return 1

    if getattr(args, "show_source", False):
        print(_show_source(artifact, kind, ctx))
        return 0

    if getattr(args, "show_rules", False):
        if kind != "prompt":
            print(f"--show-rules only valid for prompts; {artifact_id!r} is a {kind}", file=sys.stderr)
            return 1
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
