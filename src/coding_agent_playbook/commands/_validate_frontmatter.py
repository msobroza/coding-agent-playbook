"""Shape checks of optional artifact frontmatter fields (specs/prK-hook-pack.md §E.3).

The canonical dataclasses accept any value for their open-dict fields (YAML
gives no types), so ``playbook validate`` is where an author learns that a
field is malformed: each finding names the field, the offending value and the
expected shape. Kept apart from ``validate`` for its file-size budget:
``PromptFrontmatter.write_scope`` (§E.3) and ``RuleFrontmatter.lint_codes``
(specs/prK-lifecycle-hooks.md §A.7).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.commands._validation import ValidationError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence

    from coding_agent_playbook.types import Prompt, Rule

__all__ = [
    "LINT_CODES_SHAPE",
    "WRITE_SCOPE_SHAPE",
    "check_lint_codes",
    "check_write_scope",
    "lint_codes_problems",
    "write_scope_problem",
]

#: What every ``write_scope`` finding tells the author to write instead.
WRITE_SCOPE_SHAPE: Final = "expected exactly one of 'read_only: true' or 'globs: [<glob>, ...]'"
_WRITE_SCOPE_KEYS: Final = frozenset({"read_only", "globs"})


def check_write_scope(prompts: Sequence[Prompt]) -> list[ValidationError]:
    """One error per prompt whose ``write_scope`` is not a valid scope; ``[]`` when all are.

    An absent (empty) scope is valid: the prompt is unrestricted.

    Example::

        >>> check_write_scope([])
        []
    """
    errors: list[ValidationError] = []
    for prompt in prompts:
        problem = write_scope_problem(prompt.frontmatter.write_scope)
        if problem is not None:
            where = str(prompt.source_path or prompt.frontmatter.id)
            errors.append(ValidationError(path=where, message=f"write_scope: {problem}"))
    return errors


def write_scope_problem(scope: object) -> str | None:
    """Why ``scope`` is not a valid ``write_scope``, or ``None`` when it is (or is empty).

    Example::

        >>> write_scope_problem({"read_only": False})
        'read_only must be true, got False'
        >>> write_scope_problem({"globs": ["tests/**"]}) is None
        True
    """
    if scope == {}:
        return None
    if not isinstance(scope, dict):
        return f"got {scope!r}; {WRITE_SCOPE_SHAPE}"
    unknown = sorted(str(key) for key in scope if key not in _WRITE_SCOPE_KEYS)
    if unknown:
        return f"unknown key(s) {unknown!r}; {WRITE_SCOPE_SHAPE}"
    if len(scope) != 1:
        return f"got both keys {sorted(scope)!r}; {WRITE_SCOPE_SHAPE}"
    if "read_only" in scope:
        value = scope["read_only"]
        return None if value is True else f"read_only must be true, got {value!r}"
    return _globs_problem(scope["globs"])


def _globs_problem(globs: object) -> str | None:
    """Why ``globs`` is not a non-empty list of non-empty strings, else ``None``."""
    if not isinstance(globs, list) or not globs:
        return f"globs must be a non-empty list of glob strings, got {globs!r}"
    bad = [glob for glob in globs if not isinstance(glob, str) or not glob.strip()]
    if bad:
        return f"globs entries must be non-empty strings, got {bad!r}"
    return None


# --- RuleFrontmatter.lint_codes (specs/prK-lifecycle-hooks.md §A.7) --------------------------

#: What every ``lint_codes`` shape finding tells the author to write instead.
LINT_CODES_SHAPE: Final = (
    "expected 'warn: [<code>, ...]' and optional 'when: [{applies_if: {...}, warn: [...]}]' "
    "(lint feedback is warn-only: there is no 'block' key)"
)
_LINT_CODES_KEYS: Final = frozenset({"warn", "when"})
_WHEN_KEYS: Final = ("applies_if", "warn")
#: A ruff rule code: the linter's letters, then digits (``E722``, ``PLR0911``, ``UP046``).
_RUFF_CODE: Final = re.compile(r"[A-Z]+[0-9]+")

#: Raises ``ValueError`` naming an unknown or malformed ``applies_if`` key.
type PredicateCheck = Callable[[dict[str, Any]], object]


def check_lint_codes(
    rules: Sequence[Rule], check_predicate: PredicateCheck
) -> list[ValidationError]:
    """One error per problem in each rule's ``lint_codes``; ``[]`` when every one is valid.

    ``check_predicate`` evaluates one ``when[].applies_if`` the way a rule's own
    ``applies_if`` is (``detector.evaluate_predicate``), raising on an unknown key.

    Example::

        >>> check_lint_codes([], lambda predicate: True)
        []
    """
    errors: list[ValidationError] = []
    for rule in rules:
        where = str(rule.source_path or rule.frontmatter.id)
        errors.extend(
            ValidationError(path=where, message=problem)
            for problem in lint_codes_problems(rule.frontmatter.lint_codes, check_predicate)
        )
    return errors


def lint_codes_problems(codes: object, check_predicate: PredicateCheck) -> list[str]:
    """Every reason ``codes`` is not a valid ``lint_codes`` (``[]`` when valid or empty).

    Example::

        >>> lint_codes_problems({"warn": "E722"}, lambda predicate: True)
        ["lint_codes.warn: expected a list of ruff rule codes, got 'E722'"]
    """
    if codes == {}:
        return []
    if not isinstance(codes, dict):
        return [f"lint_codes: got {codes!r}; {LINT_CODES_SHAPE}"]
    problems: list[str] = []
    unknown = sorted(str(key) for key in codes if key not in _LINT_CODES_KEYS)
    if unknown:
        problems.append(f"lint_codes: unknown key(s) {unknown!r}; {LINT_CODES_SHAPE}")
    if "warn" in codes:
        problems.extend(_codes_problems("lint_codes.warn", codes["warn"]))
    if "when" in codes:
        problems.extend(_when_problems(codes["when"], check_predicate))
    return problems


def _codes_problems(where: str, codes: object, *, non_empty: bool = False) -> Iterator[str]:
    if not isinstance(codes, list) or (non_empty and not codes):
        yield f"{where}: expected a list of ruff rule codes, got {codes!r}"
        return
    for code in codes:
        if not isinstance(code, str) or not _RUFF_CODE.fullmatch(code):
            yield f"{where}: {code!r} is not a ruff rule code (letters then digits, e.g. 'E722')"


def _when_problems(when: object, check_predicate: PredicateCheck) -> Iterator[str]:
    if not isinstance(when, list):
        yield f"lint_codes.when: expected a list of {{applies_if, warn}} entries, got {when!r}"
        return
    for index, entry in enumerate(when):
        where = f"lint_codes.when[{index}]"
        if not isinstance(entry, dict) or sorted(entry) != list(_WHEN_KEYS):
            keys = sorted(entry) if isinstance(entry, dict) else entry
            yield f"{where}: expected exactly the keys {list(_WHEN_KEYS)!r}, got {keys!r}"
            continue
        yield from _predicate_problems(f"{where}.applies_if", entry["applies_if"], check_predicate)
        yield from _codes_problems(f"{where}.warn", entry["warn"], non_empty=True)


def _predicate_problems(
    where: str, predicate: object, check_predicate: PredicateCheck
) -> Iterator[str]:
    if not isinstance(predicate, dict) or not predicate:
        yield f"{where}: expected a non-empty applies_if mapping, got {predicate!r}"
        return
    # One key at a time: evaluate_predicate stops at the first key that does not
    # hold, so a typo after it would otherwise pass unseen.
    for key, value in predicate.items():
        try:
            check_predicate({key: value})
        except ValueError as exc:
            yield f"{where}: {exc}"
