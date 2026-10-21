"""Which command wrapper prefixes may be declared (specs/prK-lifecycle-hooks.md §B.1, §D.2.5, §D.7).

A developer who runs commands through a launcher of their own (a token-saving
``proxy``, ``proxy run``) declares it so the shell guards and verify-run
tagging judge the command it launches: ``[hooks] wrapper_prefixes`` (committed)
or ``PLAYBOOK_HOOK_WRAPPER_PREFIXES`` (per developer, hook-process env only).

A declared prefix is stripped before any guard sees a segment, so declaring a
command the guards inspect would hide it: with ``git`` declared, ``git push
--force`` reaches every guard as ``push --force``. :func:`hidden_program`
therefore refuses a prefix any of whose tokens names:

- a program a guard reads by name (``_GUARDED``; a test keeps it a superset of
  every builtin handler's ``argv0s`` and of the guards' own program tables);
- a built-in launcher, a runner (``uv``, ``poetry``, ...) or a shell, which the
  parser already unwraps *with their options*: stripped bare, ``sudo -u root
  rm`` would become ``-u root rm``.

validate refuses such a ``[hooks] wrapper_prefixes`` entry (H21); the
dispatcher ignores such an env entry, logs it and ``playbook-hook doctor`` warns.
"""

from __future__ import annotations

import dataclasses
import posixpath
import re
from dataclasses import dataclass
from functools import cache
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig

__all__ = [
    "WrapperDeclaration",
    "declare_wrappers",
    "hidden_program",
    "parse_wrapper_prefixes",
    "with_wrapper_prefixes",
]

#: Programs a guard inspects by name, beyond the launchers, runners and shells.
_GUARDED: Final = frozenset(
    {
        # git and its forges' CLIs: the git guards, exfil, commit convention, pre-commit bypass
        *("git", "gh", "glab", "pre-commit", "cz", "export"),
        # destructive-command-guard and the file writers the sink scans read
        *("rm", "rmdir", "find", "rsync", "chmod", "chown", "dd", "shred", "truncate"),
        *("mv", "cp", "ln", "install", "tee", "touch", "patch", ":"),
        # network clients: exfil-channel-guard, network-egress-guard
        *("curl", "wget", "http", "https", "xh", "httpie", "ssh", "scp", "sftp", "ftp"),
        *("telnet", "nc", "ncat", "netcat", "socat"),
        # package managers: the dependency guards, resync-on-detector-input-change
        *("pip", "pip3", "pipx", "conda", "mamba", "micromamba", "npm", "npx", "yarn", "pnpm"),
        # readers the secret and data guards inspect
        *("cat", "head", "tail", "less", "more", "sed", "awk", "gawk", "cut", "grep"),
        *("base64", "xxd", "od", "strings", "sqlite3", "duckdb"),
        # interpreters and code runners
        *("perl", "ruby", "node", "deno", "bun", "php", "eval", "source", "."),
        # containers and the control plane
        *("docker", "podman", "kubectl", "playbook", "coding-agent-playbook"),
        *("script", "expect", "unbuffer", "claude", "opencode"),
    }
)
#: Versioned interpreters (``python3.12``, ``pip3.13``) and every ``mkfs.<type>``.
_VERSIONED: Final = re.compile(r"(?:python|pip|perl|ruby)[\d.]*|mkfs.*")


@dataclass(frozen=True, slots=True)
class WrapperDeclaration:
    """A parsed ``PLAYBOOK_HOOK_WRAPPER_PREFIXES``: the prefixes kept and those refused.

    Example::

        >>> declare_wrappers("proxy,git")
        WrapperDeclaration(accepted=('proxy',), rejected=('git',))
    """

    accepted: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()


def parse_wrapper_prefixes(value: str) -> tuple[str, ...]:
    """The comma-separated prefixes of ``value``, spaces normalized, empties and repeats dropped.

    Example::

        >>> parse_wrapper_prefixes(" proxy ,proxy   run,, proxy")
        ('proxy', 'proxy run')
    """
    prefixes = (" ".join(part.split()) for part in value.split(","))
    return tuple(dict.fromkeys(prefix for prefix in prefixes if prefix))


def hidden_program(prefix: str) -> str | None:
    """The guarded command the first such token of ``prefix`` names (its basename), else ``None``.

    Tokens are compared by basename, as the parser matches a prefix, so
    ``/usr/bin/git`` hides ``git`` too.

    Example::

        >>> hidden_program("proxy run"), hidden_program("proxy /usr/bin/git")
        (None, 'git')
    """
    for token in prefix.split():
        name = posixpath.basename(token)
        if _is_guarded(name):
            return name
    return None


def declare_wrappers(value: str) -> WrapperDeclaration:
    """Split ``value`` (the env var) into the prefixes to strip and those that would hide a guard.

    Example::

        >>> declare_wrappers("proxy, proxy run, sudo").rejected
        ('sudo',)
    """
    prefixes = parse_wrapper_prefixes(value)
    return WrapperDeclaration(
        accepted=tuple(p for p in prefixes if hidden_program(p) is None),
        rejected=tuple(p for p in prefixes if hidden_program(p) is not None),
    )


def with_wrapper_prefixes(cfg: GuardConfig, prefixes: Sequence[str]) -> GuardConfig:
    """``cfg`` whose ``shell.wrapper_prefixes`` also strip ``prefixes`` (``cfg`` itself if none).

    Example::

        >>> with_wrapper_prefixes(cfg, ("proxy",)).shell.wrapper_prefixes  # doctest: +SKIP
        ('proxy',)
    """
    merged = tuple(dict.fromkeys((*cfg.shell.wrapper_prefixes, *prefixes)))
    if merged == cfg.shell.wrapper_prefixes:
        return cfg
    shell = dataclasses.replace(cfg.shell, wrapper_prefixes=merged)
    return dataclasses.replace(cfg, shell=shell)


def _is_guarded(name: str) -> bool:
    bare = name.removesuffix(".exe")
    return bare in _guarded_names() or _VERSIONED.fullmatch(bare) is not None


@cache
def _guarded_names() -> frozenset[str]:
    """``_GUARDED`` plus the parser's own launchers, runners and shells (loaded on first use)."""
    from coding_agent_playbook.hook_runtime.shell.wrappers import (
        DEFAULT_RUNNER_WRAPPERS,
        LAUNCHER_NAMES,
        SHELL_NAMES,
    )

    runners = {runner.split()[0] for runner in DEFAULT_RUNNER_WRAPPERS}
    return _GUARDED | LAUNCHER_NAMES | SHELL_NAMES | runners | {"fish", "csh", "tcsh"}
