"""Fake ``gh``, ``glab`` and ``ssh`` executables for the ``playbook forge`` tests (spec prF §15, Q24).

Each fake is a small Python script on ``PATH`` (the only directory on it, with
a link to the real ``git``): it records its argv, its stdin and the
environment variables the tests read, then answers from the replies the test
queued (the first queued reply whose argv is a prefix of the call's wins) or
with a default: ``--version`` prints a supported version line, ``ssh -G``
echoes the host, anything else prints nothing and exits 0. No network and no
real forge CLI ever run.

Example::

    def test_x(forge_env: ForgeEnv) -> None:
        forge_env.reply("gh", "issue", "view", json_out={"number": 3})
        ...
        assert forge_env.last("gh").argv[:2] == ("issue", "view")
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

__all__ = ["RECORDED_ENV", "FakeCall", "ForgeEnv", "make_forge_env"]

#: The environment variables each fake records (the child-env contract of spec §5.3).
RECORDED_ENV: Final = (
    "GH_HOST",
    "GITLAB_HOST",
    "GITLAB_API_HOST",
    "GH_PROMPT_DISABLED",
    "GLAB_NO_PROMPT",
    "GH_NO_UPDATE_NOTIFIER",
    "GH_NO_EXTENSION_UPDATE_NOTIFIER",
    "GH_TELEMETRY",
    "DO_NOT_TRACK",
    "GLAB_CHECK_UPDATE",
    "GLAB_SEND_TELEMETRY",
    "NO_PROMPT",
    "GH_REPO",
    "GITLAB_REPO",
)

#: What each fake prints for ``--version`` unless a test queues another answer.
VERSIONS: Final = {
    "gh": "gh version 2.94.0 (2026-06-30)\nhttps://github.com/cli/cli/releases/tag/v2.94.0\n",
    "glab": "glab 1.115.0 (c3612c8d)\n",
}

_SCRIPT: Final = """\
#!{python}
import json, os, sys
from pathlib import Path

state = Path({state!r})
cli = {cli!r}
argv = sys.argv[1:]
stdin = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
env = {{name: os.environ[name] for name in {recorded!r} if name in os.environ}}
with (state / "calls.jsonl").open("a", encoding="utf-8") as log:
    log.write(json.dumps({{"cli": cli, "argv": argv, "stdin": stdin, "env": env}}) + "\\n")
replies = json.loads((state / "replies.json").read_text(encoding="utf-8"))
for reply in replies:
    prefix = reply["argv"]
    if reply["cli"] == cli and argv[: len(prefix)] == prefix:
        if reply["once"]:
            replies.remove(reply)
            (state / "replies.json").write_text(json.dumps(replies), encoding="utf-8")
        sys.stdout.write(reply["stdout"])
        sys.stderr.write(reply["stderr"])
        sys.exit(reply["code"])
if cli == "ssh" and argv[:1] == ["-G"]:
    print("user git")
    print("hostname " + argv[-1].lower())
    print("port 22")
elif argv == ["--version"]:
    sys.stdout.write({versions!r}.get(cli, ""))
"""


@dataclass(frozen=True)
class FakeCall:
    """One recorded run of a fake: its argv (without argv0), stdin and recorded environment."""

    cli: str
    argv: tuple[str, ...]
    stdin: str
    env: Mapping[str, str]


@dataclass(frozen=True)
class ForgeEnv:
    """The fakes' directory and state: queue replies, read back calls."""

    bin_dir: Path
    state: Path

    def reply(
        self,
        cli: str,
        *argv: str,
        stdout: str = "",
        stderr: str = "",
        code: int = 0,
        json_out: object = None,
        once: bool = False,
    ) -> None:
        """Answer ``cli`` calls whose argv starts with ``argv`` (``json_out``: printed as JSON).

        ``once`` answers only the next such call. Replies match in the order queued.
        """
        replies = json.loads((self.state / "replies.json").read_text(encoding="utf-8"))
        text = json.dumps(json_out) + "\n" if json_out is not None else stdout
        replies.append(
            {
                "cli": cli,
                "argv": list(argv),
                "stdout": text,
                "stderr": stderr,
                "code": code,
                "once": once,
            }
        )
        (self.state / "replies.json").write_text(json.dumps(replies), encoding="utf-8")

    def calls(self, cli: str | None = None, *, versions: bool = False) -> list[FakeCall]:
        """Every recorded call of ``cli`` (all fakes when ``None``); ``--version`` runs only if asked."""
        log = self.state / "calls.jsonl"
        if not log.exists():
            return []
        found = []
        for line in log.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            call = FakeCall(row["cli"], tuple(row["argv"]), row["stdin"], row["env"])
            if (cli is None or call.cli == cli) and (versions or call.argv != ("--version",)):
                found.append(call)
        return found

    def last(self, cli: str) -> FakeCall:
        """The last recorded call of ``cli`` (``--version`` runs left out)."""
        calls = self.calls(cli)
        assert calls, f"no {cli} call recorded"
        return calls[-1]

    def argvs(self, cli: str) -> list[tuple[str, ...]]:
        """The argv of every recorded ``cli`` call, ``--version`` and ``ssh`` runs left out."""
        return [call.argv for call in self.calls(cli)]

    def remove(self, cli: str) -> None:
        """Take ``cli`` off ``PATH`` (a missing forge CLI)."""
        (self.bin_dir / cli).unlink()


def make_forge_env(root: Path) -> ForgeEnv:
    """Write the fakes under ``root`` and return the handle; ``PATH`` is to be ``root/bin`` only."""
    bin_dir, state = root / "bin", root / "state"
    bin_dir.mkdir(parents=True)
    state.mkdir()
    (state / "replies.json").write_text("[]", encoding="utf-8")
    for cli in ("gh", "glab", "ssh"):
        script = _SCRIPT.format(
            python=sys.executable,
            state=str(state),
            cli=cli,
            recorded=RECORDED_ENV,
            versions=VERSIONS,
        )
        path = bin_dir / cli
        path.write_text(script, encoding="utf-8")
        path.chmod(0o755)
    git = shutil.which("git")
    assert git is not None, "the forge tests need git"
    os.symlink(git, bin_dir / "git")
    return ForgeEnv(bin_dir, state)
