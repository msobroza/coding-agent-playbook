"""``playbook eval`` on a custom endpoint: the harness wiring, the judge and ``--targets --check``.

Driven through ``cli.main`` (spec #281 tickets 06 and 06b). No harness CLI is run:
:class:`~tests.cli.claude_cli_fakes.FakeClaudeCli` answers the ``claude`` and
``opencode`` ``subprocess.run`` calls (a JSON result object when JSON output is asked
for) and records each argv and child environment, so the tests assert what the engine
would spawn.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.cli import main
from coding_agent_playbook.evals.endpoints import endpoint_fingerprint
from coding_agent_playbook.evals.targets import TARGET_ENV_VAR
from tests.cli.claude_cli_fakes import FakeClaudeCli

if TYPE_CHECKING:
    from pathlib import Path

_SAMPLE = "refactor-extract-helper"
_TOKEN = "fake-endpoint-token-0000"
_URL = "https://llm.internal.example"

_EVALS = f"""
[evals.endpoints.internal]
api = "anthropic"
base_url = "{_URL}"
token_env = "INTERNAL_LLM_TOKEN"
context_tokens = 200000

[evals.endpoints.oai]
api = "openai-chat"
base_url = "{_URL}/v1"
token_env = "INTERNAL_LLM_TOKEN"

[evals.targets.internal-claude]
harness = "claude_code"
endpoint = "internal"
model = "internal-opus"
small_model = "internal-haiku"

[evals.targets.internal-coder]
harness = "opencode"
endpoint = "oai"
model = "my-org/coder-32b"

[evals.targets.personal]
harness = "claude_code"
model = "claude-opus-5-5"
"""


@pytest.fixture
def repo(tmp_path: Path, make_synthetic_repo: Any, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A consumer repo with an endpoint, endpoint targets and a personal target."""
    monkeypatch.delenv(TARGET_ENV_VAR, raising=False)
    monkeypatch.setenv("INTERNAL_LLM_TOKEN", _TOKEN)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-personal-key")
    make_synthetic_repo(tmp_path)
    committed = tmp_path / ".coding-agent-playbook.toml"
    committed.write_text(committed.read_text(encoding="utf-8") + _EVALS, encoding="utf-8")
    return tmp_path


def _run(repo: Path, *flags: str) -> int:
    return main(["eval", _SAMPLE, "--run", "--format", "json", "--repo-root", str(repo), *flags])


def _files_containing(root: Path, needle: str) -> list[Path]:
    return [
        path for path in root.rglob("*") if path.is_file() and needle.encode() in path.read_bytes()
    ]


