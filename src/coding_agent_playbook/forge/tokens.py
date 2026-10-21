"""The forge CLI commands that print a forge's token, which the guards block (specs/prF-forge-adapter.md §14, Q64).

``gh``, ``glab`` and ``playbook forge`` use the forge CLIs' own login, so no
command needs a token's value, and one printed into the transcript has left the
machine. Each :class:`~coding_agent_playbook.forge.dialects.Forge` carries its
rows (``token_printers``) beside the env vars that hold its token
(``token_env``). Rows checked against the gh 2.94.0 and glab 1.115.0 sources:
the commands the spec names, the CLIs' credential helpers (hidden, but they
print the stored token) and ``config get`` of every token key and alias.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from coding_agent_playbook.forge.dialects import CommandPath

__all__ = ["GITHUB_TOKEN_PRINTERS", "GITLAB_TOKEN_PRINTERS", "TokenPrinter"]

_NONE: Final[frozenset[str]] = frozenset()


@dataclass(frozen=True, slots=True)
class TokenPrinter:
    """A forge CLI command that prints the forge's token.

    It prints one always (``gh auth token``), when given one of ``flags``
    (``glab auth status --show-token``, unless ``=false``), or when its first
    operand is one of ``operands``, in any case (``glab config get token``).
    ``values`` are its value-taking flags, so a flag's value is never read as
    that operand.

    Example: ``TokenPrinter(("config", "get"), operands=frozenset({"token"}))``.
    """

    path: CommandPath
    flags: frozenset[str] = _NONE
    operands: frozenset[str] = _NONE
    values: frozenset[str] = _NONE


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


#: ``git-credential get`` prints ``password=<token>`` to git, its caller.
_GET: Final = _words("get")

GITHUB_TOKEN_PRINTERS: Final = (
    TokenPrinter(("auth", "token"), values=_words("-h --hostname -u --user")),
    TokenPrinter(
        ("auth", "status"),
        flags=_words("-t --show-token"),
        values=_words("-h --hostname --json --jq --template"),
    ),
    TokenPrinter(("auth", "git-credential"), operands=_GET),
    # gh's -h is --host here; the token comes from the env, hosts.yml or the keyring
    TokenPrinter(("config", "get"), operands=_words("oauth_token"), values=_words("-h --host")),
)

GITLAB_TOKEN_PRINTERS: Final = (
    TokenPrinter(("auth", "status"), flags=_words("-t --show-token"), values=_words("--hostname")),
    TokenPrinter(("auth", "git-credential"), operands=_GET),
    TokenPrinter(("auth", "credential-helper"), values=_words("-R --repo")),  # JSON, the token
    TokenPrinter(("auth", "docker-helper"), operands=_GET),  # its "Secret"
    TokenPrinter(
        ("config", "get"),  # the env vars first, then the keyring and the config files
        operands=_words("token gitlab_token oauth_token job_token oauth2_refresh_token")
        | _words("refresh_token"),
        values=_words("--host"),  # glab's -h is help
    ),
)
