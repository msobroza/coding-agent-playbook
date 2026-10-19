"""Named fakes for external I/O, shared across the test suite.

``FakeGitClient`` stands in for :class:`coding_agent_playbook.sync.git_client.SubprocessGitClient`
so ``playbook sync`` tests never shell out to git (and never monkeypatch
:mod:`subprocess`). ``None`` models "git cannot answer" (not a repository, git
missing, timeout) exactly like the real client. :func:`pre_gate_validate` stands
in for ``playbook sync``'s validate gate. ``FakeProjectFactory`` stands in for
``ProjectHandle.create`` so metrics-gate tests see which test command (and
diff base, timeout, ``--cov`` sources) would run without running a suite; its
``FakeProjectHandle`` serves canned ``RunArtifacts``. ``FakeBaselineGit`` stands in for
:class:`coding_agent_playbook.grading.baseline_git.SubprocessBaselineGit`;
``FakeGitRunner`` stands in for its working-tree reads (``SubprocessGitRunner``).
``FakeHandlerSchemas`` stands in for the hook-handler ``CONFIG_SCHEMA`` registry
(K2) behind :class:`coding_agent_playbook.hooks.resolution.merge.ConfigSchemaLookup`.
``FakePinWriter`` stands in for the ``hook_runtime.config.pin`` writers ``playbook sync``
calls (the interpreter pin and ``machine.json`` under the git dir).
``FakeCiStepRunner`` stands in for :class:`coding_agent_playbook.commands.twins.ci.SubprocessCiStepRunner`
so ``playbook ci`` tests see each step's argv without spawning a child.
``FakeRuffRunner`` stands in for the metrics gate's ``ToolRunner`` (a ruff
subprocess), so ``ruff_violations`` tests script ruff's JSON per source text.
:func:`record_opens` spies on every ``open`` so a scan test can prove a file was never read.
"""

from __future__ import annotations

import io
import json
import os
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from coding_agent_playbook.commands.twins.ci import StepRun
from coding_agent_playbook.grading.baseline_git import BaselineGitError, GitTimeoutError
from coding_agent_playbook.grading.execution_metrics.coverage_xml import CoverageReport
from coding_agent_playbook.grading.execution_metrics.junit import JunitSummary
from coding_agent_playbook.grading.execution_metrics.project import ProjectHandle, RunArtifacts
from coding_agent_playbook.grading.tool_runner import ToolRunError
from coding_agent_playbook.hook_runtime.config.pin import PinResult

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import pytest

    from coding_agent_playbook.hooks.resolution.merge import ConfigKeySpec
    from coding_agent_playbook.validation.context import SyncContext
    from coding_agent_playbook.validation.findings import ValidationError


