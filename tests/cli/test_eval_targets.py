"""``playbook eval --target`` / ``--targets`` and ``[evals]`` (spec #281 ticket 05).

Driven through ``cli.main``. No harness CLI is ever run: the ``fake`` runner
records the model it is given, and the Claude Code and OpenCode runs go through
:class:`FakeHarnessCli`, which answers their ``subprocess.run`` and records the argv.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.cli import main
from coding_agent_playbook.evals.judge import LLMJudge
from coding_agent_playbook.evals.run.claude_code_runner import ClaudeCodeRunner
from coding_agent_playbook.evals.run.opencode_runner import OpenCodeRunner
from coding_agent_playbook.evals.targets import TARGET_ENV_VAR
from coding_agent_playbook.grading import bounded_subprocess

if TYPE_CHECKING:
    from pathlib import Path

_SAMPLE = "refactor/extract-helper"

_EVALS = """
[evals]
default = "committed-fake"
release = ["opus"]

[evals.targets.committed-fake]
harness = "fake"
model = "committed-model"

[evals.targets.opus]
harness = "claude_code"
model = "claude-opus-5-5"
runs = 3

[evals.targets.coder]
harness = "opencode"
model = "my-org/coder-32b-instruct"
label = "Internal coder"

[evals.targets.ghost]
harness = "no-such-harness"
"""

_LOCAL = """
[evals]
default = "local-fake"

