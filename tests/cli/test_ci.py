"""``playbook ci``: the aggregate off-workstation twin (specs/prK-hook-pack.md §F.5).

Each ``CI_STEPS`` row runs as a child ``<python> -m coding_agent_playbook.cli
<argv> --repo-root <root>``; the rows here inject ``FakeCiStepRunner`` (never a
patched ``subprocess``) and ``FakeGit`` for the base, except the base-order
rows (real git) and one real child process. Exit codes: 0 every run step
passed, 1 any failed or timed out, 2 a usage error or an unresolvable base.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.cli.parser import build_parser
from coding_agent_playbook.commands.twins import ci
from tests.conftest import _DEFAULT_CONFIG
from tests.fakes import FakeCiStepRunner
from tests.hook_runtime.fakes import FakeGit

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

CLI_PREFIX = (sys.executable, "-m", "coding_agent_playbook.cli")
_METRICS_ARGV = ("metrics", "--baseline", "git:abc123", "--changed", "--no-run-tests")
_COMMITTED = _DEFAULT_CONFIG + "\n[output]\ncommit = true\n"


def _git(sha: str = "abc123") -> FakeGit:
    return FakeGit(
        default_branch_name="origin/main",
        merge_bases={("origin/main", "HEAD"): sha},
        commits={"HEAD": "head456"},
    )


def _clock(*ticks: float) -> Callable[[], float]:
    values: Iterator[float] = iter(ticks)
    return lambda: next(values)


def _run(
    root: Path,
    *argv: str,
    runner: FakeCiStepRunner | None = None,
    git: FakeGit | None = None,
    clock: Callable[[], float] | None = None,
) -> int:
    args = build_parser().parse_args(["ci", *argv, "--repo-root", str(root)])
    return ci.run(
        args,
        runner=runner or FakeCiStepRunner(),
        git=git if git is not None else _git(),
        clock=clock or _clock(*range(100)),
    )


@pytest.fixture
def committed(tmp_path: Path) -> Path:
    """A repo whose config commits generated output, so every default row runs."""
    (tmp_path / ".coding-agent-playbook.toml").write_text(_COMMITTED, encoding="utf-8")
    return tmp_path


def _subcommands(runner: FakeCiStepRunner) -> list[str]:
    return [argv[3] for argv in runner.calls]


def test_ci_steps_table_rows_and_owners() -> None:
    assert [(step.name, step.owner) for step in ci.CI_STEPS] == [
        ("sync-check", "prerequisites"),
        ("validate", "existing"),
        ("metrics", "F.2/F.3"),
        ("coverage", "F.1"),
        ("gate-scan", "E.2"),
        ("scan-secrets", "E.4"),
        ("commit-convention", "F.4"),
        ("commit-trailers", "E.4"),
        ("check-deps", "E.4"),
        ("scan-sinks", "E.3"),
    ]


def test_runs_steps_in_ci_steps_order(committed: Path) -> None:
    runner = FakeCiStepRunner()

    assert _run(committed, "--steps", "gate-scan,validate,sync-check", runner=runner) == 0

    root = str(committed.resolve())
    assert runner.calls == [
        (*CLI_PREFIX, "sync", "--check", "--repo-root", root),
        (*CLI_PREFIX, "validate", "--repo-root", root),
        (*CLI_PREFIX, "gate-scan", "--range", "abc123..HEAD", "--repo-root", root),
    ]
    assert runner.timeouts == [ci.DEFAULT_STEP_TIMEOUT_S] * 3


def test_metrics_step_argv_uses_merge_base_changed_no_run_tests(tmp_path: Path) -> None:
    """prK §F.2.3: always enabled; the merge base keeps main's later edits out."""
    runner = FakeCiStepRunner()

    assert _run(tmp_path, "--steps", "metrics", runner=runner, git=_git("f00d")) == 0

    root = str(tmp_path.resolve())
    argv = ("metrics", "--baseline", "git:f00d", "--changed", "--no-run-tests")
    assert runner.calls == [(*CLI_PREFIX, *argv, "--repo-root", root)]


_COVERAGE_ARGV = ("metrics", "--run-tests", "--select", "testing", "--baseline", "git:f00d")


