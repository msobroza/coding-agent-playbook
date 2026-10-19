"""The guard twins' shared contract, one row per twin (specs/prT-package-layout.md B.9.3).

Every twin runs through ``commands/twins/_runner.run_twin``: outside a git
repository it prints nothing on stdout and one ``error:`` line on stderr, and
exits 2 (specs/prK-hook-pack.md §E.4); the twins with a ``--format`` flag print
one JSON document when asked. The JSON rows run on an in-memory ``FakeGit``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

import pytest

from coding_agent_playbook.cli import main
from coding_agent_playbook.cli.parser import build_parser
from coding_agent_playbook.commands.twins import gate_scan, scan_secrets, scan_sinks
from coding_agent_playbook.hook_runtime.event import RepoInfo
from coding_agent_playbook.hook_runtime.git.parse import AddedLine, DiffLines
from coding_agent_playbook.hook_runtime.paths import find_repo
from tests.hook_runtime.fakes import FakeGit

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.git.safe_git import SafeGit

#: The committed config check-commit-trailers needs before it opens git: with no
#: trailer rows it exits 0 without reading a commit.
TRAILER_ROWS: Final = """\
[hooks.git-commit-push-policy-guard]
forbid_trailers = ["Co-Authored-By"]
"""
#: Each twin's argv in a directory that is not a git repository.
TWIN_ARGV: Final = {
    "gate-scan": ["gate-scan"],
    "scan-sinks": ["scan-sinks", "--range", "HEAD~1..HEAD"],
    "scan-secrets": ["scan-secrets", "--staged"],
    "check-commit-trailers": ["check-commit-trailers", "--range", "HEAD~1..HEAD"],
    "check-notebooks": ["check-notebooks"],
    "check-deps": ["check-deps"],
}
SINK_LINE: Final = "import pickle\nx = pickle.loads(b)\n"


@dataclass
class FakeCheckoutGit(FakeGit):
    """A ``FakeGit`` with the checkout ``SafeGit`` names (``repo``), for ``scan-secrets PATHS``."""

    repo: RepoInfo | None = None


@pytest.fixture
def plain_dir(tmp_path: Path) -> Path:
    root = Path(os.path.realpath(tmp_path)) / "plain"
    root.mkdir()
    if find_repo(str(root)) is not None:
        pytest.skip(f"{root} is inside a git repository; the row needs one that is not")
    (root / ".coding-agent-playbook.toml").write_text(TRAILER_ROWS, encoding="utf-8")
    return root


@pytest.mark.parametrize("twin", sorted(TWIN_ARGV))
def test_every_twin_outside_a_git_repository_exits_2_with_one_error_line(
    twin: str, plain_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main([*TWIN_ARGV[twin], "--repo-root", str(plain_dir)])

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert len(captured.err.splitlines()) == 1
    assert captured.err.startswith("error: ")


def _gate_scan_json(root: Path) -> int:
    added = (AddedLine("src/a.py", 2, "y = f()  # type: ignore"),)
    git = FakeGit(range_diffs={("B", "H"): DiffLines(added=added, paths=("src/a.py",))})
    args = build_parser().parse_args(["gate-scan", "--range", "B..H", "--format", "json"])
    args.repo_root = str(root)
    return gate_scan.run(args, git=git)


def _scan_sinks_json(root: Path) -> int:
    git = FakeGit(
        range_diffs={("B", "H"): DiffLines(paths=("src/io.py",))},
        revision_blobs={("H", "src/io.py"): SINK_LINE.encode()},
    )
    args = build_parser().parse_args(["scan-sinks", "--range", "B..H", "--format", "json"])
    args.repo_root = str(root)
    return scan_sinks.run(args, git=cast("SafeGit", git))


def _scan_secrets_json(root: Path) -> int:
    (root / ".env.prod").write_text("API=1\n", encoding="utf-8")
    git_dir = str(root / ".git")
    repo = RepoInfo(
        worktree_root=str(root), git_dir=git_dir, common_dir=git_dir, is_linked_worktree=False
    )
    args = build_parser().parse_args(["scan-secrets", ".env.prod", "--format", "json"])
    args.repo_root = str(root)
    return scan_secrets.run(args, git=cast("SafeGit", FakeCheckoutGit(repo=repo)))


JSON_TWINS: Final[dict[str, Callable[[Path], int]]] = {
    "gate-scan": _gate_scan_json,
    "scan-sinks": _scan_sinks_json,
    "scan-secrets": _scan_secrets_json,
}


@pytest.mark.parametrize(
    ("twin", "expected"),
    [
        ("gate-scan", {"range": "B..H", "blocking": 1, "exit": 1}),
        ("scan-sinks", {"range": "B..H", "blocking": 1, "exit": 1}),
        ("scan-secrets", {"scope": "paths", "exit": 1}),
    ],
)
def test_twins_with_a_format_flag_print_json_when_asked(
    twin: str, expected: dict[str, object], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = JSON_TWINS[twin](Path(os.path.realpath(tmp_path)))

    document = json.loads(capsys.readouterr().out)
    assert code == 1
    assert {key: document[key] for key in expected} == expected
