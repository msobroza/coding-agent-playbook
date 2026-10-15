"""Secret-token scanning: one library for the guard, the Stop sweep and the twin (specs/prK-hook-pack.md §E.4).

secret-content-guard (pre-write), stop-diff-sweep (Stop) and ``playbook
scan-secrets`` (pre-commit and CI) all call :func:`scan_text`,
:func:`scan_bounded` or :func:`scan_added_lines`, so they flag the same
tokens. A :class:`SecretFinding` names the rule, the place and the match
length, and carries **no character of the value**: model-facing and CI text
built from it can never leak the secret it reports.

The rules are ``security.patterns.SECRET_CONTENT_RULES``, compiled once here.
Lockfiles and binaries (NUL in the first 8 KiB) are skipped; a notebook's JSON
is parsed and only cell sources and text outputs are scanned, never base64
images. :func:`screen_regex` vets an overlay- or repo-supplied regex before
anything compiles it. Stdlib ``re`` only (``json`` loads on the notebook branch).
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final, Protocol

from coding_agent_playbook.security.patterns import (
    ALLOW_SECRET_PRAGMA,
    EXAMPLE_SECRET_ALLOWLIST,
    SECRET_CONTENT_RULES,
    SECRET_SCAN_SKIP_NAMES,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence

__all__ = [
    "DEFAULT_RULES",
    "MAX_REGEX_CHARS",
    "MAX_SCAN_BYTES",
    "PARTIAL_WINDOW_BYTES",
    "SECRET_ADVICE",
    "AddedText",
    "BoundedScan",
    "SecretFinding",
    "SecretRule",
    "allow_secret_rules",
    "compile_rules",
    "is_binary",
    "is_skipped_name",
    "scan_added_lines",
    "scan_bounded",
    "scan_text",
    "screen_regex",
]

#: The safe alternative every secret finding names (guard reasons, Stop lines, the twin).
SECRET_ADVICE: Final = "Use an env var or the secret manager and reference it by name."
#: Text above this is scanned only at its head and tail (secret-content-guard's cap).
MAX_SCAN_BYTES: Final = 1024 * 1024
#: The head and the tail an oversized text keeps.
PARTIAL_WINDOW_BYTES: Final = 256 * 1024
#: A NUL byte in this many leading characters marks the content binary.
BINARY_SNIFF_CHARS: Final = 8 * 1024
#: Longer overlay or repo regexes are rejected by :func:`screen_regex`.
MAX_REGEX_CHARS: Final = 512

_PRAGMA: Final = re.compile(ALLOW_SECRET_PRAGMA)
_RULE_ID: Final = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_PRAGMA_HINT: Final = "allow-secret"
#: An added notebook line that is an embedded image or a bare base64 chunk.
_NOTEBOOK_PAYLOAD: Final = re.compile(
    r'^\s*"(?:image/[^"]*|application/pdf)":\s*"|^\s*"[A-Za-z0-9+/=]{76,}(?:\\n)?",?\s*$'
)


@dataclass(frozen=True, slots=True)
class SecretRule:
    """One compiled content rule.

    Example: ``SecretRule("jwt", re.compile(r"eyJ..."), "JSON Web Token")``.
    """

    rule_id: str
    regex: re.Pattern[str]
    label: str


@dataclass(frozen=True, slots=True)
class SecretFinding:
    """A rule hit: where, which rule, how long; never the matched text.

    ``line`` is 1-based, or 0 for a hit somewhere in a notebook's cells.
    ``pragma`` says the line carries an ``allow-secret`` pragma naming this
    rule; whether it counts (committed at the base) is the caller's call.

    Example::

        >>> str(SecretFinding("jwt", "JSON Web Token", "a.py", 3, 120))
        'a.py:3: jwt: JSON Web Token (120 chars)'
    """

    rule_id: str
    label: str
    path: str
    line: int
    length: int
    pragma: bool = False

    @property
    def location(self) -> str:
        """``path:line``, or ``path`` alone for a notebook finding."""
        return self.path if self.line == 0 else f"{self.path}:{self.line}"

    def __str__(self) -> str:
        return f"{self.location}: {self.rule_id}: {self.label} ({self.length} chars)"

    def to_json(self) -> dict[str, object]:
        """``{path, line, rule, label, length}`` for the twins' JSON reports."""
        return {
            "path": self.path,
            "line": self.line,
            "rule": self.rule_id,
            "label": self.label,
            "length": self.length,
        }