@pytest.mark.parametrize(
    ("metrics_table", "steps", "runs"),
    [
        ("", ("--steps", "metrics,coverage"), True),  # named explicitly
        ("[metrics]\nrun_tests = true\n", (), True),  # the config runs tests
        ("[metrics]\nrun_tests = false\n", (), False),
        ("", (), False),
        ("[metrics]\nrun_tests = 3\n", (), True),  # unloadable: run it, so it reports why
    ],
    ids=["steps-flag", "run-tests-true", "run-tests-false", "no-table", "invalid-config"],
)
def test_coverage_step_enabled_by_run_tests_or_steps_flag(
    tmp_path: Path, metrics_table: str, steps: tuple[str, ...], runs: bool
) -> None:
    """prK §F.1.3/§F.5: the suite-running row is opt-in; its argv diffs the merge base."""
    config = _DEFAULT_CONFIG + "\n" + metrics_table
    (tmp_path / ".coding-agent-playbook.toml").write_text(config, encoding="utf-8")
    runner = FakeCiStepRunner()

    assert _run(tmp_path, *steps, runner=runner, git=_git("f00d")) == 0

    root = str(tmp_path.resolve())
    coverage_call = (*CLI_PREFIX, *_COVERAGE_ARGV, "--repo-root", root)
    assert (coverage_call in runner.calls) is runs


def test_scan_secrets_step_uses_merge_base_range(tmp_path: Path) -> None:
    """prK §E.4/§F.5: always enabled (no config needed), over <merge base>..HEAD."""
    runner = FakeCiStepRunner()

    assert _run(tmp_path, "--steps", "scan-secrets", runner=runner, git=_git("f00d")) == 0

    root = str(tmp_path.resolve())
    assert runner.calls == [
        (*CLI_PREFIX, "scan-secrets", "--range", "f00d..HEAD", "--repo-root", root)
    ]


