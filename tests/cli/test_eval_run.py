"""Tests for ``playbook eval <id> --run`` (PR R1d — the eval-runner CLI).

These exercise the execution surface that extends the v1 ``--list``/``--show``
command: select a runner via the ``coding_agent_playbook.runners`` entry-point
group, run a sample end-to-end in a temp scratch dir, render the unified
:class:`EvaluationReport` (reusing ``commands/metrics.py``'s text/json rendering),
and map the report's ``passed`` onto the process exit code.

Everything is hermetic: the only runner ever *executed* is the
:class:`~coding_agent_playbook.evals.run.fake_runner.FakeRunner` (no network, no CLI).
The ``--runner claude_code`` path is exercised only with its ``available()`` guard
monkeypatched to ``False`` so a real CLI is never invoked.
"""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.commands import eval as _eval
from coding_agent_playbook.evals import registry as _registry

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.catalog.prompt_sets import PromptSet


# --------------------------------------------------------------------------- #
# Namespace helpers
# --------------------------------------------------------------------------- #


def _ns(
    repo: Path,
    *,
    list_: bool = False,
    show: str | None = None,
    id_: str | None = None,
    run: bool = False,
    runner: str | None = None,
    fmt: str | None = None,
    judge: str | None = None,
    judge_samples: int | None = None,
    full_scoring: bool = False,
    prompt_set: str = "v1",
) -> argparse.Namespace:
    return argparse.Namespace(
        repo_root=str(repo),
        list=list_,
        show=show,
        id=id_,
        run=run,
        runner=runner,
        format=fmt,
        judge=judge,
        judge_samples=judge_samples,
        full_scoring=full_scoring,
        prompt_set=prompt_set,
    )


# A shipped engine sample with a [metrics] block and [expected] checks.
_SHIPPED_SAMPLE = "refactor/extract-helper"


def _seed(repo: Path, make_synthetic_repo: Any) -> Path:
    """A minimal valid consumer repo so SyncContext loads the engine sample set."""
    make_synthetic_repo(repo)
    return repo


# --------------------------------------------------------------------------- #
# Happy path — fake runner over a shipped sample
# --------------------------------------------------------------------------- #


def test_run_fake_on_shipped_sample_text(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any
) -> None:
    """``eval <id> --run --runner fake`` runs hermetically and prints a report.

    The default ``fake`` runner does nothing (no-op mutation), so a shipped sample
    that expects edits will *fail* its expected checks — but the command must
    still run end-to-end and render a report. We assert on the rendering + a
    well-defined exit code (0 or 1), not on a specific pass/fail.
    """
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, id_=_SHIPPED_SAMPLE, run=True, runner="fake")
    rc = _eval.run(args)
    out = capsys.readouterr().out
    assert rc in (0, 1)
    assert "Metrics" in out or "summary" in out
    assert _SHIPPED_SAMPLE in out


def test_run_fake_json_shape(tmp_path: Path, make_synthetic_repo: Any, capsys: Any) -> None:
    """``--format json`` emits a stable shape with the documented top-level keys."""
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, id_=_SHIPPED_SAMPLE, run=True, runner="fake", fmt="json")
    rc = _eval.run(args)
    out = capsys.readouterr().out
    payload = json.loads(out)

    # Documented top-level fields.
    assert payload["sample_id"] == _SHIPPED_SAMPLE
    assert payload["harness"] == "fake"
    assert isinstance(payload["passed"], bool)
    assert "aggregate_score" in payload
    assert "duration_seconds" in payload
    # The embedded report carries the metrics-style finding view.
    assert "report" in payload
    assert "findings" in payload["report"]
    assert "passed" in payload["report"]
    # Exit code mirrors report.passed.
    assert rc == (0 if payload["passed"] else 1)


