"""One forge operation ready to run, and what it prints (spec prF §6.3).

An operation handler (``_forge_issues``, ``_forge_pulls``) gets an :class:`Op`:
the parsed call, the push remote, its forge CLI and the operation's
:class:`~coding_agent_playbook.forge.operations.Translation`. :meth:`Op.argv`
builds the forge CLI's words from that translation, so the catalogue the
guards read stays the one source of the flags; :meth:`Op.body` neutralises
GitLab quick actions (Q40). A handler returns an :class:`Outcome`:
:func:`printed` JSON for a read, :func:`written` URL for a write.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from coding_agent_playbook.commands._forge_args import Call
    from coding_agent_playbook.commands._forge_cli import Done, ForgeCli
    from coding_agent_playbook.commands._forge_repo import ForgeRemote
    from coding_agent_playbook.forge.operations import Translation

__all__ = ["Op", "Outcome", "created", "items", "neutralised", "printed", "url_in", "written"]

_URL: Final = re.compile(r"https?://\S+")
#: The largest page GitLab serves.
_GLAB_PAGE: Final = 100


@dataclass(frozen=True)
class Outcome:
    """What ``playbook forge`` prints and returns: stdout, stderr and the exit code."""

    stdout: str = ""
    stderr: str = ""
    code: int = 0


@dataclass(frozen=True)
class Op:
    """One operation ready to run: the call, the push remote, its forge CLI and translation."""

    call: Call
    remote: ForgeRemote
    cli: ForgeCli
    translation: Translation

    @property
    def gitlab(self) -> bool:
        """Whether the forge is GitLab (``glab``)."""
        return self.remote.forge.name == "gitlab"

    def argv(self, *, positionals: bool = True, body: bool = True) -> list[str]:
        """The forge CLI words the translation gives: command, positionals, options, fixed, body.

        Example: ``["issue", "view", "3", "--comments", "-F", "json"]`` for
        ``issue view 3 --comments`` on GitLab.
        """
        call, translation = self.call, self.translation
        words = list(translation.argv)
        if positionals:
            words.extend(call.positional(name) for name in call.operation.positionals)
        for option, cli_option in translation.options:
            if option in call.flags:
                words.append(cli_option)
            for value in call.values(option):
                words.extend((cli_option, value))
        words.extend(translation.fixed)
        if body and call.body is not None:
            words.extend(translation.body)
        return words

    def body(self, text: str | None = None) -> str | None:
        """``text`` (default: the call's body) as sent: line-leading ``/`` neutralised on GitLab."""
        value = self.call.body if text is None else text
        if value is None:
            return None
        return neutralised(value) if self.gitlab else value

    def run(self, argv: list[str], *, body: str | None = None, check: bool = True) -> Done:
        """Run the forge CLI (``body`` on stdin, already neutralised by the caller)."""
        return self.cli.run(argv, body=body, check=check)

    def repo_url(self) -> str:
        """The push remote's repository on the web: ``https://<api host>/<repo>``."""
        return f"https://{self.remote.api_host}/{self.remote.repo}"

    def web_url(self, kind: str, number: str) -> str:
        """The web URL of ``issues``, ``pull`` or ``merge_requests`` ``number`` in the repository."""
        separator = "/-/" if self.gitlab else "/"
        return f"{self.repo_url()}{separator}{kind}/{number}"

    def json(self, argv: list[str], *, body: str | None = None) -> Any:
        """Run the forge CLI and decode its JSON stdout."""
        return self.cli.json(argv, body=body)

    def listed(self, argv: list[str], limit: int | None) -> list[Any]:
        """Every item a ``glab … list -F json`` prints, page after page, up to ``limit``.

        ``glab`` lists print one page; ``None`` reads every page (``gh`` pages itself).
        """
        per_page = min(limit, _GLAB_PAGE) if limit is not None else _GLAB_PAGE
        found: list[Any] = []
        page = 1
        while True:
            argv_page = [*argv, "--page", str(page), "--per-page", str(per_page)]
            batch = items(self.json(argv_page))
            found.extend(batch)
            if len(batch) < per_page or (limit is not None and len(found) >= limit):
                return found if limit is None else found[:limit]
            page += 1

    def pages(self, argv: list[str]) -> list[Any]:
        """Run the forge CLI and decode every JSON page it prints (``--paginate``)."""
        return self.cli.pages(self.cli.run(argv), argv)


def printed(value: object) -> Outcome:
    """``value`` as the operation's JSON on stdout."""
    return Outcome(stdout=json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def written(op: Op, url: str) -> Outcome:
    """A write's outcome: its URL on stdout, or ``{"url": …}`` with ``--json``."""
    if op.call.json:
        return printed({"url": url})
    return Outcome(stdout=f"{url}\n")


def created(op: Op, done: Done) -> Outcome:
    """A create's outcome: the URL the forge CLI printed, else its output as is."""
    url = url_in(done.stdout)
    return written(op, url) if url is not None else Outcome(stdout=done.stdout)


def items(value: Any) -> list[Any]:
    """``value`` as a list: a JSON list as is, one object as a list of one, ``null`` as none."""
    if isinstance(value, list):
        return value
    return [] if value is None else [value]


def url_in(text: str) -> str | None:
    """The last ``http(s)://`` URL in a forge CLI's output, else ``None``.

    Example::

        >>> url_in("Creating issue\\nhttps://gitlab.com/a/b/-/issues/4\\n")
        'https://gitlab.com/a/b/-/issues/4'
    """
    found = _URL.findall(text)
    return found[-1].rstrip(".,;)") if found else None


def neutralised(text: str) -> str:
    """``text`` with each line-leading ``/`` neutralised, so GitLab runs no quick action (Q40).

    A line GitLab would read as a quick action starts with ``/``; one space
    before it keeps the line as text and renders the same.

    Example::

        >>> neutralised("Done.\\n/close\\n")
        'Done.\\n /close\\n'
    """
    return "".join(
        f" {line}" if line.startswith("/") else line for line in text.splitlines(keepends=True)
    )
