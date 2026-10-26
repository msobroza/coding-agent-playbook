"""``playbook eval --compare BASE [HEAD]``: the opt-in two-side eval comparison (D37, D76; F-01; #281 14).

Off by default. With the flag, every compared eval sample runs on each side: a
detached checkout of a git ref (through that checkout's engine), ``head`` (the
current text in place) or ``edition:<tag>`` (built from a fake tag of a scratch
repo). Hermetic: only the ``fake`` runner runs, on one eval sample and one run
per side.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.cli import main
from coding_agent_playbook.cli.parser import build_parser
from coding_agent_playbook.commands import _eval_compare
from coding_agent_playbook.commands import eval as _eval
from coding_agent_playbook.release.manifest import (
    ManifestEntry,
    ReleaseManifest,
    release_dir,
    render_manifest,
)

if TYPE_CHECKING:
    import argparse
    from collections.abc import Callable
    from pathlib import Path

    import pytest

_SAMPLE = "refactor/extract-helper"


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


def test_an_unknown_sample_is_a_usage_error(
    tmp_path: Path, make_synthetic_repo: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    make_synthetic_repo(tmp_path)
    # --runner fake: the default runner (claude_code) is checked first and needs its
    # CLI, which CI does not have (PR #266 CI).
    argv = ["eval", "explain/no-such-sample", "--compare", "HEAD", "--runner", "fake"]
    argv += ["--repo-root", str(tmp_path)]
    assert _eval.run(build_parser().parse_args(argv)) == 2
    assert "explain/no-such-sample" in capsys.readouterr().err


def test_more_than_two_sides_is_a_usage_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["eval", "--compare", "a", "b", "c", "--runner", "fake", "--repo-root", str(tmp_path)]
    assert _eval.run(build_parser().parse_args(argv)) == 2
    assert "a base and a head side" in capsys.readouterr().err


def test_without_an_edition_every_sample_is_compared(
    tmp_path: Path, make_synthetic_repo: Any
) -> None:
    make_synthetic_repo(tmp_path)
    args = build_parser().parse_args(["eval", "--compare", "HEAD", "head"])
    registry = _eval_compare._registry(tmp_path)
    assert registry is not None
    sides = _eval_compare._sides(args)
    assert sides is not None
    selected = _eval_compare._selected_samples(args, registry, tmp_path, sides)
    assert selected is not None
    assert {"explain/pure-function", _SAMPLE} <= set(selected)


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


# --------------------------------------------------------------------------- #
# edition:<tag> and head: built from a fake tag of a scratch repo, run in place
# --------------------------------------------------------------------------- #

_TAG = "v9.9.9"
_GRADED_SAMPLE = "review/spot-the-bug"
_PROMPT = "catalog/core/prompts/review.md"
_RULE = "catalog/core/skills/python-coding/rules/typing.md"
_PROMPT_TEXT = (
    "---\nid: review\nname: Review\ndescription: Review code.\nslash: review\n"
    "version: 3\nincludes_rules:\n  - typing\n---\nFrozen review prompt.\n"
)
_RULE_TEXT = "---\nid: typing\nname: Typing\ndescription: Type all.\nscope: always\n---\nType.\n"


def _released_repo(tmp_path: Path, make_synthetic_repo: Any, real_git: Callable[..., str]) -> Path:
    """A scratch repo whose fake tag v9.9.9 records a manifest grading ``review``."""
    (tmp_path / "repo").mkdir()
    repo: Path = make_synthetic_repo(tmp_path / "repo")
    for rel, text in ((_PROMPT, _PROMPT_TEXT), (_RULE, _RULE_TEXT)):
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    graded = (
        ManifestEntry("coding_agent_playbook", "prompt", "review", _PROMPT, "d1"),
        ManifestEntry("coding_agent_playbook", "rule", "typing", _RULE, "d2"),
    )
    manifest = release_dir(repo / "catalog", "9.9.9") / "manifest.toml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(render_manifest(ReleaseManifest("9.9.9", "f00d", graded, ())), "utf-8")
    real_git("init", "-q", cwd=repo)
    real_git("add", "-A", cwd=repo)
    real_git("commit", "-q", "-m", "chore(release): v9.9.9", cwd=repo)
    real_git("tag", "--annotate", "--message", "Release v9.9.9", _TAG, cwd=repo)
    return repo


def _graded_source(out: Path, side: str) -> object:
    report = json.loads((out / "reports" / side / f"{_GRADED_SAMPLE}-1.json").read_text("utf-8"))
    return report["graded"]["source"]


def test_an_edition_is_compared_with_head_in_place(
    tmp_path: Path,
    make_synthetic_repo: Any,
    real_git: Callable[..., str],
    capsys: pytest.CaptureFixture[str],
    fake_uv_on_path: Path,  # each side's runs are child processes (PR #266 CI)
) -> None:
    repo = _released_repo(tmp_path, make_synthetic_repo, real_git)
    out = tmp_path / "out"
    argv = ["eval", _GRADED_SAMPLE, "--compare", f"edition:{_TAG}", "head", "--runner", "fake"]
    argv += ["--compare-runs", "1", "--compare-out", str(out), "--repo-root", str(repo)]

    code = _eval.run(build_parser().parse_args([*argv, "--format", "json"]))

    view = json.loads(capsys.readouterr().out)
    assert code == 0
    assert (view["base"], view["head"]) == (f"edition {_TAG}", "head (v1)")
    assert [row["sample_id"] for row in view["samples"]] == [_GRADED_SAMPLE]
    assert (_graded_source(out, "base"), _graded_source(out, "head")) == (_TAG, "head")
    built = out / "edition-base" / "editions" / _TAG / "core/prompts/review.md"
    assert built.read_text(encoding="utf-8") == _PROMPT_TEXT
    assert not (repo / "catalog" / "editions").exists()  # built in the work dir, never committed
    assert real_git("status", "--porcelain", cwd=repo) == ""


def test_against_an_edition_the_samples_of_its_graded_prompts_are_compared(
    tmp_path: Path, make_synthetic_repo: Any, real_git: Callable[..., str]
) -> None:
    repo = _released_repo(tmp_path, make_synthetic_repo, real_git)
    args = build_parser().parse_args(["eval", "--compare", f"edition:{_TAG}", "head"])
    registry = _eval_compare._registry(repo)
    sides = _eval_compare._sides(args)
    assert registry is not None
    assert sides is not None
    selected = _eval_compare._selected_samples(args, registry, repo, sides)
    assert selected == [sample.id for sample in registry.samples_of("review")]


def test_a_sample_that_does_not_render_on_a_side_exits_2_before_any_run(
    tmp_path: Path,
    make_synthetic_repo: Any,
    real_git: Callable[..., str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _released_repo(tmp_path, make_synthetic_repo, real_git)
    out = tmp_path / "out"
    argv = ["eval", "explain/pure-function", "--compare", f"edition:{_TAG}", "head"]
    argv += ["--runner", "fake", "--compare-out", str(out), "--repo-root", str(repo)]

    assert main(argv) == 2

    err = capsys.readouterr().err
    assert f"explain/pure-function on edition {_TAG}" in err
    assert "nothing was run" in err
    assert not (out / "reports").exists()


def test_a_missing_tag_or_a_non_release_tag_is_a_usage_error(
    tmp_path: Path,
    make_synthetic_repo: Any,
    real_git: Callable[..., str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _released_repo(tmp_path, make_synthetic_repo, real_git)
    base = ["eval", "--runner", "fake", "--repo-root", str(repo), "--compare"]

    assert main([*base, "edition:v9.9.8", "head"]) == 2
    assert "no tag v9.9.8" in capsys.readouterr().err
    assert main([*base, "edition:main", "head"]) == 2
    assert "edition:<release tag>" in capsys.readouterr().err


def test_a_run_takes_edition_head_or_an_edition_dir_not_both(
    tmp_path: Path, make_synthetic_repo: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    make_synthetic_repo(tmp_path)
    argv = ["eval", _GRADED_SAMPLE, "--run", "--runner", "fake", "--repo-root", str(tmp_path)]
    argv += ["--edition", "head", "--edition-dir", str(tmp_path / "edition")]
    assert _eval.run(build_parser().parse_args(argv)) == 2
    assert "exclude each other" in capsys.readouterr().err
