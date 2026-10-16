"""The finding types of the hook trust contract and their shared phrasing (prK §B.5).

A rule yields :class:`Finding` (severity + message); ``classify_hook`` and
``classify_hook_set`` locate each one as a :class:`HookIssue`, which validate
prints as a ``FAIL`` or ``warning:`` line. Stdlib-only, like all of ``hook_policy``.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.types import Hook

#: ``error`` fails validate (and so sync); ``warning`` is printed and passes.
Severity = Literal["error", "warning"]


class Finding(NamedTuple):
    """One unlocated contract finding: what a single rule says about a hook or a table."""

    severity: Severity
    message: str


@dataclass(frozen=True)
class HookIssue:
    """One contract finding, located: ``where`` is a ``HOOK.md`` path, a rule or a config file.

    Every message names the offending value and the expected shape.

    Example::

        >>> HookIssue("error", "playbook/hooks/x/HOOK.md", "timeout 45 exceeds 30 s ...").severity
        'error'
    """

    severity: Severity
    where: str
    message: str


def error(message: str) -> Finding:
    """A finding that fails validate."""
    return Finding("error", message)


def warning(message: str) -> Finding:
    """A finding validate prints but passes (degraded cells, clamps; OQ-43)."""
    return Finding("warning", message)


def hook_location(hook: Hook) -> str:
    """Where a hook's findings point: its ``HOOK.md``, else ``hooks/<id> (<layer>)``.

    Example: ``hook_location(hook) == "playbook/hooks/guard-x/HOOK.md"``.
    """
    if hook.source_path is not None:
        return str(hook.source_path)
    return f"hooks/{hook.frontmatter.id} ({hook.source_package})"


def seconds(value: float) -> str:
    """``45`` for ``45.0``, ``2.5`` for ``2.5``: a timeout as the author wrote it."""
    return str(int(value)) if value.is_integer() else str(value)


def did_you_mean(value: str, candidates: Iterable[str]) -> str:
    """``"; did you mean 'x'?"`` for the closest candidate, or ``""`` when none is close.

    Example::

        >>> did_you_mean("guard-y", ["guard-x"])
        "; did you mean 'guard-x'?"
    """
    close = difflib.get_close_matches(value, sorted(candidates), n=1)
    return f"; did you mean {close[0]!r}?" if close else ""
