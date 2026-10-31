"""``ProjectHandle`` — run the target's test suite once, cache the result (M4).

The execution evaluators (``test_pass_rate``, ``coverage``) both need the same
data: a single run of the project's test suite that emits junit + coverage XML.
:class:`ProjectHandle` owns that run. ``run()`` executes the test command **once**
as an arg-list subprocess (no shell) in ``root``, parses the two XML reports, and
**caches** the resulting :class:`RunArtifacts` so multiple evaluators reading the
same handle never re-run the suite.

No playbook dependency is added: the target project supplies ``pytest`` /
``pytest-cov``; we only parse the standard XML it writes (with stdlib
``xml.etree`` - see :mod:`.junit` and :mod:`.coverage_xml`).

**Isolation.** :meth:`create` builds a default command that runs the target's
pytest in a way that does *not* inherit a surrounding ``pyproject.toml``'s
``addopts`` (e.g. this engine's own ``--cov-fail-under`` / ``filterwarnings``):
``-p no:cacheprovider`` and ``-o addopts=`` clear inherited options (the latter
is the lever that neutralises an inherited config), and ``--cov-config`` pins
coverage to the target. The exit code of the run is *not* asserted here (a
failing suite is a legitimate measurement, not a handle error); only a command
that cannot be *launched* (its program is missing) raises, and so does a suite
that gives no result: it ran past ``timeout_s``, or left no readable junit or
coverage report (:class:`NoSuiteResultError`). A ``-m pytest`` command whose
interpreter lacks pytest starts, then exits 1 with no report, so it is a suite with
no result too: eval scoring checks that toolchain in-process first. A timeout, or
any interrupt such as Ctrl-C, kills the suite's process group, with the
subprocesses its tests started that stayed in it.

**prK §F.1.1 extensions** (keyword-only, defaults byte-identical):
``diff_base`` is the ref ``diff_coverage`` diffs against; ``timeout_s`` bounds
the run (a hook-driven suite must never hang the agent); ``env_overrides``
lets a hook point ``COVERAGE_FILE`` into its state dir, so the run leaves no
new file in the worktree; ``inherit_env=False`` runs the suite with exactly
``env_overrides`` (eval scoring, so agent code sees no caller secret);
:func:`default_test_cmd` takes the interpreter to run (a hook passes the
project's, not the engine's) and the ``--cov`` sources that put coverage.py in
source mode (:func:`import_roots`); ``suite_record`` (eval scoring only) runs
``python -P`` with the engine's record plugin and fails a run whose pytest
session disagrees with its reports (:mod:`.suite_record`).
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol
from xml.etree import ElementTree as ET

from coding_agent_playbook.grading.execution_metrics.coverage_xml import (
    CoverageReport,
    parse_coverage_xml,
)
from coding_agent_playbook.grading.execution_metrics.junit import JunitSummary, parse_junit_xml
from coding_agent_playbook.grading.execution_metrics.suite_record import (
    SUITE_RECORD_COVERAGE_OMIT,
    SUITE_RECORD_ENV,
    SUITE_RECORD_PLUGIN,
    SuiteRecord,
    read_suite_record,
    session_disagreement,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

#: What a truncated or tampered report raises while parsed (``ParseError`` is a
#: ``SyntaxError``, a bad count a ``ValueError``): the run then gives no result.
_UNREADABLE_REPORT: Final = (ET.ParseError, ValueError)


@dataclass(frozen=True)
class RunArtifacts:
    """The parsed outcome of one test-suite run.

    ``junit`` and ``coverage`` are the reduced summaries both execution
    evaluators read; ``returncode`` is the inner pytest exit code (``0`` all
    passed, ``1`` test failures, ``5`` no tests collected, ...). ``record`` is the
    session's own record when the handle asked for one (eval scoring), else ``None``.
    """

    junit: JunitSummary
    coverage: CoverageReport
    returncode: int
    record: SuiteRecord | None = None


class NoSuiteResultError(RuntimeError):
    """The suite ran but gave no result: it timed out, or left no readable junit or coverage report.

    Distinct from a command that cannot start (a plain ``RuntimeError``): the
    suite started, so the cause is usually its own, for example an endless test or
    a ``conftest.py`` that raises, and eval scoring fails every execution check with
    :attr:`reason`. A missing pytest looks the same from outside, which is why eval
    scoring checks its toolchain in this process before the run.

    Example::

        >>> NoSuiteResultError("test command timed out", reason="it timed out after 3 s").reason
        'it timed out after 3 s'
    """

    def __init__(self, message: str, *, reason: str) -> None:
        super().__init__(message)
        #: Why, in a few words with no command or output: fit for a committed report.
        self.reason = reason


def default_test_cmd(
    report_dir: Path,
    *,
    python: str | None = None,
    cov_sources: Sequence[str] = (),
    recorded: bool = False,
) -> list[str]:
    """The default pytest command writing junit + coverage XML into ``report_dir``.

    Uses ``<python> -m pytest`` (default ``sys.executable``, the active
    interpreter). ``-p no:cacheprovider`` and ``-o addopts=`` neutralise any
    inherited ``addopts`` from a surrounding config; ``--cov-config`` is pinned
    to the empty config :meth:`ProjectHandle.create` writes so the target's
    coverage is measured without picking up an outer ``[tool.coverage]`` table.
    Each of ``cov_sources`` becomes ``--cov=<source>`` instead of the bare
    ``--cov``, so coverage.py also reports never-imported files, at 0%.
    ``recorded`` adds ``-P`` (the cwd is not ``sys.path[0]``, so a planted
    ``pytest.py`` cannot shadow pytest) and loads the engine's record plugin, so
    ``python`` must be an interpreter that has the engine installed.

    Example::

        >>> default_test_cmd(Path("r"), python="py", cov_sources=["src"])[:5]
        ['py', '-m', 'pytest', '--junitxml=r/junit.xml', '--cov=src']
    """
    junit = report_dir / "junit.xml"
    cov = report_dir / "coverage.xml"
    cov_config = report_dir / "coveragerc"
    cov_flags = [f"--cov={source}" for source in cov_sources] or ["--cov"]
    safe_path = ["-P"] if recorded else []
    plugin = ["-p", SUITE_RECORD_PLUGIN] if recorded else []
    return [
        python or sys.executable,
        *safe_path,
        "-m",
        "pytest",
        f"--junitxml={junit}",
        *cov_flags,
        f"--cov-report=xml:{cov}",
        f"--cov-config={cov_config}",
        "-o",
        "addopts=",
        "-p",
        "no:cacheprovider",
        "-q",
        *plugin,
    ]


def import_roots(root: Path) -> tuple[str, ...]:
    """The directory the project's code imports from, as ``--cov`` sources: ``src`` or ``.``.

    A ``src/`` holding Python (a module, or a package one level down) is the
    src layout; anything else is flat, imported from the root. One source per
    project, never one per package: coverage.py names each file relative to
    the ``<source>`` holding it, so two packages' ``__init__.py`` would share a
    name and one would be dropped from the report.

    Example::

        >>> import_roots(Path("/repo/with/src-layout"))  # doctest: +SKIP
        ('src',)
    """
    src = root / "src"
    if src.is_dir() and (any(src.glob("*.py")) or any(src.glob("*/*.py"))):
        return ("src",)
    return (".",)


@dataclass
class ProjectHandle:
    """A runnable project root + its resolved test command + a report dir.

    Construct via :meth:`create` for the isolated default command, or directly
    with an explicit ``test_cmd`` (e.g. a user ``--test-cmd``). ``run()`` is
    idempotent: the first call runs the suite and caches :class:`RunArtifacts`;
    later calls return the same object.
    """

    root: Path
    test_cmd: list[str]
    report_dir: Path
    #: Reruns allowed for the flaky-tolerant pass rate (``0`` ⇒ single run).
    flaky_retries: int = 0
    #: The ref ``diff_coverage`` diffs against; ``None`` (a baseline handle) yields nothing.
    diff_base: str | None = None
    #: Bound on one suite run, in seconds (``None``: unbounded).
    timeout_s: float | None = None
    #: Environment variables set on top of the inherited environment for the run.
    env_overrides: Mapping[str, str] = field(default_factory=dict)
    #: The run must leave a junit report whatever its exit code; the default command writes one.
    require_report: bool = False
    #: Start from the caller's environment; ``False`` runs with exactly :attr:`env_overrides`.
    inherit_env: bool = True
    #: Where the record plugin writes the session's record; ``None``: no record is read.
    suite_record: Path | None = None
    _artifacts: RunArtifacts | None = field(default=None, init=False, repr=False)
    _no_result: NoSuiteResultError | None = field(default=None, init=False, repr=False)

    @classmethod
    def create(
        cls,
        root: Path,
        report_dir: Path,
        test_cmd: list[str] | None = None,
        flaky_retries: int = 0,
        *,
        diff_base: str | None = None,
        timeout_s: float | None = None,
        env_overrides: Mapping[str, str] | None = None,
        python: str | None = None,
        cov_sources: Sequence[str] = (),
        inherit_env: bool = True,
        suite_record: Path | None = None,
    ) -> ProjectHandle:
        """Build a handle, defaulting to the isolated pytest command.

        Creates ``report_dir`` and writes an empty coverage config there so the
        default command's ``--cov-config`` resolves without inheriting an outer
        ``[tool.coverage]`` table. ``flaky_retries`` (default ``0``) enables the
        flaky-tolerant pass rate (see :meth:`best_pass_rate`). ``python`` and
        ``cov_sources`` shape the default command only; an explicit
        ``test_cmd`` runs exactly as given. Only the default command must leave
        a junit report (:attr:`require_report`): an explicit one may not write it.
        ``inherit_env=False`` drops the caller's environment (:attr:`inherit_env`).
        ``suite_record`` (:attr:`suite_record`) names the record path to the plugin
        through ``env_overrides``, has the default command load it, and omits the
        plugin from coverage, so the candidate's totals and sources stay its own.

        Example::

            >>> ProjectHandle.create(root, report_dir, timeout_s=300).timeout_s  # doctest: +SKIP
            300
        """
        require_report = test_cmd is None
        report_dir = Path(report_dir)
        report_dir.mkdir(parents=True, exist_ok=True)
        # A present coverage config (blank, or omitting the plugin) beats outer discovery.
        (report_dir / "coveragerc").write_text(_coveragerc(suite_record), encoding="utf-8")
        if test_cmd is None:
            recorded = suite_record is not None
            test_cmd = default_test_cmd(
                report_dir, python=python, cov_sources=cov_sources, recorded=recorded
            )
        return cls(
            root=Path(root),
            test_cmd=list(test_cmd),
            report_dir=report_dir,
            flaky_retries=flaky_retries,
            diff_base=diff_base,
            timeout_s=timeout_s,
            env_overrides=_record_env(env_overrides, suite_record),
            require_report=require_report,
            inherit_env=inherit_env,
            suite_record=suite_record,
        )

    def run(self) -> RunArtifacts:
        """Run the suite once (cached) and return the parsed artifacts.

        Raises :class:`RuntimeError` when the command cannot be launched (e.g.
        the program is missing) - distinct from a *failing* suite, which is a
        valid measurement with a non-zero ``returncode``. The result is cached:
        ``coverage`` and ``test_pass_rate`` reading the same handle share this
        one run (no double execution). A run with no result is cached too: a later
        call re-raises its :class:`NoSuiteResultError` rather than pay the timeout again.
        """
        if self._no_result is not None:
            raise self._no_result
        if self._artifacts is None:
            try:
                self._artifacts = self._run_once()
            except NoSuiteResultError as exc:
                self._no_result = exc
                raise
        return self._artifacts

    @property
    def no_result(self) -> NoSuiteResultError | None:
        """Why the cached run gave no result; ``None`` when it gave one or has not run."""
        return self._no_result

    def best_pass_rate(self) -> float:
        """Flaky-tolerant pass rate: the *best* across the cached run + retries.

        Returns the cached run's pass rate when ``flaky_retries == 0`` (the
        deterministic default). Otherwise, while the best-so-far rate is below
        ``1.0``, the suite is rerun up to ``flaky_retries`` extra times and the
        maximum pass rate observed is returned - so a test that passes on a retry
        no longer counts as a failure. These reruns do **not** disturb the cached
        :meth:`run` artifacts that ``coverage`` reads (one coverage run, many
        attempts at the rate), and a retry with no result ends the retries.
        """
        best = self.run().junit.pass_rate()
        attempts = max(0, self.flaky_retries)
        for _ in range(attempts):
            if best >= 1.0:
                break
            rate = self._retry_pass_rate()
            if rate is None:
                break
            best = max(best, rate)
        return best

    def _retry_pass_rate(self) -> float | None:
        """One uncached rerun's pass rate; ``None`` when it gave no result.

        Why ``None`` and not the error: the cached run already gave a rate and
        coverage, and a retry that hangs must not throw both away.
        """
        try:
            return self._run_once().junit.pass_rate()
        except NoSuiteResultError:
            return None

    def _run_once(self) -> RunArtifacts:
        """Execute the test command once and parse its reports (uncached).

        Raises :class:`RuntimeError` when the command cannot be launched, and
        :class:`NoSuiteResultError` when it runs past :attr:`timeout_s` or leaves
        no readable junit or coverage report (see :meth:`_check_result`), or its
        session disagrees with them (:meth:`_session_record`).
        """
        self.report_dir.mkdir(parents=True, exist_ok=True)
        if self.suite_record is not None:
            # Every run, retries included: a leftover record must never pass for this one.
            self.suite_record.unlink(missing_ok=True)
        env = self._child_env()
        try:
            proc = _run_in_session(self.test_cmd, cwd=self.root, env=env, timeout_s=self.timeout_s)
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"could not run the test command {self.test_cmd!r}: {exc}. "
                "Is pytest installed in the target environment?"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise NoSuiteResultError(
                f"test command timed out after {exc.timeout:g}s: {self.test_cmd!r}; "
                "raise [metrics] test_timeout_s for a slow suite",
                reason=f"it timed out after {exc.timeout:g} s",
            ) from exc

        junit = self._read_junit()
        coverage = self._read_coverage()
        self._check_result(junit, proc)
        record = self._session_record(junit, proc.returncode)
        return RunArtifacts(
            junit=junit, coverage=coverage, returncode=proc.returncode, record=record
        )

    def _session_record(self, junit: JunitSummary, returncode: int) -> SuiteRecord | None:
        """The run's session record; :class:`NoSuiteResultError` when it disagrees with the run.

        ``None`` when the handle reads no record. Checked after :meth:`_check_result`,
        so its "no junit report" reasons win.
        """
        if self.suite_record is None:
            return None
        record = read_suite_record(self.suite_record)
        reason = session_disagreement(record, junit, returncode, engine_pid=os.getpid())
        if reason is not None:
            raise NoSuiteResultError(
                f"the suite's pytest session disagrees with its reports: {reason}", reason=reason
            )
        return record

    def _child_env(self) -> dict[str, str] | None:
        """The suite's environment; ``None`` inherits the caller's unchanged."""
        if not self.inherit_env:
            return dict(self.env_overrides)
        return {**os.environ, **self.env_overrides} if self.env_overrides else None

    def _check_result(self, junit: JunitSummary, proc: subprocess.CompletedProcess[str]) -> None:
        """Raise :class:`NoSuiteResultError` when ``proc`` left no junit report to read.

        A non-zero exit with *no* junit usually means pytest itself failed to
        start (bad args, a ``conftest.py`` that raises) rather than test
        failures, so an empty report must not read as "all passed". With
        :attr:`require_report` any exit counts: an ``os._exit(0)`` in a test or
        ``conftest.py`` ends pytest before it writes the report.
        """
        missing = self.require_report and not (self.report_dir / "junit.xml").is_file()
        if not missing and (junit.total > 0 or proc.returncode in (0, 5)):
            return
        detail = (proc.stderr or proc.stdout or "").strip()
        raise NoSuiteResultError(
            f"test command exited {proc.returncode} with no junit report; "
            f"the suite may not be runnable. Output:\n{detail}",
            reason=f"it exited {proc.returncode} with no junit report",
        )

    def _read_junit(self) -> JunitSummary:
        path = self.report_dir / "junit.xml"
        if not path.is_file():
            return JunitSummary(passed=0, failed=0, errors=0, skipped=0, total=0)
        return _parsed(path, parse_junit_xml)

    def _read_coverage(self) -> CoverageReport:
        path = self.report_dir / "coverage.xml"
        if not path.is_file():
            return CoverageReport()
        return _parsed(path, parse_coverage_xml)


def _coveragerc(suite_record: Path | None) -> str:
    """The coverage config :meth:`ProjectHandle.create` writes: empty, or omitting the plugin."""
    if suite_record is None:
        return "[run]\n"
    return f"[run]\nomit =\n    {SUITE_RECORD_COVERAGE_OMIT}\n"


def _record_env(overrides: Mapping[str, str] | None, suite_record: Path | None) -> dict[str, str]:
    """``overrides``, plus the variable naming ``suite_record`` to the plugin when one is set."""
    env = dict(overrides or {})
    if suite_record is not None:
        env[SUITE_RECORD_ENV] = str(suite_record)
    return env


def _parsed[R](path: Path, parse: Callable[[str], R]) -> R:
    """``parse`` over ``path``'s text; an unreadable report is :class:`NoSuiteResultError`.

    Why: a truncated report raised ``ParseError``, which no caller catches, so a
    candidate's suite could abort a whole ``eval --record`` run.
    """
    try:
        return parse(path.read_text(encoding="utf-8"))
    except _UNREADABLE_REPORT as exc:
        raise NoSuiteResultError(
            f"the suite's {path.name} cannot be read: {exc}",
            reason=f"its {path.name} report cannot be read",
        ) from exc


def _run_in_session(
    argv: Sequence[str], *, cwd: Path, env: Mapping[str, str] | None, timeout_s: float | None
) -> subprocess.CompletedProcess[str]:
    """``argv`` with captured text output, in a session and process group of its own on POSIX.

    Why: ``subprocess.run`` kills only its child at the timeout, and a test's own
    subprocess kept running after it. The group is killed on a timeout and on any
    other exception, Ctrl-C included: in its own session the suite no longer gets
    the terminal's ``SIGINT``. Then the exception propagates (``TimeoutExpired``
    for a timeout). It waits for the child rather than draining its pipes, as
    ``subprocess.run`` does on POSIX: a process that left the group can hold them.

    Example::

        >>> _run_in_session(["true"], cwd=Path("."), env=None, timeout_s=5).returncode
        0
    """
    posix = os.name == "posix"
    with subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=posix,
    ) as proc:
        try:
            stdout, stderr = proc.communicate(timeout=timeout_s)
        except BaseException:
            _kill_session(proc, posix=posix)
            proc.wait()
            raise
    return subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr)


def _kill_session(proc: subprocess.Popen[str], *, posix: bool) -> None:
    """Kill ``proc``'s process group on POSIX, then ``proc`` itself.

    Why both: Windows has no ``killpg``, and on macOS ``killpg`` fails with
    ``EPERM`` once the group holds only the leader's zombie, while a process that
    left the group still holds the pipes. ``proc.kill`` is a no-op on a reaped child.
    """
    if posix:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(proc.pid, signal.SIGKILL)
    proc.kill()


class ProjectFactory(Protocol):
    """Builds the :class:`ProjectHandle` a suite run measures (``ProjectHandle.create``).

    ``diff_base`` is set on the candidate handle only; ``timeout_s`` bounds the
    run; ``cov_sources`` shape the default command (never an explicit one).
    """

    def __call__(
        self,
        root: Path,
        report_dir: Path,
        test_cmd: list[str] | None = None,
        *,
        diff_base: str | None = None,
        timeout_s: float | None = None,
        cov_sources: Sequence[str] = (),
    ) -> ProjectHandle: ...