def test_aggregated_exit_1_when_any_step_fails(
    committed: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeCiStepRunner(exits={"validate": 1})

    assert _run(committed, runner=runner) == 1

    # no fail-fast
    assert _subcommands(runner) == ["sync", "validate", "metrics", "gate-scan", "scan-secrets"]
    out = capsys.readouterr().out
    assert "validate said hello" in out
    assert "FAIL validate (exit 1" in out
    # coverage (run_tests off), commit-convention (no commitizen), commit-trailers
    # (no rows), check-deps (no policy) and the opt-in scan-sinks
    assert "playbook ci: 4 passed, 1 failed, 5 skipped" in out


@pytest.mark.parametrize("steps", ["validate,nope", "", ",,"])
def test_unknown_step_is_usage_error_exit_2(
    committed: Path, capsys: pytest.CaptureFixture[str], steps: str
) -> None:
    runner = FakeCiStepRunner()

    assert _run(committed, "--steps", steps, runner=runner) == 2

    assert runner.calls == []
    err = capsys.readouterr().err
    assert err.startswith("error: --steps")
    assert "sync-check, validate, metrics, coverage, gate-scan, scan-secrets" in err


def test_json_records_step_argv_exit_duration(
    committed: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeCiStepRunner(exits={"gate-scan": 1})

    code = _run(
        committed,
        "--format",
        "json",
        runner=runner,
        clock=_clock(0, 1.5, 2, 2.25, 2.5, 2.75, 3, 3.5, 4, 4.125),
    )

    assert code == 1
    captured = capsys.readouterr()
    document = json.loads(captured.out)
    root = str(committed.resolve())
    assert document["exit"] == 1
    assert document["steps"] == [
        {
            "step": "sync-check",
            "argv": [*CLI_PREFIX, "sync", "--check", "--repo-root", root],
            "exit": 0,
            "duration_s": 1.5,
            "status": "passed",
        },
        {
            "step": "validate",
            "argv": [*CLI_PREFIX, "validate", "--repo-root", root],
            "exit": 0,
            "duration_s": 0.25,
            "status": "passed",
        },
        {
            "step": "metrics",
            "argv": [*CLI_PREFIX, *_METRICS_ARGV, "--repo-root", root],
            "exit": 0,
            "duration_s": 0.25,
            "status": "passed",
        },
        {
            "step": "coverage",
            "argv": [],
            "exit": None,
            "duration_s": 0.0,
            "status": "skipped",
            "note": "[metrics] run_tests is not true: run with --steps coverage",
        },
        {
            "step": "gate-scan",
            "argv": [*CLI_PREFIX, "gate-scan", "--range", "abc123..HEAD", "--repo-root", root],
            "exit": 1,
            "duration_s": 0.5,
            "status": "failed",
        },
        {
            "step": "scan-secrets",
            "argv": [*CLI_PREFIX, "scan-secrets", "--range", "abc123..HEAD", "--repo-root", root],
            "exit": 0,
            "duration_s": 0.125,
            "status": "passed",
        },
        {
            "step": "commit-convention",
            "argv": [],
            "exit": None,
            "duration_s": 0.0,
            "status": "skipped",
            "note": "no [tool.commitizen] in pyproject.toml and no [hooks.commit_convention]",
        },
        {
            "step": "commit-trailers",
            "argv": [],
            "exit": None,
            "duration_s": 0.0,
            "status": "skipped",
            "note": "no trailer row in [hooks.git-commit-push-policy-guard]",
        },
        {
            "step": "check-deps",
            "argv": [],
            "exit": None,
            "duration_s": 0.0,
            "status": "skipped",
            "note": "no dependency policy (allowlist, required_index or index_mode = deny)",
        },
        {
            "step": "scan-sinks",
            "argv": [],
            "exit": None,
            "duration_s": 0.0,
            "status": "skipped",
            "note": "opt-in: run with --steps scan-sinks",
        },
    ]
    assert "gate-scan said hello" in captured.err  # child output stays off the JSON stream


def test_sync_check_skipped_when_output_commit_false(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / ".coding-agent-playbook.toml").write_text(_DEFAULT_CONFIG, encoding="utf-8")
    runner = FakeCiStepRunner()

    assert _run(tmp_path, "--format", "json", runner=runner) == 0

    assert _subcommands(runner) == ["validate", "metrics", "gate-scan", "scan-secrets"]
    skipped = json.loads(capsys.readouterr().out)["steps"][0]
    assert skipped["step"] == "sync-check"
    assert skipped["status"] == "skipped"
    assert skipped["exit"] is None and skipped["argv"] == []
    assert "[output] commit = false" in skipped["note"]


def test_sync_check_skipped_without_config(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeCiStepRunner()

    assert _run(tmp_path, runner=runner) == 0

    assert _subcommands(runner) == ["validate", "metrics", "gate-scan", "scan-secrets"]
    assert "SKIP sync-check: no .coding-agent-playbook.toml" in capsys.readouterr().out


def test_unreadable_config_runs_sync_check_so_it_reports(tmp_path: Path) -> None:
    (tmp_path / ".coding-agent-playbook.toml").write_text("not [toml", encoding="utf-8")
    runner = FakeCiStepRunner()

    _run(tmp_path, runner=runner)

    assert _subcommands(runner)[0] == "sync"


def test_step_timeout_counts_as_failure(
    committed: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeCiStepRunner(exits={"validate": None})

    assert _run(committed, "--format", "json", runner=runner) == 1

    record = json.loads(capsys.readouterr().out)["steps"][1]
    assert (record["step"], record["exit"], record["status"]) == ("validate", None, "timeout")


def test_timeout_reads_as_timeout_in_text_mode(
    committed: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(committed, runner=FakeCiStepRunner(exits={"validate": None})) == 1
    assert "TIMEOUT validate (after " in capsys.readouterr().out


def test_subprocess_runner_times_out_and_reports_missing_programs(tmp_path: Path) -> None:
    runner = ci.SubprocessCiStepRunner()
    sleeper = [sys.executable, "-c", "import time; print('started', flush=True); time.sleep(30)"]

    slow = runner.run(sleeper, cwd=tmp_path, timeout_s=1.0)
    missing = runner.run([str(tmp_path / "no-such-program")], cwd=tmp_path, timeout_s=5.0)
    merged = runner.run(
        [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr)"],
        cwd=tmp_path,
        timeout_s=10.0,
    )

    assert slow.exit is None
    assert missing.exit == 127 and "cannot start" in missing.output
    assert (merged.exit, sorted(merged.output.split())) == (0, ["err", "out"])


def test_unresolvable_base_exits_2_with_fetch_depth_hint(
    committed: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = FakeCiStepRunner()

    assert _run(committed, runner=runner, git=FakeGit()) == 2

    assert runner.calls == []
    assert "fetch-depth: 0" in capsys.readouterr().err


def test_explicit_base_without_shared_history_exits_2(
    committed: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run(committed, "--base", "release", git=_git()) == 2
    assert "release and HEAD share no history" in capsys.readouterr().err


def test_steps_without_a_base_never_ask_git(committed: Path) -> None:
    git = FakeGit()
    runner = FakeCiStepRunner()

    assert _run(committed, "--steps", "validate", runner=runner, git=git) == 0

    assert git.calls == []
    assert _subcommands(runner) == ["validate"]


# --- base resolution against real git ---------------------------------------------------------


def _commit(real_git: Callable[..., str], root: Path, message: str) -> str:
    real_git("commit", "-q", "--allow-empty", "-m", message, cwd=root)
    return real_git("rev-parse", "HEAD", cwd=root)


@pytest.mark.parametrize("refs", ["master", "master+main", "master+main+origin"])
def test_base_resolves_origin_head_then_main_then_master(
    tmp_path: Path, real_git: Callable[..., str], refs: str
) -> None:
    root = Path(os.path.realpath(tmp_path)) / "repo"
    root.mkdir()
    (root / ".coding-agent-playbook.toml").write_text(_COMMITTED, encoding="utf-8")
    real_git("init", "-q", "-b", "work", cwd=root)
    expected = {"master": _commit(real_git, root, "one")}
    real_git("branch", "master", cwd=root)
    expected["master+main"] = _commit(real_git, root, "two")
    if "main" in refs:
        real_git("branch", "main", cwd=root)
    expected["master+main+origin"] = _commit(real_git, root, "three")
    if "origin" in refs:
        real_git("update-ref", "refs/remotes/origin/trunk", "HEAD", cwd=root)
        real_git("symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk", cwd=root)
    _commit(real_git, root, "four")
    runner = FakeCiStepRunner()
    args = build_parser().parse_args(["ci", "--steps", "gate-scan", "--repo-root", str(root)])

    assert ci.run(args, runner=runner) == 0

    assert runner.calls[0][-4:-2] == ("--range", f"{expected[refs]}..HEAD")


def test_one_real_child_process_step(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, rules=[("style-guide", "Use spaces.\n")])
    args = build_parser().parse_args(
        ["ci", "--steps", "validate", "--format", "json", "--repo-root", str(repo)]
    )

    assert ci.run(args) == 0

    captured = capsys.readouterr()
    (record,) = json.loads(captured.out)["steps"]
    assert (record["step"], record["exit"], record["status"]) == ("validate", 0, "passed")
    assert record["argv"][:4] == [*CLI_PREFIX, "validate"]
    assert record["duration_s"] > 0
    assert "validate" in captured.err.lower()


_TRAILER_ROWS = '\n[hooks.git-commit-push-policy-guard]\nforbid_trailers = ["Co-Authored-By"]\n'


@pytest.mark.parametrize(
    ("tables", "expected"),
    [
        ("", "skipped"),
        (_TRAILER_ROWS, "passed"),
    ],
)
def test_commit_trailers_step_enabled_only_with_rows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], tables: str, expected: str
) -> None:
    """prK §E.4: the trailer twin runs over <merge base>..HEAD only when a row is configured."""
    (tmp_path / ".coding-agent-playbook.toml").write_text(_DEFAULT_CONFIG + tables, "utf-8")
    runner = FakeCiStepRunner()

    code = _run(tmp_path, "--steps", "commit-trailers", "--format", "json", runner=runner)

    (record,) = json.loads(capsys.readouterr().out)["steps"]
    assert (code, record["status"]) == (0, expected)
    root = str(tmp_path.resolve())
    ran = [(*CLI_PREFIX, "check-commit-trailers", "--range", "abc123..HEAD", "--repo-root", root)]
    assert runner.calls == (ran if expected == "passed" else [])


_DEPENDENCY_POLICY = '\n[hooks.dependency-allowlist-guard]\nallowlist = ["requests"]\n'


@pytest.mark.parametrize(
    ("tables", "steps", "expected"),
    [
        ("", "check-deps,scan-sinks", ["skipped", "passed"]),
        (_DEPENDENCY_POLICY, "check-deps,scan-sinks", ["passed", "passed"]),
        (_DEPENDENCY_POLICY, "check-deps", ["passed"]),
    ],
)
def test_check_deps_and_scan_sinks_rows(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    tables: str,
    steps: str,
    expected: list[str],
) -> None:
    """prK §E.4/§E.3: check-deps runs with a dependency policy; scan-sinks only on request."""
    (tmp_path / ".coding-agent-playbook.toml").write_text(_DEFAULT_CONFIG + tables, "utf-8")
    runner = FakeCiStepRunner()

    code = _run(tmp_path, "--steps", steps, "--format", "json", runner=runner)

    records = json.loads(capsys.readouterr().out)["steps"]
    assert (code, [record["status"] for record in records]) == (0, expected)
    root = str(tmp_path.resolve())
    rows = {
        "check-deps": (*CLI_PREFIX, "check-deps", "--base", "abc123", "--repo-root", root),
        "scan-sinks": (*CLI_PREFIX, "scan-sinks", "--range", "abc123..HEAD", "--repo-root", root),
    }
    ran = [r["step"] for r in records if r["status"] == "passed"]
    assert runner.calls == [rows[name] for name in ran]


def test_unreadable_dependency_policy_runs_check_deps_so_it_reports(tmp_path: Path) -> None:
    (tmp_path / ".coding-agent-playbook.toml").write_text("not [toml", encoding="utf-8")
    runner = FakeCiStepRunner()

    _run(tmp_path, "--steps", "check-deps", runner=runner)

    assert _subcommands(runner) == ["check-deps"]
