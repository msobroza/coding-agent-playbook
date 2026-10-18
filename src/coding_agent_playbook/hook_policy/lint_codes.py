"""A linked rule's ``lint_codes``, resolved at sync into its lint hook's config (specs/prK-lifecycle-hooks.md §A.7).

``RuleFrontmatter.lint_codes`` is the one source of the codes a rule-linked
lint hook reports: ``{warn: [...], when: [{applies_if: {...}, warn: [...]}]}``.
Sync resolves it against the detector facts the rule body itself reads (each
``when`` predicate through ``detector.evaluate_predicate``) and merges the flat
result into the builtin handler's ``config["lint_codes"]``, so the rule text
and the enforcing hook never disagree, and the hook never evaluates a
predicate at run time (it cannot import ``detector``).

The resolved shape is ``{"rule": <rule id>, "skill": <skill id>, "warn": [<code>, ...]}``:
the post-edit pipeline reads ``warn`` (``_ruff_pipeline.extended_codes``, the
sync-time ruff probe) and names ``rule`` and ``skill`` in its line prefix
(D16). ``skill`` is the rule's owning skill, absent when the rule names none
(an always rule), so the prefix then stays ``rule <id>:``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

__all__ = ["LINT_CODES_KEY", "linked_lint_config", "resolve_lint_codes"]

#: The handler config key that carries the resolved codes.
LINT_CODES_KEY: Final = "lint_codes"

#: ``evaluate(predicate, facts) -> holds``; raises ``ValueError`` on an unknown key.
type Evaluate = Callable[[dict[str, Any], Mapping[str, Any]], bool]


def resolve_lint_codes(
    lint_codes: Mapping[str, Any], facts: Mapping[str, Any], evaluate: Evaluate
) -> list[str]:
    """``warn``, then each ``when`` block's ``warn`` whose ``applies_if`` holds, each code once.

    A malformed block or an invalid predicate contributes nothing (validate
    reports it before sync); this never raises.

    Example::

        >>> codes = {"warn": ["ANN001"], "when": [{"applies_if": {"py": 1}, "warn": ["UP046"]}]}
        >>> resolve_lint_codes(codes, {"py": 1}, lambda predicate, facts: predicate == facts)
        ['ANN001', 'UP046']
    """
    found = list(_codes(lint_codes.get("warn")))
    when = lint_codes.get("when")
    for block in when if isinstance(when, list) else ():
        if isinstance(block, dict) and _holds(block.get("applies_if"), facts, evaluate):
            found.extend(_codes(block.get("warn")))
    return list(dict.fromkeys(found))


def linked_lint_config(
    rule_id: str, codes: list[str], skill_id: str | None = None
) -> dict[str, Any]:
    """The ``config["lint_codes"]`` value of a hook linked to ``rule_id`` (D16).

    ``skill`` is present only when the rule names an owning skill (an always
    rule has none).

    Example::

        >>> linked_lint_config("pytest", ["PT009"], "python-testing")
        {'rule': 'pytest', 'skill': 'python-testing', 'warn': ['PT009']}
    """
    config: dict[str, Any] = {"rule": rule_id}
    if skill_id:
        config["skill"] = skill_id
    config["warn"] = list(codes)
    return config


def _codes(value: object) -> Iterator[str]:
    if isinstance(value, list):
        yield from (code for code in value if isinstance(code, str))


def _holds(predicate: object, facts: Mapping[str, Any], evaluate: Evaluate) -> bool:
    if not isinstance(predicate, dict) or not predicate:
        return False  # a when block without a condition is malformed, not "always"
    try:
        return evaluate(dict(predicate), facts)
    except ValueError:
        return False
