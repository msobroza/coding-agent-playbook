"""Tests for the jinja-free ``playbook metrics`` gate (prK §F.0.3 item 1, P-D3).

``run_metrics_gate`` is the entry point the Stop stages call in-process, so it
must never run a suite unless the request says so, must run exactly the request's
test command, and must keep the CLI's usage-error wording. The CLI output itself
is pinned byte for byte by ``tests/cli/test_metrics_golden.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.evaluators.execution.project import ProjectHandle
from coding_agent_playbook.evaluators.metric import Metric, static_metrics
from coding_agent_playbook.evaluators.normalizer import Identity
from coding_agent_playbook.evaluators.scope import Scope
from coding_agent_playbook.metrics_gate.config import MetricConfig
from coding_agent_playbook.metrics_gate.run import (
    CONFIG_FILENAME,
    MAX_FILE_BYTES,
    MetricsGateDeps,
    MetricsGateRequest,
    MetricsGateUsageError,
    load_metrics_config,
    run_metrics_gate,
)
from tests.cli.test_metrics import _BASELINE_SOURCE, _WORSE_SOURCE
from tests.engine_modules import engine_module
from tests.fakes import FakeBaselineGit, FakeGitRunner, FakeProjectFactory
from tests.import_probe import new_modules_after

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.evaluators.types import EvalContext, Measurement

_HIGH_CC_SOURCE = (
    "def tangled(x):\n"
    + "".join(f"    if x == {i}:\n        return {i}\n" for i in range(22))
    + "    return -1\n"
)
_CLEAN_SOURCE = "def add(a, b):\n    return a + b\n"

_EXECUTION_CHECKS = {"threshold:test_pass_rate", "threshold:coverage"}


def _write(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _request(root: Path, **overrides: object) -> MetricsGateRequest:
    fields: dict[str, object] = {
        "repo_root": root,
        "config": MetricConfig(mode="absolute"),
        "paths": (str(root / "mod.py"),),
    }
    fields.update(overrides)
    return MetricsGateRequest(**fields)  # type: ignore[arg-type]


@dataclass
class FakeToolPathsMetric(Metric):
    """A static metric that records the ``tool_paths`` each context carried."""

    name = "fake_tool_paths"
    scope = Scope.MODULE
    normalizer = Identity()
    seen: list[Mapping[str, str]] = field(default_factory=list)

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        self.seen.append(ctx.tool_paths)
        return []


# --------------------------------------------------------------------------- #
# What runs
# --------------------------------------------------------------------------- #


def test_run_metrics_gate_never_runs_tests_unless_requested(tmp_path: Path) -> None:
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    factory = FakeProjectFactory()
    config = MetricConfig(mode="absolute", run_tests=True, test_cmd=["pytest"])

    result = run_metrics_gate(
        _request(tmp_path, config=config), deps=MetricsGateDeps(project_factory=factory)
    )

    assert factory.calls == []
    assert {check.check_id for check in result.report.checks}.isdisjoint(_EXECUTION_CHECKS)
    assert {finding.evaluator for finding in result.report.findings}.isdisjoint(
        {"test_pass_rate", "coverage"}
    )


@pytest.mark.parametrize(
    ("request_cmd", "expected"),
    [(("make", "test"), ["make", "test"]), (None, None)],
    ids=["explicit", "handle-default"],
)
def test_request_test_cmd_is_exactly_what_runs(
    tmp_path: Path, request_cmd: tuple[str, ...] | None, expected: list[str] | None
) -> None:
    """``config.test_cmd`` is agent-editable, so the gate never falls back to it."""
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    factory = FakeProjectFactory()
    config = MetricConfig(mode="absolute", test_cmd=["from-config"])

    result = run_metrics_gate(
        _request(tmp_path, config=config, run_tests=True, test_cmd=request_cmd),
        deps=MetricsGateDeps(project_factory=factory),
    )

    assert factory.calls == [(tmp_path, expected)]
    assert {check.check_id for check in result.report.checks} >= _EXECUTION_CHECKS


def test_test_timeout_bounds_every_suite_run(tmp_path: Path) -> None:
    """prK §F.0.3 item 7: ``[metrics] test_timeout_s`` becomes ``ProjectHandle.timeout_s``."""
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    factory = FakeProjectFactory()
    config = MetricConfig(mode="absolute", test_timeout_s=42.0)

    run_metrics_gate(
        _request(tmp_path, config=config, run_tests=True),
        deps=MetricsGateDeps(project_factory=factory),
    )

    assert [request.timeout_s for request in factory.requests] == [42.0]
    assert [handle.timeout_s for handle in factory.handles] == [42.0]


def test_suite_timeout_is_a_usage_error(tmp_path: Path) -> None:
    """A run past its bound raises ``RuntimeError`` in the handle; the gate exits 2 on it."""
    import sys

    _write(tmp_path / "mod.py", _CLEAN_SOURCE)

    def slow_factory(
        root: Path, report_dir: Path, test_cmd: list[str] | None = None, **options: Any
    ) -> ProjectHandle:
        sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]
        return ProjectHandle.create(root, report_dir, sleeper, timeout_s=0.2)

    with pytest.raises(MetricsGateUsageError, match=r"timed out after 0\.2s"):
        run_metrics_gate(
            _request(tmp_path, config=MetricConfig(mode="absolute"), run_tests=True),
            deps=MetricsGateDeps(project_factory=slow_factory),
        )


def test_tool_paths_reach_every_measurement_context(tmp_path: Path) -> None:
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    _write(tmp_path / "base" / "mod.py", _CLEAN_SOURCE)
    fake = FakeToolPathsMetric()
    deps = MetricsGateDeps(load_static_metrics=lambda: [fake])

    run_metrics_gate(
        _request(tmp_path, baseline=str(tmp_path / "base"), tool_paths={"ruff": "/bin/ruff"}),
        deps=deps,
    )

    assert fake.seen == [{"ruff": "/bin/ruff"}, {"ruff": "/bin/ruff"}]


# --------------------------------------------------------------------------- #
# Result shape
# --------------------------------------------------------------------------- #


def test_result_carries_effective_config_note_and_breach(tmp_path: Path) -> None:
    _write(tmp_path / "mod.py", _HIGH_CC_SOURCE)
    _write(tmp_path / "broken.py", "def oops(:\n    pass\n")

    result = run_metrics_gate(
        _request(tmp_path, config=MetricConfig(), paths=(str(tmp_path),), strict=True)
    )

    assert result.config.mode == "absolute"
    assert result.config.strict is True
    assert result.note == "no --baseline given; 'regression' mode falls back to 'absolute'."
    assert result.skipped == (("broken.py", "unparseable (invalid syntax)"),)
    assert result.measured_count == 1
    assert result.breached is True


def test_request_mode_overrides_config(tmp_path: Path) -> None:
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    _write(tmp_path / "base" / "mod.py", _CLEAN_SOURCE)

    result = run_metrics_gate(
        _request(tmp_path, baseline=str(tmp_path / "base"), mode="regression")
    )

    assert result.config.mode == "regression"
    assert result.note is None
    assert result.breached is False


# --------------------------------------------------------------------------- #
# Usage errors keep the CLI's messages
# --------------------------------------------------------------------------- #


@pytest.mark.usefixtures("hermetic_git_env")
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"paths": ("missing.py",)}, "path not found: missing.py"),
        ({"baseline": "no-such-dir"}, "baseline directory not found: no-such-dir"),
        ({"baseline": "git:nope"}, "bad --baseline git ref 'nope' (not a valid revision)"),
    ],
    ids=["path", "baseline-dir", "git-ref"],
)
def test_usage_errors_keep_cli_messages(
    tmp_path: Path, overrides: dict[str, object], message: str
) -> None:
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)

    with pytest.raises(MetricsGateUsageError) as excinfo:
        run_metrics_gate(_request(tmp_path, **overrides))

    assert str(excinfo.value) == message


@pytest.mark.parametrize(
    ("toml", "prefix"),
    [
        ("[metrics]\nmode = \n", f"malformed {CONFIG_FILENAME}: "),
        ('[metrics]\nmode = "sideways"\n', f"invalid [metrics] config in {CONFIG_FILENAME}: "),
    ],
    ids=["malformed", "invalid"],
)
def test_load_metrics_config_usage_errors_keep_cli_messages(
    tmp_path: Path, toml: str, prefix: str
) -> None:
    (tmp_path / CONFIG_FILENAME).write_text(toml, encoding="utf-8")

    with pytest.raises(MetricsGateUsageError) as excinfo:
        load_metrics_config(tmp_path)

    assert str(excinfo.value).startswith(prefix)


def test_load_metrics_config_defaults_without_a_config_file(tmp_path: Path) -> None:
    assert load_metrics_config(tmp_path) == MetricConfig()


def test_load_metrics_config_reads_the_metrics_table(tmp_path: Path) -> None:
    (tmp_path / CONFIG_FILENAME).write_text(
        '[metrics]\nmode = "both"\nrun_tests = true\n', encoding="utf-8"
    )

    assert load_metrics_config(tmp_path) == MetricConfig(mode="both", run_tests=True)


# --------------------------------------------------------------------------- #
# git: baselines go through the BaselineGit seam, bounded by [metrics] git_timeout_s
# --------------------------------------------------------------------------- #


def _git_factory(fake: FakeBaselineGit) -> Callable[[float], FakeBaselineGit]:
    """A ``MetricsGateDeps.git_factory`` that hands out ``fake``, built with the gate's bound."""

    def build(timeout_s: float) -> FakeBaselineGit:
        fake.timeout_s = timeout_s
        return fake

    return build


