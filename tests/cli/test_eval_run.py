"""Tests for ``playbook eval <id> --run`` (PR R1d — the eval-runner CLI).

These exercise the execution surface that extends the v1 ``--list``/``--show``
command: select a runner via the ``coding_agent_playbook.runners`` entry-point
group, run a task end-to-end in a temp scratch dir, render the unified
:class:`EvaluationReport` (reusing ``commands/metrics.py``'s text/json rendering),
and map the report's ``passed`` onto the process exit code.

Everything is hermetic: the only runner ever *executed* is the
:class:`~coding_agent_playbook.evals.fake_runner.FakeRunner` (no network, no CLI).
The ``--runner claude_code`` path is exercised only with its ``available()`` guard
monkeypatched to ``False`` so a real CLI is never invoked.
"""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.commands import eval as _eval
from coding_agent_playbook.evals import registry as _registry

if TYPE_CHECKING:
    from pathlib import Path


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
    samples: int | None = None,
    full_scoring: bool = False,
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
        samples=samples,
        full_scoring=full_scoring,
    )


# A shipped engine task with a [metrics] block and [expected] checks.
_SHIPPED_TASK = "refactor-extract-helper"


def _seed(repo: Path, make_synthetic_repo: Any) -> Path:
    """A minimal valid consumer repo so SyncContext loads the engine task set."""
    make_synthetic_repo(repo)
    return repo


# --------------------------------------------------------------------------- #
# Happy path — fake runner over a shipped task
# --------------------------------------------------------------------------- #


def test_run_fake_on_shipped_task_text(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any
) -> None:
    """``eval <id> --run --runner fake`` runs hermetically and prints a report.

    The default ``fake`` runner does nothing (no-op mutation), so a shipped task
    that expects edits will *fail* its expected checks — but the command must
    still run end-to-end and render a report. We assert on the rendering + a
    well-defined exit code (0 or 1), not on a specific pass/fail.
    """
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, id_=_SHIPPED_TASK, run=True, runner="fake")
    rc = _eval.run(args)
    out = capsys.readouterr().out
    assert rc in (0, 1)
    assert "Metrics" in out or "summary" in out
    assert _SHIPPED_TASK in out


def test_run_fake_json_shape(tmp_path: Path, make_synthetic_repo: Any, capsys: Any) -> None:
    """``--format json`` emits a stable shape with the documented top-level keys."""
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, id_=_SHIPPED_TASK, run=True, runner="fake", fmt="json")
    rc = _eval.run(args)
    out = capsys.readouterr().out
    payload = json.loads(out)

    # Documented top-level fields.
    assert payload["task_id"] == _SHIPPED_TASK
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
    from coding_agent_playbook.evals.claude_code_runner import ClaudeCodeRunner

    _seed(tmp_path, make_synthetic_repo)
    monkeypatch.setattr(ClaudeCodeRunner, "available", classmethod(lambda cls: False))
    args = _ns(tmp_path, id_=_SHIPPED_TASK, run=True, runner=None)
    rc = _eval.run(args)
    assert rc == 2


# --------------------------------------------------------------------------- #
# Runner availability + selection errors
# --------------------------------------------------------------------------- #


def test_run_claude_code_unavailable_exits_2(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any, monkeypatch: Any
) -> None:
    """``--runner claude_code`` with no CLI exits 2 and suggests ``--runner fake``."""
    from coding_agent_playbook.evals.claude_code_runner import ClaudeCodeRunner

    _seed(tmp_path, make_synthetic_repo)
    monkeypatch.setattr(ClaudeCodeRunner, "available", classmethod(lambda cls: False))
    args = _ns(tmp_path, id_=_SHIPPED_TASK, run=True, runner="claude_code")
    rc = _eval.run(args)
    err = capsys.readouterr().err
    assert rc == 2
    assert "--runner fake" in err
    assert "claude_code" in err


def test_run_unknown_runner_exits_2(tmp_path: Path, make_synthetic_repo: Any, capsys: Any) -> None:
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, id_=_SHIPPED_TASK, run=True, runner="does-not-exist")
    rc = _eval.run(args)
    err = capsys.readouterr().err
    assert rc == 2
    assert "does-not-exist" in err


def test_run_unknown_task_exits_2(tmp_path: Path, make_synthetic_repo: Any, capsys: Any) -> None:
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, id_="no-such-task-xyz", run=True, runner="fake")
    rc = _eval.run(args)
    err = capsys.readouterr().err
    assert rc == 2
    assert "no-such-task-xyz" in err


