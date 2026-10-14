"""Tests for the jinja-free ``playbook metrics`` gate (prK §F.0.3 item 1, P-D3).

``run_metrics_gate`` is the entry point the Stop stages call in-process, so it
must never run a suite unless the request says so, must run exactly the request's
test command, and must keep the CLI's usage-error wording. The CLI output itself
is pinned byte for byte by ``tests/cli/test_metrics_golden.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.evaluators.metric import Metric, static_metrics
from coding_agent_playbook.evaluators.metrics_gate import (
    CONFIG_FILENAME,
    MetricsGateDeps,
    MetricsGateRequest,
    MetricsGateUsageError,
    load_metrics_config,
    run_metrics_gate,
)
from coding_agent_playbook.evaluators.normalizer import Identity
from coding_agent_playbook.evaluators.scope import Scope
from coding_agent_playbook.evaluators.types import EvalContext, Measurement, MetricConfig
from tests.fakes import FakeProjectFactory
from tests.import_probe import new_modules_after

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

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
# Import weight (the gate runs inside the Stop hook process)
# --------------------------------------------------------------------------- #


def test_metrics_gate_imports_no_jinja_yaml_cli_or_argparse() -> None:
    loaded = new_modules_after("import coding_agent_playbook.evaluators.metrics_gate")

    forbidden = ("jinja2", "markupsafe", "yaml", "argparse", "coding_agent_playbook.cli")
    assert [m for m in loaded if m.split(".")[0] in forbidden or m in forbidden] == []
    assert [m for m in loaded if m.startswith("coding_agent_playbook.commands")] == []


def test_default_deps_measure_with_the_static_metrics() -> None:
    assert MetricsGateDeps().load_static_metrics is static_metrics
