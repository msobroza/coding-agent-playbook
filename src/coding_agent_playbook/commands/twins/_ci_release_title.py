"""The release-title rule of ``playbook ci``'s ``commit-convention`` step (#281).

A pull request that changes shipped guidance (rules, prompts, skills or hooks
of the engine's catalog) must be titled ``feat`` or ``fix``, or carry a
breaking ``!``: the PR title becomes the squash commit's subject, and
commitizen computes the next release from those subjects, so any other type
would ship changed guidance without a version bump.

Shipped guidance is ``catalog/core/<kind>/**`` and
``catalog/plugins/<plugin>/<kind>/**``; eval samples, plugin READMEs and
attributions, and everything outside ``catalog/`` (engine code, docs) are not.
A title commitizen cannot parse is left to ``cz check``'s own failure.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = ["RELEASE_TYPES", "release_title_problem", "shipped_artifact_paths"]

#: The Conventional Commit types that bump a release (``!`` bumps any type).
RELEASE_TYPES: Final = ("feat", "fix")
#: A layer root of the engine's catalog followed by a guidance kind directory.
_SHIPPED: Final = re.compile(r"^catalog/(?:core|plugins/[^/]+)/(?:rules|prompts|skills|hooks)/.")
#: ``type(scope)!:`` at the start of a subject; the scope is optional.
_HEADER: Final = re.compile(r"^(?P<type>[A-Za-z]+)(?:\([^)]*\))?(?P<bang>!)?:")
#: How many artifacts the failure names before folding the rest into a count.
_LISTED: Final = 10


def shipped_artifact_paths(paths: Iterable[str]) -> tuple[str, ...]:
    """The repo-relative ``paths`` that are shipped rules, prompts, skills or hooks, sorted.

    Example::

        >>> shipped_artifact_paths(["README.md", "catalog/core/rules/always/a.md"])
        ('catalog/core/rules/always/a.md',)
    """
    return tuple(sorted({path for path in paths if _SHIPPED.match(path)}))


def release_title_problem(subject: str, changed: Iterable[str]) -> str:
    """Why ``subject`` cannot title a PR changing ``changed``; ``""`` when it can.

    ``subject`` is the squash subject (draft marker already stripped).

    Example::

        >>> release_title_problem("feat: x", ["catalog/core/rules/always/a.md"])
        ''
    """
    shipped = shipped_artifact_paths(changed)
    header = _HEADER.match(subject.strip())
    if not shipped or header is None:
        return ""
    if header["bang"] or header["type"].lower() in RELEASE_TYPES:
        return ""
    return (
        f"PR title {subject!r} changes shipped catalog artifacts ({_listed(shipped)}): "
        f"title it {', '.join(RELEASE_TYPES)} or a breaking '!' so the release bumps, "
        f"got {header['type']!r}"
    )


def _listed(paths: tuple[str, ...]) -> str:
    """The first :data:`_LISTED` paths, comma-separated, with a count of the rest."""
    head = ", ".join(paths[:_LISTED])
    rest = len(paths) - _LISTED
    return f"{head} and {rest} more" if rest > 0 else head
