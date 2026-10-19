"""``ruff_violations``: per-family ruff counts, candidate and baseline through stdin (prK §F.2.1).

ruff is ``FakeRuffRunner`` (scripted JSON per source text) behind
``MetricsGateDeps.tool_runner`` or ``ToolSetup.runner``; no ruff ever runs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

from coding_agent_playbook.grading.parse import parse_module
from coding_agent_playbook.grading.static_metrics.ruff_violations import (
    RuffViolationsMetric,
    ruff_family,
)
from coding_agent_playbook.grading.types import EvalContext, Measurement, RuffSettings, ToolSetup
from coding_agent_playbook.metrics_gate.config import MetricConfig
from coding_agent_playbook.metrics_gate.run import (
    MetricsGateDeps,
    MetricsGateRequest,
    run_metrics_gate,
)
from tests.fakes import FakeBaselineGit, FakeRuffRunner, ruff_row

RUFF: Final = "/venv/bin/ruff"
SOURCE: Final = "def load(path):\n    return path\n"
GROWN: Final = "def load(path):\n    return path\n\n\ndef save(path):\n    return path\n"


def _ctx(runner: FakeRuffRunner, source: str = SOURCE, **setup: object) -> EvalContext:
    return EvalContext(
        module=parse_module(source, "src/x.py"),
        source=source,
        label="src/x.py",
        tool_paths={"ruff": RUFF},
        tool_setup=ToolSetup(cwd=Path("/repo"), runner=runner, timeout_s=4.0, **setup),  # type: ignore[arg-type]
    )


def _measure(runner: FakeRuffRunner, source: str = SOURCE, **setup: object) -> list[Measurement]:
    return RuffViolationsMetric().measure(_ctx(runner, source, **setup))


def _values(measurements: list[Measurement]) -> dict[str, float]:
    return {m.scope_key: m.value for m in measurements}


def test_counts_per_family_scope_keys() -> None:
    runner = FakeRuffRunner(
        answers={SOURCE: [ruff_row("D103", 1), ruff_row("C901", 1), ruff_row("D100", 1)]}
    )

    measured = _measure(runner)

    assert _values(measured) == {"src/x.py::ruff:quality": 1.0, "src/x.py::ruff:docstrings": 2.0}
    assert {m.evaluator for m in measured} == {"ruff_violations"}
    assert [ruff_family(m.scope_key) for m in measured] == ["quality", "docstrings"]


def test_code_outside_every_family_ignored() -> None:
    runner = FakeRuffRunner(answers={SOURCE: [ruff_row("E501", 1), ruff_row("PLR0913", 1)]})

    assert _values(_measure(runner)) == {
        "src/x.py::ruff:quality": 1.0,
        "src/x.py::ruff:docstrings": 0.0,
    }


def test_syntax_error_code_null_yields_no_measurement() -> None:
    runner = FakeRuffRunner(answers={SOURCE: [ruff_row("D103", 1), ruff_row(None, 2)]})

    assert _measure(runner) == []


def test_timeout_yields_no_measurement_never_zero() -> None:
    assert _measure(FakeRuffRunner(timeout=True)) == []


def test_ruff_error_exit_yields_no_measurement() -> None:
    assert _measure(FakeRuffRunner(returncode=2)) == []


def test_every_family_emptied_runs_no_ruff() -> None:
    runner = FakeRuffRunner()

    assert _measure(runner, ruff=RuffSettings(families={})) == []
    assert runner.calls == []  # ruff would reject an empty --select


def test_unavailable_without_ruff_path() -> None:
    ctx = _ctx(FakeRuffRunner())
    without = EvalContext(module=ctx.module, source=SOURCE, label="src/x.py")

    assert RuffViolationsMetric().available(ctx)
    assert not RuffViolationsMetric().available(without)
    assert RuffViolationsMetric().measure(without) == []


def test_argv_reads_stdin_in_the_repo_root_with_the_configured_codes() -> None:
    runner = FakeRuffRunner()

    _measure(runner, ruff=RuffSettings(families={"quality": ("C901", "PLR0915")}))

    [(argv, stdin, cwd, timeout_s)] = runner.calls
    assert argv == (
        RUFF,
        *("check", "--no-fix", "--exit-zero", "--force-exclude", "--output-format", "json"),
        *("--stdin-filename", "src/x.py", "--select", "C901,PLR0915", "-"),
    )
    assert (stdin, cwd, timeout_s) == (SOURCE, Path("/repo"), 4.0)


@pytest.mark.parametrize("preview", [False, True])
def test_preview_flag_only_when_enabled(preview: bool) -> None:
    runner = FakeRuffRunner()

    _measure(runner, ruff=RuffSettings(preview=preview))

    [(argv, *_)] = runner.calls
    assert ("--preview" in argv) is preview


def test_config_overrides_rendered_as_config_flags() -> None:
    config = MetricConfig(ruff_config={"lint.pylint.max-args": 5, "lint.mccabe.max-complexity": 10})
    runner = FakeRuffRunner()

    _measure(runner, ruff=config.ruff_settings)

    [(argv, *_)] = runner.calls
    flags = [argv[i + 1] for i, arg in enumerate(argv) if arg == "--config"]
    assert flags == ["lint.mccabe.max-complexity=10", "lint.pylint.max-args=5"]


# --------------------------------------------------------------------------- #
# Through the gate: both sides on stdin, non-regression, the per-run memo
# --------------------------------------------------------------------------- #


def _gate(tmp_path: Path, runner: FakeRuffRunner, head: dict[str, str]) -> list[tuple[str, str]]:
    """``(scope_key, level)`` of every ruff finding of a ``git:HEAD`` run over ``tmp_path``."""
    git = FakeBaselineGit(blobs={("HEAD", rel): text for rel, text in head.items()})
    request = MetricsGateRequest(
        repo_root=tmp_path,
        config=MetricConfig(),
        paths=(str(tmp_path),),
        baseline="git:HEAD",
        tool_paths={"ruff": RUFF},
        select=("ruff_violations",),
    )
    deps = MetricsGateDeps(git_factory=lambda _timeout: git, tool_runner=runner)
    result = run_metrics_gate(request, deps=deps)
    return [(f.scope_key, f.level) for f in result.report.findings]


def _write(root: Path, rel: str, text: str) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text(text, encoding="utf-8")


def test_candidate_and_baseline_argv_both_use_stdin_force_exclude_select_exit_zero(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "x.py", GROWN)
    runner = FakeRuffRunner()

    _gate(tmp_path, runner, {"x.py": SOURCE})

    assert sorted(stdin for _, stdin, _, _ in runner.calls) == sorted([SOURCE, GROWN])
    for argv, _, cwd, _ in runner.calls:
        assert {"--stdin-filename", "--force-exclude", "--select", "--exit-zero"} <= set(argv)
        assert (argv[-1], cwd) == ("-", tmp_path)


def test_unchanged_file_costs_one_ruff_call(tmp_path: Path) -> None:
    _write(tmp_path, "x.py", SOURCE)
    runner = FakeRuffRunner()

    _gate(tmp_path, runner, {"x.py": SOURCE})

    assert len(runner.calls) == 1


def test_nonregression_0_to_0_silent_1_to_2_fails_new_unbanded_file_silent(
    tmp_path: Path,
) -> None:
    legacy_base = "def a(x):\n    return x\n"
    legacy_now = "def a(x):\n    return x  # edited\n"
    _write(tmp_path, "same.py", SOURCE)
    _write(tmp_path, "worse.py", legacy_now)
    _write(tmp_path, "new.py", GROWN)
    runner = FakeRuffRunner(
        answers={
            legacy_base: [ruff_row("D103", 1)],
            legacy_now: [ruff_row("D103", 1), ruff_row("D100", 1)],
            GROWN: [ruff_row("D103", 1), ruff_row("D103", 5), ruff_row("C901", 5)],
        }
    )

    findings = _gate(tmp_path, runner, {"same.py": SOURCE, "worse.py": legacy_base})

    assert [key for key, level in findings if level != "ok"] == ["worse.py::ruff:docstrings"]
    assert ("same.py::ruff:quality", "ok") in findings
    assert {level for key, level in findings if key.startswith("new.py")} == {"ok"}
