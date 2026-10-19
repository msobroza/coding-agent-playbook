"""The finding types every ``playbook validate`` check returns, and their report (SPEC §12.6).

A module of its own so the check modules (``validation._links``, ``validation._hooks``),
``checks`` and the validate-gated ``sync`` can all share it, its report format
and the two body checks rules, prompts and hooks have in common (a template
calling ``rule()``, a Jinja syntax error), without importing each other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from jinja2 import StrictUndefined, TemplateSyntaxError
from jinja2.sandbox import SandboxedEnvironment

# The one ``{{ rule("<id>") }}`` pattern (group 1 is the rule id). The helper is
# gone (D15): no rule, prompt or hook body may make such a call, and validate
# names the call it finds.
from coding_agent_playbook.renderer import RULE_CALL_RE as RULE_CALL_RE
from coding_agent_playbook.skills.naming import has_declared_id, skill_id_of

if TYPE_CHECKING:
    from collections.abc import Sequence
    from typing import TextIO

    from coding_agent_playbook.types import Skill


@dataclass(frozen=True)
class ValidationError:
    """One validate finding: where it is (a file path or a config key) and why.

    Example::

        >>> ValidationError(path="overlays_enabled", message="cannot import 'acme'")
        ValidationError(path='overlays_enabled', message="cannot import 'acme'")
    """

    path: str
    message: str


@dataclass(frozen=True)
class ValidationFindings:
    """Every finding of one validate run: ``errors`` fail it, ``warnings`` only print.

    Example::

        >>> ValidationFindings().errors
        []
    """

    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)


def skill_label(skill: Skill) -> str:
    """Locate ``skill`` for a finding line (a canonical :class:`Skill` has no source path).

    Shared by the Agent Skills checks (``checks``) and the member-rule checks
    (``validation._skills``). An id-less skill is named by its authored ``name``
    and, when it has one, its ``scripts/``/``references/`` parent dir.

    Example: ``skill_label(query_db)`` -> ``"skills/query-db (<repo-local>)"``.
    """
    if has_declared_id(skill):
        return f"skills/{skill_id_of(skill)} ({skill.source_package})"
    source_dir = skill.scripts_dir or skill.references_dir
    where = f", at {source_dir.parent}" if source_dir is not None else ""
    name = skill.frontmatter.get("name", "?")
    return f"skills/<no id; name {name!r}{where}> ({skill.source_package})"


def jinja_syntax_error(template: str) -> str | None:
    """The Jinja syntax error of ``template``, or None when it parses.

    Syntax only: no rule registry, no facts. Sandboxed like the renderer's
    environment, so no Jinja construction site is unsandboxed (prK §P1).

    Example::

        >>> jinja_syntax_error("{% if x %}").startswith("Unexpected end of template.")
        True
    """
    try:
        SandboxedEnvironment(autoescape=False, undefined=StrictUndefined).parse(template)
    except TemplateSyntaxError as exc:
        return exc.message or str(exc)
    return None


def report_validation_warnings(warnings: Sequence[ValidationError], stream: TextIO) -> None:
    """Print one ``warning: <path>: <message>`` line per warning (nothing else).

    Example::

        >>> import sys
        >>> report_validation_warnings([ValidationError("a.md", "degraded")], sys.stdout)
        warning: a.md: degraded
    """
    for warning in warnings:
        print(f"warning: {warning.path}: {warning.message}", file=stream)


def report_validation_errors(errors: Sequence[ValidationError], stream: TextIO) -> None:
    """Print one ``FAIL <path>: <message>`` line per error, then the count line.

    ``playbook validate`` reports on stdout; the validate gate in ``playbook
    sync`` reports on stderr (prK §P P8b).

    Example::

        >>> import sys
        >>> report_validation_errors([ValidationError("a.md", "bad")], sys.stdout)
        FAIL a.md: bad
        validation failed with 1 error(s)
    """
    for error in errors:
        print(f"FAIL {error.path}: {error.message}", file=stream)
    print(f"validation failed with {len(errors)} error(s)", file=stream)
