"""git-commit-push-policy-guard: identity, authorship, signing and where commits land (specs/prK-hook-pack.md §E.4).

Every case runs the shipped ``HOOK.md`` through ``playbook-hook simulate
pre_tool_use``. ``FakeGit`` answers the local ``git config --get`` identity
(a real one unless a case says otherwise), the current branch (``feat/x``)
and the default branch (``main``); ``FakeProc`` fails the test on any spawn.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.handlers._git_identity import IDENTITY_REASON
from coding_agent_playbook.hook_runtime.handlers.git_policy import PLACEHOLDER_REASON
from coding_agent_playbook.hook_runtime.stop.chain import write_last_green
from tests.hook_runtime.fakes import FakeGit

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hook_runtime.handlers.pack_repo import PackRepo

    type Deps = Callable[..., RuntimeDeps]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "git-commit-push-policy-guard"
IDENTITY: Final = {"user.name": "Dev Eloper", "user.email": "dev@corp.test"}
HEREDOC_COMMIT: Final = (
    "git commit -m \"$(cat <<'EOF'\nfeat: add parser\n\nCo-Authored-By: Bot <bot@x.test>\nEOF\n)\""
)


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    pack_repo.install_pack([HOOK_ID], wrapper_prefixes=("proxy",))
    return pack_repo


def _git(**fields: Any) -> FakeGit:
    defaults: dict[str, Any] = {
        "config": dict(IDENTITY),
        "symbolic_refs": {"HEAD": "feat/x"},
        "default_branch_name": "main",
    }
    return FakeGit(**{**defaults, **fields})


def _bash(
    repo: PackRepo,
    deps: Deps,
    command: str,
    *,
    git: FakeGit | None = None,
    state: Path | None = None,
    **fields: Any,
) -> SimulateReport:
    payload = repo.tool_payload("Bash", {"command": command}, **fields)
    return repo.simulate(payload, deps(git=git or _git()), state=state)


def _decision(report: SimulateReport) -> Decision:
    return report.trace.combined.decision


def _rule(report: SimulateReport) -> str:
    return next(done.result.rule_id for done in report.trace.ran if done.result.rule_id)


GOLDEN: Final[list[tuple[str, Decision]]] = [
    ("git commit --author=x -m m", Decision.DENY),
    ('git commit --author "A <a@b>" -m m', Decision.DENY),
    ("git commit -S -m m", Decision.DENY),
    ("git commit --no-gpg-sign -m m", Decision.DENY),
    ("git commit -s -m m", Decision.NONE),  # --signoff, not signing
    ("git tag -s v1 -m v1", Decision.DENY),
    ("git config user.email a@b", Decision.DENY),
    ("git config --global --unset user.name", Decision.DENY),
    ("git config set commit.gpgsign false", Decision.DENY),
    ("git config --get user.email", Decision.NONE),
    ("git config user.email", Decision.NONE),
    ("git config core.editor vim", Decision.NONE),
    ("git -c user.email=x commit -m m", Decision.DENY),
    ("git -c commit.gpgsign=false commit -m m", Decision.DENY),
    (
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=user.email GIT_CONFIG_VALUE_0=x git commit -m m",
        Decision.DENY,
    ),
    ("GIT_AUTHOR_NAME=x git commit -m m", Decision.DENY),
    ("export GIT_COMMITTER_EMAIL=x", Decision.DENY),
    ("proxy git commit --author=x -m m", Decision.DENY),
    ("git status && git commit -m 'feat: x'", Decision.NONE),
    ("echo git commit --author", Decision.NONE),
    ("git log --author=me", Decision.NONE),
    ("git push origin feat/x", Decision.NONE),
]


@pytest.mark.parametrize(("command", "expected"), GOLDEN)
def test_golden(repo: PackRepo, deps: Deps, command: str, expected: Decision) -> None:
    assert _decision(_bash(repo, deps, command)) is expected


def test_identity_reason_names_the_safe_alternative(repo: PackRepo, deps: Deps) -> None:
    report = _bash(repo, deps, "git commit --author=x -m m")

    assert report.trace.combined.reason == IDENTITY_REASON


@pytest.mark.parametrize(
    "config",
    [
        {"user.name": "Dev", "user.email": "you@example.com"},
        {"user.name": "Dev"},
        {"user.name": "", "user.email": "dev@corp.test"},
        {"user.name": "Dev", "user.email": "ci@localhost"},
    ],
)
def test_placeholder_identity_denies_without_echoing_it(
    repo: PackRepo, deps: Deps, config: dict[str, str]
) -> None:
    report = _bash(repo, deps, "git commit -m 'feat: x'", git=_git(config=config))

    assert (_decision(report), _rule(report)) == (Decision.DENY, "placeholder_identity")
    assert report.trace.combined.reason == PLACEHOLDER_REASON
    assert all(value not in report.trace.combined.reason for value in config.values() if value)


def test_on_the_default_branch_asks(repo: PackRepo, deps: Deps) -> None:
    on_main = _git(symbolic_refs={"HEAD": "main"}, default_branch_name="origin/main")

    report = _bash(repo, deps, "git commit -m 'feat: x'", git=on_main)

    assert (_decision(report), _rule(report)) == (Decision.ASK, "default_branch")


def test_trunk_based_repo_turns_the_default_branch_ask_off(pack_repo: PackRepo, deps: Deps) -> None:
    pack_repo.install_pack([HOOK_ID], per_hook={HOOK_ID: {"ask_on_default_branch": False}})
    on_main = _git(symbolic_refs={"HEAD": "main"})

    assert _decision(_bash(pack_repo, deps, "git commit -m x", git=on_main)) is Decision.NONE


def test_commit_from_another_worktree_asks(repo: PackRepo, deps: Deps, tmp_path: Path) -> None:
    other = tmp_path / "other-wt"
    (other / ".git").mkdir(parents=True)

    report = _bash(repo, deps, f"cd {other} && git commit -m 'feat: x'")

    assert (_decision(report), _rule(report)) == (Decision.ASK, "other_worktree")


def _with_rows(pack_repo: PackRepo, **rows: Any) -> PackRepo:
    pack_repo.install_pack([HOOK_ID], per_hook={HOOK_ID: rows})
    return pack_repo


def test_forbidden_trailer_in_a_heredoc_denies_only_with_rows(
    pack_repo: PackRepo, deps: Deps
) -> None:
    empty = _bash(_with_rows(pack_repo), deps, HEREDOC_COMMIT)
    ruled = _bash(_with_rows(pack_repo, forbid_trailers=["Co-Authored-By"]), deps, HEREDOC_COMMIT)

    assert _decision(empty) is Decision.NONE
    assert (_decision(ruled), _rule(ruled)) == (Decision.DENY, "trailers")
    assert "CP401 forbidden trailer Co-Authored-By" in ruled.trace.combined.reason


def test_uninspectable_message_asks_only_with_rows(pack_repo: PackRepo, deps: Deps) -> None:
    command = "git commit -F <(printf 'feat: x')"

    empty = _bash(_with_rows(pack_repo), deps, command)
    ruled = _bash(_with_rows(pack_repo, required_trailers={"Refs": "^[A-Z]+-\\d+$"}), deps, command)

    assert _decision(empty) is Decision.NONE
    assert (_decision(ruled), _rule(ruled)) == (Decision.ASK, "message_uninspectable")


def test_required_trailer_from_a_message_file(pack_repo: PackRepo, deps: Deps) -> None:
    _with_rows(pack_repo, required_trailers={"Refs": "^[A-Z]+-\\d+$"})
    pack_repo.write("msg.txt", "feat: x\n\nRefs: AB-12\n")
    pack_repo.write("bad.txt", "feat: x\n\nRefs: none\n")

    good = _bash(pack_repo, deps, "git commit -F msg.txt")
    bad = _bash(pack_repo, deps, "git commit -F bad.txt")

    assert _decision(good) is Decision.NONE
    assert _decision(bad) is Decision.DENY
    assert "CP403 trailer Refs does not match" in bad.trace.combined.reason


@pytest.mark.parametrize(
    ("command", "status", "expected"),
    [
        ("git commit -m x", (("A ", ".claude/settings.local.json"),), Decision.DENY),
        ("git commit -m x", ((" M", ".claude/settings.local.json"),), Decision.NONE),
        ("git commit -am x", ((" M", ".claude/settings.local.json"),), Decision.DENY),
        ("git commit -m x", (("M ", "src/app.py"),), Decision.NONE),
        ("git add -f CLAUDE.md", (), Decision.DENY),
        ("git add CLAUDE.md", (), Decision.NONE),
    ],
)
def test_never_commit_globs(
    pack_repo: PackRepo,
    deps: Deps,
    command: str,
    status: tuple[tuple[str, str], ...],
    expected: Decision,
) -> None:
    _with_rows(pack_repo, never_commit_globs=[".claude/**", "CLAUDE.md"])

    report = _bash(pack_repo, deps, command, git=_git(status=status))

    assert _decision(report) is expected


def test_no_data_rows_reads_no_status(repo: PackRepo, deps: Deps) -> None:
    git = _git()

    _bash(repo, deps, "git commit -am 'feat: x'", git=git)

    assert "porcelain_status" not in [call[0] for call in git.calls]


@pytest.mark.parametrize("command", ["git push origin feat/x", "gh pr create --fill"])
def test_push_requires_green_is_advisory_and_opt_in(
    pack_repo: PackRepo, deps: Deps, tmp_path: Path, command: str
) -> None:
    _with_rows(pack_repo, push_requires_green=True)
    state = tmp_path / "state"
    git = _git(head_tree_id="4b825dc6")

    red = _bash(pack_repo, deps, command, git=git, state=state)
    _record_green(state, "4b825dc6:abc")
    green = _bash(pack_repo, deps, command, git=git, state=state)

    assert (_decision(red), _rule(red)) == (Decision.ASK, "push_not_green")
    assert _decision(green) is Decision.NONE


def _record_green(state: Path, key: str) -> None:
    from coding_agent_playbook.hook_runtime.state.store import STATE_DIR_NAME, StateStore
    from tests.hook_runtime.fakes import FakeClock

    write_last_green(StateStore(str(state / STATE_DIR_NAME), clock=FakeClock()), key)


def test_unparsed_identity_change_asks(repo: PackRepo, deps: Deps) -> None:
    report = _bash(repo, deps, 'git commit --author="x -m oops')

    assert (_decision(report), _rule(report)) == (Decision.ASK, "unparsed")