def test_run_unknown_format_exits_2(tmp_path: Path, make_synthetic_repo: Any, capsys: Any) -> None:
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, id_=_SHIPPED_TASK, run=True, runner="fake", fmt="yaml")
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
    args = _ns(tmp_path, id_=_SHIPPED_TASK, run=True, runner="fake", judge="llm")
    rc = _eval.run(args)
    err = capsys.readouterr().err
    assert rc == 2
    assert "llm" in err
    assert "--judge" in err or "deterministic" in err


def test_run_unknown_judge_exits_2(tmp_path: Path, make_synthetic_repo: Any, capsys: Any) -> None:
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, id_=_SHIPPED_TASK, run=True, runner="fake", judge="does-not-exist")
    rc = _eval.run(args)
    err = capsys.readouterr().err
    assert rc == 2
    assert "does-not-exist" in err


def test_run_judge_omitted_is_deterministic_only(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any
) -> None:
    """Omitting ``--judge`` runs deterministic-only (no judge instantiated)."""
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, id_=_SHIPPED_TASK, run=True, runner="fake", judge=None, fmt="json")
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
    """An available judge is instantiated and threaded into ``run_task``.

    Hermetic: we register an available stub judge under the ``llm`` name (patching
    the loader) and assert the runner received a non-None judge + the requested
    samples.
    """
    from coding_agent_playbook.evals.judge import StubJudge
    from coding_agent_playbook.evals.runner import HarnessRunner

    _seed(tmp_path, make_synthetic_repo)

    class _AvailableStub(StubJudge):
        @classmethod
        def available(cls) -> bool:
            return True

    captured: dict[str, Any] = {}
    real_run_task = HarnessRunner.run_task

    def _spy(
        self: Any,
        task: Any,
        scratch: Any,
        *,
        judge: Any = None,
        samples: int = 1,
        fail_fast: bool = True,
    ) -> Any:
        captured["judge"] = judge
        captured["samples"] = samples
        captured["fail_fast"] = fail_fast
        return real_run_task(self, task, scratch, judge=judge, samples=samples, fail_fast=fail_fast)

    monkeypatch.setattr(_registry, "load_judge_class", lambda name: _AvailableStub)
    monkeypatch.setattr(HarnessRunner, "run_task", _spy)

    args = _ns(tmp_path, id_=_SHIPPED_TASK, run=True, runner="fake", judge="llm", samples=4)
    _eval.run(args)

    assert isinstance(captured["judge"], _AvailableStub)
    assert captured["samples"] == 4


# --------------------------------------------------------------------------- #
# Gate semantics — a worsening mutation fails (exit 1)
# --------------------------------------------------------------------------- #


