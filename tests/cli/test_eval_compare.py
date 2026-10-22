"""``playbook eval --compare <base-ref>``: the opt-in base-vs-HEAD eval comparison (D37, D76; F-01).

Off by default. With the flag, every compared task runs on a detached checkout of
the base ref and of HEAD, through each checkout's engine. Hermetic: only the
``fake`` runner runs, on one task and one sample per side.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.cli.parser import build_parser
from coding_agent_playbook.commands import eval as _eval

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_TASK = "refactor-extract-helper"


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
    argv = ["eval", _TASK, "--compare", "HEAD", "--runner", "fake", "--compare-samples", "1"]
    argv += ["--compare-out", str(out), "--repo-root", str(repo), "--format", "json", *flags]
    return _eval.run(build_parser().parse_args(argv))


def test_the_comparison_is_off_by_default() -> None:
    args = build_parser().parse_args(["eval", _TASK, "--run"])
    assert args.compare is None


def test_a_comparison_reports_each_side_and_keeps_every_run(
    tmp_path: Path, make_synthetic_repo: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _committed_repo(tmp_path, make_synthetic_repo)
    out = tmp_path / "out"

    code = _compare(repo, out, "--base-prompt-set", "v1", "--prompt-set", "v2")

    view = json.loads(capsys.readouterr().out)
    assert code == 0
    assert (view["base"], view["head"]) == ("HEAD (v1)", "HEAD (v2)")
    assert [task["task_id"] for task in view["tasks"]] == [_TASK]
    assert view["tasks"][0]["base"]["count"] == 1
    for side in ("base", "head"):
        report = json.loads((out / "reports" / side / f"{_TASK}-1.json").read_text("utf-8"))
        assert report["sample_id"] == _TASK
    assert not (out / "checkouts" / "base").exists()


def test_an_unknown_base_ref_is_a_usage_error(
    tmp_path: Path, make_synthetic_repo: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _committed_repo(tmp_path, make_synthetic_repo)
    argv = ["eval", "--compare", "no-such-ref", "--runner", "fake"]
    argv += ["--compare-out", str(tmp_path / "out"), "--repo-root", str(repo)]
    assert _eval.run(build_parser().parse_args(argv)) == 2
    assert "no-such-ref" in capsys.readouterr().err


def test_a_sample_count_below_one_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["eval", "--compare", "HEAD", "--compare-samples", "0", "--repo-root", str(tmp_path)]
    assert _eval.run(build_parser().parse_args(argv)) == 2
    assert "--compare-samples" in capsys.readouterr().err


def test_an_unknown_task_is_a_usage_error(
    tmp_path: Path, make_synthetic_repo: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    make_synthetic_repo(tmp_path)
    argv = ["eval", "explain-pure-function", "--compare", "HEAD", "--repo-root", str(tmp_path)]
    assert _eval.run(build_parser().parse_args(argv)) == 2
    assert "explain-pure-function" in capsys.readouterr().err
