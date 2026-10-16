"""tests-with-source-nudge: the ``tests-nudge`` Stop stage (specs/prK-hook-pack.md §E.2).

Driven through ``playbook-hook simulate stop`` with the coordinator and this
hook on, in a repository with ``src/`` and ``tests/`` (so sync bakes
``source_roots = ["src"]`` and ``test_roots = ["tests"]``). ``FakeGit`` gives
the changed paths (``worktree_diffs["HEAD"]``), the ``HEAD`` blobs and the
words a test mentions (``test_words``); ruff is clean through ``FakeStageRunner``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.hook_runtime._git_parse import DiffLines
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.handlers.tests_nudge import MAX_FILES
from tests.hooks.stop_kit import changed_git, reason_lines, stop, stop_payload

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hook_runtime.fakes import FakeGit
    from tests.hooks.pack_repo import PackRepo

pytestmark = pytest.mark.content

HOOK_ID: Final = "tests-with-source-nudge"
GATE_ID: Final = "stop-ci-parity-gate"
HEAD_SOURCE: Final = "def existing() -> int:\n    return 1\n"
DONE: Final = "Added the parser entry point."
NUDGE: Final = '[tests-nudge] New public API without tests: "src/x.py"::public_fn'


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    pack_repo.write("src/x.py", HEAD_SOURCE)
    pack_repo.write("tests/test_x.py", "def test_existing() -> None:\n    assert True\n")
    pack_repo.install_pack([GATE_ID, HOOK_ID])
    return pack_repo


def _changed(
    *paths: str, head: Mapping[str, str] | None = None, words: set[str] | None = None
) -> FakeGit:
    blobs = {rel: text.encode() for rel, text in (head or {"src/x.py": HEAD_SOURCE}).items()}
    return changed_git(
        worktree_diffs={"HEAD": DiffLines(paths=paths)}, head_blobs=blobs, test_words=words or set()
    )


def _stop(
    repo: PackRepo,
    deps: Callable[..., RuntimeDeps],
    state: Path,
    git: FakeGit,
    *,
    message: str = DONE,
) -> SimulateReport:
    return stop(repo, deps, stop_payload(repo, message=message), git=git, state=state)


def _nudges(report: SimulateReport) -> list[str]:
    return [n for n in report.trace.combined.user_notes if n.startswith("[tests-nudge]")]


def test_new_public_fn_without_test_context_line(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    repo.write("src/x.py", HEAD_SOURCE + "\n\ndef public_fn() -> int:\n    return 2\n")

    report = _stop(repo, deps, tmp_path, _changed("src/x.py"))

    assert report.trace.combined.decision is Decision.NONE
    assert _nudges(report) == [NUDGE]


def test_private_fn_silent(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    repo.write("src/x.py", HEAD_SOURCE + "\n\ndef _private() -> int:\n    return 2\n")

    report = _stop(repo, deps, tmp_path, _changed("src/x.py"))

    assert _nudges(report) == []


def test_question_final_message_silent(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    repo.write("src/x.py", HEAD_SOURCE + "\n\ndef public_fn() -> int:\n    return 2\n")
    git = _changed("src/x.py")

    report = _stop(repo, deps, tmp_path, git, message="Should public_fn also cache?")

    assert _nudges(report) == []
    assert not any(method == "grep_word" for method, _ in git.calls)


def test_test_referencing_fn_silent(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    repo.write("src/x.py", HEAD_SOURCE + "\n\ndef public_fn() -> int:\n    return 2\n")
    git = _changed("src/x.py", words={"public_fn"})

    report = _stop(repo, deps, tmp_path, git)

    assert _nudges(report) == []
    assert ("grep_word", ("public_fn", "tests")) in git.calls


def test_block_true_deny_line(
    pack_repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    pack_repo.write(
        "src/x.py", HEAD_SOURCE + "\n\nclass Parser:\n    def feed(self) -> None: ...\n"
    )
    pack_repo.install_pack([GATE_ID, HOOK_ID], per_hook={HOOK_ID: {"block": True}})

    report = _stop(pack_repo, deps, tmp_path, _changed("src/x.py"))

    assert report.trace.combined.decision is Decision.DENY
    assert reason_lines(report)[1:] == [
        '[tests-nudge] New public API without tests: "src/x.py"::Parser',
        '[tests-nudge] New public API without tests: "src/x.py"::Parser.feed',
    ]


def test_abstractmethod_override_main_skipped(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    head = HEAD_SOURCE + "\n\nclass Base:\n    def run(self) -> None: ...\n"
    repo.write(
        "src/x.py",
        "import abc\nfrom typing import override\n\n"
        + head
        + "\n    @abc.abstractmethod\n    def step(self) -> None: ...\n"
        + "\n    @override\n    def __repr__(self) -> str: ...\n"
        + "\n    @override\n    def describe(self) -> str: ...\n"
        + "\n    def __len__(self) -> int: ...\n"
        + "\n\ndef main() -> None: ...\n",
    )

    report = _stop(repo, deps, tmp_path, _changed("src/x.py", head={"src/x.py": head}))

    assert _nudges(report) == []


def test_new_file_tests_and_outside_roots_skipped(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    repo.write("src/new.py", "def fresh() -> None: ...\n")
    repo.write("tests/test_new.py", "def helper_for_tests() -> None: ...\n")
    repo.write("scripts/tool.py", "def script_entry() -> None: ...\n")
    git = _changed("tests/test_new.py", "scripts/tool.py", head={})
    git.untracked = ("src/new.py",)

    report = _stop(repo, deps, tmp_path, git)

    assert _nudges(report) == ['[tests-nudge] New public API without tests: "src/new.py"::fresh']


def test_at_most_20_files_parsed(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], tmp_path: Path
) -> None:
    paths = [f"src/m{n:02}.py" for n in range(MAX_FILES + 5)]
    for rel in paths:
        repo.write(rel, "def fn() -> None: ...\n")
    git = _changed(*paths, head={}, words={"fn"})

    _stop(repo, deps, tmp_path, git)

    assert len([method for method, _ in git.calls if method == "cat_head"]) == MAX_FILES == 20