def test_run_default_runner_is_claude_code(
    tmp_path: Path, make_synthetic_repo: Any, monkeypatch: Any
) -> None:
    """Omitting ``--runner`` defaults to ``claude_code`` (per R1d), guarded by available().

    With the CLI absent the command exits 2 with the clear unavailable message —
    proving the default is ``claude_code`` (not ``fake``) without invoking a CLI.
    """
    from coding_agent_playbook.evals.run.claude_code_runner import ClaudeCodeRunner

    _seed(tmp_path, make_synthetic_repo)
    monkeypatch.setattr(ClaudeCodeRunner, "available", classmethod(lambda cls: False))
    args = _ns(tmp_path, id_=_SHIPPED_SAMPLE, run=True, runner=None)
    rc = _eval.run(args)
    assert rc == 2


# --------------------------------------------------------------------------- #
# Runner availability + selection errors
# --------------------------------------------------------------------------- #


def test_run_claude_code_unavailable_exits_2(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any, monkeypatch: Any
) -> None:
    """``--runner claude_code`` with no CLI exits 2 and suggests ``--runner fake``."""
    from coding_agent_playbook.evals.run.claude_code_runner import ClaudeCodeRunner

    _seed(tmp_path, make_synthetic_repo)
    monkeypatch.setattr(ClaudeCodeRunner, "available", classmethod(lambda cls: False))
    args = _ns(tmp_path, id_=_SHIPPED_SAMPLE, run=True, runner="claude_code")
    rc = _eval.run(args)
    err = capsys.readouterr().err
    assert rc == 2
    assert "--runner fake" in err
    assert "claude_code" in err


def test_run_a_task_runs_every_sample_of_the_task(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any
) -> None:
    """``eval <task> --run`` runs each sample of the task; ``--format json`` prints a list."""
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, id_="refactor", run=True, runner="fake", fmt="json")
    rc = _eval.run(args)
    payload = json.loads(capsys.readouterr().out)

    assert rc in (0, 1)
    assert [run["sample_id"] for run in payload] == [
        "refactor/extract-helper",
        "refactor/rename-for-clarity",
    ]


def test_run_an_unknown_task_lists_the_known_tasks(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any
) -> None:
    _seed(tmp_path, make_synthetic_repo)
    rc = _eval.run(_ns(tmp_path, id_="refactr", run=True, runner="fake"))
    err = capsys.readouterr().err
    assert rc == 2
    assert "no task 'refactr'; known tasks:" in err
    assert "refactor" in err


def test_run_unknown_runner_exits_2(tmp_path: Path, make_synthetic_repo: Any, capsys: Any) -> None:
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, id_=_SHIPPED_SAMPLE, run=True, runner="does-not-exist")
    rc = _eval.run(args)
    err = capsys.readouterr().err
    assert rc == 2
    assert "does-not-exist" in err


def test_run_unknown_sample_exits_2(tmp_path: Path, make_synthetic_repo: Any, capsys: Any) -> None:
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, id_="no-such-sample-xyz", run=True, runner="fake")
    rc = _eval.run(args)
    err = capsys.readouterr().err
    assert rc == 2
    assert "no-such-sample-xyz" in err


def test_run_unknown_format_exits_2(tmp_path: Path, make_synthetic_repo: Any, capsys: Any) -> None:
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, id_=_SHIPPED_SAMPLE, run=True, runner="fake", fmt="yaml")
    rc = _eval.run(args)
    err = capsys.readouterr().err
    assert rc == 2
    assert "yaml" in err


# --------------------------------------------------------------------------- #
# --judge selection + availability (R2)
# --------------------------------------------------------------------------- #


def test_run_judge_llm_unavailable_exits_2(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any, monkeypatch: Any
) -> None:
    """``--judge llm`` with the ``claude`` CLI absent exits 2 with a clear message."""
    from coding_agent_playbook.evals.judge import LLMJudge

    _seed(tmp_path, make_synthetic_repo)
    monkeypatch.setattr(LLMJudge, "available", classmethod(lambda cls: False))
    args = _ns(tmp_path, id_=_SHIPPED_SAMPLE, run=True, runner="fake", judge="llm")
    rc = _eval.run(args)
    err = capsys.readouterr().err
    assert rc == 2
    assert "llm" in err
    assert "--judge" in err or "deterministic" in err


