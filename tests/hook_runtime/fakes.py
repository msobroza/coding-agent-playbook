"""Named fakes for the hook runtime's seams (specs/prK-lifecycle-hooks.md §D.9).

Each fake stands in for one ``RuntimeDeps`` port, so a test passes it in and
never patches a module:

- ``FakeProc`` for ``proc.SubprocessProc``: replays scripted results, records
  every call, and raises ``AssertionError("unexpected subprocess: <argv0>")``
  for a call nobody scripted, so a stray spawn fails loudly.
- ``FakeGit`` for ``git.SafeGit``: scripted answers (range queries included),
  every call recorded.
- ``FakeClock`` for ``deps.SystemClock``: time moves only when told to.
- ``FakeTrustStore`` for ``security.trust.TrustStore``: in-memory approvals.
- ``FakeHandlerResolver`` for ``registry.resolve_handler``: hook id -> handler.
- ``FakeStageRunner`` for ``stop.runner.PinnedStageRunner``: a scripted
  ``ToolRun`` per logical tool (timeouts and crashes included), calls recorded.
- ``FakeRuff`` for the pinned ruff behind ``RuntimeDeps.proc`` (and the
  sync-time rule probe): scripted D1 JSON, M1/M2 rewrites of the file, the
  HEAD format verdict and ``ruff rule`` answers; any other program fails.
- ``FakeComplexipy`` for the pinned complexipy behind ``RuntimeDeps.proc``:
  scripted ``--plain`` rows per measured source text; any other program fails.
- ``FakeTimer`` for ``deps.thread_timer`` (fires only when told, or on start)
  and ``FakeExit`` / ``fake_exit`` for ``os._exit``: the watchdog runs
  in-process and its exit surfaces as an exception.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

from coding_agent_playbook.hook_runtime.dispatch.proc import ProcResult, ProcTimeout
from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerResolutionError, Untrusted
from coding_agent_playbook.hook_runtime.git.parse import DiffLines
from coding_agent_playbook.hook_runtime.stop.runner import ToolRun

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from coding_agent_playbook.hook_runtime.config.guard_config import HookRecord
    from coding_agent_playbook.hook_runtime.dispatch.event import EventName
    from coding_agent_playbook.hook_runtime.dispatch.registry import HandlerFn, ResolveContext
    from coding_agent_playbook.hook_runtime.git.safe_git import AddedLine, Fingerprint, LoggedCommit
    from coding_agent_playbook.security.trust import HandlerApproval

type ArgvMatch = Sequence[str] | Callable[[tuple[str, ...]], bool]


@dataclass(frozen=True)
class FakeCall:
    """One recorded ``FakeProc.run`` call."""

    argv: tuple[str, ...]
    timeout: float
    env: Mapping[str, str] | None
    input: bytes | None
    cwd: str | None


@dataclass
class _Scripted:
    match: ArgvMatch
    result: ProcResult | None  # None: the call times out


def _matches(match: ArgvMatch, argv: tuple[str, ...]) -> bool:
    """A callable decides; a sequence needs ``argv[0]`` (or its basename), then its rest in order."""
    if callable(match):
        return match(argv)
    head, *rest = match
    if not argv or head not in (argv[0], os.path.basename(argv[0])):
        return False
    remaining = iter(argv[1:])
    return all(token in remaining for token in rest)  # in-order subsequence


@dataclass
class FakeProc:
    """In-memory ``ProcPort``: scripted results, recorded calls, loud on surprises.

    ``script(["git", "status"], stdout=b"...")`` answers any call whose argv
    starts with ``git`` (or a path ending in it) and contains ``status`` later,
    in order (so the hardening flags ``SafeGit`` prepends do not get in the
    way); the first matching script wins, and scripts are reusable.
    ``programs`` is what ``which`` finds.
    """

    programs: dict[str, str] = field(default_factory=dict)
    calls: list[FakeCall] = field(default_factory=list)
    _scripts: list[_Scripted] = field(default_factory=list)

    def script(
        self,
        match: ArgvMatch,
        *,
        stdout: bytes = b"",
        stderr: bytes = b"",
        returncode: int = 0,
        timeout: bool = False,
    ) -> None:
        """Answer calls matching ``match`` (see the class docstring)."""
        result = None if timeout else ProcResult(("<scripted>",), returncode, stdout, stderr)
        self._scripts.append(_Scripted(match, result))

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float,
        env: Mapping[str, str] | None = None,
        input: bytes | None = None,
        cwd: str | None = None,
    ) -> ProcResult:
        """Replay the first matching script, or fail the test."""
        command = tuple(argv)
        self.calls.append(
            FakeCall(command, timeout, None if env is None else dict(env), input, cwd)
        )
        scripted = next((s for s in self._scripts if _matches(s.match, command)), None)
        if scripted is None:
            raise AssertionError(f"unexpected subprocess: {command[0] if command else '<empty>'}")
        if scripted.result is None:
            raise ProcTimeout(command[0], timeout)
        return ProcResult(command, *_payload(scripted.result))

    def which(self, name: str, *, path: str | None = None) -> str | None:
        """``programs[name]``, else ``None``; ``path`` is ignored."""
        return self.programs.get(name)


def _payload(result: ProcResult) -> tuple[int, bytes, bytes]:
    return result.returncode, result.stdout, result.stderr


@dataclass
class FakeGit:
    """In-memory ``GitPort``: each answer is a field; ``errors`` raises per method name.

    The range answers are keyed by their arguments: ``merge_bases[(left, right)]``,
    ``range_diffs[(base, head)]`` (empty when absent), ``revision_blobs[(rev, path)]``.
    ``worktree_diffs[base]`` is ``diff_worktree``'s answer; ``archives[rev]`` maps
    repo paths to the bytes ``archive_to`` writes (``skip`` honoured, as in git).
    ``grep_word`` finds exactly the ``test_words``; ``rev_commit`` reads ``commits``.
    ``upstream`` answers ``upstream_ref``; ``unpushed_lines`` the ``unpushed`` patch;
    ``porcelain_status`` the ``status`` entries (``(XY, path)``); ``remote_urls`` the
    ``remotes`` map (name -> URL), as ``git remote -v`` lists it; ``commit_log`` the
    ``logs[rev_range]`` commits, newest first (empty when absent); ``range_paths``
    the ``changed[(base, head)]`` paths (empty when absent).
    """

    head_tree_id: str | None = None
    fingerprint_value: Fingerprint | None = None
    added: tuple[AddedLine, ...] = ()
    head_blobs: dict[str, bytes] = field(default_factory=dict)
    untracked: tuple[str, ...] = ()
    symbolic_refs: dict[str, str] = field(default_factory=dict)
    config: dict[str, str] = field(default_factory=dict)
    default_branch_name: str | None = None
    merge_bases: dict[tuple[str, str], str] = field(default_factory=dict)
    range_diffs: dict[tuple[str, str], DiffLines] = field(default_factory=dict)
    revision_blobs: dict[tuple[str, str], bytes] = field(default_factory=dict)
    worktree_diffs: dict[str, DiffLines] = field(default_factory=dict)
    archives: dict[str, dict[str, bytes]] = field(default_factory=dict)
    test_words: set[str] = field(default_factory=set)
    commits: dict[str, str] = field(default_factory=dict)
    upstream_ref: str | None = None
    unpushed: DiffLines = field(default_factory=DiffLines)
    status: tuple[tuple[str, str], ...] = ()
    remotes: dict[str, str] = field(default_factory=dict)
    logs: dict[str, tuple[LoggedCommit, ...]] = field(default_factory=dict)
    changed: dict[tuple[str, str], tuple[str, ...]] = field(default_factory=dict)
    errors: dict[str, Exception] = field(default_factory=dict)
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def _record(self, method: str, *args: str) -> None:
        self.calls.append((method, args))
        if method in self.errors:
            raise self.errors[method]

    def head_tree(self) -> str | None:
        self._record("head_tree")
        return self.head_tree_id

    def fingerprint(self) -> Fingerprint | None:
        self._record("fingerprint")
        return self.fingerprint_value

    def diff_added(self) -> tuple[AddedLine, ...]:
        self._record("diff_added")
        return self.added

    def cat_head(self, repo_rel: str) -> bytes | None:
        self._record("cat_head", repo_rel)
        return self.head_blobs.get(repo_rel)

    def ls_untracked(self) -> tuple[str, ...]:
        self._record("ls_untracked")
        return self.untracked

    def symbolic_ref(self, ref: str) -> str | None:
        self._record("symbolic_ref", ref)
        return self.symbolic_refs.get(ref)

    def config_value(self, key: str) -> str | None:
        self._record("config_value", key)
        return self.config.get(key)

    def default_branch(self) -> str | None:
        self._record("default_branch")
        return self.default_branch_name

    def merge_base(self, left: str, right: str) -> str | None:
        self._record("merge_base", left, right)
        return self.merge_bases.get((left, right))

    def diff_range(self, base: str, head: str) -> DiffLines:
        self._record("diff_range", base, head)
        return self.range_diffs.get((base, head), DiffLines())

    def show(self, rev: str, repo_rel: str) -> bytes | None:
        self._record("show", rev, repo_rel)
        return self.revision_blobs.get((rev, repo_rel))

    def diff_worktree(self, base: str) -> DiffLines:
        self._record("diff_worktree", base)
        return self.worktree_diffs.get(base, DiffLines())

    def archive_to(self, rev: str, dest: str, *, skip: Callable[[str], bool]) -> int:
        self._record("archive_to", rev)
        written = 0
        for rel, data in self.archives.get(rev, {}).items():
            if skip(rel):
                continue
            target = Path(dest, rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            written += 1
        return written

    def grep_word(self, word: str, roots: Sequence[str]) -> bool:
        self._record("grep_word", word, *roots)
        return word in self.test_words

    def rev_commit(self, rev: str) -> str | None:
        self._record("rev_commit", rev)
        return self.commits.get(rev)

    def upstream(self) -> str | None:
        self._record("upstream")
        return self.upstream_ref

    def unpushed_lines(self, upstream: str | None) -> DiffLines:
        self._record("unpushed_lines", upstream or "")
        return self.unpushed

    def porcelain_status(self) -> tuple[tuple[str, str], ...]:
        self._record("porcelain_status")
        return self.status

    def remote_urls(self) -> tuple[tuple[str, str], ...]:
        self._record("remote_urls")
        return tuple(self.remotes.items())

    def commit_log(self, rev_range: str, *, limit: int) -> tuple[LoggedCommit, ...]:
        self._record("commit_log", rev_range)
        return self.logs.get(rev_range, ())[:limit]

    def range_paths(self, base: str, head: str) -> tuple[str, ...]:
        self._record("range_paths", base, head)
        return self.changed.get((base, head), ())


@dataclass
class FakeClock:
    """A clock that moves only through :meth:`advance`."""

    now: float = 1_791_973_800.0  # 2026-10-14T10:30:00Z
    mono: float = 1_000.0

    def monotonic(self) -> float:
        return self.mono

    def time(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        """Move both clocks forward by ``seconds``."""
        self.mono += seconds
        self.now += seconds


@dataclass
class FakeTrustStore:
    """In-memory ``TrustPort``, with ``security.trust.TrustStore``'s matching rules."""

    handlers: dict[str, HandlerApproval] = field(default_factory=dict)
    executions: set[str] = field(default_factory=set)

    def allows_handler(self, hook_id: str, wanted: HandlerApproval) -> bool:
        approved = self.handlers.get(hook_id)
        return approved is not None and approved.same_code(wanted)

    def allows_execution(self, stages_sha256: str) -> bool:
        return stages_sha256 in self.executions


