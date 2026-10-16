"""The POSIX shell lexer behind ``shell.parse_shell`` (specs/prK-lifecycle-hooks.md §D.2.5).

It turns command text into the tokens of ``_shell_tokens``: words, control
operators, and redirections carrying their heredoc bodies. The command lists
inside substitutions are scanned recursively, because the shell runs them. The
lexer executes and expands nothing: a construct it cannot follow raises
``ScanError``, and nesting deeper than ``MAX_DEPTH`` raises ``ScanLimit``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from coding_agent_playbook.hook_runtime._shell_tokens import (
    MAX_DEPTH,
    PLACEHOLDER_CLOSE,
    PLACEHOLDER_OPEN,
    Op,
    RawRedirect,
    RawWord,
    ScanError,
    ScanLimit,
    ansi_c_word,
    heredoc_body,
)

if TYPE_CHECKING:
    from coding_agent_playbook.hook_runtime._shell_tokens import Token

_OPERATORS = (";;&", ";;", ";&", "&&", "||", "|&", ";", "|", "&")
_REDIRECT = re.compile(r"(\d*)(&>>|&>|>>|>&|>\||<<<|<<-|<<|<>|<&|>|<)")
_PROCESS_SUBSTITUTION = ("<(", ">(")
_WORD_END = frozenset(" \t\n;&|()<>")
#: Runs of characters that need no handling, consumed in one step (a 64 KiB word stays fast).
_PLAIN_RUN = re.compile(r"[^ \t\n;&|()<>\\'\"$`]+")
_DOUBLE_QUOTED_RUN = re.compile(r'[^"\\$`]+')
_PARAM = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9@*#?$!-]")
#: What a backslash inside double quotes does to the next character: bash drops
#: it before ``$`` and a backquote (shlex would keep it), shlex handles ``"`` and
#: ``\\`` itself, and a backslash-newline continues the line.
_DOUBLE_QUOTED_ESCAPES = {"$": "$", "`": "`", '"': '\\"', "\\": "\\\\", "\n": ""}


def scan(text: str, depth: int = 0) -> list[Token]:
    """Tokenize ``text`` as a command list nested ``depth`` levels deep.

    Example: ``scan("a && b")`` is ``[RawWord(a), Op("&&"), RawWord(b)]``.
    """
    if PLACEHOLDER_OPEN in text or PLACEHOLDER_CLOSE in text:
        raise ScanError("reserved private-use character in the command")
    return _Scanner(text).scan_list(depth, closer=False)


def body_substitutions(body: str, depth: int) -> list[list[Token]]:
    """The command lists an unquoted heredoc body runs through ``$(...)`` and backticks."""
    scanner = _Scanner(body)
    sink = RawWord()
    while scanner.pos < len(body):
        char = body[scanner.pos]
        if char == "\\":
            scanner.pos += 2
        elif char == "$":
            scanner.scan_dollar(sink, depth, in_double=True)
        elif char == "`":
            scanner.scan_backtick(sink, depth)
        else:
            scanner.pos += 1
    return sink.substs


class _Scanner:
    """A cursor over one text; heredocs wait in ``pending`` until the next newline."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0
        self.pending: list[RawRedirect] = []

    def scan_list(self, depth: int, *, closer: bool) -> list[Token]:
        """Tokens up to the end of the text, or the ``)`` closing a substitution."""
        if depth > MAX_DEPTH:
            raise ScanLimit(f"nesting deeper than {MAX_DEPTH}")
        tokens: list[Token] = []
        groups = 0
        while self._skip_blanks():
            char = self.text[self.pos]
            if char == ")" and closer and groups == 0:
                self.pos += 1
                return tokens
            if char in "()":
                groups = max(groups + (1 if char == "(" else -1), 0)
                self.pos += 1
                tokens.append(Op(char))
            elif char == "#":
                end = self.text.find("\n", self.pos)
                self.pos = len(self.text) if end < 0 else end
            elif char == "\n":
                self.pos += 1
                self._read_heredocs(depth)
                tokens.append(Op("\n"))
            else:
                tokens.append(self._scan_token(depth))
        if closer:
            raise ScanError("unterminated command substitution")
        return tokens

    def _skip_blanks(self) -> bool:
        """Skip spaces, tabs and line continuations; whether any text remains."""
        while self.pos < len(self.text):
            if self.text[self.pos] in " \t":
                self.pos += 1
            elif self.text.startswith("\\\n", self.pos):
                self.pos += 2
            else:
                return True
        return False

    def _scan_token(self, depth: int) -> Token:
        if not self.text.startswith(_PROCESS_SUBSTITUTION, self.pos):
            match = _REDIRECT.match(self.text, self.pos)
            if match:
                return self._scan_redirect(match, depth)
            for op in _OPERATORS:
                if self.text.startswith(op, self.pos):
                    self.pos += len(op)
                    return Op(op)
        return self._scan_word(depth)

    def _scan_redirect(self, match: re.Match[str], depth: int) -> RawRedirect:
        fd, op = (int(match.group(1)) if match.group(1) else None), match.group(2)
        self.pos = match.end()
        if not self._skip_blanks() or (
            self.text[self.pos] in _WORD_END
            and not self.text.startswith(_PROCESS_SUBSTITUTION, self.pos)
        ):
            raise ScanError(f"redirection {op!r} without a target")
        target = self._scan_word(depth)
        if op not in ("<<", "<<-"):
            return RawRedirect(op, fd, target)
        heredoc = RawRedirect(op, fd, None, delimiter=target.resolve().value)
        heredoc.strip_tabs, heredoc.expands = op == "<<-", not target.quoted
        self.pending.append(heredoc)
        return heredoc

    def _read_heredocs(self, depth: int) -> None:
        """Read the bodies of the heredocs opened on the line that just ended."""
        pending, self.pending = self.pending, []
        for heredoc in pending:
            heredoc.body, self.pos = heredoc_body(self.text, self.pos, heredoc)
            if heredoc.expands:
                heredoc.substs = body_substitutions(heredoc.body, depth)

    def _scan_word(self, depth: int) -> RawWord:
        word = RawWord()
        if self.text.startswith(_PROCESS_SUBSTITUTION, self.pos):
            self._scan_substitution(word, depth)
        while self.pos < len(self.text) and self.text[self.pos] not in _WORD_END:
            char = self.text[self.pos]
            if char == "\\":
                self._scan_escape(word)
            elif char == "'":
                end = self.text.find("'", self.pos + 1)
                if end < 0:
                    raise ScanError("unbalanced single quote")
                word.chunks.append(self.text[self.pos : end + 1])
                word.quoted, self.pos = True, end + 1
            elif char == '"':
                self._scan_double(word, depth)
            elif char == "$":
                self.scan_dollar(word, depth, in_double=False)
            elif char == "`":
                self.scan_backtick(word, depth)
            else:
                self.pos = self._append_run(word, _PLAIN_RUN)
        return word

    def _scan_escape(self, word: RawWord) -> None:
        if self.pos + 1 >= len(self.text):
            raise ScanError("trailing backslash")
        if self.text[self.pos + 1] != "\n":  # a line continuation leaves nothing
            word.chunks.append(self.text[self.pos : self.pos + 2])
            word.quoted = True
        self.pos += 2

    def _scan_double(self, word: RawWord, depth: int) -> None:
        word.quoted = True
        word.chunks.append('"')
        self.pos += 1
        while self.pos < len(self.text):
            char = self.text[self.pos]
            if char == '"':
                word.chunks.append('"')
                self.pos += 1
                return
            if char == "\\":
                after = self.text[self.pos + 1 : self.pos + 2]
                # Any other backslash is literal inside double quotes; shlex needs it doubled.
                word.chunks.append(_DOUBLE_QUOTED_ESCAPES.get(after, "\\\\"))
                self.pos += 2 if after in _DOUBLE_QUOTED_ESCAPES else 1
            elif char == "$":
                self.scan_dollar(word, depth, in_double=True)
            elif char == "`":
                self.scan_backtick(word, depth)
            else:
                self.pos = self._append_run(word, _DOUBLE_QUOTED_RUN)
        raise ScanError("unbalanced double quote")

    def _append_run(self, word: RawWord, run: re.Pattern[str]) -> int:
        """Append the run of plain characters at the cursor; return the position after it."""
        match = run.match(self.text, self.pos)
        end = match.end() if match else self.pos + 1
        word.chunks.append(self.text[self.pos : end])
        return end

    def scan_dollar(self, word: RawWord, depth: int, *, in_double: bool) -> None:
        """Scan the expansion (or literal ``$``) at the cursor into ``word``."""
        if self.text.startswith("$((", self.pos):
            self._scan_balanced(word, depth, 3, "(", ")", "unterminated arithmetic expansion")
        elif self.text.startswith("$(", self.pos):
            self._scan_substitution(word, depth)
        elif self.text.startswith("${", self.pos):
            self._scan_balanced(word, depth, 2, "{", "}", "unterminated parameter expansion")
        elif not in_double and self.text.startswith("$'", self.pos):
            self._scan_ansi_c(word)
        elif not in_double and self.text.startswith('$"', self.pos):
            self.pos += 1
            self._scan_double(word, depth)
        elif match := _PARAM.match(self.text, self.pos + 1):
            word.chunks.append("$" + match.group())
            word.dynamic, self.pos = True, match.end()
        else:
            word.chunks.append("$")
            self.pos += 1

    def _scan_substitution(self, word: RawWord, depth: int) -> None:
        start = self.pos
        self.pos += 2  # "$(", "<(" or ">("
        tokens = self.scan_list(depth + 1, closer=True)
        word.placeholder(self.text[start : self.pos])
        word.substs.append(tokens)

    def _scan_balanced(
        self, word: RawWord, depth: int, skip: int, opener: str, closer: str, problem: str
    ) -> None:
        """``$((...))`` or ``${...}``; a substitution inside still runs, so it is scanned."""
        depth += 1  # nested expansions recurse here, so they count toward the depth limit
        if depth > MAX_DEPTH:
            raise ScanLimit(f"nesting deeper than {MAX_DEPTH}")
        start, level, inner = self.pos, skip - 1, RawWord()
        self.pos += skip
        while level:
            if self.pos >= len(self.text):
                raise ScanError(problem)
            char = self.text[self.pos]
            if char == "$":
                self.scan_dollar(inner, depth, in_double=True)
            elif char == "`":
                self.scan_backtick(inner, depth)
            elif char == "\\":
                self.pos += 2
            else:
                level += (char == opener) - (char == closer)
                self.pos += 1
        word.placeholder(self.text[start : self.pos])
        word.substs.extend(inner.substs)

    def scan_backtick(self, word: RawWord, depth: int) -> None:
        """A backquoted substitution: unescape its body, then scan it as its own text."""
        start, chars = self.pos, []
        self.pos += 1
        while True:
            if self.pos >= len(self.text):
                raise ScanError("unterminated backquote")
            char = self.text[self.pos]
            if char == "`":
                break
            if char == "\\" and self.text[self.pos + 1 : self.pos + 2] in ("`", "\\", "$"):
                self.pos += 1
                char = self.text[self.pos]
            chars.append(char)
            self.pos += 1
        self.pos += 1
        word.placeholder(self.text[start : self.pos])
        word.substs.append(scan("".join(chars), depth + 1))

    def _scan_ansi_c(self, word: RawWord) -> None:
        """``$'...'``: an escape-decoding single quote."""
        end = self.pos + 2
        while end < len(self.text) and self.text[end] != "'":
            end += 2 if self.text[end] == "\\" else 1
        if end >= len(self.text):
            raise ScanError("unbalanced $'...' quote")
        word.chunks.append(ansi_c_word(self.text[self.pos + 2 : end]))
        word.quoted, self.pos = True, end + 1
