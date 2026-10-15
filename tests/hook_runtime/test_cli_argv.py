"""The one ``dispatch`` argv and the ``playbook-hook`` entry (specs/prK-lifecycle-hooks.md §D.1, D-14, K-7).

The §C.2.1 launcher command and the §C.3.2 shim spawn are parsed exactly as
rendered (K3/K4 add the cross-checks against their templates). ``dispatch``
never exits 2: every argv problem goes to the failure policy.
"""

from __future__ import annotations

import io
import json
import re
import shlex
import sys
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.hook_registrations import OPENCODE_REG_EVENTS
from coding_agent_playbook.hook_registrations._templates import shim_template
from coding_agent_playbook.hook_runtime.cli import DispatchArgs, main, parse_dispatch_argv
from coding_agent_playbook.hook_runtime.event import EventName, Harness
from coding_agent_playbook.hook_runtime.harness import DENY_EXIT
from tests.hook_runtime.guard_repo import GuardRepo, streams
from tests.import_probe import probe_env

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.proc import SubprocessProc

#: The §C.2.1 registration command, verbatim (strict mode adds --strict-launch).
CLAUDE_COMMAND = (
    'sh "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}'
    '/.claude/hooks/playbook/launch.sh" {strict}dispatch pre_tool_use --harness claude_code'
)
#: The §C.3.2 shim's spawn argv after the pin: ``-I -m <module> dispatch ...``.
SHIM_ARGV = [
    "-I",
    "-m",
    "coding_agent_playbook.hook_runtime",
    "dispatch",
    "post_tool_use",
    "--harness",
    "opencode",
    "--project-dir",
    "/work/proj",
]


def _launcher_args(command: str) -> list[str]:
    """What the launcher passes on: ``"$@"`` after ``sh launch.sh`` and its ``--strict-launch`` shift."""
    words = shlex.split(command)
    assert words[0] == "sh" and words[1].endswith("/.claude/hooks/playbook/launch.sh")
    rest = words[2:]
    return rest[1:] if rest[:1] == ["--strict-launch"] else rest


@pytest.mark.parametrize("strict", ["", "--strict-launch "])
def test_parses_claude_launcher_argv(strict: str) -> None:
    args = _launcher_args(CLAUDE_COMMAND.replace("{strict}", strict))

    assert args[0] == "dispatch"
    assert parse_dispatch_argv(args[1:]) == DispatchArgs(
        EventName.PRE_TOOL_USE, Harness.CLAUDE_CODE, None, None
    )


def test_parses_opencode_shim_argv_with_project_dir() -> None:
    assert SHIM_ARGV[:3] == ["-I", "-m", "coding_agent_playbook.hook_runtime"]

    parsed = parse_dispatch_argv(SHIM_ARGV[4:])

    assert parsed == DispatchArgs(EventName.POST_TOOL_USE, Harness.OPENCODE, "/work/proj", None)


def _shim_spawn_argv(event: str, root: str) -> list[str]:
    """The argv array the packaged shim template passes to ``spawn`` after the pin.

    The template's literal is read as written: quoted strings stay, the
    ``event`` and ``ROOT`` identifiers take the given values.
    """
    match = re.search(r"spawn\(py, \[(.*?)\]", shim_template("opencode-plugin.js"), re.DOTALL)
    assert match is not None, "no spawn(py, [...]) call in the shim template"
    values = {"event": event, "ROOT": root}
    words = [word.strip() for word in match.group(1).split(",")]
    return [word[1:-1] if word.startswith('"') else values[word] for word in words]


@pytest.mark.parametrize("event", OPENCODE_REG_EVENTS)
def test_shim_spawn_argv_parses_with_hook_runtime_cli(event: str) -> None:
    argv = _shim_spawn_argv(event, "/work/proj")

    assert _shim_spawn_argv("post_tool_use", "/work/proj") == SHIM_ARGV
    assert argv[:4] == ["-I", "-m", "coding_agent_playbook.hook_runtime", "dispatch"]
    assert parse_dispatch_argv(argv[4:]) == DispatchArgs(
        EventName(event), Harness.OPENCODE, "/work/proj", None
    )


