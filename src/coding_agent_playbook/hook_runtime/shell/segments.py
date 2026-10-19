"""From lexer tokens to ``Segment``s, in execution order (specs/prK-lifecycle-hooks.md §D.2.5).

Each simple command becomes one ``Segment``: keywords and ``NAME=value``
prefixes are stripped, launchers are unwrapped, and the cwd follows ``cd X &&``
(a subshell's ``cd`` ends at its ``)``). The command lists a command runs while
it expands its words (substitutions) come first; the ones it runs itself
(shell ``-c``, ``eval``, ``find -exec``) come right after it. ``parse.py``
re-exports ``Redirect`` and ``Segment``.
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.hook_runtime.shell._scan import scan
from coding_agent_playbook.hook_runtime.shell.tokens import Op, RawRedirect, RawWord, ScanLimit
from coding_agent_playbook.hook_runtime.shell.wrappers import unwrap

if TYPE_CHECKING:
    from collections.abc import Iterable

    from coding_agent_playbook.hook_runtime.shell.tokens import Token, Word
    from coding_agent_playbook.hook_runtime.shell.wrappers import SegmentOrigin, ShellConfig

MAX_SEGMENTS: Final = 256

_PIPES = frozenset({"|", "|&"})
#: Separators after which a ``cd`` is still in effect for the next command.
_SEQUENTIAL = frozenset({"&&", ";", "\n", ""})
_KEYWORDS = frozenset(
    ["!", "{", "}", "if", "then", "else", "elif", "fi", "do", "done", "while", "until", "esac"]
)
_CD = frozenset({"cd", "pushd"})


@dataclass(frozen=True, slots=True)
class Redirect:
    """One redirection: ``op`` without its fd (``>``, ``>>``, ``<<``, ``>&``, ...).

    ``target`` is ``None`` for a heredoc; ``dynamic`` marks a target holding an
    expansion. Example: ``2>&1`` is ``Redirect(">&", "1", 2)``.
    """

    op: str
    target: str | None
    fd: int | None
    dynamic: bool = False


@dataclass(frozen=True, slots=True, kw_only=True)
class Segment:
    """One simple command that will run.

    ``argv`` is effective (env prefixes and launchers stripped) and
    ``raw_argv`` is every word as written, after quote removal. ``dynamic``
    holds the ``argv`` indexes containing ``$VAR``, ``${...}``, ``$(...)`` or
    backticks. ``cwd`` follows ``cd X &&`` (``None`` = unknown). ``origin``
    says where the command came from and ``depth`` how deeply it is nested;
    ``args_open`` marks ``xargs`` / ``find -exec`` commands, whose arguments
    are appended at run time.

    Example: ``sudo rm -rf x`` is ``Segment(argv=("rm", "-rf", "x"),
    raw_argv=("sudo", "rm", "-rf", "x"), wrappers=("sudo",), ...)``.
    """

    argv: tuple[str, ...]
    raw_argv: tuple[str, ...]
    env: tuple[tuple[str, str], ...] = ()
    wrappers: tuple[str, ...] = ()
    redirects: tuple[Redirect, ...] = ()
    heredoc_bodies: tuple[str, ...] = field(default=(), repr=False)
    cwd: str | None = None
    dynamic: frozenset[int] = frozenset()
    origin: SegmentOrigin = "top"
    depth: int = 0
    pipes_to_next: bool = False
    background: bool = False
    args_open: bool = False


def build_segments(tokens: list[Token], cwd: str | None, cfg: ShellConfig) -> tuple[Segment, ...]:
    """The segments ``tokens`` run, starting in ``cwd``; raises ``ScanLimit`` past a limit.

    Example: ``build_segments(scan("cd a && ls"), "/r", ShellConfig())[1].cwd == "/r/a"``.
    """
    builder = _SegmentBuilder(cfg)
    builder.add_list(tokens, cwd, _Frame())
    return tuple(builder.segments)


@dataclass(frozen=True, slots=True)
class _Frame:
    """What a nested command list inherits from the command that runs it."""

    origin: SegmentOrigin = "top"
    depth: int = 0
    env: tuple[tuple[str, str], ...] = ()
    wrappers: tuple[str, ...] = ()
    args_open: bool = False


class _SegmentBuilder:
    def __init__(self, cfg: ShellConfig) -> None:
        self._cfg = cfg
        self.segments: list[Segment] = []

    def add_list(self, tokens: list[Token], cwd: str | None, frame: _Frame) -> None:
        """Split one list at its operators; ``(``...``)`` scopes a ``cd`` to the subshell."""
        saved: list[str | None] = []
        words: list[RawWord] = []
        redirects: list[RawRedirect] = []
        for token in [*tokens, Op("")]:
            if isinstance(token, RawWord):
                words.append(token)
            elif isinstance(token, RawRedirect):
                redirects.append(token)
            else:
                target = self._add_command(words, redirects, cwd, frame, token.text)
                words, redirects = [], []
                if token.text == "(":
                    saved.append(cwd)
                elif token.text == ")":
                    cwd = saved.pop() if saved else cwd
                elif target is not None and token.text in _SEQUENTIAL:
                    cwd = target[0]

    def _add_command(
        self,
        raw_words: list[RawWord],
        raw_redirects: list[RawRedirect],
        cwd: str | None,
        frame: _Frame,
        separator: str,
    ) -> tuple[str | None] | None:
        """Emit one simple command, substitutions first; a ``cd`` returns its new cwd."""
        inner = replace(frame, origin="subst", depth=frame.depth + 1, args_open=False)
        for tokens in _substitutions(raw_words, raw_redirects):
            self.add_list(tokens, cwd, inner)
        words = _strip_keywords([raw.resolve() for raw in raw_words])
        redirects = tuple(_redirect(raw) for raw in raw_redirects)
        bodies = tuple(raw.body for raw in raw_redirects if raw.target is None)
        segment = self._emit(words, redirects, bodies, cwd, frame, separator)
        return None if segment is None else _cd_target(segment, cwd)

    def _emit(
        self,
        words: list[Word],
        redirects: tuple[Redirect, ...],
        bodies: tuple[str, ...],
        cwd: str | None,
        frame: _Frame,
        separator: str,
    ) -> Segment | None:
        count = next((i for i, w in enumerate(words) if not w.assignment), len(words))
        unwrapped = unwrap(words[count:], self._cfg)
        if not unwrapped.argv and not redirects and not unwrapped.wrappers:
            return None  # a bare assignment or keyword: nothing runs
        segment = Segment(
            argv=tuple(w.value for w in unwrapped.argv),
            raw_argv=tuple(w.value for w in words),
            env=(*frame.env, *map(_assignment, words[:count]), *unwrapped.env),
            wrappers=(*frame.wrappers, *unwrapped.wrappers),
            redirects=redirects,
            heredoc_bodies=bodies,
            cwd=cwd,
            dynamic=frozenset(i for i, w in enumerate(unwrapped.argv) if w.dynamic),
            origin=unwrapped.origin or frame.origin,
            depth=frame.depth,
            pipes_to_next=separator in _PIPES,
            background=separator == "&",
            args_open=frame.args_open or unwrapped.args_open,
        )
        self._append(segment)
        if unwrapped.limit:
            raise ScanLimit("more than 4 launchers")
        child = _Frame(
            segment.origin, segment.depth, segment.env, segment.wrappers, segment.args_open
        )
        for origin, launcher, script in unwrapped.nested:
            wrappers = (*segment.wrappers, launcher)
            nested = replace(child, origin=origin, depth=frame.depth + 1, wrappers=wrappers)
            self.add_list(scan(script.value, nested.depth), cwd, nested)
        for exec_words in unwrapped.find_execs:
            found = replace(child, origin="find_exec", wrappers=(*segment.wrappers, "find"))
            self._emit(exec_words, (), (), cwd, replace(found, args_open=True), "")
        return segment

    def _append(self, segment: Segment) -> None:
        if len(self.segments) >= MAX_SEGMENTS:
            raise ScanLimit(f"more than {MAX_SEGMENTS} segments")
        self.segments.append(segment)


def _substitutions(words: list[RawWord], redirects: list[RawRedirect]) -> Iterable[list[Token]]:
    """Every command list the shell runs while expanding one command's words."""
    for word in words:
        yield from word.substs
    for redirect in redirects:
        yield from redirect.substs
        if redirect.target is not None:
            yield from redirect.target.substs