@dataclass
class FakeHandlerResolver:
    """``HandlerResolver`` from a table: hook id -> handler, ``Untrusted`` or an exception.

    A hook missing from the table fails resolution, as an unregistered builtin does.
    ``calls`` records ``(hook_id, event)`` in order.
    """

    handlers: dict[str, HandlerFn | Untrusted | Exception] = field(default_factory=dict)
    calls: list[tuple[str, str]] = field(default_factory=list)

    def __call__(
        self, record: HookRecord, event: EventName, ctx: ResolveContext
    ) -> HandlerFn | Untrusted:
        self.calls.append((record.id, event.value))
        found = self.handlers.get(record.id)
        if found is None:
            raise HandlerResolutionError(f"no handler scripted for {record.id!r}")
        if isinstance(found, Exception):
            raise found
        return found


@dataclass(frozen=True)
class StageCall:
    """One recorded ``FakeStageRunner.run`` call (``cwd``: ``None`` is the worktree root).

    ``env`` is the child environment the stage passed (``None``: inherited).
    """

    tool: str
    args: tuple[str, ...]
    timeout: float
    cwd: str | None
    env: Mapping[str, str] | None = None


type StageAnswer = ToolRun | Exception | Callable[[StageCall], ToolRun]


@dataclass
class FakeStageRunner:
    """In-memory ``StageRunner``: one scripted ``ToolRun`` per logical tool, every call recorded.

    ``script("ruff", returncode=1, stdout=b"[]")`` answers every ``ruff`` run;
    ``timeout=True`` makes it a ``timeout`` skip and ``crash=True`` makes the
    call raise, as a broken tool wrapper would. ``answer("ruff", fn)`` lets
    ``fn(call)`` decide per call (e.g. by ``args`` or ``cwd``). An unscripted
    tool is ``toolchain_missing``. ``calls`` holds every :class:`StageCall`.
    """

    runs: dict[str, StageAnswer] = field(default_factory=dict)
    calls: list[StageCall] = field(default_factory=list)

    def answer(self, tool: str, fn: Callable[[StageCall], ToolRun]) -> None:
        """Answer every run of ``tool`` with ``fn(call)``."""
        self.runs[tool] = fn

    def script(
        self,
        tool: str,
        *,
        returncode: int = 0,
        stdout: bytes = b"",
        stderr: bytes = b"",
        timeout: bool = False,
        crash: bool = False,
    ) -> None:
        """Answer every run of ``tool`` (see the class docstring)."""
        if crash:
            self.runs[tool] = RuntimeError(f"{tool} wrapper crashed")
        elif timeout:
            self.runs[tool] = ToolRun(tool, skip_category="timeout")
        else:
            self.runs[tool] = ToolRun(tool, returncode, stdout, stderr)

    def run(
        self,
        tool: str,
        args: Sequence[str],
        *,
        timeout: float,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> ToolRun:
        call = StageCall(tool, tuple(args), timeout, cwd, None if env is None else dict(env))
        self.calls.append(call)
        found = self.runs.get(tool, ToolRun(tool, skip_category="toolchain_missing"))
        if isinstance(found, Exception):
            raise found
        return found if isinstance(found, ToolRun) else found(call)


@dataclass
class FakeTimer:
    """A ``TimerHandle`` that fires only through :meth:`fire` (or at start, when asked)."""

    interval: float
    function: Callable[[], None]
    fire_on_start: bool = False
    started: bool = False
    cancelled: bool = False
    daemon: bool = True

    def start(self) -> None:
        self.started = True
        if self.fire_on_start:
            self.fire()

    def fire(self) -> None:
        """Run the timer's function now, as the real thread would at the deadline."""
        if not self.cancelled:
            self.function()

    def cancel(self) -> None:
        self.cancelled = True

    def join(self, timeout: float | None = None) -> None:
        return None


@dataclass
class FakeTimers:
    """A ``TimerFactory`` recording every ``FakeTimer`` it made."""

    fire_on_start: bool = False
    made: list[FakeTimer] = field(default_factory=list)

    def __call__(self, interval: float, function: Callable[[], None]) -> FakeTimer:
        timer = FakeTimer(interval, function, fire_on_start=self.fire_on_start)
        self.made.append(timer)
        return timer


def ruff_row(code: str | None, row: int, message: str = "finding") -> dict[str, object]:
    """One D1 diagnostic as ``ruff check --output-format json`` prints it (the parts read)."""
    return {"code": code, "location": {"row": row, "column": 1}, "message": message}


@dataclass
class FakeComplexipy:
    """In-memory ``ProcPort`` for the pinned complexipy: answers by the file it measures.

    A call reads ``<cwd>/<argv[1]>`` (the source the ``cognitive_complexity``
    metric wrote) and prints ``by_source[<that text>]`` as complexipy's
    ``--plain`` rows (none for any other text). Any program other than
    ``complexipy`` fails the test, like ``FakeProc``.
    """

    by_source: dict[str, dict[str, int]] = field(default_factory=dict)
    calls: list[FakeCall] = field(default_factory=list)

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float,
        env: Mapping[str, str] | None = None,
        input: bytes | None = None,
        cwd: str | None = None,
    ) -> ProcResult:
        from tests.fakes import complexipy_plain

        command = tuple(argv)
        self.calls.append(
            FakeCall(command, timeout, None if env is None else dict(env), input, cwd)
        )
        if not command or os.path.basename(command[0]) != "complexipy" or cwd is None:
            raise AssertionError(f"unexpected subprocess: {command[0] if command else '<empty>'}")
        source = Path(cwd, command[1]).read_text(encoding="utf-8")
        return ProcResult(command, 0, complexipy_plain(self.by_source.get(source, {})))

    def which(self, name: str, *, path: str | None = None) -> str | None:
        return None