def test_run_failing_gate_exits_1(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any, monkeypatch: Any
) -> None:
    """A registered fake runner whose mutation worsens CC fails the gate → exit 1.

    Hermetic: we register a test-only ``fake`` runner whose mutation breaks the
    expected checks of a synthetic task. We drive it via the entry-point selection
    by monkeypatching the loader to return our worsening FakeRunner class.
    """
    import textwrap

    from coding_agent_playbook.evals.fake_runner import FakeRunner, write_files

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

    # Build a synthetic task on disk with a [metrics] CC gate + an [expected]
    # file-unchanged check that the worsening edit violates.
    task_dir = tmp_path / "eval_tasks" / "synthetic"
    setup = task_dir / "setup"
    setup.mkdir(parents=True, exist_ok=True)
    (setup / "mod.py").write_text(
        "def classify(n):\n    return 'small' if n < 10 else 'big'\n",
        encoding="utf-8",
    )
    (task_dir / "task.toml").write_text(
        textwrap.dedent(
            """\
            id = "synthetic"
            prompt_id = "refactor"
            description = "synthetic worsening task"
            version = 1

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

    # Point loading at the synthetic task dir.
    args = _ns(tmp_path, id_="synthetic", run=True, runner="fake")
    # Make the task discoverable: the synthetic task lives under tmp_path.
    monkeypatch.setattr(
        _eval, "_load_task", lambda task_id, repo_root: _load_synthetic(task_dir, task_id)
    )

    rc = _eval.run(args)
    out = capsys.readouterr().out
    assert rc == 1
    assert "FAIL" in out or "fail" in out


def _load_synthetic(task_dir: Path, task_id: str) -> Any:
    from coding_agent_playbook.evals.loader import load_eval_task_from_dir

    return load_eval_task_from_dir(task_dir, source_package="<test>")


# --------------------------------------------------------------------------- #
# v1 surface unchanged — --list / --show still work
# --------------------------------------------------------------------------- #


def test_list_still_works(tmp_path: Path, make_synthetic_repo: Any, capsys: Any) -> None:
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, list_=True)
    rc = _eval.run(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert "Eval tasks" in out


def test_show_still_works(tmp_path: Path, make_synthetic_repo: Any, capsys: Any) -> None:
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, show=_SHIPPED_TASK)
    rc = _eval.run(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert f"Task: {_SHIPPED_TASK}" in out


def test_bare_id_without_run_prints_a_run_hint(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any
) -> None:
    """Without ``--run``, a bare ``<id>`` runs nothing and says how to (exit 0)."""
    _seed(tmp_path, make_synthetic_repo)
    args = _ns(tmp_path, id_=_SHIPPED_TASK, run=False)
    rc = _eval.run(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert "runner" in out.lower()


def test_run_requires_an_id(tmp_path: Path, capsys: Any) -> None:
    """``--run`` with no task id is a usage error (exit 2)."""
    args = _ns(tmp_path, id_=None, run=True, runner="fake")
    rc = _eval.run(args)
    err = capsys.readouterr().err
    assert rc == 2
    assert "id" in err.lower() or "task" in err.lower()


# --------------------------------------------------------------------------- #
# Review tasks, unscorable runs, and judged-score labelling
# --------------------------------------------------------------------------- #

#: A shipped review task: its gate is ``file_unchanged``, so a no-op agent passes it.
_REVIEW_TASK = "review-spot-the-bug"


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


def test_run_review_task_renders_and_skips_rubric_without_judge(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any
) -> None:
    """Regression: the review prompt crashed on ``rule()`` before any agent ran,
    and the judge-less rubric layer then printed a vacuous ``[PASS]``."""
    _seed(tmp_path, make_synthetic_repo)
    rc = _eval.run(_ns(tmp_path, id_=_REVIEW_TASK, run=True, runner="fake"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "[skip] rubric" in out
    assert "[PASS] rubric" not in out
    assert "uncalibrated" not in out


def test_run_judge_error_exits_2_not_a_verdict(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any, monkeypatch: Any
) -> None:
    """A judge that cannot score makes the task unscorable: exit 2, no report."""
    _seed(tmp_path, make_synthetic_repo)
    monkeypatch.setattr(_registry, "load_judge_class", lambda name: _available_judge(None))
    rc = _eval.run(_ns(tmp_path, id_=_REVIEW_TASK, run=True, runner="fake", judge="llm"))
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
    from coding_agent_playbook.evals.runner import HarnessRunner

    def _boom(self: Any, task: Any, scratch: Any, **kwargs: Any) -> Any:
        raise PromptResolutionError("prompt 'refactor' for task 'x' failed to render: boom")

    _seed(tmp_path, make_synthetic_repo)
    monkeypatch.setattr(HarnessRunner, "run_task", _boom)
    rc = _eval.run(_ns(tmp_path, id_=_SHIPPED_TASK, run=True, runner="fake"))
    assert rc == 2
    assert "failed to render: boom" in capsys.readouterr().err


def test_run_with_a_judge_labels_scores_uncalibrated(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any, monkeypatch: Any
) -> None:
    """Judged scores carry an "uncalibrated" note until SPEC §19 Q12 lands."""
    _seed(tmp_path, make_synthetic_repo)
    monkeypatch.setattr(_registry, "load_judge_class", lambda name: _available_judge(0.9))
    rc = _eval.run(_ns(tmp_path, id_=_REVIEW_TASK, run=True, runner="fake", judge="llm"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "[PASS] rubric" in out
    assert "uncalibrated" in out


def test_run_json_reports_whether_judged_scores_are_uncalibrated(
    tmp_path: Path, make_synthetic_repo: Any, capsys: Any, monkeypatch: Any
) -> None:
    _seed(tmp_path, make_synthetic_repo)
    _eval.run(_ns(tmp_path, id_=_REVIEW_TASK, run=True, runner="fake", fmt="json"))
    assert json.loads(capsys.readouterr().out)["uncalibrated_judge"] is False

    monkeypatch.setattr(_registry, "load_judge_class", lambda name: _available_judge(0.9))
    _eval.run(_ns(tmp_path, id_=_REVIEW_TASK, run=True, runner="fake", fmt="json", judge="llm"))
    assert json.loads(capsys.readouterr().out)["uncalibrated_judge"] is True
