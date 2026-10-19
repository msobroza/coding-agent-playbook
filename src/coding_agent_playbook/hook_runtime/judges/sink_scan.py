"""The unsafe-sink visitor: which sink calls an edit adds (specs/prK-hook-pack.md §E.3).

ml-unsafe-deserialization-guard, its twin ``playbook scan-sinks`` and K8's
Stop rescan share this one pure implementation: text in, findings out.

- :class:`SinkTable` is the hook's ``config.block`` / ``config.warn`` rows:
  ``{call, kwarg?, missing?, unless?, advice?}``. ``call`` is a dotted
  pattern (``pickle.loads``, ``subprocess.*``, ``*.from_pretrained``, ``*``);
  ``kwarg`` names literal keyword values that must be present, ``missing``
  keywords that must be absent, ``unless`` keyword values (last dotted part)
  that make the call safe. A block row wins over a warn row.
- A call site is ``(callee resolved through import aliases, its keyword
  arguments)``; ``np`` and ``pd`` resolve conventionally when not imported
  (a notebook cell rarely repeats its imports).
- :func:`new_sink_calls` counts ``post - pre`` as multisets, so a sink the
  edit leaves alone never counts. When either text does not parse, both are
  scanned by the regex fallback, keeping the two counts comparable.

``ast`` and ``fnmatch`` load only on this branch (§D.1); the regex fallback
(``_sink_regex``) only when a text does not parse.
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

__all__ = [
    "CONVENTIONAL_ALIASES",
    "EXPR",
    "PRAGMA",
    "SPLAT",
    "Keyword",
    "SinkCall",
    "SinkHit",
    "SinkRow",
    "SinkTable",
    "new_sink_calls",
    "resolve_alias",
    "sink_calls",
    "trusted_artifact_line",
]

type SinkKind = Literal["block", "warn"]
#: A keyword argument as compared: its name and a literal ``repr``, dotted name or ``EXPR``.
type Keyword = tuple[str, str]

#: The value of a keyword argument that is neither a literal nor a dotted name.
EXPR: Final = "<expr>"
#: ``**kwargs``: any keyword may be there, so a ``missing`` row cannot match.
SPLAT: Final = "**"
#: Names that mean these modules even unimported: a notebook cell's ``np`` was imported
#: in another cell, and an ML snippet's ``np.load`` is numpy's in practice.
CONVENTIONAL_ALIASES: Final[Mapping[str, str]] = {"np": "numpy", "pd": "pandas"}
_ROW_KEYS: Final = frozenset({"call", "kwarg", "missing", "unless", "advice"})
#: The escape: a provenance must follow the marker.
PRAGMA: Final = re.compile(r"#\s*playbook:\s*trusted-artifact\s+\S")


@dataclass(frozen=True, slots=True)
class SinkRow:
    """One table row (module docstring); ``kind`` says which list it came from.

    Example: ``SinkRow("torch.load", "block", kwarg=(("weights_only", "False"),))``.
    """

    call: str
    kind: SinkKind
    kwarg: tuple[Keyword, ...] = ()
    missing: tuple[str, ...] = ()
    unless: tuple[tuple[str, frozenset[str]], ...] = ()
    advice: str = ""

    def matches(self, callee: str, keywords: frozenset[Keyword]) -> bool:
        """Whether a call of ``callee`` with ``keywords`` is this row's sink."""
        if not fnmatchcase(callee, self.call):
            return False
        names = {name for name, _ in keywords}
        if any(pair not in keywords for pair in self.kwarg):
            return False
        if self.missing and (SPLAT in names or names.intersection(self.missing)):
            return False
        return not any(_safe_value(keywords, name, safe) for name, safe in self.unless)


def _safe_value(keywords: frozenset[Keyword], name: str, safe: frozenset[str]) -> bool:
    return any(key == name and value.rsplit(".", 1)[-1] in safe for key, value in keywords)