@dataclass
class FakeGitClient:
    """In-memory :class:`~coding_agent_playbook.sync.git_client.GitClient`.

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


#: The command a :class:`FakeProjectHandle` claims to run; it never runs it.
NO_OP_SUITE_CMD = [sys.executable, "-c", "pass"]


def empty_run() -> RunArtifacts:
    """What an empty, passing suite reports: no tests, no coverage, exit 0."""
    return RunArtifacts(junit=JunitSummary(0, 0, 0, 0, 0), coverage=CoverageReport(), returncode=0)


@dataclass
class FakeProjectHandle(ProjectHandle):
    """A :class:`ProjectHandle` whose suite never runs: each run serves ``artifacts``.

    ``runs`` counts the suite runs the handle was asked for (``run()`` caches
    the first, as the real handle does), so a test can prove a suite ran once.
    """

    artifacts: RunArtifacts = field(default_factory=empty_run)
    runs: int = 0

    def _run_once(self) -> RunArtifacts:
        self.runs += 1
        return self.artifacts


@dataclass(frozen=True)
class SuiteRequest:
    """One handle the metrics gate asked :class:`FakeProjectFactory` for, with its options."""

    root: Path
    test_cmd: list[str] | None
    diff_base: str | None
    timeout_s: float | None
    cov_sources: tuple[str, ...]


@dataclass
class FakeProjectFactory:
    """Stands in for ``ProjectHandle.create`` in :class:`MetricsGateDeps`.

    Records ``(root, test_cmd)`` in ``calls`` and the full request in
    ``requests`` for every handle the gate asks for, then hands out a
    :class:`FakeProjectHandle` serving ``artifacts``, so no project suite ever
    runs. ``calls == []`` proves the gate never built a handle; ``handles``
    keeps each one for its ``runs`` count.
    """

    artifacts: RunArtifacts = field(default_factory=empty_run)
    calls: list[tuple[Path, list[str] | None]] = field(default_factory=list)
    requests: list[SuiteRequest] = field(default_factory=list)
    handles: list[FakeProjectHandle] = field(default_factory=list)

    def __call__(
        self,
        root: Path,
        report_dir: Path,
        test_cmd: list[str] | None = None,
        *,
        diff_base: str | None = None,
        timeout_s: float | None = None,
        cov_sources: Sequence[str] = (),
    ) -> ProjectHandle:
        self.calls.append((root, test_cmd))
        self.requests.append(SuiteRequest(root, test_cmd, diff_base, timeout_s, tuple(cov_sources)))
        handle = FakeProjectHandle(
            root=root,
            test_cmd=list(NO_OP_SUITE_CMD),
            report_dir=report_dir,
            diff_base=diff_base,
            timeout_s=timeout_s,
            artifacts=self.artifacts,
        )
        self.handles.append(handle)
        return handle


@dataclass
class FakeBaselineGit:
    """In-memory :class:`~coding_agent_playbook.grading.baseline_git.BaselineGit`.

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
class FakeGitRunner:
    """In-memory :data:`~coding_agent_playbook.grading.baseline_git.GitRunner`.

    ``outputs`` maps a git subcommand (``"diff"``, ``"ls-files"``, ``"status"``,
    ``"rev-parse"``) to its stdout; an unlisted one prints nothing. A subcommand
    in ``fail_on`` raises :class:`BaselineGitError`. ``calls`` records each argv.
    Build one per gate with :meth:`factory` (the ``MetricsGateDeps`` shape).
    """

    outputs: dict[str, bytes] = field(default_factory=dict)
    fail_on: set[str] = field(default_factory=set)
    calls: list[tuple[str, ...]] = field(default_factory=list)
    roots: list[tuple[Path, float]] = field(default_factory=list)

    def __call__(self, args: Sequence[str]) -> bytes:
        self.calls.append(tuple(args))
        if args[0] in self.fail_on:
            raise BaselineGitError(f"fatal: {args[0]} failed")
        return self.outputs.get(args[0], b"")

    def factory(self, repo_root: Path, timeout_s: float) -> FakeGitRunner:
        """Record the root and bound the gate asked for, then hand out this fake."""
        self.roots.append((repo_root, timeout_s))
        return self


@dataclass
class FakeHandlerSchemas:
    """In-memory :class:`~coding_agent_playbook.hooks.resolution.merge.ConfigSchemaLookup`.

    ``schemas`` maps a builtin handler name to its config key policies; an
    unknown name has none (``{}``), like a handler without a ``CONFIG_SCHEMA``.
    ``domains`` maps a name to the ``[guardrails]`` domain it reads (its
    ``CONFIG_DOMAIN``). ``calls`` records every name asked for key policies, in order.
    """

    schemas: dict[str, dict[str, ConfigKeySpec]] = field(default_factory=dict)
    calls: list[str] = field(default_factory=list)
    domains: dict[str, str] = field(default_factory=dict)

    def key_specs(self, builtin: str) -> Mapping[str, ConfigKeySpec]:
        self.calls.append(builtin)
        return self.schemas.get(builtin, {})

    def config_domain(self, builtin: str) -> str | None:
        return self.domains.get(builtin)