@dataclass(frozen=True, slots=True)
class BoundedScan:
    """:func:`scan_bounded`'s result: the findings and whether the middle went unscanned."""

    findings: tuple[SecretFinding, ...]
    partial: bool


class AddedLineLike(Protocol):
    """An added diff line: ``hook_runtime``'s ``AddedLine`` or :class:`AddedText`."""

    @property
    def path(self) -> str: ...

    @property
    def line(self) -> int: ...

    @property
    def text(self) -> str: ...


@dataclass(frozen=True, slots=True)
class AddedText:
    """A plain :class:`AddedLineLike` (``security`` never imports ``hook_runtime``).

    Example: ``AddedText("src/a.py", 4, "x = 1")``.
    """

    path: str
    line: int
    text: str


def compile_rules(sources: Iterable[tuple[str, str, str]]) -> tuple[SecretRule, ...]:
    """Compile ``(rule id, regex source, label)`` rows; ``re.error`` names a bad source.

    Example::

        >>> compile_rules([("x", "X-[0-9]{4}", "demo")])[0].rule_id
        'x'
    """
    return tuple(SecretRule(rule_id, re.compile(src), label) for rule_id, src, label in sources)


#: The engine's rules, compiled once per process.
DEFAULT_RULES: Final = compile_rules(SECRET_CONTENT_RULES)


def scan_text(
    text: str, path: str, *, rules: Sequence[SecretRule] = DEFAULT_RULES
) -> list[SecretFinding]:
    """Every secret token in ``text`` (the whole content of ``path``), in text order.

    Example::

        >>> [f.rule_id for f in scan_text("k = " + "AKIA" + "Z7Q2" * 4, "a.py")]
        ['aws-access-key-id']
    """
    if is_skipped_name(path) or is_binary(text):
        return []
    if path.lower().endswith(".ipynb"):
        chunks = _notebook_texts(text)
        if chunks is not None:
            return [replace(f, line=0) for chunk in chunks for f in _scan(chunk, path, rules)]
    return _scan(text, path, rules)


def scan_bounded(
    text: str,
    path: str,
    *,
    rules: Sequence[SecretRule] = DEFAULT_RULES,
    max_bytes: int = MAX_SCAN_BYTES,
    window: int = PARTIAL_WINDOW_BYTES,
) -> BoundedScan:
    """:func:`scan_text`, but above ``max_bytes`` only the head and tail ``window`` bytes.

    Both windows are cut at line ends, and tail findings keep their real line
    numbers. ``partial`` tells the guard to ask rather than pass.

    Example::

        >>> scan_bounded("x = 1\\n", "a.py").partial
        False
    """
    data = text.encode("utf-8", errors="replace")
    if len(data) <= max_bytes or is_skipped_name(path) or is_binary(text):
        return BoundedScan(tuple(scan_text(text, path, rules=rules)), partial=False)
    head_end = data.rfind(b"\n", 0, window) + 1 or window
    tail_start = data.find(b"\n", len(data) - window) + 1 or len(data) - window
    head = _scan(data[:head_end].decode("utf-8", errors="replace"), path, rules)
    tail_first_line = data.count(b"\n", 0, tail_start) + 1
    tail_text = data[tail_start:].decode("utf-8", errors="replace")
    tail = _scan(tail_text, path, rules, first_line=tail_first_line)
    return BoundedScan((*head, *tail), partial=True)


def scan_added_lines(
    lines: Iterable[AddedLineLike], *, rules: Sequence[SecretRule] = DEFAULT_RULES
) -> list[SecretFinding]:
    """Every secret token on the added lines of a diff, at each line's new number.

    Lockfiles and a notebook's embedded image lines are skipped. One regex
    pass covers all lines, so a large diff costs one scan per rule.

    Example::

        >>> scan_added_lines([AddedText("a.py", 7, "x = 1")])
        []
    """
    kept = [line for line in lines if not _skipped_added(line)]
    joined = "\n".join(line.text for line in kept)
    found = _scan(joined, "", rules)
    return [replace(f, path=kept[f.line - 1].path, line=kept[f.line - 1].line) for f in found]


def allow_secret_rules(line: str) -> frozenset[str]:
    """The rule ids an ``allow-secret`` pragma on ``line`` names (empty: no pragma, or no id).

    A bare pragma waives nothing: each waiver names the rule it is for.

    Example::

        >>> sorted(allow_secret_rules("k = x  # playbook: allow-secret jwt, slack-token"))
        ['jwt', 'slack-token']
    """
    match = _PRAGMA.search(line)
    if match is None:
        return frozenset()
    tokens = re.split(r"[\s,]+", match["rules"].strip())
    return frozenset(token for token in tokens if _RULE_ID.fullmatch(token))


