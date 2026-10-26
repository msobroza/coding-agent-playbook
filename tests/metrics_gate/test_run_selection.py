"""What the metrics gate measures: selection, ``--changed``, ``exclude`` and snapshots (prK §F.0.3).

These drive :func:`run_metrics_gate` with named fakes (``FakeGitRunner`` for the
working-tree reads, ``FakeBaselineGit`` for blobs, ``FakeProjectFactory`` for
suites), so no git and no suite runs. ``tests/cli/test_metrics_selection.py``
covers the CLI flags end to end against a real repository.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.grading.metric import static_metrics
from coding_agent_playbook.grading.types import Measurement
from coding_agent_playbook.metrics_gate.config import MetricConfig
from coding_agent_playbook.metrics_gate.policy import OPT_IN_METRICS
from coding_agent_playbook.metrics_gate.run import (
    MetricsGateDeps,
    MetricsGateRequest,
    MetricsGateUsageError,
    run_metrics_gate,
)
from coding_agent_playbook.metrics_gate.snapshot import read_snapshot, write_snapshot
from tests.cli.test_metrics import _BASELINE_SOURCE, _CLEAN_SOURCE, _WORSE_SOURCE
from tests.fakes import FakeBaselineGit, FakeGitRunner, FakeProjectFactory

if TYPE_CHECKING:
    from pathlib import Path

#: The default selection: every static metric except the opt-in ones (prK §F.2.1).
_STATIC_CHECKS = [
    f"threshold:{metric.name}" for metric in static_metrics() if metric.name not in OPT_IN_METRICS
]
_FIXTURE = "eval_samples/review/t1/setup/needle.py"


def _write(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _request(root: Path, **overrides: object) -> MetricsGateRequest:
    fields: dict[str, object] = {
        "repo_root": root,
        "config": MetricConfig(mode="absolute"),
        "paths": (str(root),),
    }
    fields.update(overrides)
    return MetricsGateRequest(**fields)  # type: ignore[arg-type]


def _check_ids(root: Path, **overrides: object) -> list[str]:
    _write(root / "mod.py", _CLEAN_SOURCE)
    result = run_metrics_gate(_request(root, **overrides))
    return [check.check_id for check in result.report.checks]


def _git_deps(runner: FakeGitRunner, git: FakeBaselineGit | None = None) -> MetricsGateDeps:
    baseline_git = git if git is not None else FakeBaselineGit()
    return MetricsGateDeps(
        git_factory=lambda _timeout: baseline_git, git_runner_factory=runner.factory
    )


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #


def test_default_selection_grades_today_gated_set(tmp_path: Path) -> None:
    assert _check_ids(tmp_path) == _STATIC_CHECKS


def test_request_selection_overrides_config(tmp_path: Path) -> None:
    config = MetricConfig(mode="absolute", select=("wmc",), ignore=("cyclomatic_complexity",))

    from_config = _check_ids(tmp_path, config=config)
    from_request = _check_ids(tmp_path, config=config, select=("cyclomatic_complexity",), ignore=())

    assert from_config == ["threshold:wmc"]
    assert from_request == ["threshold:cyclomatic_complexity"]


def test_config_extend_select_and_ignore_apply(tmp_path: Path) -> None:
    config = MetricConfig(mode="absolute", select=("wmc",), extend_select=("dit", "cbo"))

    chosen = _check_ids(tmp_path, config=config, ignore=("cbo",))

    assert sorted(chosen) == ["threshold:dit", "threshold:wmc"]
    assert chosen == [check for check in _STATIC_CHECKS if check in chosen]  # registry order


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"select": ("complexity",)}, "unknown metric or family 'complexity'; expected one of: "),
        (
            {"config": MetricConfig(mode="absolute", ignore=("nope",))},
            "unknown metric or family 'nope'",
        ),
        ({"extend_select": ("coverage",)}, "execution metric(s) coverage selected without"),
    ],
    ids=["unknown-request", "unknown-config", "execution-by-name"],
)
def test_bad_selection_is_a_usage_error(
    tmp_path: Path, overrides: dict[str, object], message: str
) -> None:
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)

    with pytest.raises(MetricsGateUsageError) as excinfo:
        run_metrics_gate(_request(tmp_path, **overrides))

    assert str(excinfo.value).startswith(message)


def test_config_named_execution_metrics_are_dropped_when_tests_do_not_run(tmp_path: Path) -> None:
    """``[metrics]`` serves test runs too; ``--no-run-tests`` and the hooks stay static."""
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    factory = FakeProjectFactory()
    config = MetricConfig(mode="absolute", run_tests=True, select=("quality", "testing"))

    result = run_metrics_gate(
        _request(tmp_path, config=config), deps=MetricsGateDeps(project_factory=factory)
    )

    assert factory.calls == []
    assert {check.check_id for check in result.report.checks} <= set(_STATIC_CHECKS)


def test_run_tests_without_a_selected_execution_metric_runs_no_suite(tmp_path: Path) -> None:
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    factory = FakeProjectFactory()

    run_metrics_gate(
        _request(tmp_path, run_tests=True, select=("quality",)),
        deps=MetricsGateDeps(project_factory=factory),
    )

    assert factory.calls == []


# --------------------------------------------------------------------------- #
# --changed and exclude
# --------------------------------------------------------------------------- #


def test_changed_only_keeps_diffed_and_untracked_targets(tmp_path: Path) -> None:
    for name in ("a.py", "b.py", "c.py"):
        _write(tmp_path / name, _CLEAN_SOURCE)
    runner = FakeGitRunner(outputs={"diff": b"a.py\0notes.txt\0", "ls-files": b"c.py\0"})
    config = MetricConfig(mode="absolute", git_timeout_s=4.0)

    result = run_metrics_gate(
        _request(tmp_path, config=config, baseline="git:HEAD", changed_only=True),
        deps=_git_deps(runner),
    )

    assert result.measured_count == 2
    assert {f.scope_key.split("::")[0] for f in result.report.findings} == {"a.py", "c.py"}
    assert runner.roots == [(tmp_path, 4.0)]
    assert [argv[0] for argv in runner.calls] == ["diff", "ls-files"]
    assert "HEAD" in runner.calls[0]


def test_changed_only_intersects_explicit_paths(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "a.py", _CLEAN_SOURCE)
    _write(tmp_path / "other" / "b.py", _CLEAN_SOURCE)
    runner = FakeGitRunner(outputs={"diff": b"pkg/a.py\0other/b.py\0"})

    result = run_metrics_gate(
        _request(tmp_path, paths=(str(tmp_path / "pkg"),), baseline="git:HEAD", changed_only=True),
        deps=_git_deps(runner),
    )

    assert result.measured_count == 1


@pytest.mark.parametrize("baseline", [None, "base-dir", "json:snap.json"])
def test_changed_only_without_a_git_baseline_is_a_usage_error(
    tmp_path: Path, baseline: str | None
) -> None:
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)

    with pytest.raises(MetricsGateUsageError) as excinfo:
        run_metrics_gate(_request(tmp_path, baseline=baseline, changed_only=True))

    assert str(excinfo.value).startswith("--changed needs a git: baseline")


def test_changed_only_with_a_bad_ref_names_the_ref(tmp_path: Path) -> None:
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    runner = FakeGitRunner()

    with pytest.raises(MetricsGateUsageError, match="bad --baseline git ref 'nope'"):
        run_metrics_gate(
            _request(tmp_path, baseline="git:nope", changed_only=True), deps=_git_deps(runner)
        )

    assert runner.calls == []


def test_exclude_drops_matching_targets_even_when_passed_explicitly(tmp_path: Path) -> None:
    needle = _write(tmp_path / _FIXTURE, "def broken(:\n")
    _write(tmp_path / "gen" / "big.py", _CLEAN_SOURCE)
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)

    default = run_metrics_gate(_request(tmp_path, paths=(str(needle), str(tmp_path / "mod.py"))))
    custom = run_metrics_gate(
        _request(tmp_path, config=MetricConfig(mode="absolute", exclude=("gen/**",)))
    )

    assert (default.measured_count, default.skipped) == (1, ())
    # A custom list replaces the default: the fixture is back in, gen/ is out.
    assert custom.measured_count == 1
    assert [label for label, _ in custom.skipped] == [_FIXTURE]


# --------------------------------------------------------------------------- #
# Snapshots: --emit-measurements and --baseline json:
# --------------------------------------------------------------------------- #


def test_emit_measurements_writes_the_candidate_snapshot(tmp_path: Path) -> None:
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    out = tmp_path / "snap.json"

    result = run_metrics_gate(
        _request(
            tmp_path,
            emit_measurements=out,
            snapshot_tree="4b825dc6",
            select=("cyclomatic_complexity",),
        )
    )

    document = json.loads(out.read_text(encoding="utf-8"))
    assert (document["schema"], document["tree"]) == (1, "4b825dc6")
    assert document["measurements"] == [
        {"evaluator": "cyclomatic_complexity", "scope_key": "mod.py::add", "value": 1.0}
    ]
    assert len(result.report.findings) == 1


def test_emit_measurements_write_failure_is_a_usage_error(tmp_path: Path) -> None:
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)

    with pytest.raises(MetricsGateUsageError, match="cannot write --emit-measurements"):
        run_metrics_gate(_request(tmp_path, emit_measurements=tmp_path / "no" / "snap.json"))


def test_json_baseline_grades_regressions_without_a_baseline_suite_run(tmp_path: Path) -> None:
    _write(tmp_path / "mod.py", _BASELINE_SOURCE)
    snapshot = tmp_path / "base.json"
    run_metrics_gate(_request(tmp_path, emit_measurements=snapshot))
    _write(tmp_path / "mod.py", _WORSE_SOURCE)
    write_snapshot(
        snapshot,
        [*read_snapshot(snapshot), Measurement("coverage", "suite", 100.0)],
        tree=None,
    )
    factory = FakeProjectFactory()

    result = run_metrics_gate(
        _request(
            tmp_path,
            config=MetricConfig(mode="regression"),
            baseline=f"json:{snapshot}",
            run_tests=True,
        ),
        deps=MetricsGateDeps(project_factory=factory),
    )

    assert [root for root, _ in factory.calls] == [tmp_path]  # the candidate run only
    regressions = [f for f in result.report.findings if f.kind == "regression"]
    assert "mod.py::classify" in {f.scope_key for f in regressions if f.level == "fail"}


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (None, "cannot read measurement snapshot"),
        ('{"schema": 9, "tree": null, "measurements": []}', "schema 9 is not supported"),
    ],
    ids=["missing", "schema"],
)
def test_bad_json_baseline_is_a_usage_error(
    tmp_path: Path, content: str | None, message: str
) -> None:
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    snapshot = tmp_path / "base.json"
    if content is not None:
        snapshot.write_text(content, encoding="utf-8")

    with pytest.raises(MetricsGateUsageError, match=message):
        run_metrics_gate(_request(tmp_path, baseline=f"json:{snapshot}"))
