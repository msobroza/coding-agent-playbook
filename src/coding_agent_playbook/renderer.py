"""Renderer subsystem: Jinja2 environment + format post-processing.

See SPEC.md §9. Frontmatter is parsed by the engine before this module runs
and is always treated as static YAML — only the body is rendered through Jinja.
File-extension dispatch: ``.md`` body is returned verbatim; ``.md.j2`` body is
rendered through a sandboxed Jinja2 environment with ``StrictUndefined`` so
typos fail loudly and attribute escapes to Python internals raise.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Protocol

import yaml
from jinja2 import FileSystemLoader, StrictUndefined
from jinja2.exceptions import SecurityError
from jinja2.sandbox import SandboxedEnvironment

# Re-exported (``as SENTINEL``) so existing ``renderer.SENTINEL`` imports keep
# working; the import-light ``_sentinel`` module is the single home (prK §P3).
from coding_agent_playbook._sentinel import SENTINEL as SENTINEL
from coding_agent_playbook._sentinel import sentinel_line
from coding_agent_playbook.hook_policy import advisory_block, advisory_text
from coding_agent_playbook.hook_registrations import (
    DeclaredMember,
    claude_settings_projection,
    declared_stop_budget_s,
)
from coding_agent_playbook.prompt_rule_delivery import (
    includes_rules_appendix,
    insert_pointer_block,
    skill_pointer_block,
)
from coding_agent_playbook.types import HookFrontmatter

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    # Annotations only: every runtime construction is a ``SandboxedEnvironment``
    # (tests/unit/test_no_unsandboxed_jinja.py allows no other jinja2 import).
    from jinja2 import Environment

    from coding_agent_playbook.prompt_rule_delivery import SkillReferenceIndex

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

# A ``{{ rule("id") }}`` call in a template; group 1 is the rule id.
# Whitespace- and trim-marker-tolerant (``{{rule("x")}}``, ``{{- rule('x') -}}``).
# The helper is gone (D15), so a call only renders as ``UndefinedError``;
# ``playbook validate`` uses this to name the call in prompts, rules and hook bodies.
RULE_CALL_RE = re.compile(r"\{\{-?\s*rule\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*-?\}\}")


def with_sentinel_body(frontmatter: str, body: str) -> str:
    """Compose a generated file whose frontmatter must stay on line 1.

    Parsers such as OpenCode's (gray-matter) and the Agent Skills loaders only
    see frontmatter when the file *starts* with ``---``, so the sentinel cannot
    be line 1 there: :func:`~coding_agent_playbook._sentinel.sentinel_line` is
    the **first body line** (the second position ``_sentinel.has_sentinel``
    accepts), followed by a blank line and ``body``. ``frontmatter`` must start
    with ``---``.

    Example::

        with_sentinel_body("---\ndescription: d\n---", "Body\n")
    """
    return f"{frontmatter.rstrip('\n')}\n{sentinel_line('html')}\n\n{body}"


class RuleRegistry(Protocol):
    """How the ``## Reference rules`` appendix renders an included rule's text.

    ``rule_registry.RuleRegistryImpl`` implements it; this protocol is the
    contract the renderer depends on. Tests can pass an in-memory
    implementation; production passes the merged-overlay registry.
    """

    def render_for_inclusion(self, rule_id: str, context: dict[str, Any]) -> str:
        """Return the rendered body of ``rule_id`` for inline placement in a
        prompt, with a ``### {rule.name}`` header prepended. Returns ``""``
        if the rule's ``applies_if`` evaluates to false for the current facts.
        """
        ...


def build_environment(template_search_paths: Sequence[Path]) -> Environment:
    """Build a sandboxed Jinja environment configured per SPEC §9.3.

    The environment is a ``SandboxedEnvironment`` (a subclass of the annotated
    ``Environment``): templates are author-controlled *and* agent-writable
    (``playbook/**/*.md.j2``, overlay ``resources/``), so a body such as
    ``{{ lipsum.__globals__["os"] }}`` must raise ``SecurityError`` instead
    of reaching ``os`` (prK §P1). It is deliberately not the immutable
    variant, which would also reject in-template list/dict mutation.

    Rules, prompts and hook bodies all render in this one shape. There is no
    ``rule()`` helper (D15): a template calling it raises ``UndefinedError``,
    and prompts declare their rules in ``includes_rules`` instead.

    Example::

        env = build_environment([])
        render_string("{{ project_name }}", {"project_name": "demo"}, env=env)
    """
    env = SandboxedEnvironment(
        loader=FileSystemLoader([str(p) for p in template_search_paths]),
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )

    # SPEC §9.4: helpers read facts from ``env.globals["_facts"]``. Callers stash
    # facts there before each render so helpers don't need to be re-bound.
    def _facts() -> dict[str, Any]:
        value = env.globals.get("_facts", {})
        return value if isinstance(value, dict) else {}

    def _has_framework(name: str) -> bool:
        frameworks = _facts().get("frameworks", {})
        return name in frameworks

    env.globals["has_framework"] = _has_framework

    def _has_ml_dep(name: str) -> bool:
        ml_stack = _facts().get("ml_stack", {})
        return name in ml_stack

    env.globals["has_ml_dep"] = _has_ml_dep
    return env


def render_artifact_body(
    template_path: Path,
    context: dict[str, Any],
    *,
    env: Environment,
) -> str:
    """Dispatch on extension. ``.md`` returns the file verbatim; ``.md.j2``
    is rendered through ``env``. The body is the only part rendered;
    frontmatter must be split off by the caller first.
    """
    if template_path.suffix == ".j2":
        template = env.get_template(template_path.name)
        return template.render(**context)
    return template_path.read_text(encoding="utf-8")


def render_string(body: str, context: dict[str, Any], *, env: Environment) -> str:
    """Render a literal template string through ``env``. Used by the
    rule-inclusion path and by tests that don't need the loader.
    """
    template = env.from_string(body)
    return template.render(**context)


class TemplateSecurityError(Exception):
    """An artifact template reached for Python internals the Jinja sandbox blocks.

    Raised in place of jinja2's bare ``SecurityError`` so ``playbook sync`` and
    ``playbook render`` name the offending file instead of printing a traceback
    (specs/prK-lifecycle-hooks.md §P1). ``source`` is the artifact's source path
    (its id when it has none); ``detail`` is jinja2's reason.

    Example::

        TemplateSecurityError("playbook/rules/x.md.j2", "access to attribute "
                              "'__globals__' of 'function' object is unsafe.")
    """

    def __init__(self, source: str, detail: str) -> None:
        super().__init__(f"{source}: template rejected by the Jinja sandbox: {detail}")
        self.source = source
        self.detail = detail


def render_sandboxed(body: str, context: dict[str, Any], *, env: Environment, source: str) -> str:
    """Render ``body`` like :func:`render_string`, naming ``source`` on a sandbox violation.

    jinja2's ``SecurityError`` becomes :class:`TemplateSecurityError` carrying
    ``source`` (the artifact's file, or its id). A ``TemplateSecurityError``
    raised by a nested render propagates unchanged, so the error always names
    the template that actually escaped.

    Example::

        body = render_sandboxed(rule.template_body, ctx, env=env, source="playbook/rules/x.md.j2")
    """
    try:
        return render_string(body, context, env=env)
    except SecurityError as exc:
        raise TemplateSecurityError(source, str(exc)) from exc


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
    return f"{sentinel_line('html')}\n---\n{fenced}\n---\n{body}"


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
    ``_sentinel.has_sentinel`` accepts (specs/prK-lifecycle-hooks.md §C.4.3).
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