@dataclass
class FakeRuff:
    """In-memory ``ProcPort`` for the pinned ruff: answers by subcommand, records every argv.

    - D1 (``check ... --output-format json``) prints ``diagnostics`` (rows from
      :func:`ruff_row`), exit ``d1_exit``; its separate ``--preview`` call
      (``preview``) prints ``preview_diagnostics``;
    - the metrics gate's ``ruff_violations`` call (``check ... --stdin-filename
      <label> -``, kind ``metrics``) prints ``by_stdin[<the bytes on stdin>]``
      (``[]`` for any other text);
    - M1 (``check --fix-only``) and M2 (``format``) print the text on stdin
      through ``fix`` / ``reformat`` (identity when ``None``); the path form
      (``-- <path>``) rewrites that file instead;
    - the HEAD check (``format --check ... -``) exits 0 when ``format_clean``;
    - ``rule --all`` prints ``rules`` (exit 2 when ``rule_all`` is off: a ruff
      without the JSON listing) and ``rule <code>`` answers from ``rules``
      (exit 2 for an unknown code).

    ``timeouts`` holds the kinds (:meth:`kind`) that time out. Any program
    other than ``ruff`` fails the test, like ``FakeProc``.
    """

    diagnostics: list[dict[str, object]] = field(default_factory=list)
    preview_diagnostics: list[dict[str, object]] = field(default_factory=list)
    by_stdin: dict[bytes, list[dict[str, object]]] = field(default_factory=dict)
    d1_exit: int = 0
    format_clean: bool = True
    fix: Callable[[str], str] | None = None
    reformat: Callable[[str], str] | None = None
    rules: list[dict[str, object]] = field(default_factory=list)
    rule_all: bool = True
    timeouts: set[str] = field(default_factory=set)
    calls: list[FakeCall] = field(default_factory=list)
    programs: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def kind(args: Sequence[str]) -> str:
        """``d1``, ``preview``, ``metrics``, ``fix``, ``format-check``, ``format``, ``rule-all``
        or ``rule``."""
        head = args[0] if args else ""
        if head == "check":
            if "--fix-only" in args:
                return "fix"
            if "--stdin-filename" in args:
                return "metrics"
            return "preview" if "--preview" in args else "d1"
        if head == "format":
            return "format-check" if "--check" in args else "format"
        return "rule-all" if "--all" in args else head

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float,
        env: Mapping[str, str] | None = None,
        input: bytes | None = None,
        cwd: str | None = None,
    ) -> ProcResult:
        command = tuple(argv)
        self.calls.append(
            FakeCall(command, timeout, None if env is None else dict(env), input, cwd)
        )
        if not command or not os.path.basename(command[0]).startswith("ruff"):
            raise AssertionError(f"unexpected subprocess: {command[0] if command else '<empty>'}")
        args = command[1:]
        kind = self.kind(args)
        if kind in self.timeouts:
            raise ProcTimeout(command[0], timeout)
        if kind == "metrics":
            return ProcResult(command, 0, json.dumps(self.by_stdin.get(input or b"", [])).encode())
        if kind in ("fix", "format") and args[-1:] == ("-",):
            change = (self.fix if kind == "fix" else self.reformat) or (lambda text: text)
            return ProcResult(command, 0, change((input or b"").decode("utf-8")).encode("utf-8"))
        returncode, stdout = self._answer(kind, args)
        return ProcResult(command, returncode, stdout)

    def which(self, name: str, *, path: str | None = None) -> str | None:
        return self.programs.get(name)

    def argvs(self, kind: str) -> list[tuple[str, ...]]:
        """The ruff arguments (after the program) of every call of ``kind``, in order."""
        return [c.argv[1:] for c in self.calls if self.kind(c.argv[1:]) == kind]

    def kinds(self) -> list[str]:
        """The kind of every call, in order."""
        return [self.kind(c.argv[1:]) for c in self.calls]

    def _answer(self, kind: str, args: Sequence[str]) -> tuple[int, bytes]:
        if kind == "d1":
            return self.d1_exit, json.dumps(self.diagnostics).encode()
        if kind == "preview":
            return 0, json.dumps(self.preview_diagnostics).encode()
        if kind in ("fix", "format"):
            self._rewrite(args[-1], self.fix if kind == "fix" else self.reformat)
            return 0, b""
        if kind == "format-check":
            return (0 if self.format_clean else 1), b""
        if kind == "rule-all":
            return (0, json.dumps(self.rules).encode()) if self.rule_all else (2, b"")
        return self._rule(args[1] if len(args) > 1 else "")

    def _rule(self, code: str) -> tuple[int, bytes]:
        row = next((r for r in self.rules if r.get("code") == code), None)
        return (2, b"") if row is None else (0, json.dumps(row).encode())

    @staticmethod
    def _rewrite(path: str, change: Callable[[str], str] | None) -> None:
        if change is None:
            return
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(change(text))


class FakeExit(BaseException):
    """Raised by :func:`fake_exit`: a ``BaseException`` so no handler ``except`` swallows it."""

    def __init__(self, code: int) -> None:
        super().__init__(code)
        self.code = code


def fake_exit(code: int) -> NoReturn:
    """``os._exit`` for in-process tests: raises :class:`FakeExit`."""
    raise FakeExit(code)


__all__ = [
    "FakeCall",
    "FakeClock",
    "FakeExit",
    "FakeGit",
    "FakeHandlerResolver",
    "FakeProc",
    "FakeRuff",
    "FakeStageRunner",
    "FakeTimer",
    "FakeTimers",
    "FakeTrustStore",
    "StageCall",
    "fake_exit",
    "ruff_row",
]