def is_skipped_name(path: str) -> bool:
    """Whether ``path`` is a lockfile the scanners never read for content.

    Example::

        >>> is_skipped_name("web/package-lock.json")
        True
    """
    return posixpath.basename(path) in SECRET_SCAN_SKIP_NAMES


def is_binary(text: str) -> bool:
    """Whether ``text`` has a NUL in its first 8 Ki characters (git's own binary sniff).

    Example::

        >>> is_binary("PK\\x03\\x04\\x00")
        True
    """
    return "\x00" in text[:BINARY_SNIFF_CHARS]


def screen_regex(pattern: str) -> str | None:
    """Why ``pattern`` is unsafe to run on agent-controlled text, or ``None`` when it is fine.

    Rejects patterns over :data:`MAX_REGEX_CHARS`, patterns that do not
    compile, and nested unbounded quantifiers (``(a+)+``, ``(a*)*``), the
    shape behind catastrophic backtracking. ``playbook validate`` runs it on
    every overlay- or repo-supplied regex of §E.4.

    Example::

        >>> screen_regex(r"^uv run (mypy|pytest)\\b") is None
        True
        >>> screen_regex("(a+)+$")  # doctest: +ELLIPSIS
        "regex '(a+)+$' nests unbounded quantifiers..."
    """
    if len(pattern) > MAX_REGEX_CHARS:
        return f"regex is {len(pattern)} characters long; the limit is {MAX_REGEX_CHARS}"
    try:
        re.compile(pattern)
        from coding_agent_playbook.security._regex_shape import has_nested_unbounded_repeat

        nested = has_nested_unbounded_repeat(pattern)
    except re.error as exc:
        return f"regex {pattern!r} does not compile: {exc}"
    except RecursionError:
        return f"regex {pattern!r} is nested too deeply to check"
    if nested:
        return (
            f"regex {pattern!r} nests unbounded quantifiers (like (a+)+), which can "
            "backtrack catastrophically; bound the inner or the outer repeat"
        )
    return None


def _scan(
    text: str, path: str, rules: Sequence[SecretRule], *, first_line: int = 1
) -> list[SecretFinding]:
    """Findings of ``rules`` in ``text`` whose line 1 is ``first_line``, in text order."""
    hits = sorted(
        (match.start(), match.end(), rule)
        for rule in rules
        for match in rule.regex.finditer(text)
        if match.group() not in EXAMPLE_SECRET_ALLOWLIST
    )
    findings: list[SecretFinding] = []
    line, counted = first_line, 0
    check_pragma = _PRAGMA_HINT in text
    for start, end, rule in hits:
        line += text.count("\n", counted, start)
        counted = start
        pragma = check_pragma and rule.rule_id in allow_secret_rules(_line_at(text, start))
        findings.append(SecretFinding(rule.rule_id, rule.label, path, line, end - start, pragma))
    return findings


def _line_at(text: str, offset: int) -> str:
    """The whole line of ``text`` holding ``offset``."""
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    return text[start : end if end >= 0 else len(text)]


def _skipped_added(line: AddedLineLike) -> bool:
    if is_skipped_name(line.path):
        return True
    return line.path.lower().endswith(".ipynb") and _NOTEBOOK_PAYLOAD.search(line.text) is not None


def _notebook_texts(text: str) -> list[str] | None:
    """The cell sources and text outputs of notebook JSON ``text``; ``None`` if not a notebook."""
    import json

    try:
        doc = json.loads(text)
    except (ValueError, RecursionError):
        return None
    cells = doc.get("cells") if isinstance(doc, dict) else None
    if not isinstance(cells, list):
        return None
    return [chunk for cell in cells if isinstance(cell, dict) for chunk in _cell_texts(cell)]


def _cell_texts(cell: dict[str, object]) -> Iterator[str]:
    yield _joined(cell.get("source"))
    outputs = cell.get("outputs")
    for output in outputs if isinstance(outputs, list) else ():
        if not isinstance(output, dict):
            continue
        for key in ("text", "traceback", "evalue"):
            yield _joined(output.get(key))
        data = output.get("data")
        if isinstance(data, dict):
            yield from (_joined(v) for mime, v in data.items() if str(mime).startswith("text/"))


def _joined(value: object) -> str:
    """nbformat's multiline string: a string or a list of strings."""
    if isinstance(value, list):
        return "".join(part for part in value if isinstance(part, str))
    return value if isinstance(value, str) else ""