def _strip_keywords(words: list[Word]) -> list[Word]:
    """Drop leading reserved words (``if``, ``then``, ``do``, ``{``, ``!``, ``fi``, ...)."""
    start = 0
    while start < len(words) and not words[start].quoted and words[start].value in _KEYWORDS:
        start += 1
    return words[start:]


def _assignment(word: Word) -> tuple[str, str]:
    name, _, value = word.value.partition("=")
    return name.removesuffix("+"), value


def _redirect(raw: RawRedirect) -> Redirect:
    if raw.target is None:
        return Redirect(raw.op, None, raw.fd)
    target = raw.target.resolve()
    return Redirect(raw.op, target.value, raw.fd, target.dynamic)


def _cd_target(segment: Segment, cwd: str | None) -> tuple[str | None] | None:
    """``None`` unless ``segment`` is a ``cd``; else a 1-tuple of its target (``None`` = unknown)."""
    argv = segment.argv
    if not argv or argv[0] not in _CD:
        return None
    index = 1
    while index < len(argv) and argv[index].startswith("-") and argv[index] != "-":
        index += 1
        if argv[index - 1] == "--":
            break
    if index >= len(argv) or index in segment.dynamic:
        return (None,)  # `cd` alone goes to $HOME, unknown here
    target = argv[index]
    if target == "-" or target.startswith("~"):
        return (None,)
    if target.startswith("/"):
        return (posixpath.normpath(target),)
    return (None,) if cwd is None else (posixpath.normpath(posixpath.join(cwd, target)),)