def test_run_unknown_judge_exits_2(tmp_path: Path, make_synthetic_repo: Any, capsys: Any) -> None:
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, id_=_SHIPPED_SAMPLE, run=True, runner="fake", judge="does-not-exist")
    rc = _eval.run(args)
    err = capsys.readouterr().err
    assert rc == 2
    assert "does-not-exist" in err


def test_run_judge_omitted_is_deterministic_only(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any
) -> None:
    """Omitting ``--judge`` runs deterministic-only (no judge instantiated)."""
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, id_=_SHIPPED_SAMPLE, run=True, runner="fake", judge=None, fmt="json")
    rc = _eval.run(args)
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert rc in (0, 1)
    # No judged findings without a judge.
    findings = payload["report"]["findings"]
    assert not any(str(f.get("evaluator", "")).startswith("judged:") for f in findings)


def test_run_judge_available_is_passed_to_runner(
    tmp_path: Path, make_synthetic_repo: Any, monkeypatch: Any
) -> None:
    """An available judge is instantiated and threaded into ``run_sample``.

    Hermetic: we register an available stub judge under the ``llm`` name (patching
    the loader) and assert the runner received a non-None judge + the requested
    samples.
    """
    from coding_agent_playbook.evals.judge import StubJudge
    from coding_agent_playbook.evals.run.harness_runner import HarnessRunner

    _seed(tmp_path, make_synthetic_repo)

    class _AvailableStub(StubJudge):
        @classmethod
        def available(cls) -> bool:
            return True

    captured: dict[str, Any] = {}
    real_run_sample = HarnessRunner.run_sample

    def _spy(
        self: Any,
        sample: Any,
        scratch: Any,
        *,
        judge: Any = None,
        judge_samples: int = 1,
        fail_fast: bool = True,
        prompt_set: PromptSet = "v1",
    ) -> Any:
        captured["judge"] = judge
        captured["judge_samples"] = judge_samples
        captured["fail_fast"] = fail_fast
        return real_run_sample(
            self,
            sample,
            scratch,
            judge=judge,
            judge_samples=judge_samples,
            fail_fast=fail_fast,
            prompt_set=prompt_set,
        )

    monkeypatch.setattr(_registry, "load_judge_class", lambda name: _AvailableStub)
    monkeypatch.setattr(HarnessRunner, "run_sample", _spy)

    args = _ns(tmp_path, id_=_SHIPPED_SAMPLE, run=True, runner="fake", judge="llm", judge_samples=4)
    _eval.run(args)

    assert isinstance(captured["judge"], _AvailableStub)
    assert captured["judge_samples"] == 4


# --------------------------------------------------------------------------- #
# Gate semantics — a worsening mutation fails (exit 1)
# --------------------------------------------------------------------------- #


