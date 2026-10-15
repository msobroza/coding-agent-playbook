"""Shape checks of optional artifact frontmatter fields (specs/prK-hook-pack.md §E.3).

The canonical dataclasses accept any value for their open-dict fields (YAML
gives no types), so ``playbook validate`` is where an author learns that a
field is malformed: each finding names the field, the offending value and the
expected shape. Kept apart from ``validate`` for its file-size budget; K7's
``lint_codes`` check joins this module.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from coding_agent_playbook.commands._validation import ValidationError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.types import Prompt

__all__ = ["WRITE_SCOPE_SHAPE", "check_write_scope", "write_scope_problem"]

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
