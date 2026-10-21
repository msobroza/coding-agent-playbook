"""The forge-operation catalogue: what ``playbook forge`` offers and how each forge runs it (spec prF §6).

``playbook forge [-C <path>] <noun> <verb> [arguments] [--json]`` runs one
:class:`Operation` from :data:`OPERATIONS`. Each names its words, its
arguments, its :data:`Kind` and, per forge, a :class:`Translation` (``None``:
the forge lacks it, exit 3, Q30). The guards read the same rows (§8.1): an
operation of kind ``sends_data`` given ``--body-file PATH`` sends that file,
and one that ``opens_pull_request`` asks ``push_requires_green`` first;
:func:`operation_call` reads a ``playbook forge`` command line for them.

Bodies (Q36) come as ``--body TEXT``, ``--body-file PATH`` or ``--body-file -``
(stdin); ``playbook forge`` passes every body to the forge CLI on stdin, never
on argv (:attr:`Translation.body`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.forge.dialects import CommandPath, Forge

__all__ = [
    "BODY_FILE",
    "BODY_OPTIONS",
    "OPERATIONS",
    "Kind",
    "Operation",
    "OperationCall",
    "Translation",
    "operation_call",
]

#: What an operation does on the forge: reads, changes state, sends text the
#: agent wrote, or pushes git objects (no operation pushes: ``pr create`` never
#: does, Q43).
type Kind = Literal["read", "write", "sends_data", "pushes"]

#: The option whose value is a local file sent as the body (``-`` is stdin).
BODY_FILE: Final = "--body-file"
#: The options that carry a body; the forge CLI always reads it from stdin.
BODY_OPTIONS: Final = frozenset({"--body", BODY_FILE})
#: ``-C <path>``: run as if started in ``<path>``; given before the operation's words.
_DIRECTORY: Final = "-C"
#: ``--json`` (§6.1): a flag, given before or after the operation's words.
_JSON: Final = "--json"
_NONE: Final[frozenset[str]] = frozenset()


@dataclass(frozen=True, slots=True)
class Translation:
    """How one forge CLI runs one forge operation (spec §6.3).

    The operation's positionals become the forge CLI's operands, in order, and
    its body goes on stdin (``body``). Every other option of the operation is
    in ``options`` (passed with its value), in ``unsupported`` (exit 3, Q30),
    or named in ``note``, which says how ``playbook forge`` handles it.

    Example: ``Translation(("mr", "update"), fixed=("--ready",))`` runs
    ``glab mr update <n> --ready``.
    """

    #: The forge CLI's command words after argv0; empty when no forge CLI runs (``which``).
    argv: CommandPath
    #: ``(operation option, forge CLI option)`` for each option passed straight through.
    options: tuple[tuple[str, str], ...] = ()
    #: Forge CLI words every call adds.
    fixed: tuple[str, ...] = ()
    #: The forge CLI words that make it read the body from stdin (empty: it reads stdin unasked).
    body: tuple[str, ...] = ()
    #: Operation options this forge lacks: exit 3.
    unsupported: frozenset[str] = _NONE
    #: The call needs a paid plan (GitLab Premium): exit 3 where the plan lacks it.
    paid: bool = False
    #: What the call does beyond passing options, as spec §6.3 states it.
    note: str = ""


@dataclass(frozen=True, slots=True)
class Operation:
    """One forge operation: its words, arguments, kind and per-forge translations.

    Example::

        >>> operation_call(["pr", "create", "--title", "x"]).operation.opens_pull_request
        True
    """

    #: ``("issue", "create")``; ``("which",)``.
    words: tuple[str, ...]
    kind: Kind
    #: Positional arguments, by name: ``("n",)``, ``("parent", "child")``.
    positionals: tuple[str, ...] = ()
    #: Options that take a value.
    values: frozenset[str] = _NONE
    #: Options that take none.
    flags: frozenset[str] = _NONE
    #: Options that may be given more than once.
    repeatable: frozenset[str] = _NONE
    #: ``(option, allowed values)`` for an option with a closed set of values.
    choices: tuple[tuple[str, tuple[str, ...]], ...] = ()
    #: The operation opens a pull request (``push_requires_green`` asks first, spec §8.3).
    opens_pull_request: bool = False
    #: ``(forge name, translation)`` for every forge; ``None``: unsupported there (exit 3).
    translations: tuple[tuple[str, Translation | None], ...] = ()

    @property
    def name(self) -> str:
        """The operation's words as typed: ``"issue create"``."""
        return " ".join(self.words)

    def translation(self, forge: Forge) -> Translation | None:
        """How ``forge``'s CLI runs this operation; ``None`` when ``forge`` lacks it (exit 3).

        Example::

            >>> from coding_agent_playbook.forge.dialects import GITLAB
            >>> operation_call(["issue", "children", "3"]).operation.translation(GITLAB) is None
            True
        """
        for name, translation in self.translations:
            if name == forge.name:
                return translation
        raise KeyError(f"{self.name!r} has no translation for the {forge.name!r} forge")