@dataclass(frozen=True, slots=True)
class SinkTable:
    """The rows a scan matches, block rows first.

    Example::

        >>> SinkTable.from_config({"block": [{"call": "pickle.loads"}]}).rows[0].kind
        'block'
    """

    rows: tuple[SinkRow, ...] = ()

    @classmethod
    def from_config(cls, config: Mapping[str, object]) -> SinkTable:
        """The table of a hook config's ``block`` / ``warn`` lists; ``ValueError`` names a bad row."""
        rows = [row for kind in ("block", "warn") for row in _rows(config.get(kind), kind)]
        return cls(tuple(rows))

    def classify(self, callee: str, keywords: frozenset[Keyword]) -> SinkRow | None:
        """The first row the call matches (block rows come first), else ``None``."""
        return next((row for row in self.rows if row.matches(callee, keywords)), None)


def _rows(raw: object, kind: SinkKind) -> Iterator[SinkRow]:
    if raw is None:
        return
    if not isinstance(raw, list):
        raise ValueError(f"{kind}: expected a list of sink rows, got {raw!r}")
    for index, row in enumerate(raw):
        yield _row(row, f"{kind}[{index}]", kind)


def _row(raw: object, where: str, kind: SinkKind) -> SinkRow:
    if not isinstance(raw, dict) or not isinstance(raw.get("call"), str):
        raise ValueError(f"{where}: expected a table with a string 'call', got {raw!r}")
    unknown = sorted(set(raw) - _ROW_KEYS)
    if unknown:
        raise ValueError(f"{where}: unknown keys {unknown!r}; allowed: {sorted(_ROW_KEYS)}")
    kwarg, unless = raw.get("kwarg") or {}, raw.get("unless") or {}
    missing, advice = raw.get("missing") or [], raw.get("advice") or ""
    if not (isinstance(kwarg, dict) and isinstance(unless, dict) and isinstance(missing, list)):
        raise ValueError(f"{where}: kwarg/unless must be tables and missing a list, got {raw!r}")
    return SinkRow(
        call=raw["call"],
        kind=kind,
        kwarg=tuple((str(name), repr(value)) for name, value in kwarg.items()),
        missing=tuple(str(name) for name in missing),
        unless=tuple((str(name), frozenset(map(str, safe))) for name, safe in unless.items()),
        advice=str(advice),
    )


@dataclass(frozen=True, slots=True)
class SinkCall:
    """One call site: resolved ``callee``, its keyword arguments and 1-based ``line``."""

    callee: str
    keywords: frozenset[Keyword]
    line: int

    @property
    def key(self) -> tuple[str, frozenset[Keyword]]:
        """What the multiset counts: the call without its position."""
        return (self.callee, self.keywords)


@dataclass(frozen=True, slots=True)
class SinkHit:
    """A new sink call, the row it matched and its stripped source line.

    Example: ``hit.kind == "block"`` for an added ``pickle.loads(data)``.
    """

    call: SinkCall
    row: SinkRow
    line_text: str = ""

    @property
    def callee(self) -> str:
        return self.call.callee

    @property
    def kind(self) -> SinkKind:
        return self.row.kind

    @property
    def line(self) -> int:
        return self.call.line


def new_sink_calls(pre_text: str | None, post_text: str, table: SinkTable) -> list[SinkHit]:
    """The sink calls ``post_text`` has beyond ``pre_text`` (``None``: a new file), in line order.

    Example::

        >>> table = SinkTable.from_config({"block": [{"call": "pickle.loads"}]})
        >>> [h.line for h in new_sink_calls("", "import pickle\\npickle.loads(b)\\n", table)]
        [2]
    """
    pre, post = pre_text or "", post_text
    pre_calls, post_calls = sink_calls(pre, table), sink_calls(post, table)
    if pre_calls is None or post_calls is None:
        from coding_agent_playbook.hook_runtime.handlers._sink_regex import regex_sink_calls

        pre_calls, post_calls = regex_sink_calls(pre, table), regex_sink_calls(post, table)
    extra = Counter(call.key for call in post_calls) - Counter(call.key for call in pre_calls)
    lines, old = post.splitlines(), Counter(_text(pre.splitlines(), c) for c in pre_calls)
    hits: list[SinkHit] = []
    for call in _fresh_first(post_calls, lines, old):
        if extra[call.key] > 0:
            extra[call.key] -= 1
            row = table.classify(call.callee, call.keywords)
            assert row is not None  # sink_calls keeps only calls a row matches
            hits.append(SinkHit(call, row, _text(lines, call)))
    return sorted(hits, key=lambda hit: hit.line)