def test_git_baseline_reads_every_file_in_one_batch(tmp_path: Path) -> None:
    _write(tmp_path / "mod.py", _WORSE_SOURCE)
    _write(tmp_path / "new.py", _CLEAN_SOURCE)
    fake = FakeBaselineGit(blobs={("HEAD", "mod.py"): _BASELINE_SOURCE})
    config = MetricConfig(mode="regression", git_timeout_s=3.5)

    result = run_metrics_gate(
        _request(tmp_path, config=config, paths=(str(tmp_path),), baseline="git:HEAD"),
        deps=MetricsGateDeps(git_factory=_git_factory(fake)),
    )

    assert fake.timeout_s == 3.5
    assert fake.calls == [("rev-parse", "HEAD"), ("cat-file", "HEAD")]
    regressions = [f for f in result.report.findings if f.kind == "regression"]
    assert [f.scope_key for f in regressions if f.level == "fail"] == ["mod.py::classify"]
    assert {f.kind for f in result.report.findings if f.scope_key.startswith("new.py")} == {"new"}


@pytest.mark.parametrize("command", ["rev-parse", "cat-file"])
def test_git_timeout_is_a_usage_error_naming_command_and_seconds(
    tmp_path: Path, command: str
) -> None:
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    fake = FakeBaselineGit(timeout_on={command})

    with pytest.raises(MetricsGateUsageError) as excinfo:
        run_metrics_gate(
            _request(tmp_path, config=MetricConfig(git_timeout_s=2), baseline="git:HEAD"),
            deps=MetricsGateDeps(git_factory=_git_factory(fake)),
        )

    assert str(excinfo.value).startswith(f"git {command} timed out after 2s")


