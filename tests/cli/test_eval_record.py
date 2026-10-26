"""``playbook eval --run --record`` writes one release metrics file (spec #281 ticket 07).

Driven through ``cli.main``. No harness CLI runs: the ``fake`` runner stands in
for the agent, and Claude Code runs go through :class:`FakeClaudeCli`, which
answers ``claude --version`` and ``claude -p`` with canned output.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

import coding_agent_playbook
from coding_agent_playbook.cli import main
from coding_agent_playbook.config.files import CONFIG_FILENAME
from coding_agent_playbook.evals.endpoints import endpoint_fingerprint
from coding_agent_playbook.evals.judge import LLMJudge
from coding_agent_playbook.evals.release_metrics_schema import validate_release_metrics
from coding_agent_playbook.evals.run.claude_code_runner import ClaudeCodeRunner
from coding_agent_playbook.evals.run.fake_runner import FakeRunner
from coding_agent_playbook.evals.run.harness_runner import SampleResult
from coding_agent_playbook.evals.targets import TARGET_ENV_VAR
from coding_agent_playbook.grading.types import EvaluationReport
from coding_agent_playbook.validation.context import SyncContext
from tests.cli import claude_cli_fakes

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.evals.sample import EvalSample

_SAMPLE = "refactor-extract-helper"

_EVALS = """
[evals.targets.fake-pinned]
harness = "fake"
model = "fake-model-1"

[evals.targets.opus]
harness = "claude_code"
model = "claude-opus-5-5"
runs = 2

