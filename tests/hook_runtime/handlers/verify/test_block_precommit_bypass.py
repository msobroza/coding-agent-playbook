"""block-precommit-bypass: the repo's playbook pre-commit hooks must run (specs/prK-hook-pack.md §E.2).

Every case runs the shipped ``HOOK.md`` through ``playbook-hook simulate
pre_tool_use`` against a fixture repo whose ``guard_config.precommit`` lists
playbook hook ids (as sync renders them from ``.pre-commit-config.yaml``) and
whose ``[hooks] wrapper_prefixes`` is ``["proxy"]``. ``FakeProc`` fails the test
on any spawn: the guard parses argv, it never runs git.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.hook_runtime.dispatch.decision import Decision
from coding_agent_playbook.hook_runtime.dispatch.event import Harness
from coding_agent_playbook.hook_runtime.dispatch.policy import UNATTENDED_ENV_VAR
from coding_agent_playbook.hook_runtime.handlers.verify.block_precommit_bypass import reason_for
from tests.hook_runtime.handlers.pack_repo import precommit_config

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.diagnostics.simulate import SimulateReport
    from coding_agent_playbook.hook_runtime.dispatch.deps import RuntimeDeps
    from tests.hook_payloads import HookPayloadCase
    from tests.hook_runtime.handlers.pack_repo import PackRepo

    type Payload = Callable[[str, str, str], HookPayloadCase]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "block-precommit-bypass"
IDS: Final = ("playbook-metrics", "playbook-validate")
GIT_CONFIG: Final = "[core]\n\tbare = false\n"


@pytest.fixture
def repo(pack_repo: PackRepo) -> PackRepo:
    (pack_repo.root / ".git" / "hooks").mkdir(parents=True, exist_ok=True)
    (pack_repo.root / ".git" / "config").write_text(GIT_CONFIG, "utf-8")
    # Declared out of order: sync renders the ids sorted, as IDS lists them.
    pack_repo.write(".pre-commit-config.yaml", precommit_config(*reversed(IDS)))
    pack_repo.install_pack([HOOK_ID], wrapper_prefixes=("proxy",))
    return pack_repo


def _bash(repo: PackRepo, deps: Callable[..., RuntimeDeps], command: str) -> SimulateReport:
    return repo.simulate(repo.tool_payload("Bash", {"command": command}), deps())


def _decision(report: SimulateReport) -> Decision:
    return report.trace.combined.decision


def _rules(report: SimulateReport) -> list[str]:
    return [done.result.rule_id for done in report.trace.ran]


#: The §E.2 test table, plus the neighbours each row must not catch.
E2_TABLE: Final = [
    ("git commit --no-verify -m x", Decision.DENY),
    ("git commit -nm x", Decision.DENY),
    ("git commit -an", Decision.DENY),
    ("git push -n", Decision.NONE),
    ('git commit -m "fix -n handling"', Decision.NONE),
    ("git commit -m --no-verify", Decision.NONE),
    ("git push --no-verify origin main", Decision.DENY),
    ("git merge --no-verify feature", Decision.DENY),
    ("SKIP=playbook-metrics git commit", Decision.DENY),
    ("SKIP=end-of-file-fixer git commit", Decision.NONE),
    ("export SKIP=playbook-validate", Decision.DENY),
    (
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null git commit",
        Decision.DENY,
    ),
    ("GIT_CONFIG_PARAMETERS=\"'core.hooksPath'='/dev/null'\" git commit", Decision.DENY),
    ("git -c core.hooksPath=/dev/null commit -m x", Decision.DENY),
    ("git config core.hooksPath /tmp/none", Decision.DENY),
    ("git config --get core.hooksPath", Decision.NONE),
    ("git config --file .git/config core.hooksPath /tmp/none", Decision.DENY),
    ("git config set core.hooksPath /tmp/none", Decision.DENY),
    ("git config alias.ci 'commit --no-verify'", Decision.DENY),
    ("git config alias.lg 'log -n 5'", Decision.NONE),
    ("PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m x", Decision.DENY),
    ("pre-commit uninstall", Decision.DENY),
    ("rm .git/hooks/pre-commit", Decision.DENY),
    ("chmod -x .git/hooks/pre-commit", Decision.DENY),
    ("echo exit 0 > .git/hooks/pre-commit", Decision.DENY),
    ("cat .git/hooks/pre-commit", Decision.NONE),
    ("proxy git commit --no-verify", Decision.DENY),
    ("echo git commit --no-verify", Decision.NONE),
    ("git status && git commit -m done", Decision.NONE),
    # prF §8.1: a forge CLI that pushes runs git's pre-push hooks under its own env prefix
    ("SKIP=playbook-validate glab mr create --fill", Decision.DENY),
    (
        "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null "
        "glab mr create --fill",
        Decision.DENY,
    ),
    ("SKIP=playbook-metrics gh repo create app --source . --push", Decision.DENY),
    ("glab mr create --fill", Decision.NONE),
]


@pytest.mark.parametrize(("command", "expected"), E2_TABLE)
def test_e2_table(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], command: str, expected: Decision
) -> None:
    assert _decision(_bash(repo, deps, command)) is expected


def test_no_playbook_ids_inactive(pack_repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    pack_repo.install_pack([HOOK_ID], wrapper_prefixes=("proxy",))

    for command in ("git commit --no-verify -m x", "rm .git/hooks/pre-commit"):
        assert _decision(_bash(pack_repo, deps, command)) is Decision.NONE


def test_commit_tree_outside_rebase_asks(repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    command = "git update-ref refs/heads/main $(git commit-tree HEAD^{tree} -m x)"

    asked = _bash(repo, deps, command)
    (repo.root / ".git" / "rebase-merge").mkdir()
    rebasing = _bash(repo, deps, command)

    assert _decision(asked) is Decision.ASK
    assert asked.trace.combined.reason == reason_for(Decision.ASK, IDS)
    assert _decision(rebasing) is Decision.NONE


def test_commit_tree_headless_denies(repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    payload = repo.tool_payload("Bash", {"command": "git commit-tree HEAD^{tree} -m x"})

    report = repo.simulate(payload, deps(), env={UNATTENDED_ENV_VAR: "1"})

    assert _decision(report) is Decision.DENY


def test_file_edit_of_git_hooks_denied(repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    target = repo.root / ".git" / "hooks" / "pre-commit"
    payload = repo.tool_payload("Write", {"file_path": str(target), "content": "exit 0\n"})

    report = repo.simulate(payload, deps())

    assert _decision(report) is Decision.DENY
    assert _rules(report) == ["hooks_dir"]


@pytest.mark.parametrize(
    ("new", "expected"),
    [
        ("[core]\n\thooksPath = /dev/null\n\tbare = false\n", Decision.DENY),
        ("[core]\n\tbare = false\n[user]\n\tname = dev\n", Decision.NONE),
    ],
)
def test_core_hookspath_edit_in_git_config_denied(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], new: str, expected: Decision
) -> None:
    tool_input = {
        "file_path": str(repo.root / ".git" / "config"),
        "old_string": GIT_CONFIG,
        "new_string": new,
    }

    report = repo.simulate(repo.tool_payload("Edit", tool_input), deps())

    assert _decision(report) is expected


def test_reason_lists_ids(repo: PackRepo, deps: Callable[..., RuntimeDeps]) -> None:
    report = _bash(repo, deps, "git commit --no-verify -m x")

    assert report.trace.combined.reason.splitlines() == [
        "Blocked: this repo's pre-commit hooks (playbook-metrics, playbook-validate) must run.",
        "Fix what the hook reported (playbook validate && playbook sync, or the metrics "
        "regression).",
        "If you believe it is a false positive, stop and tell the user.",
    ]
    assert "--no-verify" not in report.trace.combined.reason  # never teaches the bypass


def test_unparsed_command_naming_a_bypass_asks(
    repo: PackRepo, deps: Callable[..., RuntimeDeps]
) -> None:
    unterminated = "git commit --no-verify -m 'oops"

    report = _bash(repo, deps, unterminated)

    assert _decision(report) is Decision.ASK
    assert _rules(report) == ["unparsed"]


def test_golden_claude_payloads(
    repo: PackRepo, deps: Callable[..., RuntimeDeps], hook_payload: Payload
) -> None:
    for case in ("bpb_bash_commit_no_verify", "bpb_bash_skip_other_hook"):
        golden = hook_payload("claude_code", "pre_tool_use", case)
        report = repo.simulate(repo.relocate(golden), deps(), harness=Harness.CLAUDE_CODE)
        expected = golden.expected["result"]
        combined = report.trace.combined
        assert (combined.decision.value, combined.reason) == (
            expected["decision"],
            expected.get("reason", ""),
        )
        assert report.trace.wire == golden.wire()
