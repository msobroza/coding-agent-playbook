"""``playbook gate-scan``: gate-weakening-guard's off-workstation twin (specs/prK-hook-pack.md §E.2).

Every row runs the real command in-process against a real repository built
under ``hermetic_git_env`` (through ``real_git``): a stateless ``SafeGit``
diffs the range, and the policy is the engine default extended by the
``[hooks.gate-weakening-guard]`` table committed at the range's base.
Exit codes: 0 clean, 1 blocking findings, 2 a usage error or unresolvable base.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.cli import main

if TYPE_CHECKING:
    from collections.abc import Callable

_CONSUMER_TABLE = """\
[hooks.gate-weakening-guard]
added_line_patterns = [{ id = "todo-skip", regex = "TODO\\\\(skip\\\\)" }]
"""


class Repo:
    """A real repository on ``main`` with a ``src/`` layout; ``commit`` writes files and commits."""

    def __init__(self, root: Path, git: Callable[..., str]) -> None:
        self.root = root
        self.git = git

    def commit(self, message: str, files: dict[str, str] | None = None) -> str:
        for name, text in (files or {}).items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.git("add", "-A", cwd=self.root)
        self.git("commit", "-q", "--allow-empty", "-m", message, cwd=self.root)
        return self.git("rev-parse", "HEAD", cwd=self.root)

    def scan(self, *args: str) -> int:
        return main(["gate-scan", *args, "--repo-root", str(self.root)])


@pytest.fixture
def repo(tmp_path: Path, real_git: Callable[..., str]) -> Repo:
    root = Path(os.path.realpath(tmp_path)) / "consumer"
    root.mkdir()
    real_git("init", "-q", "-b", "main", cwd=root)
    built = Repo(root, real_git)
    built.commit("init", {"src/pkg/a.py": "x = 1\n", "pyproject.toml": "[project]\nname = 'c'\n"})
    return built


def test_range_head_parent_exits_1_on_fixture(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("suppress", {"src/pkg/a.py": "x = 1\ny = f()  # type: ignore\n"})

    assert repo.scan("--range", "HEAD~1..HEAD") == 1

    out = capsys.readouterr().out
    assert "src/pkg/a.py:2: type-ignore: y = f()  # type: ignore" in out
    assert "gate-scan HEAD~1..HEAD: 1 blocking" in out


def test_clean_range_exits_0(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.commit("feature", {"src/pkg/b.py": "def g() -> int:\n    return 2\n"})

    assert repo.scan("--range", "HEAD~1..HEAD") == 0
    assert "gate-scan HEAD~1..HEAD: clean" in capsys.readouterr().out


def test_justified_loosening_is_a_note_and_exits_0(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("mypy", {"pyproject.toml": "[project]\nname = 'c'\n[tool.mypy]\nstrict = true\n"})
    relaxed = "[project]\nname = 'c'\n[tool.mypy]\nstrict = false  # migrating\n"
    repo.commit("relax", {"pyproject.toml": relaxed})

    assert repo.scan("--range", "HEAD~1..HEAD") == 0

    out = capsys.readouterr().out
    assert "note: pyproject.toml: config-loosening: [tool.mypy] strict: true → false" in out


@pytest.mark.parametrize(
    "bad_range", ["no-such-ref..HEAD", "--output=/tmp/leak..HEAD", "HEAD", "HEAD~1..HEAD:x"]
)
def test_bad_range_exits_2(repo: Repo, capsys: pytest.CaptureFixture[str], bad_range: str) -> None:
    repo.commit("more", {"src/pkg/a.py": "x = 2\n"})

    assert repo.scan(f"--range={bad_range}") == 2

    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert captured.out == ""


def test_json_format_lists_findings(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    repo.commit(
        "skip", {"tests/test_a.py": "import pytest\n\n@pytest.mark.skip\ndef test_a(): ...\n"}
    )

    assert repo.scan("--range", "HEAD~1..HEAD", "--format", "json") == 1

    report = json.loads(capsys.readouterr().out)
    assert report["exit"] == 1
    assert report["blocking"] == 1
    assert report["findings"] == [
        {
            "path": "tests/test_a.py",
            "line": 3,
            "rule": "pytest-skip-marker",
            "kind": "suppression",
            "detail": "@pytest.mark.skip",
            "justified": False,
        }
    ]


def test_default_range_is_merge_base_to_head(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("legacy", {"src/pkg/old.py": "z = g()  # type: ignore\n"})
    base = repo.git("rev-parse", "HEAD", cwd=repo.root)
    repo.git("checkout", "-q", "-b", "feature", cwd=repo.root)
    repo.commit("work", {"src/pkg/new.py": "import os  # noqa\n"})

    assert repo.scan() == 1

    out = capsys.readouterr().out
    assert "src/pkg/new.py:1: noqa" in out
    assert "old.py" not in out  # committed before the merge base
    assert f"gate-scan {base[:12]}..HEAD" in out


def test_symmetric_range_diffs_from_the_merge_base(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.git("checkout", "-q", "-b", "feature", cwd=repo.root)
    repo.commit("work", {"src/pkg/new.py": "import os  # noqa\n"})
    repo.git("checkout", "-q", "main", cwd=repo.root)
    repo.commit("main moves", {"src/pkg/main.py": "w = h()  # type: ignore\n"})

    assert repo.scan("--range", "main...feature") == 1

    out = capsys.readouterr().out
    assert "src/pkg/new.py:1: noqa" in out
    assert "main.py" not in out


def test_unresolvable_default_base_exits_2(
    tmp_path: Path, real_git: Callable[..., str], capsys: pytest.CaptureFixture[str]
) -> None:
    root = Path(os.path.realpath(tmp_path)) / "lonely"
    root.mkdir()
    real_git("init", "-q", "-b", "work", cwd=root)
    Repo(root, real_git).commit("init", {"a.py": "x = 1\n"})

    assert main(["gate-scan", "--repo-root", str(root)]) == 2
    assert "fetch-depth: 0" in capsys.readouterr().err


def test_policy_comes_from_the_base_revision(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("policy", {".coding-agent-playbook.toml": _CONSUMER_TABLE})
    loosened = _CONSUMER_TABLE + 'justification_regex = "x"\n'
    repo.commit(
        "sneaky",
        {
            ".coding-agent-playbook.toml": loosened,
            "src/pkg/a.py": "x = 1  # TODO(skip)\ny = f()  # type: ignore  x\n",
        },
    )

    assert repo.scan("--range", "HEAD~1..HEAD") == 1

    out = capsys.readouterr().out
    assert "src/pkg/a.py:1: todo-skip" in out  # the base's extension applies
    assert "src/pkg/a.py:2: type-ignore" in out  # the head's own regex does not


def test_malformed_consumer_table_exits_2(repo: Repo, capsys: pytest.CaptureFixture[str]) -> None:
    bad = "[hooks.gate-weakening-guard]\nadded_line_patterns = 'x'\n"
    repo.commit("policy", {".coding-agent-playbook.toml": bad})
    repo.commit("more", {"src/pkg/a.py": "x = 3\n"})

    assert repo.scan("--range", "HEAD~1..HEAD") == 2
    assert "added_line_patterns" in capsys.readouterr().err


def test_a_base_config_that_is_not_toml_exits_2_naming_the_revision(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    repo.commit("policy", {".coding-agent-playbook.toml": "[hooks.gate-weakening-guard\n"})
    repo.commit("more", {"src/pkg/a.py": "x = 3\n"})

    assert repo.scan("--range", "HEAD~1..HEAD") == 2

    captured = capsys.readouterr()
    assert captured.err.startswith("error: .coding-agent-playbook.toml at HEAD~1: invalid TOML: ")
    assert captured.out == ""


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ('hooks = "x"\n', "[hooks] must be a table, got 'x'"),
        ('[hooks]\ngate-weakening-guard = "x"\n', "[hooks.gate-weakening-guard] must be a table"),
    ],
    ids=["hooks", "hook-table"],
)
def test_a_base_hooks_value_that_is_not_a_table_exits_2_naming_it(
    repo: Repo, capsys: pytest.CaptureFixture[str], config: str, message: str
) -> None:
    """Stricter on purpose (spec B.5.5): a base ``hooks = "x"`` read as no policy."""
    repo.commit("policy", {".coding-agent-playbook.toml": config})
    repo.commit("more", {"src/pkg/a.py": "x = 3\n"})

    assert repo.scan("--range", "HEAD~1..HEAD") == 2
    assert capsys.readouterr().err.startswith(
        f"error: .coding-agent-playbook.toml at HEAD~1: {message}"
    )


_GITLAB_CI = """\
lint:
  script:
    - ruff check .