@pytest.mark.parametrize(
    ("command", "run_tests", "message"),
    [
        ("cat-file", False, "bad --baseline git ref 'HEAD': fatal: cat-file failed for HEAD"),
        (
            "worktree add",
            True,
            "could not create baseline worktree for 'HEAD': fatal: worktree add failed for HEAD",
        ),
    ],
    ids=["read", "worktree"],
)
def test_git_failures_keep_cli_messages(
    tmp_path: Path, command: str, run_tests: bool, message: str
) -> None:
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    deps = MetricsGateDeps(
        git_factory=_git_factory(FakeBaselineGit(fail_on={command})),
        # Under run_tests diff_coverage also reads the working-tree diff.
        git_runner_factory=FakeGitRunner().factory,
        project_factory=FakeProjectFactory(),
    )

    with pytest.raises(MetricsGateUsageError) as excinfo:
        run_metrics_gate(_request(tmp_path, baseline="git:HEAD", run_tests=run_tests), deps=deps)

    assert str(excinfo.value) == message


def test_git_suite_baseline_runs_in_a_worktree_then_removes_it(tmp_path: Path) -> None:
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    fake = FakeBaselineGit(blobs={("HEAD", "mod.py"): _CLEAN_SOURCE})
    factory = FakeProjectFactory()

    run_metrics_gate(
        _request(tmp_path, baseline="git:HEAD", run_tests=True),
        deps=MetricsGateDeps(
            git_factory=_git_factory(fake),
            git_runner_factory=FakeGitRunner().factory,
            project_factory=factory,
        ),
    )

    assert [command for command, _ in fake.calls][-2:] == ["worktree add", "worktree remove"]
    assert [root.name for root, _ in factory.calls] == [tmp_path.name, "baseline-worktree"]
    # Only the candidate run diffs: the baseline handle has no diff base.
    assert [request.diff_base for request in factory.requests] == ["HEAD", None]


