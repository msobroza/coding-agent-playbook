"""The forge CLI process ``playbook forge`` runs: found, version-checked, told its host (spec prF §5.3, §6).

:func:`open_cli` finds the forge's CLI on ``PATH``, checks its ``--version``
against the minimum once per call (Q38), and, for ``glab``, that no
``GITLAB_API_HOST`` or ``glab`` ``api_host`` setting points it at another host
than the push remote's API host (Q55). :meth:`ForgeCli.run` then runs it in
the work tree with the child environment of §5.3: ``GH_HOST=<api host>`` or
``GITLAB_HOST=https://<api host>`` (Q60) and the prompt, update-notifier and
telemetry switches off. A body goes on stdin, never on argv. A failed call
stops with its stderr passed through unchanged (exit 1), or exit 2 with the
login step when the CLI reports no login. The engine never reads a token.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.commands._forge_stop import (
    MINIMUM_VERSIONS,
    ForgeStop,
    host_mismatch,
    logged_out,
    missing_cli,
    old_cli,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.commands._forge_repo import ForgeRemote
    from coding_agent_playbook.forge.dialects import Forge

__all__ = ["Done", "ForgeCli", "child_env", "json_pages", "open_cli"]

#: The variables every forge CLI call gets, whichever the forge (Q55).
_QUIET: Final = {
    "GH_PROMPT_DISABLED": "1",
    "GLAB_NO_PROMPT": "true",
    "GH_NO_UPDATE_NOTIFIER": "1",
    "GH_NO_EXTENSION_UPDATE_NOTIFIER": "1",
    "GH_TELEMETRY": "false",
    "DO_NOT_TRACK": "1",
    "GLAB_CHECK_UPDATE": "false",
    "GLAB_SEND_TELEMETRY": "false",
}
#: Caller variables the CLI must not see (:func:`child_env`).
_DROPPED: Final = frozenset({"NO_PROMPT", "GH_REPO", "GITLAB_REPO"})
_VERSION: Final = re.compile(r"(\d+)\.(\d+)\.(\d+)")
#: ``--version`` and ``glab config get`` read local files only.
_LOCAL_TIMEOUT_S: Final = 30
#: A forge call may page through a long list or check out a large branch.
_CALL_TIMEOUT_S: Final = 600
#: ``gh`` exits 4 when a command needs a login it lacks.
_GH_AUTH_EXIT: Final = 4
#: What ``glab`` prints when it has no usable login for the host.
_GLAB_LOGGED_OUT: Final = re.compile(
    r"401 Unauthorized|glab auth login|not authenticated|no token found|has not been authenticated",
    re.IGNORECASE,
)
_SCHEME: Final = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")


@dataclass(frozen=True)
class Done:
    """One finished forge CLI call: its exit code, stdout and stderr."""

    code: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ForgeCli:
    """The push remote's forge CLI, ready to run: its executable, child environment and work tree."""

    forge: Forge
    executable: str
    env: Mapping[str, str]
    cwd: Path
    #: The host the CLI talks to (``which``'s ``api_host``): hints name it.
    host: str
    #: The caller's environment, for the Domino-aware hints.
    caller_env: Mapping[str, str]

    def run(
        self,
        argv: Sequence[str],
        *,
        body: str | None = None,
        check: bool = True,
        timeout_s: float = _CALL_TIMEOUT_S,
    ) -> Done:
        """Run the CLI with ``argv`` (after argv0), ``body`` on stdin.

        With ``check``, a failure stops ``playbook forge``: exit 2 with the login
        step when the CLI has no login, else exit 1 with its stderr passed through.

        Example: ``cli.run(["issue", "view", "3", "--json", "number"])``.
        """
        try:
            done = subprocess.run(
                [self.executable, *argv],
                input=body if body is not None else "",
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=self.cwd,
                env=dict(self.env),
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise ForgeStop(1, f"`{self.forge.cli}` timed out after {timeout_s:g} s") from None
        except OSError as error:
            raise ForgeStop(1, f"cannot run `{self.forge.cli}`: {error}") from None
        result = Done(done.returncode, done.stdout, done.stderr)
        if check and result.code != 0:
            raise self.failure(result)
        return result

    def json(self, argv: Sequence[str], *, body: str | None = None) -> Any:
        """Run the CLI and decode its JSON stdout (exit 1 when it prints none)."""
        done = self.run(argv, body=body)
        try:
            return json.loads(done.stdout)
        except json.JSONDecodeError:
            raise self._no_json(argv) from None

    def pages(self, done: Done, argv: Sequence[str]) -> list[Any]:
        """The JSON values ``done`` printed, page after page (``--paginate`` prints several).

        A page that is a list is flattened into the result; output that is not
        JSON exits 1.
        """
        try:
            return json_pages(done.stdout)
        except json.JSONDecodeError:
            raise self._no_json(argv) from None

    def _no_json(self, argv: Sequence[str]) -> ForgeStop:
        return ForgeStop(1, f"`{self.forge.cli} {' '.join(argv[:2])}` printed no JSON")

    def failure(self, done: Done) -> ForgeStop:
        """The stop for the failed call ``done``: exit 2 when logged out, else exit 1."""
        if self.logged_out(done):
            stop = logged_out(self.forge, self.host, self.caller_env)
            return ForgeStop(2, stop.message, passthrough=done.stderr)
        message = "" if done.stderr.strip() else f"`{self.forge.cli}` exited {done.code}"
        return ForgeStop(1, message, passthrough=done.stderr)

    def logged_out(self, done: Done) -> bool:
        """Whether the failed call ``done`` failed for want of a login."""
        if self.forge.cli == "gh":
            return done.code == _GH_AUTH_EXIT
        return bool(_GLAB_LOGGED_OUT.search(done.stderr))


def json_pages(text: str) -> list[Any]:
    """Every JSON value in ``text``, one page after another; a list page is flattened.

    Example::

        >>> json_pages('[1, 2]\\n[3]')
        [1, 2, 3]
    """
    decoder = json.JSONDecoder()
    values: list[Any] = []
    index = 0
    while True:
        while index < len(text) and text[index].isspace():
            index += 1
        if index >= len(text):
            return values
        value, index = decoder.raw_decode(text, index)
        values.extend(value if isinstance(value, list) else [value])


def child_env(remote: ForgeRemote, env: Mapping[str, str]) -> dict[str, str]:
    """The forge CLI's environment: ``env`` plus its host and the quiet switches (§5.3).

    ``glab`` takes its host from the remote whenever it runs in a repository, so
    a ``[forge]`` ``api_host`` that differs from the remote's host also goes in
    ``GITLAB_API_HOST``. Dropped: ``NO_PROMPT``, which ``glab`` reads before
    ``GLAB_NO_PROMPT``, and ``GH_REPO`` / ``GITLAB_REPO``, which would point the
    CLI at a repository (and a host) other than the work tree's remotes, the
    ones the guards judge a ``playbook forge`` call by.

    Example::

        >>> child_env(remote, {})["GITLAB_HOST"]  # doctest: +SKIP
        'https://gitlab.acme.com'
    """
    child = {key: value for key, value in env.items() if key not in _DROPPED}
    child.update(_QUIET)
    if remote.forge.cli == "glab":
        child["GITLAB_HOST"] = f"https://{remote.api_host}"
        if remote.api_host != remote.host:
            child["GITLAB_API_HOST"] = remote.api_host
    else:
        child["GH_HOST"] = remote.api_host
    return child


def open_cli(remote: ForgeRemote, env: Mapping[str, str]) -> ForgeCli:
    """The forge CLI for ``remote``, checked: on ``PATH``, recent enough, pointed at its host.

    Exit 2 when it is missing or older than the minimum (Q38), and when
    ``GITLAB_API_HOST`` or ``glab config get api_host`` names another host (Q55).
    """
    forge = remote.forge
    executable = shutil.which(forge.cli, path=env.get("PATH"))
    if executable is None:
        raise missing_cli(forge, env)
    cli = ForgeCli(
        forge=forge,
        executable=executable,
        env=child_env(remote, env),
        cwd=remote.top,
        host=remote.api_host,
        caller_env=env,
    )
    _check_version(cli)
    if forge.cli == "glab":
        _check_api_host(cli, remote, env)
    return cli


def _check_version(cli: ForgeCli) -> None:
    done = cli.run(["--version"], check=False, timeout_s=_LOCAL_TIMEOUT_S)
    match = _VERSION.search(done.stdout) if done.code == 0 else None
    found = tuple(int(part) for part in match.groups()) if match is not None else None
    if found is None or found < MINIMUM_VERSIONS[cli.forge.name]:
        raise old_cli(cli.forge, found, cli.caller_env)


def _check_api_host(cli: ForgeCli, remote: ForgeRemote, env: Mapping[str, str]) -> None:
    """Exit 2 when ``GITLAB_API_HOST`` or ``glab``'s ``api_host`` for the host names another host.

    ``glab config get`` reads ``GITLAB_API_HOST`` first, so it runs without the
    one the child environment may carry, to read the configured value.
    """
    api_host = remote.api_host
    expected = _host_name(api_host)
    named = env.get("GITLAB_API_HOST", "").strip()
    if named and _host_name(named) != expected:
        raise host_mismatch("GITLAB_API_HOST", _host_name(named), api_host)
    bare = {key: value for key, value in cli.env.items() if key != "GITLAB_API_HOST"}
    reader = replace(cli, env=bare)
    argv = ["config", "get", "api_host", "--host", remote.host]
    done = reader.run(argv, check=False, timeout_s=_LOCAL_TIMEOUT_S)
    configured = done.stdout.strip() if done.code == 0 else ""
    if configured and _host_name(configured) != expected:
        source = f"`glab` `api_host` for {remote.host}"
        raise host_mismatch(source, _host_name(configured), api_host)


def _host_name(value: str) -> str:
    """``value`` as a bare host name: scheme, userinfo, path and port dropped, lower-cased."""
    text = _SCHEME.sub("", value.strip()).split("/", 1)[0].rpartition("@")[2]
    if text.startswith("["):
        return text.partition("]")[0][1:].lower()
    return text.partition(":")[0].lower().rstrip(".")