@dataclass(frozen=True, slots=True)
class OperationCall:
    """The operation a ``playbook forge`` command line runs, its arguments and its ``-C`` path.

    Example: ``OperationCall(<pr view>, ("3",), "../app")`` for ``-C ../app pr view 3``.
    """

    operation: Operation
    #: The words after the operation's words.
    args: tuple[str, ...]
    #: The last ``-C`` path, else ``None``.
    directory: str | None


def operation_call(words: Sequence[str]) -> OperationCall | None:
    """The operation ``words`` (argv after ``playbook forge``) runs, else ``None``.

    Reads ``-C <path>`` / ``-C<path>`` and ``--json`` before the operation's
    words, as ``playbook forge``'s own parser does.

    Example::

        >>> call = operation_call(["-C", "../app", "pr", "view", "3"])
        >>> call.operation.name, call.args, call.directory
        ('pr view', ('3',), '../app')
    """
    index, directory = 0, None
    while index < len(words):
        word = words[index]
        if word == _DIRECTORY:
            if index + 1 >= len(words):
                return None
            directory, index = words[index + 1], index + 2
        elif word.startswith(_DIRECTORY):
            directory, index = word[len(_DIRECTORY) :], index + 1
        elif word == _JSON:
            index += 1
        else:
            break
    rest = tuple(words[index:])
    for candidate in OPERATIONS:
        if rest[: len(candidate.words)] == candidate.words:
            return OperationCall(candidate, rest[len(candidate.words) :], directory)
    return None


def _flags(text: str) -> frozenset[str]:
    return frozenset(text.split())


def _same(text: str) -> tuple[tuple[str, str], ...]:
    """Options the forge CLI takes under the operation's own names."""
    return tuple((option, option) for option in text.split())


def _op(
    usage: str,
    kind: Kind,
    *,
    github: Translation | None,
    gitlab: Translation | None,
    values: str = "",
    flags: str = "",
    repeatable: str = "",
    choices: tuple[tuple[str, tuple[str, ...]], ...] = (),
    opens_pull_request: bool = False,
) -> Operation:
    """Build one operation from its ``usage``: its words, then ``<positional>`` names."""
    words = usage.split()
    return Operation(
        words=tuple(word for word in words if not word.startswith("<")),
        kind=kind,
        positionals=tuple(word.strip("<>") for word in words if word.startswith("<")),
        values=_flags(values),
        flags=_flags(flags),
        repeatable=_flags(repeatable),
        choices=choices,
        opens_pull_request=opens_pull_request,
        translations=(("github", github), ("gitlab", gitlab)),
    )


_BODY: Final = f"--body {BODY_FILE}"
_GH_STDIN: Final = ("--body-file", "-")
_GLAB_STDIN: Final = ("--description-file", "-")
_GH_JSON: Final = ("--json",)
_GLAB_JSON: Final = ("-F", "json")
_NOT_PUSHED: Final = "never pushes (Q43): a branch not on the remote exits 2"
_SKIP_CI: Final = "a title holding a skip-CI marker exits 1 (Q55)"
_ADD_REMOVE_LABEL: Final = (("--add", "--add-label"), ("--remove", "--remove-label"))
_LABEL_UNLABEL: Final = (("--add", "--label"), ("--remove", "--unlabel"))
_WHICH: Final = Translation((), note="prints {forge, cli, host, api_host, repo, remote}")

