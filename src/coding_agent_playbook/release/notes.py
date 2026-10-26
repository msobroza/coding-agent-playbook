"""The per-release notes: ``catalog/releases/<version>/notes.md`` (ADR 0012).

The notes are the one changelog. They name changed artifacts by kind and id
(from the manifest digest diff, ``release.changes``) and pull requests by number,
with a breaking section, and nothing else: no commit subjects (they are free
text a reviewer never approved as release copy) and no URLs (the package ships
offline and forge-neutral).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from coding_agent_playbook.release.changes import ArtifactChanges
    from coding_agent_playbook.release.manifest import ManifestEntry

__all__ = ["CommitMessage", "PullRequestRef", "pull_requests", "render_notes"]

#: ``... (#123)`` at the end of a squash-merge subject.
_SQUASH_NUMBER: Final = re.compile(r"\(#(\d+)\)\s*$")
#: GitHub's merge-commit subject.
_MERGE_NUMBER: Final = re.compile(r"^Merge pull request #(\d+)\b")
#: A Conventional Commit header with ``!`` before the colon: ``feat(x)!: ...``.
_BANG_HEADER: Final = re.compile(r"^\w+(\([^)]*\))?!:")
_BREAKING_FOOTER: Final = re.compile(r"^BREAKING[ -]CHANGE:", re.MULTILINE)
_NONE: Final = "None."


@dataclass(frozen=True)
class CommitMessage:
    """One first-parent commit of the release range: its subject and body."""

    subject: str
    body: str = ""


@dataclass(frozen=True, order=True)
class PullRequestRef:
    """A pull request merged into the release, by number, and whether it breaks consumers."""

    number: int
    breaking: bool = False


def pull_requests(commits: Iterable[CommitMessage]) -> list[PullRequestRef]:
    """The pull requests ``commits`` merged, sorted by number; commits without one are skipped.

    A squash subject ends in ``(#N)``; a merge commit says ``Merge pull request #N``.
    A ``!`` header or a ``BREAKING CHANGE:`` footer marks the pull request breaking.

    Example::

        >>> pull_requests([CommitMessage("feat(x)!: drop y (#7)")])
        [PullRequestRef(number=7, breaking=True)]
    """
    found: dict[int, bool] = {}
    for commit in commits:
        number = _number(commit.subject)
        if number is not None:
            found[number] = found.get(number, False) or _is_breaking(commit)
    return [PullRequestRef(number, breaking) for number, breaking in sorted(found.items())]


def _number(subject: str) -> int | None:
    match = _SQUASH_NUMBER.search(subject) or _MERGE_NUMBER.match(subject)
    return int(match.group(1)) if match else None


def _is_breaking(commit: CommitMessage) -> bool:
    return bool(_BANG_HEADER.match(commit.subject) or _BREAKING_FOOTER.search(commit.body))


def render_notes(
    version: str,
    *,
    previous: str | None,
    changes: ArtifactChanges | None,
    pulls: Sequence[PullRequestRef],
) -> str:
    """The markdown notes of release ``version``.

    ``previous`` is the previous release's version and ``changes`` the digest
    diff against its manifest; both are ``None`` for the first release.

    Example::

        >>> render_notes("9.9.9", previous=None, changes=None, pulls=[]).splitlines()[0]
        '# Release 9.9.9'
    """
    since = "First release." if previous is None else f"Changes since {previous}."
    lines = [f"# Release {version}", "", since, ""]
    lines += _section("Breaking changes", [f"#{p.number}" for p in pulls if p.breaking])
    lines += _artifact_sections(changes)
    lines += _section("Pull requests", [f"#{p.number}" for p in pulls])
    return "\n".join(lines).rstrip("\n") + "\n"


def _artifact_sections(changes: ArtifactChanges | None) -> list[str]:
    if changes is None:
        return []
    return [
        *_section("Changed artifacts", _labels(changes.changed)),
        *_section("Added artifacts", _labels(changes.added)),
        *_section("Removed artifacts", _labels(changes.removed)),
    ]


def _labels(entries: Sequence[ManifestEntry]) -> list[str]:
    """``kind `id``` per entry, with a plugin's layer named; one line per artifact."""
    return sorted({_label(entry) for entry in entries})


def _label(entry: ManifestEntry) -> str:
    label = f"{entry.kind} `{entry.id}`"
    if entry.layer == ENGINE_PACKAGE:
        return label
    return f"{label} ({entry.layer.rsplit('.', 1)[-1]})"


def _section(title: str, items: Sequence[str]) -> list[str]:
    body = [f"- {item}" for item in items] or [_NONE]
    return [f"## {title}", "", *body, ""]