@pytest.mark.usefixtures("hermetic_git_env")
def test_undecodable_git_baseline_is_treated_as_all_new(tmp_path: Path) -> None:
    import subprocess

    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True, timeout=30)

    git("init", "-q")
    (tmp_path / "mod.py").write_bytes(b"x = '\xff'\n")
    git("add", "mod.py")
    git("commit", "-q", "-m", "latin-1 bytes")
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)

    result = run_metrics_gate(
        _request(tmp_path, config=MetricConfig(mode="regression"), baseline="git:HEAD")
    )

    assert result.breached is False
    assert {f.kind for f in result.report.findings} == {"new"}


# --------------------------------------------------------------------------- #
# Bad input is skipped with a note, never a traceback (prK §F.0.3 item 7)
# --------------------------------------------------------------------------- #


@dataclass
class FakeRaisingMetric(Metric):
    """A static metric that raises ``error`` on any source containing ``trigger``.

    It stands in for a builtin walker that a hostile source drives into
    ``RecursionError`` or ``ValueError``; every other source measures as empty.
    """

    name = "fake_raising"
    scope = Scope.MODULE
    normalizer = Identity()
    error: Exception = field(default_factory=lambda: ValueError("bad literal"))
    trigger: str = "# HOSTILE"

    def measure(self, ctx: EvalContext) -> list[Measurement]:
        if self.trigger in ctx.source:
            raise self.error
        return []


def _with_raising_metric(error: Exception) -> MetricsGateDeps:
    return MetricsGateDeps(
        load_static_metrics=lambda: [*static_metrics(), FakeRaisingMetric(error=error)]
    )


_HOSTILE_CLEAN = _CLEAN_SOURCE + "# HOSTILE\n"


@pytest.mark.parametrize(
    ("hostile", "deps", "cap", "reason"),
    [
        (
            _HOSTILE_CLEAN,
            _with_raising_metric(RecursionError("deep")),
            MAX_FILE_BYTES,
            "too deeply nested to measure",
        ),
        (
            _HOSTILE_CLEAN,
            _with_raising_metric(ValueError("bad literal")),
            MAX_FILE_BYTES,
            "unmeasurable (bad literal)",
        ),
        (
            "x = 1\0\n",
            None,
            MAX_FILE_BYTES,
            "unparseable (source code string cannot contain null bytes)",
        ),
        ("#" * 65, None, 64, "too large (65 bytes, over the 64-byte cap)"),
        ("-" * 200_000 + "1\n", None, MAX_FILE_BYTES, "unparseable ("),
    ],
    ids=["recursion-error", "value-error", "nul-byte", "over-cap", "parser-overflow"],
)
def test_candidate_parse_errors_are_skipped_not_raised(
    tmp_path: Path, hostile: str, deps: MetricsGateDeps | None, cap: int, reason: str
) -> None:
    _write(tmp_path / "hostile.py", hostile)
    _write(tmp_path / "clean.py", _CLEAN_SOURCE)

    result = run_metrics_gate(
        _request(tmp_path, paths=(str(tmp_path),), max_file_bytes=cap), deps=deps
    )

    [(label, note)] = result.skipped
    assert (label, note[: len(reason)]) == ("hostile.py", reason)
    assert result.measured_count == 1
    assert result.breached is False