#: Every forge operation (spec §6.3), in the spec's order.
OPERATIONS: Final = (
    _op(
        "issue create",
        "sends_data",
        values=f"--title {_BODY} --label --assignee --parent --blocked-by",
        flags="--confidential",
        repeatable="--label",
        github=Translation(
            ("issue", "create"),
            options=_same("--title --label --assignee"),
            body=_GH_STDIN,
            unsupported=_flags("--confidential"),
            note="--parent and --blocked-by run as `issue link-child` and `issue block` "
            "once the issue exists",
        ),
        gitlab=Translation(
            ("issue", "create"),
            options=_same("--title --label --assignee --confidential"),
            fixed=("--yes",),
            body=_GLAB_STDIN,
            unsupported=_flags("--parent"),
            note="--parent exits 3 (the skill writes `Part of #n`); --blocked-by via a link "
            "(Premium, else exit 3)",
        ),
    ),
    _op(
        "issue view <n>",
        "read",
        flags="--comments",
        github=Translation(("issue", "view"), options=_same("--comments"), fixed=_GH_JSON),
        gitlab=Translation(
            ("issue", "view"),
            options=_same("--comments"),
            fixed=_GLAB_JSON,
            note="notes paginated, system notes dropped",
        ),
    ),
    _op(
        "issue list",
        "read",
        values="--state --label --assignee --search --limit",
        flags="--no-label",
        repeatable="--label",
        github=Translation(
            ("issue", "list"),
            options=_same("--state --label --assignee --search --limit"),
            fixed=_GH_JSON,
            note="--no-label as `no:label` in the search",
        ),
        gitlab=Translation(
            ("issue", "list"),
            options=(*_same("--label --assignee --search"), ("--limit", "--per-page")),
            fixed=("-O", "json"),
            note="--state closed or all as `--closed` or `--all`; --no-label keeps the issues "
            "without labels",
        ),
    ),
    _op(
        "issue comment <n>",
        "sends_data",
        values=_BODY,
        github=Translation(("issue", "comment"), body=_GH_STDIN),
        gitlab=Translation(("issue", "note"), note="the body on stdin"),
    ),
    _op(
        "issue label <n>",
        "write",
        values="--add --remove",
        github=Translation(("issue", "edit"), options=_ADD_REMOVE_LABEL),
        gitlab=Translation(("issue", "update"), options=_LABEL_UNLABEL, note="one request"),
    ),
    _op(
        "issue close <n>",
        "sends_data",
        values="--comment --reason",
        choices=(("--reason", ("completed", "not-planned", "duplicate")),),
        github=Translation(
            ("issue", "close"),
            options=_same("--comment --reason"),
            note="one call (Q41); --reason not-planned is gh's `not planned`",
        ),
        gitlab=Translation(
            ("issue", "close"),
            note="--comment and --reason (as a closing line) go in a note first, then "
            "`glab issue close`; a failed second call exits 1 naming the posted note (Q41)",
        ),
    ),
    _op(
        "issue assign <n>",
        "write",
        values="--add",
        github=Translation(("issue", "edit"), options=(("--add", "--add-assignee"),)),
        gitlab=Translation(
            ("issue", "update"),
            options=(("--add", "--assignee"),),
            note="the --add value prefixed with `+` (`--assignee +@me`)",
        ),
    ),
    _op(
        "issue edit <n>",
        "sends_data",
        values=f"--title {_BODY}",
        github=Translation(("issue", "edit"), options=_same("--title"), body=_GH_STDIN),
        gitlab=Translation(("issue", "update"), options=_same("--title"), body=_GLAB_STDIN),
    ),
    _op(
        "issue link-child <parent> <child>",
        "write",
        github=Translation(
            ("issue", "edit"), note="`gh issue edit <parent> --add-sub-issue <child>`"
        ),
        gitlab=None,
    ),
    _op(
        "issue children <parent>",
        "read",
        github=Translation(("issue", "view"), fixed=("--json", "subIssues")),
        gitlab=None,
    ),
    _op(
        "issue block <child> <blocker>",
        "write",
        github=Translation(
            ("issue", "edit"), note="`gh issue edit <child> --add-blocked-by <blocker>`"
        ),
        gitlab=Translation(("issue", "note"), paid=True, note="a `/blocked_by` quick-action note"),
    ),
    _op(
        "issue blockers <n>",
        "read",
        github=Translation(("issue", "view"), fixed=("--json", "blockedBy")),
        gitlab=Translation(
            ("api",),
            paid=True,
            note="`projects/:id/issues/<iid>/links`, the `is_blocked_by` links",
        ),
    ),
    _op(
        "label list",
        "read",
        github=Translation(("label", "list"), fixed=_GH_JSON),
        gitlab=Translation(("label", "list"), fixed=_GLAB_JSON),
    ),
    _op(
        "label create <name>",
        "write",
        values="--color --description",
        github=Translation(("label", "create"), options=_same("--color --description")),
        gitlab=Translation(
            ("label", "create"),
            options=_same("--color --description"),
            note="the name goes in `--name`",
        ),
    ),
    _op(
        "pr create",
        "sends_data",
        values=f"--title {_BODY} --base",
        flags="--draft",
        opens_pull_request=True,
        github=Translation(
            ("pr", "create"),
            options=_same("--title --base --draft"),
            body=_GH_STDIN,
            note=f"`--head <branch>`; {_NOT_PUSHED}",
        ),
        gitlab=Translation(
            ("mr", "create"),
            options=(*_same("--title --draft"), ("--base", "--target-branch")),
            fixed=("--push=false", "--yes"),
            body=_GLAB_STDIN,
            note=f"`--source-branch <branch>`; {_NOT_PUSHED}; {_SKIP_CI}",
        ),
    ),
    _op(
        "pr view <n>",
        "read",
        flags="--comments",
        github=Translation(("pr", "view"), options=_same("--comments"), fixed=_GH_JSON),
        gitlab=Translation(("mr", "view"), options=_same("--comments"), fixed=_GLAB_JSON),
    ),
    _op(
        "pr list",
        "read",
        values="--state --label",
        flags="--external",
        github=Translation(
            ("pr", "list"),
            options=_same("--state --label"),
            fixed=_GH_JSON,
            note="--external via `gh api …/pulls` `author_association`",
        ),
        gitlab=Translation(
            ("mr", "list"),
            options=_same("--label"),
            fixed=_GLAB_JSON,
            note="--state closed, merged or all as `--closed`, `--merged` or `--all`; "
            "--external via one membership lookup per author",
        ),
    ),
    _op(
        "pr diff <n>",
        "read",
        github=Translation(("pr", "diff"), fixed=("--color", "never")),
        gitlab=Translation(("mr", "diff"), fixed=("--color", "never")),
    ),
    _op(
        "pr checkout <n>",
        "read",
        github=Translation(("pr", "checkout")),
        gitlab=Translation(("mr", "checkout")),
    ),
    _op(
        "pr comment <n>",
        "sends_data",
        values=f"{_BODY} --reply-to",
        github=Translation(
            ("pr", "comment"),
            body=_GH_STDIN,
            note="--reply-to via `gh api …/pulls/<n>/comments/<id>/replies` (Q22)",
        ),
        gitlab=Translation(
            ("mr", "note", "create"),
            note="the body on stdin; --reply-to via `glab api …/discussions/<id>/notes` (Q22)",
        ),
    ),
    _op(
        "pr label <n>",
        "write",
        values="--add --remove",
        github=Translation(("pr", "edit"), options=_ADD_REMOVE_LABEL),
        gitlab=Translation(("mr", "update"), options=_LABEL_UNLABEL),
    ),
    _op(
        "pr close <n>",
        "sends_data",
        values="--comment",
        github=Translation(("pr", "close"), options=_same("--comment")),
        gitlab=Translation(
            ("mr", "close"), note="--comment goes in a note first, then `glab mr close`"
        ),
    ),
    _op(
        "pr ready <n>",
        "write",
        github=Translation(("pr", "ready")),
        gitlab=Translation(("mr", "update"), fixed=("--ready",)),
    ),
    _op(
        "pr edit <n>",
        "sends_data",
        values=f"--title {_BODY}",
        github=Translation(("pr", "edit"), options=_same("--title"), body=_GH_STDIN),
        gitlab=Translation(
            ("mr", "update"), options=_same("--title"), body=_GLAB_STDIN, note=_SKIP_CI
        ),
    ),
    _op(
        "pr checks <n>",
        "read",
        github=Translation(("pr", "checks"), fixed=_GH_JSON),
        gitlab=Translation(("ci", "status"), fixed=_GLAB_JSON, note="the pull request's pipeline"),
    ),
    _op(
        "ref view <ref>",
        "read",
        github=Translation(
            ("pr", "view"),
            fixed=_GH_JSON,
            note="`#n` / `n`: the pull request, else the issue; a URL by its path",
        ),
        gitlab=Translation(
            ("issue", "view"),
            fixed=_GLAB_JSON,
            note="`#n`: the issue, `!n`: the pull request (`glab mr view`); a URL by its path",
        ),
    ),
    _op("which", "read", github=_WHICH, gitlab=_WHICH),
    _op(
        "auth status",
        "read",
        github=Translation(("auth", "status"), note="`--hostname <host>`"),
        gitlab=Translation(("auth", "status"), note="`--hostname <host>`, never `-t`"),
    ),
)