[evals.targets.opus-priced]
harness = "claude_code"
model = "claude-opus-5-5"
price = { input = 2.0, output = 10.0 }
"""

_CLAUDE_RESULT = json.dumps(
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "done",
        "total_cost_usd": 123.0,
        "modelUsage": {"claude-opus-5-5": {"inputTokens": 1000, "outputTokens": 100}},
    }
)


class FakeClaudeCli:
    """Answers the ``claude`` CLI's ``--version`` and ``-p`` calls; records each argv."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.argvs: list[list[str]] = []
        self._real_run = subprocess.run
        for cls in (ClaudeCodeRunner, LLMJudge):
            monkeypatch.setattr(cls, "available", classmethod(lambda _cls: True))
        monkeypatch.setattr(subprocess, "run", self._run)

    def _run(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if not args or args[0] != "claude":
            return self._real_run(args, **kwargs)
        self.argvs.append(list(args))
        answer = "2.1.300 (Claude Code)\n" if args[1:] == ["--version"] else _CLAUDE_RESULT
        return subprocess.CompletedProcess(args, 0, answer, "")


@pytest.fixture
def repo(tmp_path: Path, make_synthetic_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A consumer repo whose committed config names pinned and priced targets."""
    monkeypatch.delenv(TARGET_ENV_VAR, raising=False)
    make_synthetic_repo(tmp_path)
    committed = tmp_path / CONFIG_FILENAME
    committed.write_text(committed.read_text(encoding="utf-8") + _EVALS, encoding="utf-8")
    return tmp_path


def _record(repo: Path, *flags: str) -> tuple[int, Path]:
    out = repo / "metrics" / "target.json"
    rc = main(["eval", "--run", "--repo-root", str(repo), "--record", str(out), *flags])
    return rc, out


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    validate_release_metrics(data)
    return data


def test_one_sample_runs_n_times_into_a_valid_file(repo: Path) -> None:
    rc, out = _record(repo, _SAMPLE, "--target", "fake-pinned", "--runs", "2")
    assert rc == 0
    data = _load(out)
    assert data["release"] == coding_agent_playbook.__version__
    assert data["target"]["name"] == "fake-pinned"
    assert data["target"]["harness_version"] is None
    entry = data["samples"][_SAMPLE]
    assert (entry["runs"], entry["graded"], entry["prompt_id"]) == (2, "head", "refactor")
    assert entry["prompt_digest"] is not None
    assert (entry["tokens_mean"], entry["cost_usd_mean"]) == (None, None)
    assert data["summary"]["samples"] == 1


def _canned_run(
    runner: FakeRunner, sample: EvalSample, *_args: Any, **_kwargs: Any
) -> SampleResult:
    """A passing result without materializing the sample: ``--all`` covers every shipped one."""
    report = EvaluationReport(findings=[], warn_count=0, fail_count=0, composite=1.0, passed=True)
    return SampleResult(sample.id, runner.name, report, True, 1.0, 0.1, "")


def test_all_runs_every_sample(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(FakeRunner, "run_sample", _canned_run)
    rc, out = _record(repo, "--all", "--target", "fake-pinned")
    assert rc == 0
    expected = {s.id for s in SyncContext.from_repo(repo).artifact_source.list_eval_samples()}
    data = _load(out)
    assert set(data["samples"]) == expected
    assert data["summary"]["runs"] == len(expected)


def test_claude_code_records_tokens_model_and_version_but_never_its_cost(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli = FakeClaudeCli(monkeypatch)
    rc, out = _record(repo, _SAMPLE, "--target", "opus")
    assert rc == 0
    data = _load(out)
    assert ["claude", "--version"] in cli.argvs
    assert data["target"]["harness_version"] == "2.1.300"
    assert data["target"]["reported_model"] == "claude-opus-5-5"
    assert data["target"]["runs"] == 2  # the target's runs, without --runs
    entry = data["samples"][_SAMPLE]
    assert (entry["runs"], entry["tokens_mean"], entry["cost_usd_mean"]) == (2, 1100.0, None)


def test_cost_comes_from_the_target_price(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    FakeClaudeCli(monkeypatch)
    rc, out = _record(repo, _SAMPLE, "--target", "opus-priced")
    assert rc == 0
    # 1000 input x 2.0 + 100 output x 10.0 per million tokens.
    assert _load(out)["samples"][_SAMPLE]["cost_usd_mean"] == pytest.approx(0.003)


_ENDPOINT_TOKEN = "fake-endpoint-token-0000"
_ENDPOINT_URL = "https://llm.internal.example"
_ENDPOINT_EVALS = f"""
[evals.endpoints.internal]
api = "anthropic"
base_url = "{_ENDPOINT_URL}"
token_env = "INTERNAL_LLM_TOKEN"

[evals.targets.internal-claude]
harness = "claude_code"
endpoint = "internal"
model = "internal-opus"
"""


def test_endpoint_target_records_its_name_and_fingerprint_but_never_its_secrets(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Ticket 06 x 07: a recorded endpoint run names the endpoint by fingerprint;
    # neither the token nor the URL reaches argv or the metrics file.
    committed = repo / CONFIG_FILENAME
    committed.write_text(committed.read_text(encoding="utf-8") + _ENDPOINT_EVALS, encoding="utf-8")
    monkeypatch.setenv("INTERNAL_LLM_TOKEN", _ENDPOINT_TOKEN)
    cli = claude_cli_fakes.FakeClaudeCli(monkeypatch, answer=f"done, saw {_ENDPOINT_TOKEN}")

    rc, out = _record(repo, _SAMPLE, "--target", "internal-claude")

    assert rc == 0
    assert cli.calls
    assert all(_ENDPOINT_TOKEN not in part for argv, _env in cli.calls for part in argv)
    text = out.read_text(encoding="utf-8")
    assert _ENDPOINT_TOKEN not in text
    assert "llm.internal.example" not in text
    data = _load(out)
    assert data["target"]["endpoint"] == {
        "name": "internal",
        "fingerprint": endpoint_fingerprint(_ENDPOINT_URL),
    }
    assert data["target"]["reported_model"] == "internal-opus"


@pytest.mark.parametrize(
    ("flags", "message"),
    [
        (("--runner", "fake"), "explicit model"),
        (("--target", "claude_code:opus"), "moving alias"),
        (("--target", "opus", "--judge", "llm"), "pinned judge model"),
    ],
)
def test_unpinned_models_are_refused_before_any_run(
    repo: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    flags: tuple[str, ...],
    message: str,
) -> None:
    cli = FakeClaudeCli(monkeypatch)
    rc, out = _record(repo, _SAMPLE, *flags)
    assert rc == 2
    assert message in capsys.readouterr().err
    assert cli.argvs == []
    assert not out.exists()


def test_a_moving_alias_judge_model_is_refused(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    committed = repo / CONFIG_FILENAME
    judge = '\n[evals.judge]\nmodel = "sonnet"\n'
    committed.write_text(committed.read_text(encoding="utf-8") + judge, encoding="utf-8")
    FakeClaudeCli(monkeypatch)
    rc, _ = _record(repo, _SAMPLE, "--target", "opus", "--judge", "llm")
    assert rc == 2
    assert "'sonnet'" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["eval", _SAMPLE, "--record", "x.json", "--target", "fake-pinned"], "need --run"),
        (["eval", "--run", "--all", "--target", "fake-pinned"], "pass --record too"),
        (
            ["eval", _SAMPLE, "--run", "--all", "--record", "x.json", "--target", "fake-pinned"],
            "either --all samples or one sample",
        ),
        (
            [
                "eval",
                _SAMPLE,
                "--run",
                "--record",
                "x.json",
                "--runs",
                "0",
                "--target",
                "fake-pinned",
            ],
            "--runs must be >= 1",
        ),
    ],
)
def test_misused_record_flags_are_usage_errors(
    repo: Path, capsys: pytest.CaptureFixture[str], argv: list[str], message: str
) -> None:
    assert main([*argv, "--repo-root", str(repo)]) == 2
    assert message in capsys.readouterr().err


def test_format_with_record_is_refused(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc, out = _record(repo, _SAMPLE, "--target", "fake-pinned", "--format", "json")
    assert rc == 2
    assert "--format json does not apply to --record" in capsys.readouterr().err
    assert not out.exists()


@pytest.mark.parametrize(("flags", "fail_fast"), [((), True), (("--full-scoring",), False)])
def test_full_scoring_reaches_every_recorded_run(
    repo: Path, monkeypatch: pytest.MonkeyPatch, flags: tuple[str, ...], fail_fast: bool
) -> None:
    seen: list[object] = []

    def recording_run(runner: FakeRunner, sample: EvalSample, *a: Any, **kw: Any) -> SampleResult:
        seen.append(kw.get("fail_fast"))
        return _canned_run(runner, sample)

    monkeypatch.setattr(FakeRunner, "run_sample", recording_run)
    rc, _ = _record(repo, _SAMPLE, "--target", "fake-pinned", "--runs", "2", *flags)
    assert rc == 0
    assert seen == [fail_fast, fail_fast]


def test_a_bad_prompt_on_any_sample_fails_before_the_first_paid_run(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # PR #310 review: a bad prompt on the last sample used to surface only after
    # every earlier sample had been paid for.
    from coding_agent_playbook.commands import _eval_record
    from coding_agent_playbook.evals.prompting import PromptResolutionError, render_prompt

    last = max(s.id for s in SyncContext.from_repo(repo).artifact_source.list_eval_samples())

    def failing_last(sample: EvalSample, **kwargs: Any) -> str:
        if sample.id == last:
            raise PromptResolutionError(f"no prompt for {sample.id}")
        return render_prompt(sample, **kwargs)

    monkeypatch.setattr(_eval_record, "render_prompt", failing_last)
    cli = FakeClaudeCli(monkeypatch)
    rc, out = _record(repo, "--all", "--target", "opus")
    assert rc == 2
    assert f"sample {last!r} has no prompt to run" in capsys.readouterr().err
    assert cli.argvs == []
    assert not out.exists()
