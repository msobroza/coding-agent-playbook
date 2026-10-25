"""``playbook ci``'s ``commit-convention`` row: the release-title rule for catalog changes (#281).

A pull request that changes shipped rules, prompts, skills or hooks
(``catalog/core/<kind>/`` or ``catalog/plugins/<plugin>/<kind>/``) must be
titled ``feat``, ``fix`` or carry ``!``, so commitizen bumps the release when
guidance changes. A real git history (isolated through the hermetic git env)
holds the changed files; ``FakeCiStepRunner`` records every ``cz`` argv, so
commitizen never runs.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.cli.parser import build_parser
from coding_agent_playbook.commands.twins import ci
from coding_agent_playbook.commands.twins._ci_release_title import (
    release_title_problem,
    shipped_artifact_paths,
)
from tests.fakes import FakeCiStepRunner
from tests.hook_runtime.fakes import FakeGit

if TYPE_CHECKING:
    from collections.abc import Callable

_CZ = "/v/bin/cz"
_RULE = "catalog/core/rules/always/clean-code.md"
_SKILL = "catalog/plugins/mattpocock_skills/skills/tdd/SKILL.md"


def _branch_changing(tmp_path: Path, real_git: Callable[..., str], *paths: str) -> Path:
    """``main`` (one commit) and ``feat`` on top of it, one commit writing every path."""
    root = Path(os.path.realpath(tmp_path)) / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text("[tool.commitizen]\nname = 'cz_conventional_commits'\n")
    real_git("init", "-q", "-b", "main", cwd=root)
    real_git("add", "pyproject.toml", cwd=root)
    real_git("commit", "-q", "-m", "base", cwd=root)
    real_git("checkout", "-q", "-b", "feat", cwd=root)
    for rel in paths:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("changed\n", encoding="utf-8")
    real_git("add", "-A", cwd=root)
    real_git("commit", "-q", "-m", "change", cwd=root)
    return root


def _convention(root: Path, title: str, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    """Run only the commit-convention row with ``title`` as the PR title; ``(exit, stdout)``."""
    args = build_parser().parse_args(
        ["ci", "--steps", "commit-convention", "--base", "main", "--repo-root", str(root)]
    )
    runner = FakeCiStepRunner()
    code = ci.run(args, runner=runner, which={"cz": _CZ}.get, env={"PLAYBOOK_PR_TITLE": title})
    assert (_CZ, "check", "--message", title) in runner.calls
    return code, capsys.readouterr().out


def test_a_docs_title_on_a_catalog_change_fails_naming_the_artifacts_and_the_types(
    tmp_path: Path, real_git: Callable[..., str], capsys: pytest.CaptureFixture[str]
) -> None:
    root = _branch_changing(tmp_path, real_git, _RULE, _SKILL, "README.md")

    code, out = _convention(root, "docs(rules): reword the clean-code rule", capsys)

    assert code == 1
    assert "FAIL commit-convention (exit 1" in out
    assert f"{_RULE}, {_SKILL}" in out
    assert "README.md," not in out
    assert "feat, fix or a breaking '!'" in out
    assert "got 'docs'" in out


@pytest.mark.parametrize(
    "title",
    [
        "feat(rules): reword the clean-code rule",
        "fix: typo in the tdd skill",
        "refactor!: rename the clean-code rule",
        "Draft: feat: still a draft",
    ],
)
def test_a_release_title_on_a_catalog_change_passes(
    tmp_path: Path, real_git: Callable[..., str], capsys: pytest.CaptureFixture[str], title: str
) -> None:
    root = _branch_changing(tmp_path, real_git, _RULE, _SKILL)
    args = build_parser().parse_args(
        ["ci", "--steps", "commit-convention", "--base", "main", "--repo-root", str(root)]
    )

    code = ci.run(
        args, runner=FakeCiStepRunner(), which={"cz": _CZ}.get, env={"PLAYBOOK_PR_TITLE": title}
    )

    assert code == 0, capsys.readouterr().out


def test_a_docs_title_on_a_non_catalog_change_passes(
    tmp_path: Path, real_git: Callable[..., str], capsys: pytest.CaptureFixture[str]
) -> None:
    """Eval samples, plugin READMEs and engine docs are not shipped guidance."""
    root = _branch_changing(
        tmp_path,
        real_git,
        "README.md",
        "docs/guide.md",
        "catalog/core/eval_samples/review-spot-the-bug/sample.toml",
        "catalog/plugins/mattpocock_skills/ATTRIBUTIONS.md",
    )

    code, out = _convention(root, "docs: explain the release flow", capsys)

    assert code == 0, out
    assert "changes shipped" not in out


def test_the_rule_needs_a_pr_title(tmp_path: Path) -> None:
    """Without ``PLAYBOOK_PR_TITLE`` (a push build) the changed paths are never listed."""
    git = FakeGit(
        default_branch_name="origin/main",
        merge_bases={("origin/main", "HEAD"): "abc"},
        commits={"HEAD": "def"},
        changed={("abc", "HEAD"): (_RULE,)},
    )
    (tmp_path / "pyproject.toml").write_text("[tool.commitizen]\nname = 'cz'\n", "utf-8")
    args = build_parser().parse_args(
        ["ci", "--steps", "commit-convention", "--repo-root", str(tmp_path)]
    )

    assert ci.run(args, runner=FakeCiStepRunner(), git=git, which={"cz": _CZ}.get, env={}) == 0

    assert [call for call, _ in git.calls if call == "range_paths"] == []


def test_the_rule_lists_the_paths_of_the_merge_base_range(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    git = FakeGit(
        default_branch_name="origin/main",
        merge_bases={("origin/main", "HEAD"): "abc"},
        commits={"HEAD": "def"},
        changed={("abc", "HEAD"): (_RULE,)},
    )
    (tmp_path / "pyproject.toml").write_text("[tool.commitizen]\nname = 'cz'\n", "utf-8")
    args = build_parser().parse_args(
        ["ci", "--steps", "commit-convention", "--repo-root", str(tmp_path)]
    )
    env = {"PLAYBOOK_PR_TITLE": "chore: tidy"}

    assert ci.run(args, runner=FakeCiStepRunner(), git=git, which={"cz": _CZ}.get, env=env) == 1

    assert ("range_paths", ("abc", "HEAD")) in git.calls
    assert _RULE in capsys.readouterr().out


@pytest.mark.parametrize(
    ("path", "shipped"),
    [
        ("catalog/core/rules/always/a.md", True),
        ("catalog/core/prompts/v2/review.md.j2", True),
        ("catalog/core/skills/forge/SKILL.md", True),
        ("catalog/core/hooks/safety/secret-content-guard/HOOK.md", True),
        ("catalog/plugins/superpowers/skills/x/SKILL.md", True),
        ("catalog/plugins/mattpocock_skills/rules/a.md", True),
        ("catalog/core/eval_samples/review-spot-the-bug/sample.toml", False),
        ("catalog/plugins/superpowers/README.md", False),
        ("catalog/plugins/rules/a.md", False),
        ("catalog/editions/v0.1.0/core/rules/always/a.md", False),
        ("src/coding_agent_playbook/catalog/rules.py", False),
        ("playbook/rules/a.md", False),
    ],
)
def test_shipped_artifact_paths_keeps_only_catalog_guidance(path: str, shipped: bool) -> None:
    assert shipped_artifact_paths([path]) == ((path,) if shipped else ())


@pytest.mark.parametrize(
    ("title", "ok"),
    [
        ("feat: x", True),
        ("fix(hooks): x", True),
        ("docs!: x", True),
        ("chore(skills)!: x", True),
        ("docs: x", False),
        ("refactor(rules): x", False),
        ("not conventional at all", True),
    ],
)
def test_release_title_problem_on_a_catalog_change(title: str, ok: bool) -> None:
    """A title cz cannot parse is left to cz's own failure, not reported twice."""
    problem = release_title_problem(title, (_RULE,))

    assert (problem == "") is ok


def test_release_title_problem_folds_a_long_artifact_list() -> None:
    paths = tuple(f"catalog/core/rules/always/r{n:02}.md" for n in range(12))

    problem = release_title_problem("docs: x", paths)

    assert "catalog/core/rules/always/r09.md" in problem
    assert "r10.md" not in problem
    assert "and 2 more" in problem