def test_endpoint_target_spawns_claude_isolated_with_the_token_in_env_only(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    cli = FakeClaudeCli(monkeypatch, answer="done")
    assert _run(repo, "--target", "internal-claude") in (0, 1)
    out = capsys.readouterr().out

    argv, env = cli.calls[0]
    assert argv[:2] == ["claude", "-p"]
    model_at = argv.index("--model")
    assert argv[model_at + 1] == "internal-opus"
    settings = json.loads(argv[argv.index("--settings") + 1])
    assert settings["env"]["ANTHROPIC_BASE_URL"] == _URL
    assert settings["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"] == "internal-haiku"
    assert all(_TOKEN not in part for part in argv)

    assert env is not None
    assert env["ANTHROPIC_AUTH_TOKEN"] == _TOKEN
    assert "ANTHROPIC_API_KEY" not in env
    assert env["CLAUDE_CODE_MAX_CONTEXT_TOKENS"] == "200000"
    assert env["PLAYBOOK_HOOK_UNATTENDED"] == "1"
    assert cli.config_dir_entries[0] == []

    payload = json.loads(out)
    assert payload["target"]["endpoint"] == {
        "name": "internal",
        "fingerprint": endpoint_fingerprint(_URL),
    }
    assert payload["target"]["harness_settings"] == "isolated"
    assert _TOKEN not in out
    assert "llm.internal.example" not in out
    assert _files_containing(repo, _TOKEN) == []


def test_target_without_endpoint_keeps_personal_settings_and_says_so(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    cli = FakeClaudeCli(monkeypatch, answer="done")
    _run(repo, "--target", "personal")
    argv, env = cli.calls[0]
    assert "--settings" not in argv
    assert env is not None
    assert env["ANTHROPIC_API_KEY"] == "fake-personal-key"
    assert "CLAUDE_CONFIG_DIR" not in env
    target = json.loads(capsys.readouterr().out)["target"]
    assert (target["endpoint"], target["harness_settings"]) == (None, "personal")


def test_missing_token_variable_exits_2_naming_it(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    cli = FakeClaudeCli(monkeypatch)
    monkeypatch.setenv("INTERNAL_LLM_TOKEN", "")
    assert _run(repo, "--target", "internal-claude") == 2
    assert "INTERNAL_LLM_TOKEN is unset or empty" in capsys.readouterr().err
    assert cli.calls == []


def test_opencode_endpoint_target_spawns_opencode_isolated_with_an_inline_config(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://otel.example")
    cli = FakeClaudeCli(monkeypatch, answer="done")
    assert _run(repo, "--target", "internal-coder") in (0, 1)
    out = capsys.readouterr().out

    argv, env = cli.calls[0]
    assert argv[:4] == ["opencode", "run", "--format", "json"]
    assert argv[argv.index("--model") + 1] == "playbook-target/my-org/coder-32b"
    assert all(_TOKEN not in part for part in argv)

    assert env is not None
    config = json.loads(env["OPENCODE_CONFIG_CONTENT"])
    assert config["enabled_providers"] == ["playbook-target"]
    provider = config["provider"]["playbook-target"]
    assert provider["npm"] == "@ai-sdk/openai-compatible"
    assert provider["options"]["baseURL"] == f"{_URL}/v1"
    assert provider["options"]["apiKey"] == "{env:PLAYBOOK_ENDPOINT_TOKEN}"
    assert _TOKEN not in env["OPENCODE_CONFIG_CONTENT"]
    assert env["PLAYBOOK_ENDPOINT_TOKEN"] == _TOKEN
    for dropped in ("ANTHROPIC_API_KEY", "INTERNAL_LLM_TOKEN", "OTEL_EXPORTER_OTLP_ENDPOINT"):
        assert dropped not in env, dropped
    assert env["OPENCODE_DISABLE_CLAUDE_CODE"] == "1"
    assert env["PLAYBOOK_HOOK_UNATTENDED"] == "1"

    payload = json.loads(out)
    assert payload["target"]["endpoint"]["name"] == "oai"
    assert payload["target"]["harness_settings"] == "isolated"
    assert _TOKEN not in out
    assert _files_containing(repo, _TOKEN) == []


def test_opencode_token_that_would_corrupt_the_config_exits_2_naming_the_variable(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    cli = FakeClaudeCli(monkeypatch)
    monkeypatch.setenv("INTERNAL_LLM_TOKEN", 'fake"token')
    assert _run(repo, "--target", "internal-coder") == 2
    err = capsys.readouterr().err
    assert "INTERNAL_LLM_TOKEN" in err
    assert 'fake"token' not in err
    assert cli.calls == []


def test_judge_on_an_endpoint_grades_isolated_with_its_model(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    (repo / ".coding-agent-playbook.local.toml").write_text(
        '[evals.judge]\nendpoint = "internal"\nmodel = "internal-judge"\n', encoding="utf-8"
    )
    cli = FakeClaudeCli(monkeypatch, answer="1")
    _run(repo, "--target", "personal", "--judge", "llm", "--full-scoring")
    judge_calls = [(argv, env) for argv, env in cli.calls if "internal-judge" in argv]
    assert judge_calls, cli.calls
    argv, env = judge_calls[0]
    assert argv[argv.index("--model") + 1] == "internal-judge"
    assert json.loads(argv[argv.index("--settings") + 1])["env"]["ANTHROPIC_BASE_URL"] == _URL
    assert all(_TOKEN not in part for part in argv)
    assert env is not None
    assert env["ANTHROPIC_AUTH_TOKEN"] == _TOKEN
    assert "ANTHROPIC_API_KEY" not in env
    assert "CLAUDE_CONFIG_DIR" in env
    assert _TOKEN not in capsys.readouterr().out


def test_targets_lists_the_endpoint(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    FakeClaudeCli(monkeypatch)
    assert main(["eval", "--targets", "--repo-root", str(repo)]) == 0
    out = capsys.readouterr().out
    row = next(line for line in out.splitlines() if "internal-claude" in line)
    assert "endpoint=internal" in row
    assert _URL not in out


def test_targets_check_runs_one_turn_per_target_and_reports_each(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    cli = FakeClaudeCli(monkeypatch, answer="OK")
    assert main(["eval", "--targets", "--check", "--repo-root", str(repo)]) == 0
    out = capsys.readouterr().out
    assert "ok    internal-claude" in out
    assert "ok    personal" in out
    assert "ok    internal-coder" in out
    prompts = {argv[2] if argv[0] == "claude" else argv[4] for argv, _env in cli.calls}
    assert prompts == {"Reply with the single word OK."}
    assert len(cli.calls) == 3


def test_targets_check_fails_a_target_whose_harness_errors(
    repo: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # The fake echoes the token back, as a misbehaving gateway might; the endpoint
    # run redacts it (the personal target was never given it).
    FakeClaudeCli(monkeypatch, answer=f"API Error: 401 for {_TOKEN}", rc=1)
    assert main(["eval", "--targets", "--check", "--repo-root", str(repo)]) == 1
    rows = capsys.readouterr().out.splitlines()
    row = next(line for line in rows if line.startswith("FAIL  internal-claude"))
    assert row == "FAIL  internal-claude: exited 1: API Error: 401 for [redacted]"


def test_check_needs_targets(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["eval", "--check", "--repo-root", str(repo)]) == 2
    assert "--check goes with --targets" in capsys.readouterr().err