@pytest.mark.parametrize(
    ("argv", "problem"),
    [
        (
            ["pre_tool_use", "--harness", "claude_code", "--config", "x"],
            "unexpected argument '--config'",
        ),
        (["pre_tool_use"], "missing --harness"),
        (["pre_tool_use", "--harness", "cursor"], "unknown harness 'cursor'"),
        (["pre_tool_use", "--harness", "claude_code", "extra"], "unexpected argument 'extra'"),
        (["pre_tool_use", "--harness"], "--harness needs a value"),
        (
            ["pre_tool_use", "--harness", "opencode", "--harness", "opencode"],
            "--harness given twice",
        ),
    ],
)
def test_bad_dispatch_argv_is_a_problem_not_an_error(argv: list[str], problem: str) -> None:
    parsed = parse_dispatch_argv(argv)

    assert parsed.event is EventName.PRE_TOOL_USE
    assert problem in (parsed.problem or "")


@pytest.mark.parametrize(
    "argv",
    [
        [],
        ["--harness", "claude_code"],
        ["PreToolUse", "--harness", "claude_code"],
        ["pre_tool_use", "--harness", "claude_code", "--strict-launch"],
        ["pre_tool_use", "--harness", "nope"],
        ["pre_tool_use"],
        ["pre_tool_use", "--harness", "claude_code", "trailing"],
    ],
)
def test_bad_dispatch_argv_never_exits_2(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps], argv: list[str]
) -> None:
    repo = GuardRepo.create(tmp_path)
    repo.install()
    out, err = streams()
    deps = runtime_deps(env=repo.env(), out=out, err=err)
    payload = repo.payload(EventName.PRE_TOOL_USE, tool="Bash")

    code = main(["dispatch", *argv], deps=deps, stdin=io.BytesIO(payload))

    assert code in (0, DENY_EXIT)
    if parse_dispatch_argv(argv).event is not None:  # a known event with a bad argv: it asks
        assert json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"] == "ask"


def test_unattended_argv_fault_denies_with_the_deny_exit(
    tmp_path: Path, runtime_deps: Callable[..., RuntimeDeps]
) -> None:
    repo = GuardRepo.create(tmp_path)
    repo.install()
    deps = runtime_deps(env=repo.env(CI="true"))
    payload = repo.payload(EventName.PRE_TOOL_USE, tool="Bash")

    code = main(
        ["dispatch", "pre_tool_use", "--harness", "claude_code", "--x"],
        deps=deps,
        stdin=io.BytesIO(payload),
    )

    assert code == DENY_EXIT


def test_project_dir_defaults_to_claude_project_dir_then_cwd() -> None:
    explicit = parse_dispatch_argv(["stop", "--harness", "opencode", "--project-dir", "/p"])
    implicit = parse_dispatch_argv(["stop", "--harness", "claude_code"])

    assert explicit.project_root({"CLAUDE_PROJECT_DIR": "/env"}, "/cwd") == "/p"
    assert implicit.project_root({"CLAUDE_PROJECT_DIR": "/env"}, "/cwd") == "/env"
    assert implicit.project_root({}, "/cwd") == "/cwd"


def test_version_prints_the_engine_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--version"]) == 0

    assert capsys.readouterr().out.startswith("playbook-hook ")


@pytest.mark.parametrize(("argv", "code"), [([], 2), (["frobnicate"], 2), (["--help"], 0)])
def test_unknown_subcommand_prints_usage(
    argv: list[str], code: int, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(argv) == code

    assert "usage: playbook-hook dispatch" in capsys.readouterr().err


def test_module_entry_keeps_stdout_one_json_object(
    tmp_path: Path, real_proc: SubprocessProc
) -> None:
    """The real ``-I -m`` launch: fd 1 is the rendered output only, stray prints go to stderr."""
    repo = GuardRepo.create(tmp_path)  # no guard_config.json: the ConfigFault ask
    payload = repo.payload(EventName.PRE_TOOL_USE, tool="Bash")
    env = {**probe_env(), "CLAUDE_PROJECT_DIR": str(repo.root)}
    argv = [
        sys.executable,
        "-I",
        "-m",
        "coding_agent_playbook.hook_runtime",
        "dispatch",
        "pre_tool_use",
        "--harness",
        "claude_code",
    ]

    result = real_proc.run(argv, timeout=60, env=env, input=payload, cwd=str(repo.root))

    assert result.returncode == 0, result.stderr
    body = json.loads(result.stdout)
    assert body["hookSpecificOutput"]["permissionDecision"] == "ask"
