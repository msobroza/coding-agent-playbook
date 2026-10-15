"""Git argv parsing shared by the git guards (specs/prK-lifecycle-hooks.md §D.1, §E.4).

``parse_git`` reads a parsed shell ``Segment``, so wrappers (``proxy``, ``sudo``,
``env``) are already gone and env prefixes are already split out.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.hook_runtime.gitargv import (
    GitInvocation,
    Uninspectable,
    commit_message_sources,
    parse_git,
)
from coding_agent_playbook.hook_runtime.shell import ShellConfig, parse_shell

if TYPE_CHECKING:
    from pathlib import Path

_PROXY = ShellConfig(wrapper_prefixes=("proxy",))


def _git(text: str, *, cwd: str | None = "/r") -> GitInvocation | None:
    return parse_git(parse_shell(text, "posix", cwd, _PROXY).segments[-1])


def _parsed(text: str, *, cwd: str | None = "/r") -> GitInvocation:
    invocation = _git(text, cwd=cwd)
    assert invocation is not None
    return invocation


def test_parse_git_dash_C_and_dash_c() -> None:
    invocation = _parsed(
        "git -C sub -C ../other -c core.hooksPath=/dev/null -c commit.gpgSign -c x.y= commit -m msg"
    )

    assert invocation.subcommand == "commit"
    assert invocation.args == ("-m", "msg")
    assert invocation.cwd == "/r/other"
    assert invocation.config == (
        ("core.hooksPath", "/dev/null"),
        ("commit.gpgSign", "true"),
        ("x.y", ""),
    )
    assert invocation.config_value("CORE.HOOKSPATH") == "/dev/null"
    assert invocation.config_value("user.name") is None


def test_parse_git_reads_git_config_count_key_value_env() -> None:
    invocation = _parsed(
        "GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/dev/null "
        "GIT_CONFIG_KEY_1=commit.gpgSign GIT_CONFIG_VALUE_1=false "
        "git -c core.hooksPath=cli commit"
    )

    assert invocation.config == (
        ("core.hooksPath", "/dev/null"),
        ("commit.gpgSign", "false"),
        ("core.hooksPath", "cli"),
    )
    assert invocation.config_value("core.hookspath") == "cli"


@pytest.mark.parametrize(
    "env",
    [
        "GIT_CONFIG_COUNT=x GIT_CONFIG_KEY_0=a.b GIT_CONFIG_VALUE_0=1",
        "GIT_CONFIG_COUNT=2 GIT_CONFIG_KEY_1=a.b GIT_CONFIG_VALUE_1=1",
        "GIT_CONFIG_KEY_0=a.b GIT_CONFIG_VALUE_0=1",
    ],
    ids=["non-numeric-count", "missing-key-0", "no-count"],
)
def test_malformed_git_config_env_contributes_nothing(env: str) -> None:
    assert _parsed(f"{env} git status").config == ()


def test_git_config_env_through_the_env_wrapper() -> None:
    invocation = _parsed(
        "env GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=x git push"
    )

    assert invocation.config == (("core.hooksPath", "x"),)


def test_non_git_segment_returns_none() -> None:
    assert _git("ls -la") is None
    assert _git("echo git commit --no-verify") is None
    assert _git("gitk --all") is None
    assert _git('"$GIT" push') is None


def test_wrappers_and_paths_still_reach_git() -> None:
    assert _parsed("proxy git push --force").subcommand == "push"
    assert _parsed("sudo /usr/bin/git status").subcommand == "status"
    assert _parsed("git.exe status").subcommand == "status"


def test_global_options_are_kept_and_the_subcommand_found() -> None:
    invocation = _parsed(
        "git --no-pager -P --git-dir=.bare --work-tree w --namespace ns "
        "--config-env=core.hooksPath=HP --literal-pathspecs log -1"
    )

    assert invocation.subcommand == "log"
    assert invocation.args == ("-1",)
    assert (invocation.git_dir, invocation.work_tree) == (".bare", "w")
    assert invocation.config == (("core.hooksPath", "$HP"),)
    assert invocation.global_args[:2] == ("--no-pager", "-P")


def test_git_dir_and_work_tree_fall_back_to_env() -> None:
    invocation = _parsed("GIT_DIR=/x/.git GIT_WORK_TREE=/x git status")

    assert (invocation.git_dir, invocation.work_tree) == ("/x/.git", "/x")


@pytest.mark.parametrize(
    ("text", "cwd", "expected"),
    [
        ("git -C /abs status", "/r", "/abs"),
        ("git -C '' status", "/r", "/r"),
        ('git -C "$D" status', "/r", None),
        ("git -C sub status", None, None),
        ("cd sub && git status", "/r", "/r/sub"),
    ],
)
def test_dash_C_folds_into_the_segment_cwd(
    text: str, cwd: str | None, expected: str | None
) -> None:
    assert _parsed(text, cwd=cwd).cwd == expected


@pytest.mark.parametrize(
    ("text", "subcommand", "global_args"),
    [
        ("git", None, ()),
        ("git --version", None, ("--version",)),
        ("git -c", None, ("-c",)),
    ],
)
def test_git_without_a_subcommand(
    text: str, subcommand: str | None, global_args: tuple[str, ...]
) -> None:
    invocation = _parsed(text)

    assert (invocation.subcommand, invocation.args, invocation.global_args) == (
        subcommand,
        (),
        global_args,
    )


_HEREDOC_M = "git commit -m \"$(cat <<'EOF'\nfeat: x\n\nRefs: AB-1\nEOF\n)\""


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("git commit -m a -m b", ["a\n\nb"]),
        ("git commit -am 'fix -n handling'", ["fix -n handling"]),
        ("git commit --message=one --message two", ["one\n\ntwo"]),
        (_HEREDOC_M, ["feat: x\n\nRefs: AB-1"]),
        ("git commit -F - <<EOF\nfeat: y\nEOF\n", ["feat: y\n"]),
        ("git commit -F msg.txt", ["feat: from file\n"]),
        ("git commit -F sub/../msg.txt", ["feat: from file\n"]),
        ("git commit -F /etc/hostname", "outside the worktree"),
        ("git commit -F <(printf x)", "process substitution"),
        ("git commit -m \"$(printf 'feat: x')\"", "command substitution"),
        ("git commit", "an editor composes"),
        ("git commit --amend --no-edit", "reused"),
        ("git commit -C HEAD", "reused"),
    ],
)
def test_commit_message_sources(tmp_path: Path, text: str, expected: list[str] | str) -> None:
    (tmp_path / "msg.txt").write_text("feat: from file\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    invocation = _parsed(text, cwd=str(tmp_path))

    found = commit_message_sources(invocation, root=str(tmp_path))

    if isinstance(expected, list):
        assert found == expected
    else:
        assert isinstance(found, Uninspectable)
        assert expected in found.why


def test_echo_git_commit_is_not_a_git_invocation() -> None:
    assert _git("echo git commit --author=x -m y") is None
