"""Per-format post-processing of a Jinja-rendered artifact body (SPEC §9.7).

:func:`render_for` turns a body rendered in the sandbox of ``rendering.jinja``
into the text one harness reads: a Continue rule or prompt, a Claude Code or
AGENTS.md section, a Claude Code or OpenCode command, or a hook projection.
Frontmatter is parsed by the engine before this module runs and is always
treated as static YAML — only the body was rendered through Jinja.
"""

from __future__ import annotations

import json
import re
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

import yaml

from coding_agent_playbook.artifacts.hook_frontmatter import HookFrontmatter
from coding_agent_playbook.generated_output.sentinel import sentinel_line
from coding_agent_playbook.hooks.enforcement import advisory_block, advisory_text
from coding_agent_playbook.hooks.registrations.claude import claude_settings_projection
from coding_agent_playbook.hooks.registrations.plan import DeclaredMember, declared_stop_budget_s
from coding_agent_playbook.rendering.prompt_rule_delivery import (
    includes_rules_appendix,
    insert_pointer_block,
    skill_pointer_block,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from coding_agent_playbook.rendering.prompt_rule_delivery import SkillReferenceIndex
    from coding_agent_playbook.rendering.rule_registry import RuleRegistry

#: A markdown link from a member rule (``rules/<id>.md``) to a file of its skill's
#: ``references/``; group 1 is the path below ``references/``, fragment excluded.
_SKILL_REFERENCE_LINK = re.compile(r"\[[^\]\n]*\]\(\.\./references/([^)#\s]+)(?:#[^)\s]*)?\)")

# Aliases the CLI accepts as a short-form for --format. Resolved to the full
# internal name before render_for() dispatches.
FORMAT_ALIASES: dict[str, str] = {
    "continue": "continue_rule",
    "claude": "claude_md_section",
    "agents": "agents_md_section",
    "opencode": "prompt_opencode_command",
}

#: The tools a read-only prompt's Claude command removes (specs/prK-hook-pack.md §E.3).
CLAUDE_READ_ONLY_DISALLOWED = "Edit Write NotebookEdit"

# All built-in formats. Adapters may register more via the renderer registry
# (future work — v1 just has the built-ins inline here).
BUILTIN_FORMATS: frozenset[str] = frozenset(
    {
        "continue_rule",
        "claude_md_section",
        "agents_md_section",
        "prompt_continue",
        "prompt_claude_command",
        "prompt_opencode_command",
        # Hooks (specs/prK-lifecycle-hooks.md §C.4.1): the advisory markdown every
        # advisory target shares, and the debug JSON of the Claude registrations.
        "hook_advisory",
        "hook_claude_settings",
    }
)


def with_sentinel_body(frontmatter: str, body: str) -> str:
    """Compose a generated file whose frontmatter must stay on line 1.

    Parsers such as OpenCode's (gray-matter) and the Agent Skills loaders only
    see frontmatter when the file *starts* with ``---``, so the sentinel cannot
    be line 1 there: :func:`~coding_agent_playbook.generated_output.sentinel.sentinel_line` is
    the **first body line** (the second position ``generated_output.sentinel.has_sentinel``
    accepts), followed by a blank line and ``body``. ``frontmatter`` must start
    with ``---``.

    Example::

        with_sentinel_body("---\ndescription: d\n---", "Body\n")
    """
    return f"{frontmatter.rstrip('\n')}\n{sentinel_line('html')}\n\n{body}"


def render_for(
    _template_path: Path,
    body: str,
    fmt: str,
    *,
    frontmatter: dict[str, Any],
    rule_registry: RuleRegistry | None = None,
    skill_references: SkillReferenceIndex | None = None,
) -> str:
    """Apply per-format post-processing to a Jinja-rendered body (SPEC §9.7).

    ``fmt`` is one of the formats in ``BUILTIN_FORMATS`` (or a short alias in
    ``FORMAT_ALIASES``). ``prompt_continue`` appends the ``## Reference rules``
    appendix built through ``rule_registry``; ``prompt_claude_command`` and
    ``prompt_opencode_command`` insert the ``## Before you start`` block built
    through ``skill_references`` (D15). Without the matching argument the
    prompt renders with neither, so ``includes_rules`` is declarative only.

    ``_template_path`` is reserved for future format-specific dispatch
    (SPEC §9.7); current transforms key off ``fmt`` and ``frontmatter`` only,
    and ``hook_claude_settings`` names it when the frontmatter is malformed.

    Example::

        render_for(path, body, "prompt_claude_command", frontmatter=fm, skill_references=registry)
    """
    resolved = FORMAT_ALIASES.get(fmt, fmt)
    if resolved not in BUILTIN_FORMATS:
        valid = ", ".join(sorted(BUILTIN_FORMATS))
        raise ValueError(f"unknown format {fmt!r}; valid formats: {valid}")

    if resolved == "continue_rule":
        return _render_continue_rule(body, frontmatter)
    if resolved in ("claude_md_section", "agents_md_section"):
        return _render_markdown_rule_section(body, frontmatter)
    if resolved == "hook_advisory":
        return _render_hook_advisory(body, frontmatter)
    if resolved == "hook_claude_settings":
        return _render_hook_claude_settings(_template_path, frontmatter)
    includes_rules = frontmatter.get("includes_rules") or []
    if resolved == "prompt_continue":
        appendix = includes_rules_appendix(includes_rules, rule_registry)
        return _render_prompt_continue(body, frontmatter, appendix)
    block = skill_pointer_block(includes_rules, skill_references)
    if resolved == "prompt_claude_command":
        return _render_prompt_claude_command(body, frontmatter, block)
    if resolved == "prompt_opencode_command":
        return _render_prompt_opencode_command(body, frontmatter, block)

    # All BUILTIN_FORMATS are handled above; reaching here means a new format
    # was added to the set but its branch was forgotten.
    raise NotImplementedError(  # pragma: no cover
        f"render_for: format {resolved!r} in BUILTIN_FORMATS but has no dispatch "
        f"branch. Add a `_render_{resolved}` helper and an elif branch above."
    )


# --- Format transforms ----------------------------------------------------


def _render_continue_rule(body: str, frontmatter: dict[str, Any]) -> str:
    """Emit a Continue-shaped rule file (SPEC §9.7).

    Continue's semantics: ``globs`` is meaningful only when
    ``alwaysApply: false``. When ``scope == "always"`` we drop any globs
    from the projected frontmatter so the output matches Continue's contract.
    Links to the rule's skill ``references/`` become plain file names, because
    Continue receives no skill files (prU D46(9)).
    """
    scope = frontmatter.get("scope", "scoped")
    continue_frontmatter: dict[str, Any] = {
        "name": frontmatter["name"],
        "description": frontmatter["description"],
    }
    if scope == "always":
        continue_frontmatter["alwaysApply"] = True
    else:
        continue_frontmatter["alwaysApply"] = False
        globs = frontmatter.get("globs") or []
        if globs:
            continue_frontmatter["globs"] = list(globs)
    fenced = yaml.safe_dump(continue_frontmatter, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"{sentinel_line('html')}\n---\n{fenced}\n---\n{unlink_skill_references(body)}"


def unlink_skill_references(body: str) -> str:
    """``body`` with each ``[label](../references/<path>)`` link replaced by the file name.

    A member rule links its skill's free-form documents relative to ``rules/``;
    a harness that gets the rule without the skill (Continue) would show a dead
    link, so the reader gets the file name to look for instead (prU D46(9)).

    Example: ``unlink_skill_references("[ex](../references/a/ex.md)")`` -> ``"ex.md"``.
    """
    return _SKILL_REFERENCE_LINK.sub(lambda m: PurePosixPath(m.group(1)).name, body)


def _render_markdown_rule_section(body: str, frontmatter: dict[str, Any]) -> str:
    """Emit a markdown section for the Claude Code rules file or AGENTS.md (SPEC §9.7).

    The two adapters share byte-identical output: a level-2 heading with the
    rule name, an optional ``*Applies to: ...*`` line for scoped rules, the
    rendered body, and a ``---`` separator so successive sections stack
    cleanly.
    """
    name = frontmatter["name"]
    scope = frontmatter.get("scope", "scoped")
    globs = frontmatter.get("globs") or []
    parts = [f"## {name}", ""]
    if scope == "scoped" and globs:
        globs_str = ", ".join(f"`{glob}`" for glob in globs)
        parts.append(f"*Applies to: {globs_str}*")
        parts.append("")
    parts.append(body.rstrip("\n"))
    parts.append("")
    parts.append("---")
    parts.append("")
    return "\n".join(parts)


def _render_hook_advisory(body: str, frontmatter: dict[str, Any]) -> str:
    """``### <name>``, the rendered hook body, and its static enforcement line (§C.4.1).

    ``frontmatter`` is the hook's (``HookFrontmatter.to_mapping()``); the line
    comes from its declared ``events`` and ``supports`` only.
    """
    events = frontmatter.get("events") or []
    supports = frontmatter.get("supports") or []
    return advisory_block(frontmatter["name"], advisory_text(body, events, supports))


def _render_hook_claude_settings(source: Path, frontmatter: dict[str, Any]) -> str:
    """The hook's Claude registrations as ``settings.json`` JSON, alone in the repo (debug-only).

    Built from the declared frontmatter (no ``[hooks]`` gating or consumer
    config); raises ``HookSchemaError`` naming ``source`` on a malformed one.
    """
    fm = HookFrontmatter.from_mapping(frontmatter, where=str(source))
    projection = claude_settings_projection(
        [DeclaredMember.from_frontmatter(fm)], stop_budget_s=declared_stop_budget_s(fm)
    )
    return json.dumps(projection, indent=2, ensure_ascii=False) + "\n"


def _render_prompt_continue(
    body: str,
    frontmatter: dict[str, Any],
    appendix: str,
) -> str:
    """Emit a Continue-shaped prompt file (SPEC §9.7)."""
    continue_frontmatter: dict[str, Any] = {
        "name": frontmatter["name"],
        "description": frontmatter["description"],
        "invokable": True,
    }
    fenced = yaml.safe_dump(continue_frontmatter, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"{sentinel_line('html')}\n---\n{fenced}\n---\n{body}{appendix}"


def is_read_only_prompt(frontmatter: dict[str, Any]) -> bool:
    """Whether a prompt's ``write_scope`` is ``{read_only: true}`` (specs/prK-hook-pack.md §E.3).

    Only an explicit ``True`` counts: a malformed scope (validate rejects it)
    never removes tools from a command.

    Example::

        >>> is_read_only_prompt({"write_scope": {"read_only": True}})
        True
        >>> is_read_only_prompt({"write_scope": {"globs": ["tests/**"]}})
        False
    """
    scope = frontmatter.get("write_scope")
    return isinstance(scope, dict) and scope.get("read_only") is True


def _titled(body: str, name: str) -> str:
    """``body``, opened by ``# {name}`` unless it already starts with a level-1 heading."""
    return body if body.lstrip().startswith("# ") else f"# {name}\n\n{body}"


def render_inline_prompt_markdown(
    body: str, frontmatter: Mapping[str, Any], rule_registry: RuleRegistry | None
) -> str:
    """A prompt as plain markdown with its rules inline: title, body, appendix (agent_harness).

    The agent_harness prompt leaf: its scoped rules are top-level
    ``references/<id>.md`` files, not skill references, so there is no skill
    to point at (P3-6). Byte-identical to the Claude command text the leaf used
    before D15 for a prompt that never called ``rule()``: ``# <name>`` when the
    body has no title, then the body, then ``includes_rules_appendix``. No
    sentinel and no frontmatter: the leaf's own ``SKILL.md`` envelope has both.

    Example::

        render_inline_prompt_markdown(prompt.body, asdict(prompt.frontmatter), registry)
    """
    appendix = includes_rules_appendix(frontmatter.get("includes_rules") or [], rule_registry)
    return f"{_titled(body, frontmatter['name'])}{appendix}"


def _render_prompt_claude_command(
    body: str,
    frontmatter: dict[str, Any],
    block: str,
) -> str:
    """Emit a Claude Code slash-command file (SPEC §9.7).

    Claude Code commands are pure markdown. The output starts with the
    autogenerated-sentinel HTML comment so adapter cleanup can recognise
    the file as engine-owned; we then prepend ``# {name}`` if the body
    does not already start with a level-1 heading, and insert the
    ``## Before you start`` block (``""`` leaves the body as it is, D15).

    A read-only prompt instead opens with a ``disallowed-tools`` frontmatter
    block (Claude removes those tools while the command runs) and carries the
    sentinel on its first body line, the second anchored position
    ``generated_output.sentinel.has_sentinel`` accepts (specs/prK-lifecycle-hooks.md §C.4.3).
    Every other prompt renders exactly as before.
    """
    output = insert_pointer_block(_titled(body, frontmatter["name"]), block)
    marked = f"{sentinel_line('html')}\n{output}"
    if is_read_only_prompt(frontmatter):
        return f"---\ndisallowed-tools: {CLAUDE_READ_ONLY_DISALLOWED}\n---\n{marked}"
    return marked


def _render_prompt_opencode_command(
    body: str,
    frontmatter: dict[str, Any],
    block: str,
) -> str:
    """Emit an OpenCode slash-command file (SPEC §9.7).

    OpenCode uses ``$ARGUMENTS`` for a single input variable and ``$1`` /
    ``$2`` for multiple. Substitution is a literal ``str.replace`` on the
    placeholder pattern ``{{ var }}`` AFTER Jinja rendering — prompt
    authors writing for OpenCode know to use that exact spelling.

    Contract — Jinja-context exclusion for ``input_variables`` names:
        Substitution is a literal ``str.replace`` applied **after** Jinja
        rendering. Callers must **not** include ``input_variables[*].name``
        keys in the Jinja context passed to :func:`render_artifact_body`,
        or those placeholders will be expanded prematurely by Jinja and
        this transform will be a silent no-op. The orchestrator (PR 10)
        ensures input-variable names are reserved for the format-time
        substitution.

    The ``## Before you start`` block (D15) is inserted after the
    substitution: it holds no placeholder, so its text is never rewritten.
    """
    description = frontmatter["description"]
    input_variables = frontmatter.get("input_variables") or []
    rendered_body = body
    if len(input_variables) == 1:
        var = input_variables[0]
        rendered_body = rendered_body.replace(f"{{{{ {var['name']} }}}}", "$ARGUMENTS")
    else:
        for index, var in enumerate(input_variables, start=1):
            rendered_body = rendered_body.replace(f"{{{{ {var['name']} }}}}", f"${index}")
    # YAML-escape the description so colons/quotes/etc. don't break the envelope.
    description_line = yaml.safe_dump(
        {"description": description}, sort_keys=False, allow_unicode=True
    ).rstrip("\n")
    # OpenCode parses commands with gray-matter, which only sees frontmatter at
    # offset 0: a sentinel on line 1 dropped the description and leaked the
    # comment and the envelope into the prompt. So the envelope comes first.
    # A read-only prompt runs as OpenCode's built-in ``plan`` agent, which has
    # no edit tools (specs/prK-hook-pack.md §E.3; SPEC §10.6.1 lists ``agent``).
    agent_line = "\nagent: plan" if is_read_only_prompt(frontmatter) else ""
    envelope = f"---\n{description_line}{agent_line}\n---"
    return with_sentinel_body(envelope, insert_pointer_block(rendered_body, block))