def _fresh_first(calls: list[SinkCall], lines: list[str], old: Counter[str]) -> list[SinkCall]:
    """``calls`` whose line text is not already in the old text first: those are the new ones."""
    fresh: list[SinkCall] = []
    kept: list[SinkCall] = []
    for call in calls:
        text = _text(lines, call)
        if old[text] > 0:
            old[text] -= 1
            kept.append(call)
        else:
            fresh.append(call)
    return [*fresh, *kept]


def _text(lines: list[str], call: SinkCall) -> str:
    return lines[call.line - 1].strip() if 0 < call.line <= len(lines) else ""


# --- the ast visitor --------------------------------------------------------------------------


def sink_calls(text: str, table: SinkTable) -> list[SinkCall] | None:
    """Every call in ``text`` a row matches, or ``None`` when ``text`` does not parse.

    Example::

        >>> sink_calls("def f(:", SinkTable()) is None
        True
    """
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):  # ValueError: a NUL byte in the source
        return None
    aliases = {**CONVENTIONAL_ALIASES, **_ast_aliases(tree)}
    found: list[SinkCall] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        call = SinkCall(resolve_alias(_callee(node.func), aliases), _keywords(node), node.lineno)
        if table.classify(call.callee, call.keywords) is not None:
            found.append(call)
    return sorted(found, key=lambda call: call.line)  # ast.walk is breadth-first


def _ast_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                local = name.asname or name.name.split(".")[0]
                aliases[local] = name.name if name.asname else local
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for name in node.names:
                aliases[name.asname or name.name] = f"{node.module}.{name.name}"
    return aliases


def _callee(func: ast.expr) -> str:
    parts: list[str] = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    parts.append(func.id if isinstance(func, ast.Name) else "?")
    return ".".join(reversed(parts))


def _keywords(node: ast.Call) -> frozenset[Keyword]:
    return frozenset((kw.arg or SPLAT, _value(kw.value)) for kw in node.keywords)


def _value(node: ast.expr) -> str:
    if isinstance(node, ast.Constant):
        return repr(node.value)
    dotted = _callee(node) if isinstance(node, ast.Name | ast.Attribute) else "?"
    return EXPR if dotted.startswith("?") else dotted


def resolve_alias(dotted: str, aliases: Mapping[str, str]) -> str:
    """``dotted`` with its first part replaced by what ``aliases`` binds it to.

    Example::

        >>> resolve_alias("pk.loads", {"pk": "pickle"})
        'pickle.loads'
    """
    head, _, rest = dotted.partition(".")
    base = aliases.get(head, head)
    return f"{base}.{rest}" if rest else base


def trusted_artifact_line(text: str, line: int) -> str | None:
    """The stripped line holding a trusted-artifact pragma for a call on ``line``, else ``None``.

    The pragma counts on the call line itself or on the line above.

    Example::

        >>> trusted_artifact_line("# playbook: trusted-artifact s3://m/v3\\nm = load(p)\\n", 2)
        '# playbook: trusted-artifact s3://m/v3'
    """
    lines = text.splitlines()
    for number in (line, line - 1):
        if 0 < number <= len(lines) and PRAGMA.search(lines[number - 1]):
            return lines[number - 1].strip()
    return None