[evals.targets.local-fake]
harness = "fake"
model = "local-model"
"""


class FakeHarnessCli:
    """Stands in for the ``claude`` / ``opencode`` / judge CLIs: records each argv, answers."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, answer: str = "done") -> None:
        self.argvs: list[list[str]] = []
        self._answer = answer
        self._real_bounded = bounded_subprocess.run_bounded
        self._real_run = subprocess.run
        for cls in (ClaudeCodeRunner, OpenCodeRunner, LLMJudge):
            monkeypatch.setattr(cls, "available", classmethod(lambda _cls: True))
        monkeypatch.setattr(subprocess, "run", self._run)
        monkeypatch.setattr(bounded_subprocess, "run_bounded", self._run_bounded)

    def _run_bounded(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        """The agent and judge calls; every other program runs for real."""
        if not args or args[0] not in ("claude", "opencode"):
            return self._real_bounded(args, **kwargs)
        return self._run(args, **kwargs)

    def _run(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args and args[0] in ("claude", "opencode"):
            self.argvs.append(list(args))
            return subprocess.CompletedProcess(args, 0, self._answer, "")
        return self._real_run(args, **kwargs)


@pytest.fixture
def repo(tmp_path: Path, make_synthetic_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A consumer repo whose committed config carries the ``[evals]`` targets above."""
    monkeypatch.delenv(TARGET_ENV_VAR, raising=False)
    make_synthetic_repo(tmp_path)
    committed = tmp_path / ".coding-agent-playbook.toml"
    committed.write_text(committed.read_text(encoding="utf-8") + _EVALS, encoding="utf-8")
    return tmp_path


def _run_json(repo: Path, capsys: pytest.CaptureFixture[str], *flags: str) -> dict[str, Any]:
    rc = main(["eval", _SAMPLE, "--run", "--format", "json", "--repo-root", str(repo), *flags])
    out = capsys.readouterr().out
    assert rc in (0, 1), out
    payload: dict[str, Any] = json.loads(out)
    return payload


def test_committed_default_target_runs_and_is_recorded(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    payload = _run_json(repo, capsys)
    assert payload["target"] == {
        "name": "committed-fake",
        "harness": "fake",
        "model": "committed-model",
        "reported_model": None,
        "endpoint": None,
        "harness_settings": "personal",
    }


def test_local_default_wins_over_the_committed_one(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / ".coding-agent-playbook.local.toml").write_text(_LOCAL, encoding="utf-8")
    assert _run_json(repo, capsys)["target"]["name"] == "local-fake"


def test_environment_variable_wins_over_the_defaults(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo / ".coding-agent-playbook.local.toml").write_text(_LOCAL, encoding="utf-8")
    monkeypatch.setenv(TARGET_ENV_VAR, "fake:env-model")
    assert _run_json(repo, capsys)["target"]["model"] == "env-model"


def test_target_flag_wins_over_the_environment_variable(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(TARGET_ENV_VAR, "fake:env-model")
    target = _run_json(repo, capsys, "--target", "fake:flag-model")["target"]
    assert (target["name"], target["model"]) == ("fake:flag-model", "flag-model")


def test_claude_code_target_sends_its_model(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    cli = FakeHarnessCli(monkeypatch)
    payload = _run_json(repo, capsys, "--target", "opus")
    assert cli.argvs[0][0] == "claude"
    assert cli.argvs[0][-2:] == ["--model", "claude-opus-5-5"]
    assert payload["target"]["harness"] == "claude_code"


def test_opencode_target_sends_its_model(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    cli = FakeHarnessCli(monkeypatch)
    _run_json(repo, capsys, "--target", "coder")
    assert cli.argvs[0][:2] == ["opencode", "run"]
    assert cli.argvs[0][-2:] == ["--model", "my-org/coder-32b-instruct"]


def test_judge_settings_give_the_judge_its_model_and_samples(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    committed = repo / ".coding-agent-playbook.toml"
    judge = '\n[evals.judge]\nmodel = "judge-model"\nsamples = 2\n'
    committed.write_text(committed.read_text(encoding="utf-8") + judge, encoding="utf-8")
    cli = FakeHarnessCli(monkeypatch, answer="1")
    _run_json(repo, capsys, "--target", "opus", "--judge", "llm", "--full-scoring")
    judge_argvs = [argv for argv in cli.argvs if argv[-2:] == ["--model", "judge-model"]]
    # The refactor/extract-helper sample has 4 rubric criteria: 4 criteria x 2 samples.
    assert len(judge_argvs) == 4 * 2, cli.argvs


def test_zero_config_runs_claude_code_on_its_default_model(
    tmp_path: Path,
    make_synthetic_repo: Any,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(TARGET_ENV_VAR, raising=False)
    make_synthetic_repo(tmp_path)
    cli = FakeHarnessCli(monkeypatch)
    payload = _run_json(tmp_path, capsys)
    assert cli.argvs[0][:2] == ["claude", "-p"]
    assert "--model" not in cli.argvs[0]
    assert payload["target"] == {
        "name": "default",
        "harness": "claude_code",
        "model": None,
        "reported_model": None,
        "endpoint": None,
        "harness_settings": "personal",
    }


def test_runner_flag_is_the_harness_without_a_model(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = _run_json(repo, capsys, "--runner", "fake")["target"]
    assert (target["name"], target["harness"], target["model"]) == ("fake", "fake", None)


def test_text_report_names_the_target(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["eval", _SAMPLE, "--run", "--repo-root", str(repo)])
    assert (
        "target: committed-fake (fake, model committed-model, personal harness settings)"
        in capsys.readouterr().out
    )


def test_unknown_target_lists_the_configured_names(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(["eval", _SAMPLE, "--run", "--repo-root", str(repo), "--target", "nope"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "unknown eval target 'nope'" in err
    assert "coder, committed-fake, ghost, opus" in err


@pytest.mark.parametrize(
    ("flags", "message"),
    [
        (("--target", "opus", "--runner", "fake"), "not both"),
        (("--target", "ghost"), "unknown --runner 'no-such-harness'"),
        (("--target", "custom:m"), "unknown --runner 'custom'"),
    ],
)
def test_unusable_target_choices_exit_2(
    repo: Path, capsys: pytest.CaptureFixture[str], flags: tuple[str, ...], message: str
) -> None:
    rc = main(["eval", _SAMPLE, "--run", "--repo-root", str(repo), *flags])
    assert rc == 2
    assert message in capsys.readouterr().err


def test_compare_refuses_target(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["eval", "--compare", "HEAD", "--repo-root", str(repo), "--target", "opus"])
    assert rc == 2
    assert "--compare does not take --target" in capsys.readouterr().err


def test_targets_lists_each_target_its_origin_and_cli(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ClaudeCodeRunner, "available", classmethod(lambda _cls: True))
    monkeypatch.setattr(OpenCodeRunner, "available", classmethod(lambda _cls: False))
    (repo / ".coding-agent-playbook.local.toml").write_text(_LOCAL, encoding="utf-8")

    assert main(["eval", "--targets", "--repo-root", str(repo)]) == 0
    lines = capsys.readouterr().out.splitlines()

    assert (
        lines[0] == "default: local-fake (from .coding-agent-playbook.local.toml [evals] default)"
    )
    rows = {
        line.split()[1] if line.startswith("*") else line.split()[0]: line for line in lines[1:]
    }
    assert rows["local-fake"].startswith("* local-fake")
    assert "from .coding-agent-playbook.local.toml" in rows["local-fake"]
    assert "model=claude-opus-5-5" in rows["opus"]
    assert "CLI installed" in rows["opus"]
    assert rows["opus"].endswith("runs=3  release")
    assert "CLI not installed" in rows["coder"]
    assert "label='Internal coder'" in rows["coder"]
    assert "CLI unknown harness" in rows["ghost"]


def test_targets_without_config_shows_the_built_in_default(
    tmp_path: Path,
    make_synthetic_repo: Any,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(TARGET_ENV_VAR, raising=False)
    make_synthetic_repo(tmp_path)
    assert main(["eval", "--targets", "--repo-root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("default: default (built-in: Claude Code, its default model)")
    assert "no eval targets configured" in out
    assert "* default  harness=claude_code  model=(harness default)  from built-in" in out


def test_bad_evals_table_exits_2_naming_the_file(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (repo / ".coding-agent-playbook.local.toml").write_text(
        '[evals]\nrelease = ["opus"]\n', encoding="utf-8"
    )
    assert main(["eval", "--targets", "--repo-root", str(repo)]) == 2
    assert ".coding-agent-playbook.local.toml: [evals] has unknown key" in capsys.readouterr().err
