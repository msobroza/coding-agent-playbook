"""The shell-guard argv0 prefilter (specs/prK-hook-pack.md §E.4).

A guard declaring ``argv0s`` is not called on a shell command none of whose
segments runs one of them; a config key's row tables add their own ``argv0``.
A command the parser could not follow, PowerShell and non-shell calls always
reach the guard. The spy handler below is a real registered builtin, resolved
through ``FakeHandlerResolver``, and dispatched in process.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.hook_runtime._prefilter import argv0_matches, command_argv0s
from coding_agent_playbook.hook_runtime.dispatch.decision import Decision, HandlerResult
from coding_agent_playbook.hook_runtime.registry import register_hook_handler
from coding_agent_playbook.hook_runtime.shell.parse import parse_shell
from tests.hook_runtime.dispatch_kit import PRE, body, dispatch
from tests.hook_runtime.guard_repo import hook_record

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.dispatch.event import CanonicalEvent
    from coding_agent_playbook.hook_runtime.registry import HandlerContext
    from tests.hook_runtime.fakes import FakeHandlerResolver
    from tests.hook_runtime.guard_repo import GuardRepo

SPY_CALLS: list[str] = []
ROWS: Final = [{"argv0": "kubectl", "regex": "delete", "decision": "deny"}]


@register_hook_handler(
    "k8_prefilter_spy",
    events=["pre_tool_use"],
    decisions=["deny", "none"],
    argv0s=("git", "mkfs*"),
    argv0_rows="extra_rows",
)
def _spy(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult:
    SPY_CALLS.append(ev.tool.name if ev.tool is not None else "")
    ctx.proc.run(["git", "status"], timeout=2.0)  # FakeProc: any unscripted spawn fails loudly
    return HandlerResult(decision=Decision.DENY, hook_id=ctx.hook.id, reason="spy")


@pytest.fixture
def spied(
    repo: GuardRepo, resolver: FakeHandlerResolver, make_deps: Callable[..., RuntimeDeps]
) -> Callable[[str, str], tuple[bool, Any]]:
    """Run one tool call against the spy guard; returns (spy called, proc calls)."""
    repo.install(
        hook_record(
            "guard-a",
            decisions=("deny", "none"),
            handler={"kind": "builtin", "name": "k8_prefilter_spy", "config": {"extra_rows": ROWS}},
        )
    )
    resolver.handlers["guard-a"] = _spy

    def run(tool: str, command: str) -> tuple[bool, Any]:
        SPY_CALLS.clear()
        deps = make_deps()
        deps.proc.script(["git", "status"])  # type: ignore[attr-defined]
        wire = dispatch(deps, repo, PRE, tool=None, tool_name=tool, tool_input={"command": command})
        return bool(SPY_CALLS), (body(wire), deps.proc.calls)  # type: ignore[attr-defined]

    return run


def test_no_guard_code_runs_without_matching_argv0(
    spied: Callable[[str, str], tuple[bool, Any]],
) -> None:
    called, (rendered, proc_calls) = spied("Bash", "ls -la && echo git push")

    assert called is False
    assert rendered == {}
    assert proc_calls == []


@pytest.mark.parametrize(
    ("tool", "command"),
    [
        ("Bash", "cd sub && git status"),
        ("Bash", "sudo mkfs.ext4 /dev/sdb1"),
        ("Bash", "kubectl delete ns prod"),  # an overlay row's argv0
        ("Bash", "echo 'unterminated"),  # unparsed: the guard takes its raw branch
        ("PowerShell", "Remove-Item -Recurse x"),  # never shlex-parsed
    ],
)
def test_matching_or_unreadable_commands_reach_the_guard(
    spied: Callable[[str, str], tuple[bool, Any]], tool: str, command: str
) -> None:
    called, _ = spied(tool, command)

    assert called is True


def test_prefix_rows_match_mkfs_ext4() -> None:
    assert argv0_matches(["mkfs.ext4"], ["mkfs*"]) is True
    assert argv0_matches(["mkfs"], ["mkfs*"]) is True
    assert argv0_matches(["mk"], ["mkfs*"]) is False
    assert argv0_matches(["git"], ["gi"]) is False


def test_command_argv0s_unwraps_and_trusts_only_parsed_posix() -> None:
    parsed = parse_shell("FOO=1 sudo /usr/bin/rm -rf x | bash -c 'git push'", "posix", "/r")

    assert command_argv0s(parsed) == frozenset({"rm", "bash", "git"})
    assert command_argv0s(parse_shell("echo 'open", "posix", "/r")) is None
    assert command_argv0s(parse_shell("rm x", "powershell", "/r")) is None
