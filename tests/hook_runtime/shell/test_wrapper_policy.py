"""Which wrapper prefixes may be declared (specs/prK-lifecycle-hooks.md §B.1, §D.2.5, §D.7).

A declared wrapper is stripped before every shell guard judges a segment, so a
declaration naming a command the guards inspect would hide that command from
them. ``hidden_program`` is the one rule validate (H21) and the dispatcher
(``PLAYBOOK_HOOK_WRAPPER_PREFIXES``) share; the coverage test keeps its program
list a superset of what the guards declare or read by name.
"""

from __future__ import annotations

import importlib

import pytest

from coding_agent_playbook.hook_runtime.handlers._data_reads import READER_ARGV0S
from coding_agent_playbook.hook_runtime.handlers._destructive_paths import (
    INTERPRETERS,
    PATH_ARGV0S,
)
from coding_agent_playbook.hook_runtime.handlers._egress import EGRESS_ARGV0S
from coding_agent_playbook.hook_runtime.judges.install_commands import _READERS
from coding_agent_playbook.hook_runtime.registry import (
    builtin_handler_modules,
    registered_handlers,
)
from coding_agent_playbook.hook_runtime.shell.parse import ShellConfig, parse_shell
from coding_agent_playbook.hook_runtime.shell.wrapper_policy import (
    WrapperDeclaration,
    declare_wrappers,
    hidden_program,
    parse_wrapper_prefixes,
)


@pytest.mark.parametrize(
    ("prefix", "hidden"),
    [
        ("proxy", None),
        ("proxy run", None),
        ("token-saver exec-wrapped", None),
        ("git", "git"),
        ("/usr/bin/git", "git"),
        ("git.exe", "git.exe"),
        ("proxy git", "git"),  # a later token hides a command just as well
        ("sudo", "sudo"),  # stripped bare, `sudo -u root rm` would become `-u root rm`
        ("uv run", "uv"),
        ("python3.12", "python3.12"),
        ("mkfs.ext4", "mkfs.ext4"),
        ("bash", "bash"),
        ("rm", "rm"),
        ("curl", "curl"),
        ("tee", "tee"),
        ("", None),
    ],
)
def test_hidden_program_names_the_guarded_token(prefix: str, hidden: str | None) -> None:
    assert hidden_program(prefix) == hidden


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("proxy", ("proxy",)),
        ("proxy,proxy run", ("proxy", "proxy run")),
        (" proxy ,  proxy   run ,, proxy ", ("proxy", "proxy run")),
        (" , ", ()),
        ("", ()),
    ],
)
def test_parse_wrapper_prefixes_splits_commas_and_normalizes_spaces(
    value: str, expected: tuple[str, ...]
) -> None:
    assert parse_wrapper_prefixes(value) == expected


def test_declare_wrappers_rejects_each_entry_that_would_hide_a_guarded_command() -> None:
    declared = declare_wrappers("proxy, git ,proxy run,sudo")

    assert declared == WrapperDeclaration(accepted=("proxy", "proxy run"), rejected=("git", "sudo"))


def _declared_argv0s() -> set[str]:
    """Every argv0 a builtin handler's prefilter declares (``mkfs*`` read as ``mkfs.x``)."""
    for module in builtin_handler_modules().values():
        importlib.import_module(module)
    names: set[str] = set()
    for declaration in registered_handlers().values():
        names.update(declaration.argv0s or ())
    return {name.replace("*", ".x") for name in names}


def _read_by_name() -> set[str]:
    """Programs guards read by name without a prefilter declaration."""
    return {
        *READER_ARGV0S,
        *INTERPRETERS,
        *(name.replace("*", ".x") for name in PATH_ARGV0S),
        *EGRESS_ARGV0S,
        *_READERS,
        "pip",
        "pip3",
        "pre-commit",
        "export",
    }


def test_every_program_a_guard_inspects_is_guarded() -> None:
    names = _declared_argv0s() | _read_by_name()

    assert names, "the registry declared no argv0 at all: the coverage check is vacuous"
    assert [name for name in sorted(names) if hidden_program(name) != name] == []


@pytest.mark.parametrize("launcher", ["env", "sudo", "doas", "command", "exec", "nohup", "time"])
def test_every_builtin_launcher_and_runner_is_guarded(launcher: str) -> None:
    for name in (launcher, "nice", "ionice", "stdbuf", "timeout", "xargs", "uvx", "poetry"):
        assert hidden_program(name) == name


def test_an_accepted_wrapper_never_hides_a_guarded_segment() -> None:
    """What the rule protects: unwrapping an accepted prefix leaves the guarded argv0 visible."""
    accepted = declare_wrappers("proxy,proxy run").accepted
    command = parse_shell("proxy run git push --force", "posix", "/r", ShellConfig(accepted))

    assert command.segments[0].argv[0] == "git"
