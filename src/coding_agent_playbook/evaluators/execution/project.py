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
that cannot be *launched* (e.g. pytest absent) raises.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from coding_agent_playbook.evaluators.execution.coverage_xml import (
    CoverageReport,
    parse_coverage_xml,
)
from coding_agent_playbook.evaluators.execution.junit import JunitSummary, parse_junit_xml


@dataclass(frozen=True)
class RunArtifacts:
    """The parsed outcome of one test-suite run.

    ``junit`` and ``coverage`` are the reduced summaries both execution
    evaluators read; ``returncode`` is the inner pytest exit code (``0`` all
    passed, ``1`` test failures, ``5`` no tests collected, ...).
    """

    junit: JunitSummary
    coverage: CoverageReport
    returncode: int


def default_test_cmd(report_dir: Path) -> list[str]:
    """The default pytest command writing junit + coverage XML into ``report_dir``.

    Uses ``sys.executable -m pytest`` so the run targets the active interpreter.
    ``-p no:cacheprovider`` and ``-o addopts=`` neutralise any inherited
    ``addopts`` from a surrounding config; ``--cov-config`` is pinned to the
    empty config :meth:`ProjectHandle.create` writes so the target's coverage is
    measured without picking up an outer ``[tool.coverage]`` table.
    """
    junit = report_dir / "junit.xml"
    cov = report_dir / "coverage.xml"
    cov_config = report_dir / "coveragerc"
    return [
        sys.executable,
        "-m",
        "pytest",
        f"--junitxml={junit}",
        "--cov",
        f"--cov-report=xml:{cov}",
        f"--cov-config={cov_config}",
        "-o",
        "addopts=",
        "-p",
        "no:cacheprovider",
        "-q",
    ]


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
    _artifacts: RunArtifacts | None = field(default=None, init=False, repr=False)

    @classmethod
    def create(
        cls,
        root: Path,
        report_dir: Path,
        test_cmd: list[str] | None = None,
        flaky_retries: int = 0,
    ) -> ProjectHandle:
        """Build a handle, defaulting to the isolated pytest command.

        Creates ``report_dir`` and writes an empty coverage config there so the
        default command's ``--cov-config`` resolves without inheriting an outer
        ``[tool.coverage]`` table. ``flaky_retries`` (default ``0``) enables the
        flaky-tolerant pass rate (see :meth:`best_pass_rate`).
        """
        report_dir = Path(report_dir)
        report_dir.mkdir(parents=True, exist_ok=True)
        # Empty coverage config: a present-but-blank file beats outer discovery.
        (report_dir / "coveragerc").write_text("[run]\n", encoding="utf-8")
        cmd = test_cmd if test_cmd is not None else default_test_cmd(report_dir)
        return cls(
            root=Path(root),
            test_cmd=list(cmd),
            report_dir=report_dir,
            flaky_retries=flaky_retries,
        )

    def run(self) -> RunArtifacts:
        """Run the suite once (cached) and return the parsed artifacts.

        Raises :class:`RuntimeError` when the command cannot be launched (e.g.
        the program is missing) - distinct from a *failing* suite, which is a
        valid measurement with a non-zero ``returncode``. The result is cached:
        ``coverage`` and ``test_pass_rate`` reading the same handle share this
        one run (no double execution).
        """
        if self._artifacts is None:
            self._artifacts = self._run_once()
        return self._artifacts

    def best_pass_rate(self) -> float:
        """Flaky-tolerant pass rate: the *best* across the cached run + retries.

        Returns the cached run's pass rate when ``flaky_retries == 0`` (the
        deterministic default). Otherwise, while the best-so-far rate is below
        ``1.0``, the suite is rerun up to ``flaky_retries`` extra times and the
        maximum pass rate observed is returned - so a test that passes on a retry
        no longer counts as a failure. These reruns do **not** disturb the cached
        :meth:`run` artifacts that ``coverage`` reads (one coverage run, many
        attempts at the rate).
        """
        best = self.run().junit.pass_rate()
        attempts = max(0, self.flaky_retries)
        for _ in range(attempts):
            if best >= 1.0:
                break
            best = max(best, self._run_once().junit.pass_rate())
        return best

    def _run_once(self) -> RunArtifacts:
        """Execute the test command once and parse its reports (uncached)."""
        self.report_dir.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                self.test_cmd,
                cwd=self.root,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                f"could not run the test command {self.test_cmd!r}: {exc}. "
                "Is pytest installed in the target environment?"
            ) from exc

        junit = self._read_junit()
        coverage = self._read_coverage()

        # A non-zero exit with *no* junit produced usually means pytest itself
        # failed to start (bad args / collection crash) rather than test
        # failures; surface that as a runtime error so the caller does not treat
        # an empty report as "all passed".
        if junit.total == 0 and proc.returncode not in (0, 5):
            detail = (proc.stderr or proc.stdout or "").strip()
            raise RuntimeError(
                f"test command exited {proc.returncode} with no junit report; "
                f"the suite may not be runnable. Output:\n{detail}"
            )

        return RunArtifacts(junit=junit, coverage=coverage, returncode=proc.returncode)

    def _read_junit(self) -> JunitSummary:
        path = self.report_dir / "junit.xml"
        if not path.is_file():
            return JunitSummary(passed=0, failed=0, errors=0, skipped=0, total=0)
        return parse_junit_xml(path.read_text(encoding="utf-8"))

    def _read_coverage(self) -> CoverageReport:
        path = self.report_dir / "coverage.xml"
        if not path.is_file():
            return CoverageReport()
        return parse_coverage_xml(path.read_text(encoding="utf-8"))
