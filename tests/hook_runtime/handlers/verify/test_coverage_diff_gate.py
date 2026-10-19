"""coverage-diff-gate: the ``coverage`` Stop stage (specs/prK-hook-pack.md §F.1.2).

Every Stop is a real ``playbook-hook simulate stop`` dispatch. The suite never
runs: ``FakeSuiteFactory`` (``RuntimeDeps.suite_handle``) serves canned
``RunArtifacts`` through a ``FakeProjectHandle``, the autouse ``FakeProc``
fails the test on any spawn, and ``FakeGit`` answers the diff. The stage is an
execution stage, so ``FakeTrustStore`` approves the rendered stage list unless
a case says otherwise.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.evaluators.execution.coverage_xml import CoverageReport
from coding_agent_playbook.evaluators.execution.junit import JunitSummary
from coding_agent_playbook.evaluators.execution.project import RunArtifacts
from coding_agent_playbook.guard_config import DetectInputs
from coding_agent_playbook.hook_runtime.config.guard_config import GUARD_CONFIG_REL
from coding_agent_playbook.hook_runtime.config.guard_tables import GuardTables
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.event import EventName
from coding_agent_playbook.hook_runtime.git.parse import AddedLine, DiffLines
from coding_agent_playbook.hook_runtime.handlers._coverage_report import (
    ADVICE_LINE,
    NO_SNAPSHOT_LINE,
)
from coding_agent_playbook.hook_runtime.state.store import STATE_DIR_NAME
from coding_agent_playbook.hook_runtime.stop.coordinator import GatePolicy
from coding_agent_playbook.hook_runtime.stop.suite import SuiteUnavailable
from tests.hook_runtime.fakes import FakeStageRunner, FakeTrustStore
from tests.hook_runtime.handlers.stop_kit import (
    HEAD_TREE,
    NO_CLAIM,
    TREE,
    changed_git,
    reason_lines,
    script_ruff,
    stop_payload,
)
from tests.hook_runtime.tool_fakes import FakeSuiteFactory

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hook_runtime.fakes import FakeGit
    from tests.hook_runtime.handlers.pack_repo import PackRepo

    type Deps = Callable[..., RuntimeDeps]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "coverage-diff-gate"
COORDINATOR: Final = "stop-ci-parity-gate"
PYTEST_COV: Final = DetectInputs(facts={"dev_dependencies": {"pytest-cov": ">=5"}})
GREEN_SUITE: Final = JunitSummary(passed=3, failed=0, errors=0, skipped=0, total=3)


def _install(repo: PackRepo, *, tests: bool = False, **config: Any) -> FakeTrustStore:
    """The coordinator plus coverage-diff-gate; a trust store approving their stage list."""
    per_hook: dict[str, dict[str, Any]] = {HOOK_ID: config}
    if tests:
        per_hook[COORDINATOR] = {"stages": ["tests"]}
    repo.install_pack([COORDINATOR, HOOK_ID], per_hook=per_hook, detect=PYTEST_COV)
    table = json.loads((repo.root / GUARD_CONFIG_REL).read_bytes())["stop_gate"]
    gate = GuardTables({"stop_gate": table}).stop_gate()
    return FakeTrustStore(executions={GatePolicy.from_gate(gate).stages_sha256()})


def _changed(*files: tuple[str, int]) -> DiffLines:
    """``git diff`` adding lines ``1..n`` to each ``(path, n)``."""
    return DiffLines(
        added=tuple(AddedLine(path, line, "x = 1") for path, n in files for line in range(1, n + 1))
    )


def _artifacts(
    lines: Mapping[str, Mapping[int, int]],
    *,
    total: float = 90.0,
    junit: JunitSummary = GREEN_SUITE,
) -> RunArtifacts:
    report = CoverageReport(lines={path: dict(hits) for path, hits in lines.items()}, total=total)
    return RunArtifacts(junit=junit, coverage=report, returncode=0 if not junit.failed else 1)


def _hits(covered: int, missed: range) -> dict[int, int]:
    return {line: 0 if line in missed else 1 for line in range(1, covered + len(missed) + 1)}


def _stop(
    repo: PackRepo,
    deps: Deps,
    state: Path,
    *,
    git: FakeGit,
    suites: FakeSuiteFactory,
    trust: FakeTrustStore,
    message: str | None = None,
) -> SimulateReport:
    runner = FakeStageRunner()
    script_ruff(runner)
    payload = stop_payload(repo) if message is None else stop_payload(repo, message=message)
    fields = {"git": git, "stage_runner": runner, "trust": trust, "suite_handle": suites}
    return repo.simulate(payload, deps(**fields), event=EventName.STOP, state=state)


def _src(repo: PackRepo, *files: tuple[str, int]) -> None:
    for path, n in files:
        repo.write(path, "x = 1\n" * n)


def _notes(report: SimulateReport) -> tuple[str, ...]:
    return report.trace.combined.user_notes


def test_untrusted_repo_zero_suite_runs(pack_repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    _install(pack_repo)
    _src(pack_repo, ("src/pkg/a.py", 4))
    suites = FakeSuiteFactory()
    git = changed_git(worktree_diffs={"HEAD": _changed(("src/pkg/a.py", 4))})

    report = _stop(pack_repo, deps, tmp_path, git=git, suites=suites, trust=FakeTrustStore())

    assert (suites.specs, suites.runs) == ([], 0)
    assert report.trace.combined.decision is Decision.NONE
    assert any("execution stages (coverage) skipped" in note for note in _notes(report))


def test_24_changed_lines_15_hit_one_block_with_ranges(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    trust = _install(pack_repo)
    _src(pack_repo, ("src/pkg/a.py", 16), ("src/pkg/b.py", 8))
    lines = {"src/pkg/a.py": _hits(12, range(12, 16)), "src/pkg/b.py": _hits(3, range(3, 8))}
    suites = FakeSuiteFactory(artifacts=_artifacts(lines))
    git = changed_git(worktree_diffs={"HEAD": _changed(("src/pkg/a.py", 16), ("src/pkg/b.py", 8))})

    report = _stop(pack_repo, deps, tmp_path, git=git, suites=suites, trust=trust)

    assert report.trace.combined.decision is Decision.DENY
    assert reason_lines(report)[1:] == [
        "[coverage] coverage: 62.5% of 24 changed lines executed (min 80%)",
        '[coverage] "src/pkg/a.py": 12-15 · "src/pkg/b.py": 3-7',
        f"[coverage] {NO_SNAPSHOT_LINE}",
        f"[coverage] {ADVICE_LINE}",
    ]
    assert suites.runs == 1


def test_all_changed_lines_covered_silent(pack_repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    trust = _install(pack_repo)
    _src(pack_repo, ("src/pkg/a.py", 4))
    suites = FakeSuiteFactory(artifacts=_artifacts({"src/pkg/a.py": _hits(4, range(0))}))
    git = changed_git(worktree_diffs={"HEAD": _changed(("src/pkg/a.py", 4))})

    report = _stop(pack_repo, deps, tmp_path, git=git, suites=suites, trust=trust)

    assert report.trace.combined.decision is Decision.NONE
    assert _notes(report) == ("verified locally (lint, coverage); the CI matrix is authoritative",)


def test_only_test_files_changed_silent(pack_repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    trust = _install(pack_repo)
    _src(pack_repo, ("tests/test_a.py", 4))
    suites = FakeSuiteFactory()
    git = changed_git(worktree_diffs={"HEAD": _changed(("tests/test_a.py", 4))})

    report = _stop(pack_repo, deps, tmp_path, git=git, suites=suites, trust=trust)

    assert (suites.specs, report.trace.combined.decision) == ([], Decision.NONE)
    assert not [note for note in _notes(report) if "coverage" in note]


def test_no_completion_claim_never_runs_the_suite(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    trust = _install(pack_repo)
    _src(pack_repo, ("src/pkg/a.py", 4))
    suites = FakeSuiteFactory()
    git = changed_git(worktree_diffs={"HEAD": _changed(("src/pkg/a.py", 4))})

    _stop(pack_repo, deps, tmp_path, git=git, suites=suites, trust=trust, message=NO_CLAIM)

    assert suites.specs == []


def test_red_suite_with_tests_disabled_not_verified_no_grade(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    trust = _install(pack_repo)
    _src(pack_repo, ("src/pkg/a.py", 4))
    red = JunitSummary(passed=1, failed=2, errors=0, skipped=0, total=3)
    suites = FakeSuiteFactory(
        artifacts=_artifacts({"src/pkg/a.py": _hits(0, range(1, 5))}, junit=red)
    )
    git = changed_git(worktree_diffs={"HEAD": _changed(("src/pkg/a.py", 4))})

    report = _stop(pack_repo, deps, tmp_path, git=git, suites=suites, trust=trust)

    assert report.trace.combined.decision is Decision.NONE
    assert _notes(report) == (
        "suite red (2 failed); coverage not graded",
        "NOT verified: coverage skipped (suite_red)",
    )


def test_timeout_not_verified_never_green(pack_repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    trust = _install(pack_repo)
    _src(pack_repo, ("src/pkg/a.py", 4))
    suites = FakeSuiteFactory(problem=SuiteUnavailable("timeout", "pytest did not finish"))
    git = changed_git(worktree_diffs={"HEAD": _changed(("src/pkg/a.py", 4))})

    report = _stop(pack_repo, deps, tmp_path, git=git, suites=suites, trust=trust)

    assert report.trace.combined.decision is Decision.NONE
    assert _notes(report) == ("NOT verified: coverage skipped (timeout)",)


def _snapshot(state: Path, tree: str, total: float) -> Path:
    path = state / STATE_DIR_NAME / "coverage" / f"{tree}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"evaluator": "coverage", "scope_key": "suite", "value": total}
    path.write_text(json.dumps({"schema": 1, "tree": tree, "measurements": [row]}), "utf-8")
    return path


def test_cached_head_tree_snapshot_total_drop_adds_total_line(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    trust = _install(pack_repo)
    _src(pack_repo, ("src/pkg/a.py", 4))
    _snapshot(tmp_path, HEAD_TREE, 84.1)
    covered = _artifacts({"src/pkg/a.py": _hits(4, range(0))}, total=83.7)
    git = changed_git(worktree_diffs={"HEAD": _changed(("src/pkg/a.py", 4))})

    report = _stop(
        pack_repo, deps, tmp_path, git=git, suites=FakeSuiteFactory(artifacts=covered), trust=trust
    )

    assert reason_lines(report)[1:] == [
        "[coverage] coverage: total 84.1% -> 83.7% vs HEAD (must not drop)",
        f"[coverage] {ADVICE_LINE}",
    ]


def test_tests_and_coverage_enabled_exactly_one_project_run(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    """Done-when (Track K10): the tests stage reads the coverage stage's run."""
    trust = _install(pack_repo, tests=True)
    _src(pack_repo, ("src/pkg/a.py", 4))
    suites = FakeSuiteFactory(artifacts=_artifacts({"src/pkg/a.py": _hits(4, range(0))}))
    git = changed_git(worktree_diffs={"HEAD": _changed(("src/pkg/a.py", 4))})

    report = _stop(pack_repo, deps, tmp_path, git=git, suites=suites, trust=trust)

    assert (len(suites.handles), suites.runs) == (1, 1)
    assert _notes(report) == (
        "verified locally (lint, tests, coverage); the CI matrix is authoritative",
    )