def test_run_failing_gate_exits_1(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any, monkeypatch: Any
) -> None:
    """A registered fake runner whose mutation worsens CC fails the gate → exit 1.

    Hermetic: we register a test-only ``fake`` runner whose mutation breaks the
    expected checks of a synthetic sample. We drive it via the entry-point selection
    by monkeypatching the loader to return our worsening FakeRunner class.
    """
    import textwrap

    from coding_agent_playbook.evals.run.fake_runner import FakeRunner, write_files

    _seed(tmp_path, make_synthetic_repo)

    worse = textwrap.dedent(
        """\
        def classify(n):
            if n < 0:
                return "neg"
            if n == 0:
                return "zero"
            if n < 10:
                return "small"
            if n < 100:
                return "medium"
            if n % 2 == 0:
                return "even"
            if n % 3 == 0:
                return "div3"
            if n % 5 == 0:
                return "div5"
            return "other"
        """
    )

    # Build a synthetic sample on disk with a [metrics] CC gate + an [expected]
    # file-unchanged check that the worsening edit violates.
    sample_dir = tmp_path / "eval_samples" / "refactor" / "synthetic"
    setup = sample_dir / "setup"
    setup.mkdir(parents=True, exist_ok=True)
    (setup / "mod.py").write_text(
        "def classify(n):\n    return 'small' if n < 10 else 'big'\n",
        encoding="utf-8",
    )
    (sample_dir / "sample.toml").write_text(
        textwrap.dedent(
            """\
            id = "refactor/synthetic"
            description = "synthetic worsening sample"

            [setup]
            files = ["mod.py"]

            [gate]
            expr = "unchanged and cc"

            [gate.bind]
            unchanged = { check = "file_unchanged", path = "mod.py" }
            cc = { check = "non_regression", metric = "cyclomatic_complexity", warn = 0.5, fail = 0.25 }

            [verdict]
            trial = "gate"
            """
        ),
        encoding="utf-8",
    )

    # A runner class constructible with no args that applies the worsening edit.
    class _WorseRunner(FakeRunner):
        def __init__(self) -> None:
            super().__init__(write_files({"mod.py": worse}))

    # Patch runner discovery so ``--runner fake`` yields our worsening runner.
    monkeypatch.setattr(_registry, "load_runner_class", lambda name: _WorseRunner)

    # Point loading at the synthetic sample dir.
    args = _ns(tmp_path, id_="refactor/synthetic", run=True, runner="fake")
    # Make the sample discoverable: the synthetic sample lives under tmp_path.
    monkeypatch.setattr(
        _eval, "_select_samples", lambda name, repo_root: (_load_synthetic(sample_dir),)
    )

    rc = _eval.run(args)
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL" in out or "fail" in out


def _load_synthetic(sample_dir: Path) -> Any:
    from coding_agent_playbook.evals.task_registry import load_task_sample

    return load_task_sample(sample_dir, source_package="<test>")


# --------------------------------------------------------------------------- #
# v1 surface unchanged — --list / --show still work
# --------------------------------------------------------------------------- #