@dataclass
class FakePinWriter:
    """In-memory :class:`~coding_agent_playbook.sync._machine_local.PinWriter`.

    ``git=False`` models a repository outside git (both writers return ``None``).
    The interpreter pin follows the real first-writer-wins rule: ``pinned`` holds
    the current pin, set by the first call (to ``interpreter``) unless already
    set. ``calls`` records ``(method, repo_root)``; ``tools`` the last tool map,
    ``resource_roots`` the last ``pkg:`` id -> directory map and ``drops`` the
    last per-tool dropped codes.
    """

    git: bool = True
    interpreter: str = "/fake/venv/bin/python"
    pinned: str | None = None
    calls: list[tuple[str, Path]] = field(default_factory=list)
    tools: dict[str, list[str]] = field(default_factory=dict)
    resource_roots: dict[str, str] = field(default_factory=dict)
    drops: dict[str, list[str]] = field(default_factory=dict)

    def ensure_interpreter_pin(self, repo_root: Path) -> PinResult | None:
        self.calls.append(("ensure_interpreter_pin", repo_root))
        if not self.git:
            return None
        written = self.pinned is None
        self.pinned = self.pinned or self.interpreter
        return PinResult(Path("/fake/.git/playbook-hooks/interpreter"), self.pinned, written, False)

    def write_machine_pins(
        self,
        repo_root: Path,
        tools: Mapping[str, Sequence[str]],
        engine_version: str,
        resource_roots: Mapping[str, str] | None = None,
        drops: Mapping[str, Sequence[str]] | None = None,
    ) -> Path | None:
        self.calls.append(("write_machine_pins", repo_root))
        self.tools = {name: list(argv) for name, argv in tools.items()}
        self.resource_roots = dict(resource_roots or {})
        self.drops = {name: list(codes) for name, codes in (drops or {}).items()}
        return Path("/fake/.git/playbook-hooks/machine.json") if self.git else None


@dataclass
class FakeCiStepRunner:
    """In-memory :class:`~coding_agent_playbook.commands.twins.ci.CiStepRunner`.

    ``exits`` maps a step's subcommand (``validate``, ``sync``, ``gate-scan``)
    to its exit code, ``None`` for a timeout; unlisted steps exit 0. Any other
    program (the ``cz`` the ``commit-convention`` row runs) is keyed by its
    basename, or by ``cz_exits[<the call's last argument>]`` when listed there.
    ``calls`` records each argv, ``timeouts`` each per-step timeout, in order.
    """

    exits: dict[str, int | None] = field(default_factory=dict)
    cz_exits: dict[str, int | None] = field(default_factory=dict)
    calls: list[tuple[str, ...]] = field(default_factory=list)
    timeouts: list[float] = field(default_factory=list)

    def run(self, argv: Sequence[str], *, cwd: Path, timeout_s: float) -> StepRun:
        self.calls.append(tuple(argv))
        self.timeouts.append(timeout_s)
        if tuple(argv[1:3]) != ("-m", "coding_agent_playbook.cli"):
            program = os.path.basename(argv[0])
            code = self.cz_exits.get(argv[-1], self.exits.get(program, 0))
            return StepRun(code, f"{program} said hello\n")
        subcommand = argv[3]  # after <python> -m coding_agent_playbook.cli
        return StepRun(self.exits.get(subcommand, 0), f"{subcommand} said hello\n")


def ruff_row(code: str | None, row: int = 1, message: str = "") -> dict[str, object]:
    """One ``ruff check --output-format json`` row (``code=None``: a syntax error).

    Example: ``FakeRuffRunner(answers={"x = (": [ruff_row(None)]})``.
    """
    return {"code": code, "location": {"row": row, "column": 1}, "message": message}


@dataclass
class FakeRuffRunner:
    """In-memory ``ToolRunner`` for ``ruff check ... -``: answers by the source on stdin.

    ``answers`` maps a source text to its JSON rows (unlisted sources: ``[]``);
    ``returncode`` is every call's exit; ``timeout`` makes every call raise
    :class:`ToolRunError` as a timed-out subprocess does. ``calls`` records
    ``(argv, stdin text, cwd, timeout_s)``.
    """

    answers: dict[str, list[dict[str, object]]] = field(default_factory=dict)
    returncode: int = 0
    timeout: bool = False
    calls: list[tuple[tuple[str, ...], str, Path | None, float]] = field(default_factory=list)

    def __call__(
        self, argv: Sequence[str], stdin: bytes, cwd: Path | None, timeout_s: float
    ) -> tuple[int, bytes]:
        source = stdin.decode("utf-8")
        self.calls.append((tuple(argv), source, cwd, timeout_s))
        if self.timeout:
            raise ToolRunError(f"{argv[0]} timed out after {timeout_s:g}s")
        return self.returncode, json.dumps(self.answers.get(source, [])).encode()


def record_opens(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Record every path opened through ``open``/``Path.open`` (read or write).

    Example: ``opened = record_opens(monkeypatch); scan(); assert secret not in opened``.
    """
    opened: list[Path] = []
    real_open = io.open

    def spy(file: object, *args: object, **kwargs: object) -> object:
        if isinstance(file, str | Path):
            opened.append(Path(file))
        return real_open(file, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(io, "open", spy)
    monkeypatch.setattr("builtins.open", spy)
    return opened
