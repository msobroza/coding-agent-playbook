"""Named fakes for external I/O, shared across the test suite.

``FakeGitClient`` stands in for :class:`coding_agent_playbook.git_client.SubprocessGitClient`
so ``playbook sync`` tests never shell out to git (and never monkeypatch
:mod:`subprocess`). ``None`` models "git cannot answer" (not a repository, git
missing, timeout) exactly like the real client. :func:`pre_gate_validate` stands
in for ``playbook sync``'s validate gate.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from coding_agent_playbook.commands._validation import ValidationError
    from coding_agent_playbook.orchestrator import SyncContext


@dataclass
class FakeGitClient:
    """In-memory :class:`~coding_agent_playbook.git_client.GitClient`.

    ``tracked`` is the set of tracked repo-relative paths, in the index's own
    spelling (``None`` = git cannot answer); ``staged`` is what ``staged_paths``
    returns verbatim. Every call is recorded in ``calls`` so tests can assert
    what was asked.

    Matching models git on macOS (``core.precomposeunicode``): a decomposed (NFD)
    query matches its precomposed (NFC) index entry, and the index spelling is
    returned; ``ignore_case=True`` models the ``:(icase)`` pathspec magic.
    """

    tracked: set[str] | None = field(default_factory=set)
    staged: list[str] | None = field(default_factory=list)
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def tracked_paths(
        self, repo_root: Path, paths: Sequence[str], *, ignore_case: bool = False
    ) -> list[str] | None:
        self.calls.append(("tracked_paths", tuple(paths)))
        if self.tracked is None:
            return None

        def key(path: str) -> str:
            nfc = unicodedata.normalize("NFC", path)
            return nfc.casefold() if ignore_case else nfc

        index = {key(path): path for path in sorted(self.tracked)}
        return [index[key(path)] for path in paths if key(path) in index]

    def staged_paths(self, repo_root: Path) -> list[str] | None:
        self.calls.append(("staged_paths", ()))
        return None if self.staged is None else list(self.staged)


def pre_gate_validate(ctx: SyncContext) -> list[ValidationError]:
    """A validate gate that finds nothing: models a sync by an engine older than the gate.

    ``playbook sync`` refuses content ``playbook validate`` rejects (prK §P P8),
    such as a skill ``id: Demo`` that breaks the Agent Skills name rule. Output
    from a release before the gate can still hold it, so regression tests seed
    that output with ``execute(repo, validate=pre_gate_validate)``.
    """
    return []