def test_list_still_works(tmp_path: Path, make_synthetic_repo: Any, capsys: Any) -> None:
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, list_=True)
    rc = _eval.run(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert "Eval samples" in out


def test_show_still_works(tmp_path: Path, make_synthetic_repo: Any, capsys: Any) -> None:
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, show=_SHIPPED_SAMPLE)
    rc = _eval.run(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert f"Sample: {_SHIPPED_SAMPLE}" in out


def test_bare_id_without_run_prints_a_run_hint(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any
) -> None:
    """Without ``--run``, a bare ``<id>`` runs nothing and says how to (exit 0)."""
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, id_=_SHIPPED_SAMPLE, run=False)
    rc = _eval.run(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert "runner" in out.lower()


def test_run_requires_an_id(tmp_path: Path, capsys: Any) -> None:
    """``--run`` with no sample id is a usage error (exit 2)."""
    args = _ns(tmp_path, id_=None, run=True, runner="fake")
    rc = _eval.run(args)
    err = capsys.readouterr().err
    assert rc == 2
    assert "id" in err.lower() or "sample" in err.lower()


# --------------------------------------------------------------------------- #
# Review samples, unscorable runs, and judged-score labelling
# --------------------------------------------------------------------------- #

#: A shipped review sample: its gate is ``file_unchanged``, so a no-op agent passes it.
_REVIEW_SAMPLE = "review/spot-the-bug"


def _available_judge(score: float | None) -> type:
    """A judge class the CLI can load as ``--judge llm``.

    ``score=None`` makes every grading raise :class:`JudgeError` (a broken CLI).
    """
    from coding_agent_playbook.evals.judge import JudgeError, StubJudge

    class _Judge(StubJudge):
        @classmethod
        def available(cls) -> bool:
            return True

        def score_criterion(self, criterion: str, artifact: Any, n: int = 1) -> float:
            if score is None:
                raise JudgeError("judge 'claude' gave no score: exited 1: API Error: 529")
            return score

    return _Judge


def test_run_review_sample_renders_and_skips_rubric_without_judge(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any
) -> None:
    """Regression: the review prompt crashed on ``rule()`` before any agent ran,
    and the judge-less rubric layer then printed a vacuous ``[PASS]``."""
    _seed(tmp_path, make_synthetic_repo)
    rc = _eval.run(_ns(tmp_path, id_=_REVIEW_SAMPLE, run=True, runner="fake"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "[skip] rubric" in out
    assert "[PASS] rubric" not in out
    assert "uncalibrated" not in out


def test_run_judge_error_exits_2_not_a_verdict(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any, monkeypatch: Any
) -> None:
    """A judge that cannot score makes the sample unscorable: exit 2, no report."""
    _seed(tmp_path, make_synthetic_repo)
    monkeypatch.setattr(_registry, "load_judge_class", lambda name: _available_judge(None))
    rc = _eval.run(_ns(tmp_path, id_=_REVIEW_SAMPLE, run=True, runner="fake", judge="llm"))
    captured = capsys.readouterr()
    assert rc == 2
    assert "could not be scored" in captured.err
    assert "API Error: 529" in captured.err
    assert "summary:" not in captured.out


def test_run_prompt_render_error_exits_2(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any, monkeypatch: Any
) -> None:
    """A prompt that fails to render is an authoring error (exit 2), not a FAIL (1)."""
    from coding_agent_playbook.evals.prompting import PromptResolutionError
    from coding_agent_playbook.evals.run.harness_runner import HarnessRunner

    def _boom(self: Any, sample: Any, scratch: Any, **kwargs: Any) -> Any:
        raise PromptResolutionError("prompt 'refactor' for sample 'x' failed to render: boom")

    _seed(tmp_path, make_synthetic_repo)
    monkeypatch.setattr(HarnessRunner, "run_sample", _boom)
    rc = _eval.run(_ns(tmp_path, id_=_SHIPPED_SAMPLE, run=True, runner="fake"))
    assert rc == 2
    assert "failed to render: boom" in capsys.readouterr().err


def test_run_with_a_judge_labels_scores_uncalibrated(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any, monkeypatch: Any
) -> None:
    """Judged scores carry an "uncalibrated" note until SPEC §19 Q12 lands."""
    _seed(tmp_path, make_synthetic_repo)
    monkeypatch.setattr(_registry, "load_judge_class", lambda name: _available_judge(0.9))
    rc = _eval.run(_ns(tmp_path, id_=_REVIEW_SAMPLE, run=True, runner="fake", judge="llm"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "[PASS] rubric" in out
    assert "uncalibrated" in out


def test_run_json_reports_whether_judged_scores_are_uncalibrated(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any, monkeypatch: Any
) -> None:
    _seed(tmp_path, make_synthetic_repo)
    _eval.run(_ns(tmp_path, id_=_REVIEW_SAMPLE, run=True, runner="fake", fmt="json"))
    assert json.loads(capsys.readouterr().out)["uncalibrated_judge"] is False

    monkeypatch.setattr(_registry, "load_judge_class", lambda name: _available_judge(0.9))
    _eval.run(_ns(tmp_path, id_=_REVIEW_SAMPLE, run=True, runner="fake", fmt="json", judge="llm"))
    assert json.loads(capsys.readouterr().out)["uncalibrated_judge"] is True


# --------------------------------------------------------------------------- #
# --judge-samples and its deprecated --samples alias (D80)
# --------------------------------------------------------------------------- #


def _counting_judge(calls: list[int]) -> type:
    """A judge class the CLI loads as ``--judge llm`` that records each ``n``."""
    from coding_agent_playbook.evals.judge import StubJudge

    class _Judge(StubJudge):
        @classmethod
        def available(cls) -> bool:
            return True

        def score_criterion(self, criterion: str, artifact: Any, n: int = 1) -> float:
            calls.append(n)
            return 0.9

    return _Judge


def _run_argv(repo: Path, *flags: str) -> int:
    """Parse ``playbook eval`` argv through the real parser and run it."""
    from coding_agent_playbook.cli.parser import build_parser

    argv = ["eval", _REVIEW_SAMPLE, "--run", "--runner", "fake", "--judge", "llm"]
    args = build_parser().parse_args([*argv, "--repo-root", str(repo), *flags])
    return int(_eval.run(args))


def test_judge_samples_reaches_the_judge_as_n(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any, monkeypatch: Any
) -> None:
    """``--judge-samples 3`` scores each rubric criterion with ``n=3``."""
    _seed(tmp_path, make_synthetic_repo)
    calls: list[int] = []
    monkeypatch.setattr(_registry, "load_judge_class", lambda name: _counting_judge(calls))
    assert _run_argv(tmp_path, "--judge-samples", "3") == 0
    assert calls and set(calls) == {3}
    assert "--samples" not in capsys.readouterr().err


def test_deprecated_samples_alias_still_works_and_warns_once(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any, monkeypatch: Any
) -> None:
    """``--samples 3`` scores like ``--judge-samples 3`` and names the new flag once."""
    _seed(tmp_path, make_synthetic_repo)
    calls: list[int] = []
    monkeypatch.setattr(_registry, "load_judge_class", lambda name: _counting_judge(calls))
    assert _run_argv(tmp_path, "--samples", "3", "--format", "json") == 0
    assert calls and set(calls) == {3}
    alias = capsys.readouterr()
    err_lines = [line for line in alias.err.splitlines() if line]
    assert len(err_lines) == 1
    assert "--judge-samples" in err_lines[0]
    # Same report as the new spelling, so the alias cannot drift after resolution.
    assert _run_argv(tmp_path, "--judge-samples", "3", "--format", "json") == 0
    assert _timeless(alias.out) == _timeless(capsys.readouterr().out)


def _timeless(report_json: str) -> dict[str, Any]:
    """A parsed ``--format json`` report without its wall-clock duration."""
    report: dict[str, Any] = json.loads(report_json)
    report.pop("duration_seconds", None)
    return report


@pytest.mark.parametrize("flag", ["--judge-samples", "--samples"])
@pytest.mark.parametrize("value", ["0", "-3"])
def test_non_positive_judge_samples_is_a_usage_error(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any, monkeypatch: Any, flag: str, value: str
) -> None:
    """A non-positive count is rejected with the offending value, never floored to 1."""
    _seed(tmp_path, make_synthetic_repo)
    calls: list[int] = []
    monkeypatch.setattr(_registry, "load_judge_class", lambda name: _counting_judge(calls))
    assert _run_argv(tmp_path, flag, value) == 2
    assert f"--judge-samples must be >= 1, got {value}" in capsys.readouterr().err
    assert calls == []


def test_both_sample_flags_is_a_usage_error(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any, monkeypatch: Any
) -> None:
    _seed(tmp_path, make_synthetic_repo)
    calls: list[int] = []
    monkeypatch.setattr(_registry, "load_judge_class", lambda name: _counting_judge(calls))
    assert _run_argv(tmp_path, "--samples", "2", "--judge-samples", "3") == 2
    err = capsys.readouterr().err
    assert "--samples" in err and "--judge-samples" in err
    assert calls == []


def test_help_lists_judge_samples_but_not_samples(capsys: Any) -> None:
    from coding_agent_playbook.cli.parser import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(["eval", "--help"])
    help_text = capsys.readouterr().out
    assert "--judge-samples" in help_text
    assert "--samples" not in help_text
