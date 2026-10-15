"""Named fakes for external I/O, shared across the test suite.

``FakeGitClient`` stands in for :class:`coding_agent_playbook.git_client.SubprocessGitClient`
so ``playbook sync`` tests never shell out to git (and never monkeypatch
:mod:`subprocess`). ``None`` models "git cannot answer" (not a repository, git
missing, timeout) exactly like the real client. :func:`pre_gate_validate` stands
in for ``playbook sync``'s validate gate. ``FakeProjectFactory`` stands in for
``ProjectHandle.create`` so metrics-gate tests see which test command would run
without running a suite, and ``FakeBaselineGit`` stands in for
:class:`coding_agent_playbook.evaluators.baseline_git.SubprocessBaselineGit`.
``FakeHandlerSchemas`` stands in for the hook-handler ``CONFIG_SCHEMA`` registry
(K2) behind :class:`coding_agent_playbook.hook_policy.ConfigSchemaLookup`.
"""

from __future__ import annotations

import sys
import unicodedata
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from coding_agent_playbook.evaluators.baseline_git import BaselineGitError, GitTimeoutError
from coding_agent_playbook.evaluators.execution.project import ProjectHandle

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.commands._validation import ValidationError
    from coding_agent_playbook.hook_policy import ConfigKeySpec
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


#: A suite command that runs nothing and writes no report (an empty, passing suite).
NO_OP_SUITE_CMD = [sys.executable, "-c", "pass"]


@dataclass
class FakeProjectFactory:
    """Stands in for ``ProjectHandle.create`` in :class:`MetricsGateDeps`.

    Records ``(root, test_cmd)`` for every handle the gate asks for, then builds
    a real handle that runs :data:`NO_OP_SUITE_CMD`, so no project suite ever
    runs. ``calls == []`` proves the gate never built a handle.
    """

    calls: list[tuple[Path, list[str] | None]] = field(default_factory=list)

    def __call__(
        self, root: Path, report_dir: Path, test_cmd: list[str] | None = None
    ) -> ProjectHandle:
        self.calls.append((root, test_cmd))
        return ProjectHandle.create(root, report_dir, test_cmd=NO_OP_SUITE_CMD)


@dataclass
class FakeBaselineGit:
    """In-memory :class:`~coding_agent_playbook.evaluators.baseline_git.BaselineGit`.

    ``blobs`` maps ``(ref, repo-relative path)`` to the source at that ref, and
    ``commits`` holds the refs that verify. A git command named in
    ``timeout_on`` (``"rev-parse"``, ``"cat-file"``, ``"worktree add"``) raises
    the real :class:`GitTimeoutError` for ``timeout_s``, the bound the gate built
    this fake with; one named in ``fail_on`` raises :class:`BaselineGitError`
    carrying a git-style ``fatal:`` line. ``calls`` records ``(command, ref)`` in
    order. Like the real client, ``remove_worktree`` never raises.
    """

    timeout_s: float = 10.0
    commits: set[str] = field(default_factory=lambda: {"HEAD"})
    blobs: dict[tuple[str, str], str] = field(default_factory=dict)
    timeout_on: set[str] = field(default_factory=set)
    fail_on: set[str] = field(default_factory=set)
    calls: list[tuple[str, str]] = field(default_factory=list)

    def is_commit(self, repo_root: Path, ref: str) -> bool:
        self._record("rev-parse", ref)
        return ref in self.commits

    def read_sources(self, repo_root: Path, ref: str, rel_paths: Sequence[str]) -> dict[str, bytes]:
        self._record("cat-file", ref)
        return {
            rel: self.blobs[(ref, rel)].encode("utf-8")
            for rel in rel_paths
            if (ref, rel) in self.blobs
        }

    def add_worktree(self, repo_root: Path, worktree: Path, ref: str) -> None:
        self._record("worktree add", ref)
        for (blob_ref, rel), source in self.blobs.items():
            if blob_ref == ref:
                (worktree / rel).parent.mkdir(parents=True, exist_ok=True)
                (worktree / rel).write_text(source, encoding="utf-8")

    def remove_worktree(self, repo_root: Path, worktree: Path) -> None:
        self.calls.append(("worktree remove", ""))

    def _record(self, command: str, ref: str) -> None:
        self.calls.append((command, ref))
        if command in self.timeout_on:
            raise GitTimeoutError(command, self.timeout_s)
        if command in self.fail_on:
            raise BaselineGitError(f"fatal: {command} failed for {ref}")


@dataclass
class FakeHandlerSchemas:
    """In-memory :class:`~coding_agent_playbook.hook_policy.ConfigSchemaLookup`.

    ``schemas`` maps a builtin handler name to its config key policies; an
    unknown name has none (``{}``), like a handler without a ``CONFIG_SCHEMA``.
    ``calls`` records every name asked for, in order.
    """

    schemas: dict[str, dict[str, ConfigKeySpec]] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)

    def key_specs(self, builtin: str) -> Mapping[str, ConfigKeySpec]:
        self.calls.append(builtin)
        return self.schemas.get(builtin, {})
