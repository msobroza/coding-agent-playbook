"""``playbook eval --compare <base-ref>``: the opt-in base-vs-HEAD eval comparison (D37, D76; F-01).

Off by default. With the flag, every compared eval sample runs on a detached
checkout of the base ref and of HEAD, through each checkout's engine. Hermetic:
only the ``fake`` runner runs, on one eval sample and one run per side.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.cli import main
from coding_agent_playbook.cli.parser import build_parser
from coding_agent_playbook.commands import _eval_compare
from coding_agent_playbook.commands import eval as _eval

if TYPE_CHECKING:
    import argparse
    from pathlib import Path

    import pytest

_SAMPLE = "refactor-extract-helper"


def _committed_repo(tmp_path: Path, make_synthetic_repo: Any) -> Path:
    (tmp_path / "repo").mkdir()
    repo: Path = make_synthetic_repo(tmp_path / "repo")
    for args in (("init", "-q"), ("add", "-A")):
        subprocess.run(["git", "-C", str(repo), *args], check=True, timeout=60)
    identity = ("-c", "user.name=t", "-c", "user.email=t@example.com")
    commit = ("git", "-C", str(repo), *identity, "commit", "-qm", "init")
    subprocess.run(commit, check=True, timeout=60)
    return repo


def _compare(repo: Path, out: Path, *flags: str) -> int:
    argv = ["eval", _SAMPLE, "--compare", "HEAD", "--runner", "fake", "--compare-runs", "1"]
    argv += ["--compare-out", str(out), "--repo-root", str(repo), "--format", "json", *flags]
    return _eval.run(build_parser().parse_args(argv))


def test_the_comparison_is_off_by_default() -> None:
    args = build_parser().parse_args(["eval", _SAMPLE, "--run"])
    assert args.compare is None


def test_a_comparison_reports_each_side_and_keeps_every_run(
    tmp_path: Path,
    make_synthetic_repo: Any,
    capsys: pytest.CaptureFixture[str],
    fake_uv_on_path: Path,  # each compared side is a child process (PR #266 CI)
) -> None:
    repo = _committed_repo(tmp_path, make_synthetic_repo)
    out = tmp_path / "out"

    code = _compare(repo, out, "--base-prompt-set", "v1", "--prompt-set", "v2")

    captured = capsys.readouterr()
    view = json.loads(captured.out)
    assert code == 0
    assert (view["base"], view["head"]) == ("HEAD (v1)", "HEAD (v2)")
    assert (view["runner"], view["judge"], view["score"]) == ("fake", None, "gate score")
    assert "gate score only" in captured.err
    assert [row["sample_id"] for row in view["samples"]] == [_SAMPLE]
    assert view["samples"][0]["base"]["count"] == 1
    for side in ("base", "head"):
        report = json.loads((out / "reports" / side / f"{_SAMPLE}-1.json").read_text("utf-8"))
        assert report["sample_id"] == _SAMPLE
    assert not (out / "checkouts" / "base").exists()


def test_an_unknown_base_ref_is_a_usage_error(
    tmp_path: Path, make_synthetic_repo: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _committed_repo(tmp_path, make_synthetic_repo)
    argv = ["eval", "--compare", "no-such-ref", "--runner", "fake"]
    argv += ["--compare-out", str(tmp_path / "out"), "--repo-root", str(repo)]
    assert main(argv) == 2
    assert "no-such-ref" in capsys.readouterr().err


def test_a_run_count_below_one_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["eval", "--compare", "HEAD", "--compare-runs", "0", "--repo-root", str(tmp_path)]
    assert _eval.run(build_parser().parse_args(argv)) == 2
    assert "--compare-runs" in capsys.readouterr().err


def test_a_sample_outside_the_compared_prompts_is_a_usage_error(
    tmp_path: Path, make_synthetic_repo: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    make_synthetic_repo(tmp_path)
    # --runner fake: the default runner (claude_code) is checked first and needs its
    # CLI, which CI does not have (PR #266 CI).
    argv = ["eval", "explain-pure-function", "--compare", "HEAD", "--runner", "fake"]
    argv += ["--repo-root", str(tmp_path)]
    assert _eval.run(build_parser().parse_args(argv)) == 2
    assert "explain-pure-function" in capsys.readouterr().err


def _compare_args(*flags: str) -> argparse.Namespace:
    return build_parser().parse_args(["eval", "--compare", "HEAD", *flags])


def test_an_unknown_runner_is_a_usage_error_naming_the_registered_ones(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["eval", "--compare", "HEAD", "--runner", "nope", "--repo-root", str(tmp_path)]
    assert _eval.run(build_parser().parse_args(argv)) == 2
    err = capsys.readouterr().err
    assert "'nope'" in err
    assert "registered runners:" in err
    assert "fake" in err


def test_an_unavailable_runner_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from coding_agent_playbook.evals.run.claude_code_runner import ClaudeCodeRunner

    monkeypatch.setattr(ClaudeCodeRunner, "available", classmethod(lambda cls: False))
    argv = ["eval", "--compare", "HEAD", "--runner", "claude_code", "--repo-root", str(tmp_path)]
    assert _eval.run(build_parser().parse_args(argv)) == 2
    assert "unavailable" in capsys.readouterr().err


def test_an_unknown_judge_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    args = _compare_args("--runner", "fake", "--judge", "nope")
    assert _eval_compare._agent_options(args) is None
    assert "registered judges:" in capsys.readouterr().err


class FakeAvailableJudge:
    """A judge the registry hands back that is always available."""

    @classmethod
    def available(cls) -> bool:
        return True


def test_runner_judge_and_scoring_flags_pass_through_to_every_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coding_agent_playbook.evals import registry

    monkeypatch.setattr(registry, "load_judge_class", lambda name: FakeAvailableJudge)
    flags = ("--runner", "fake", "--judge", "llm", "--judge-samples", "2", "--full-scoring")
    options = _eval_compare._agent_options(_compare_args(*flags))
    assert options is not None
    assert (options.runner, options.judge, options.flags) == ("fake", "llm", flags)


def test_the_deprecated_judge_samples_alias_also_passes_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coding_agent_playbook.evals import registry

    monkeypatch.setattr(registry, "load_judge_class", lambda name: FakeAvailableJudge)
    options = _eval_compare._agent_options(
        _compare_args("--runner", "fake", "--judge", "llm", "--samples", "3")
    )
    assert options is not None
    assert options.flags[-2:] == ("--judge-samples", "3")


def test_without_a_judge_no_judge_flags_pass_through() -> None:
    options = _eval_compare._agent_options(_compare_args("--runner", "fake"))
    assert options is not None
    assert (options.judge, options.flags) == (None, ("--runner", "fake"))