def test_tests_stage_red_from_the_shared_run(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    trust = _install(pack_repo, tests=True)
    _src(pack_repo, ("src/pkg/a.py", 4))
    red = JunitSummary(passed=2, failed=1, errors=0, skipped=0, total=3)
    suites = FakeSuiteFactory(artifacts=_artifacts({"src/pkg/a.py": _hits(4, range(0))}, junit=red))
    git = changed_git(worktree_diffs={"HEAD": _changed(("src/pkg/a.py", 4))})

    report = _stop(pack_repo, deps, tmp_path, git=git, suites=suites, trust=trust)

    assert report.trace.combined.decision is Decision.DENY
    assert reason_lines(report)[1:] == ["[tests] 1 failed, 0 errors (pytest exit 1)"]
    assert _notes(report) == ("NOT verified: coverage skipped (suite_red)",)
    assert suites.runs == 1


def test_coverage_file_env_points_into_state_dir(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    trust = _install(pack_repo)
    _src(pack_repo, ("src/pkg/a.py", 4))
    suites = FakeSuiteFactory(artifacts=_artifacts({"src/pkg/a.py": _hits(4, range(0))}))
    git = changed_git(worktree_diffs={"HEAD": _changed(("src/pkg/a.py", 4))})

    _stop(pack_repo, deps, tmp_path, git=git, suites=suites, trust=trust)

    (spec,) = suites.specs
    report_dir = tmp_path / STATE_DIR_NAME / "suite" / TREE
    assert spec.report_dir == report_dir
    assert spec.env["COVERAGE_FILE"] == str(report_dir / ".coverage")
    assert spec.env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert (spec.tool, spec.args[:2]) == ("project_python", ("-m", "pytest"))
    assert f"--junitxml={report_dir / 'junit.xml'}" in spec.run_args
    assert "--cov=src" in spec.run_args


def test_green_writes_snapshot_for_fingerprint(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    trust = _install(pack_repo)
    _src(pack_repo, ("src/pkg/a.py", 4))
    suites = FakeSuiteFactory(
        artifacts=_artifacts({"src/pkg/a.py": _hits(4, range(0))}, total=88.0)
    )
    git = changed_git(worktree_diffs={"HEAD": _changed(("src/pkg/a.py", 4))})

    _stop(pack_repo, deps, tmp_path, git=git, suites=suites, trust=trust)

    written = json.loads((tmp_path / STATE_DIR_NAME / "coverage" / f"{TREE}.json").read_text())
    assert (written["schema"], written["tree"]) == (1, TREE)
    assert {"evaluator": "coverage", "scope_key": "suite", "value": 88.0} in written["measurements"]


def test_merge_base_diff_base_uses_default_branch_resolver(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    trust = _install(pack_repo, diff_base="merge-base")
    _src(pack_repo, ("src/pkg/a.py", 4))
    suites = FakeSuiteFactory(artifacts=_artifacts({"src/pkg/a.py": _hits(4, range(0))}))
    git = changed_git(
        default_branch_name="origin/main",
        merge_bases={("origin/main", "HEAD"): "base0"},
        worktree_diffs={"base0": _changed(("src/pkg/a.py", 4))},
    )

    report = _stop(pack_repo, deps, tmp_path, git=git, suites=suites, trust=trust)

    assert ("diff_worktree", ("base0",)) in git.calls
    assert suites.handles[0].diff_base == "base0"
    assert report.trace.combined.decision is Decision.NONE


def test_coverage_stage_record_is_the_projects_pytest(pack_repo: PackRepo) -> None:
    """The approved record (§B.4) names the pinned project interpreter, never a path."""
    _install(pack_repo, timeout_s=120)
    table = json.loads((pack_repo.root / GUARD_CONFIG_REL).read_bytes())["stop_gate"]

    (record,) = [r for r in table["stages"] if r["name"] == "coverage"]
    assert record == {
        "name": "coverage",
        "owner": HOOK_ID,
        "cost": "execution",
        "tool": "project_python",
        "args": ["-m", "pytest", "-o", "addopts=", "-p", "no:cacheprovider", "-q"],
        "timeout_s": 120.0,
        "needs_diff": True,
        "mode": "block",
    }


def test_older_tree_report_dirs_are_removed(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    """One tree's reports at a time: the state dir never grows with every Stop."""
    trust = _install(pack_repo)
    _src(pack_repo, ("src/pkg/a.py", 4))
    diffs = {"HEAD": _changed(("src/pkg/a.py", 4))}
    artifacts = _artifacts({"src/pkg/a.py": _hits(4, range(0))})
    suite_root = tmp_path / STATE_DIR_NAME / "suite"

    for tree in ("a" * 40, "b" * 40):
        git = changed_git(tree, worktree_diffs=diffs)
        _stop(pack_repo, deps, tmp_path, git=git, suites=FakeSuiteFactory(artifacts), trust=trust)

    assert sorted(path.name for path in suite_root.iterdir()) == ["b" * 40]


def test_context_decision_reports_without_blocking(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    trust = _install(pack_repo, decision="context")
    _src(pack_repo, ("src/pkg/a.py", 4))
    lines = {"src/pkg/a.py": _hits(1, range(2, 5))}
    git = changed_git(worktree_diffs={"HEAD": _changed(("src/pkg/a.py", 4))})

    report = _stop(
        pack_repo, deps, tmp_path, git=git, suites=FakeSuiteFactory(_artifacts(lines)), trust=trust
    )

    assert report.trace.combined.decision is Decision.NONE
    assert _notes(report)[0] == "[coverage] coverage: 25.0% of 4 changed lines executed (min 80%)"


def test_bad_metrics_table_is_not_verified_never_green(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    trust = _install(pack_repo)
    _src(pack_repo, ("src/pkg/a.py", 4))
    pack_repo.write(".coding-agent-playbook.toml", "[metrics]\nmode = 3\n")
    suites = FakeSuiteFactory(artifacts=_artifacts({"src/pkg/a.py": _hits(4, range(0))}))
    git = changed_git(worktree_diffs={"HEAD": _changed(("src/pkg/a.py", 4))})

    report = _stop(pack_repo, deps, tmp_path, git=git, suites=suites, trust=trust)

    notes = _notes(report)
    assert notes[0].startswith("coverage not graded: invalid [metrics] config")
    assert notes[1] == "NOT verified: coverage skipped (crash)"


def test_alone_without_the_coordinator_needs_the_execution_approval(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path
) -> None:
    """With stop-ci-parity-gate off the stage runs alone, still never without trust."""
    pack_repo.install_pack([HOOK_ID], detect=PYTEST_COV)
    table = json.loads((pack_repo.root / GUARD_CONFIG_REL).read_bytes())["stop_gate"]
    gate = GuardTables({"stop_gate": table}).stop_gate()
    approved = FakeTrustStore(executions={GatePolicy.from_gate(gate).stages_sha256()})
    _src(pack_repo, ("src/pkg/a.py", 4))
    lines = {"src/pkg/a.py": _hits(1, range(2, 5))}
    git = changed_git(worktree_diffs={"HEAD": _changed(("src/pkg/a.py", 4))})
    untrusted, trusted = FakeSuiteFactory(_artifacts(lines)), FakeSuiteFactory(_artifacts(lines))

    quiet = _stop(pack_repo, deps, tmp_path, git=git, suites=untrusted, trust=FakeTrustStore())
    blocked = _stop(pack_repo, deps, tmp_path, git=git, suites=trusted, trust=approved)

    assert (untrusted.runs, quiet.trace.combined.decision) == (0, Decision.NONE)
    assert (trusted.runs, blocked.trace.combined.decision) == (1, Decision.DENY)