playbook-ci:
  script:
    - playbook ci --base "$CI_MERGE_REQUEST_DIFF_BASE_SHA"
"""


def test_a_gitlab_ci_job_made_optional_or_removed_exits_1(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    """prF §10.3: the twin hands GitLab CI files to the scanner as before/after pairs."""
    repo.commit("ci", {".gitlab-ci.yml": _GITLAB_CI})
    weakened = _GITLAB_CI.replace("lint:\n  script:\n    - ruff check .\n\n", "")
    repo.commit(
        "drop lint", {".gitlab-ci.yml": weakened.replace("  script:", "  when: manual\n  script:")}
    )

    assert repo.scan("--range", "HEAD~1..HEAD") == 1

    out = capsys.readouterr().out
    assert ".gitlab-ci.yml: gitlab-ci-job-removed: job 'lint' removed" in out
    assert ".gitlab-ci.yml: playbook-ci-job-loosened: job 'playbook-ci' gains when: manual" in out


def test_ci_config_globs_committed_at_the_base_extend_the_watched_files(
    repo: Repo, capsys: pytest.CaptureFixture[str]
) -> None:
    table = '[hooks.gate-weakening-guard]\nci_config_globs = ["ci/*.gitlab-ci.yml"]\n'
    repo.commit("ci", {".coding-agent-playbook.toml": table, "ci/deploy.gitlab-ci.yml": _GITLAB_CI})
    repo.commit("drop", {"ci/deploy.gitlab-ci.yml": "stages: [test]\n"})

    assert repo.scan("--range", "HEAD~1..HEAD") == 1
    assert "ci/deploy.gitlab-ci.yml: gitlab-ci-job-removed: job 'lint' removed" in (
        capsys.readouterr().out
    )
