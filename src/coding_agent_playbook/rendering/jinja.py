"""The sandboxed Jinja environment every artifact body renders in (SPEC §9.3).

Frontmatter is parsed by the engine before this module runs and is always
treated as static YAML — only the body is rendered through Jinja.
File-extension dispatch: ``.md`` body is returned verbatim; ``.md.j2`` body is
rendered through a sandboxed Jinja2 environment with ``StrictUndefined`` so
typos fail loudly and attribute escapes to Python internals raise. The
per-format post-processing of a rendered body is ``rendering.formats``.

This is the one module that constructs a Jinja environment: a render pass gets
it through ``rendering.session``, and ``playbook validate``'s parse-only check is
:func:`jinja_syntax_error` (tests/rendering/test_no_unsandboxed_jinja.py).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from jinja2 import FileSystemLoader, StrictUndefined, TemplateSyntaxError
from jinja2.exceptions import SecurityError
from jinja2.sandbox import SandboxedEnvironment

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    # Annotations only: every runtime construction is a ``SandboxedEnvironment``
    # (tests/rendering/test_no_unsandboxed_jinja.py allows no other jinja2 import).
    from jinja2 import Environment

# A ``{{ rule("id") }}`` call in a template; group 1 is the rule id.
# Whitespace- and trim-marker-tolerant (``{{rule("x")}}``, ``{{- rule('x') -}}``).
# The helper is gone (D15), so a call only renders as ``UndefinedError``;
# ``playbook validate`` uses this to name the call in prompts, rules and hook bodies.
RULE_CALL_RE = re.compile(r"\{\{-?\s*rule\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*-?\}\}")


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
    ``framework_skill(role)`` returns the enabled framework's skill for a D74
    role (``""`` without one) and ``skill_active(name)`` whether that skill
    renders in this repo; both read what ``RenderSession.open`` stashes.

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

    # D74: the session stashes the enabled framework's role map and the ids of the
    # skills that render under ``_framework_roles`` / ``_active_skills``.
    def _framework_skill(role: str) -> str:
        roles = env.globals.get("_framework_roles", {})
        return str(roles.get(role, "")) if isinstance(roles, dict) else ""

    def _skill_active(name: str) -> bool:
        active = env.globals.get("_active_skills", frozenset())
        return isinstance(active, frozenset) and name in active

    env.globals["framework_skill"] = _framework_skill
    env.globals["skill_active"] = _skill_active
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


def jinja_syntax_error(template: str) -> str | None:
    """The Jinja syntax error of ``template``, or None when it parses.

    Syntax only: no loader, no facts. ``playbook validate`` runs it on rule,
    prompt and hook bodies; sandboxed like :func:`build_environment`, so no Jinja
    construction site is unsandboxed (prK §P1).

    Example::

        >>> jinja_syntax_error("{% if x %}").startswith("Unexpected end of template.")
        True
    """
    try:
        SandboxedEnvironment(autoescape=False, undefined=StrictUndefined).parse(template)
    except TemplateSyntaxError as exc:
        return exc.message or str(exc)
    return None


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