def test_undecodable_candidate_is_skipped_as_unreadable(tmp_path: Path) -> None:
    (tmp_path / "latin1.py").write_bytes(b"x = '\xff'\n")

    result = run_metrics_gate(_request(tmp_path, paths=(str(tmp_path),)))

    [(label, note)] = result.skipped
    assert label == "latin1.py"
    assert note.startswith("unreadable (")


@pytest.mark.parametrize(
    ("baseline", "deps"),
    [
        (b"x = 1\0\n", None),
        (b"x = '\xff'\n", None),
        (b"x = 1\n" + b"#" * 64, None),
        (_HOSTILE_CLEAN.encode(), _with_raising_metric(RecursionError("deep"))),
        (_HOSTILE_CLEAN.encode(), _with_raising_metric(ValueError("bad literal"))),
    ],
    ids=["nul-byte", "not-utf8", "over-cap", "recursion-error", "value-error"],
)
def test_bad_baseline_file_is_dropped_as_all_new(
    tmp_path: Path, baseline: bytes, deps: MetricsGateDeps | None
) -> None:
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / "mod.py").write_bytes(baseline)

    result = run_metrics_gate(
        _request(
            tmp_path,
            config=MetricConfig(mode="regression"),
            baseline=str(tmp_path / "base"),
            max_file_bytes=64,
        ),
        deps=deps,
    )

    assert {f.kind for f in result.report.findings} == {"new"}


def test_oversized_git_baseline_blob_is_dropped_as_all_new(tmp_path: Path) -> None:
    _write(tmp_path / "mod.py", _CLEAN_SOURCE)
    fake = FakeBaselineGit(blobs={("HEAD", "mod.py"): _CLEAN_SOURCE + "#" * 64})

    result = run_metrics_gate(
        _request(
            tmp_path, config=MetricConfig(mode="regression"), baseline="git:HEAD", max_file_bytes=64
        ),
        deps=MetricsGateDeps(git_factory=_git_factory(fake)),
    )

    assert {f.kind for f in result.report.findings} == {"new"}


def test_default_file_cap_is_one_megabyte() -> None:
    assert MAX_FILE_BYTES == 1_000_000
    assert MetricsGateRequest(repo_root=Path("."), config=MetricConfig()).max_file_bytes == (
        MAX_FILE_BYTES
    )


# --------------------------------------------------------------------------- #
# Import weight (the gate runs inside the Stop hook process)
# --------------------------------------------------------------------------- #


def test_metrics_gate_imports_no_jinja_yaml_cli_or_argparse() -> None:
    loaded = new_modules_after("import coding_agent_playbook.metrics_gate.run")

    cli = engine_module("coding_agent_playbook.cli")
    forbidden = ("jinja2", "markupsafe", "yaml", "argparse", cli)
    assert [m for m in loaded if m.split(".")[0] in forbidden or m in forbidden] == []
    # The packages above metrics_gate in engine-layers; each move PR that creates
    # one adds its prefix (specs/prT-package-layout.md 5.3.3).
    above = tuple(
        engine_module(f"coding_agent_playbook.{name}")
        for name in ("commands", "precommit", "validation")
    )
    assert [m for m in loaded if m.startswith(above)] == []


def test_default_deps_measure_with_the_static_metrics() -> None:
    assert MetricsGateDeps().load_static_metrics is static_metrics
