"""Rewrite only owned prose and TOML values; historical records are immutable."""

from __future__ import annotations

import ast
import io
import re
import tokenize
import tomllib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from tests.architecture._module_move_common import (
    SourcePositions,
    apply_edits,
    docstring_nodes,
    rewrite_lines,
)
from tests.architecture._module_move_python import literal_target
from tests.architecture._module_move_resolve import compose

if TYPE_CHECKING:
    from collections.abc import Iterator

    from tests.architecture._module_move_resolve import Resolver
    from tests.architecture.module_moves import MoveMap

KEEP = "<!-- module-moves: keep -->"
START = "<!-- module-moves:start -->"
END = "<!-- module-moves:end -->"
_DOTTED = re.compile(
    r"(?<![\w.])[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+(?::[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)?"
)
_PATH = re.compile(r"(?<![\w./-])(?:[A-Za-z_]\w*/)+[\w./-]*|(?<![\w./-])[A-Za-z_]\w*\.py\b")
_QUOTED = re.compile(r""""(?:\\.|[^"\\])*"|'[^']*' """, re.VERBOSE)


@dataclass
class _ProseState:
    keep: bool = False
    generated: bool = False

    def skip_line(self, line: str) -> bool:
        if KEEP in line:
            self.keep = not self.keep
        if START in line:
            self.generated = True
        protected = self.keep or self.generated or KEEP in line
        if END in line:
            self.generated = False
        return protected


def _closed(state: _ProseState) -> None:
    for unclosed, opening, closing in ((state.keep, KEEP, KEEP), (state.generated, START, END)):
        if unclosed:
            raise ValueError(f"Unclosed module-moves marker {opening!r}; expected {closing!r}")


def path_map(moves: MoveMap) -> dict[str, str]:
    """Derive doc paths and add split/test overrides; e.g. path_map(moves)."""
    pairs = {}
    for move in moves.modules:
        if not move.old.startswith("coding_agent_playbook."):
            continue
        suffix = "/" if move.package else ".py"
        old = move.old.removeprefix("coding_agent_playbook.").replace(".", "/") + suffix
        new = (
            compose(move.old, moves).removeprefix("coding_agent_playbook.").replace(".", "/")
            + suffix
        )
        pairs[old] = new
    pairs.update((move.old, move.new) for move in moves.paths)
    return pairs


def _path_target(value: str, resolver: Resolver) -> str:
    punctuation = value[len(value.rstrip(".")) :]
    value = value.rstrip(".")
    prefix = "src/coding_agent_playbook/" if value.startswith("src/coding_agent_playbook/") else ""
    relative = value.removeprefix(prefix)
    if not prefix and "/" not in relative:
        return value + punctuation
    pairs = path_map(resolver.moves)
    return prefix + _compose_path(relative, pairs) + punctuation


def _compose_path(relative: str, pairs: dict[str, str]) -> str:
    seen: set[str] = set()
    for _ in range(len(pairs) + 1):
        if relative in seen:
            raise ValueError(f"Non-idempotent path move at {relative!r}")
        seen.add(relative)
        match = next(
            (
                old
                for old in sorted(pairs, key=len, reverse=True)
                if relative == old or (old.endswith("/") and relative.startswith(old))
            ),
            None,
        )
        if match is None:
            return relative
        relative = pairs[match] + relative[len(match) :]
    raise ValueError(f"Non-idempotent path move at {relative!r}")


def validate_paths(moves: MoveMap) -> None:
    """Reject path cycles before any file is opened; e.g. validate_paths(moves)."""
    pairs = path_map(moves)
    for old in pairs:
        _compose_path(old, pairs)


def _dotted_target(match: re.Match[str], resolver: Resolver, *, prose: bool) -> str:
    value = match.group()
    if prose and (
        not value.startswith("coding_agent_playbook.")
        or value.startswith(("coding_agent_playbook.plugins.", "coding_agent_playbook.packs."))
    ):
        return value
    return literal_target(value, resolver) or value


def _prose_line(line: str, resolver: Resolver, state: _ProseState) -> str:
    if state.skip_line(line):
        return line
    rewritten = _DOTTED.sub(lambda m: _dotted_target(m, resolver, prose=True), line)
    return _PATH.sub(lambda m: _path_target(m.group(), resolver), rewritten)


def rewrite_prose(
    source: str,
    resolver: Resolver,
    *,
    state: _ProseState | None = None,
    line_offset: int = 0,
) -> tuple[str, list[str]]:
    """Preserve marked history while rewriting mapped paths; e.g. rewrite_prose(readme, r)."""
    shared = state is not None
    state = state or _ProseState()
    result = rewrite_lines(
        source, lambda line: _prose_line(line, resolver, state), line_offset=line_offset
    )
    if not shared:
        _closed(state)
    return result


def bare_reviews(source: str, moves: MoveMap) -> list[str]:
    """Report ambiguous filenames without treating them as stale; e.g. bare_reviews(readme, moves)."""
    bare = {old.rsplit("/", 1)[-1] for old in path_map(moves) if old.endswith(".py")}
    findings = []
    state = _ProseState()
    for number, line in enumerate(source.splitlines(), 1):
        if state.skip_line(line):
            continue
        for name in sorted(bare):
            if re.search(r"(?<![\w./-])" + re.escape(name) + r"(?![\w/])", line):
                findings.append(f"{number}: bare {name!r}")
    return findings


def _outside_quotes(line: str, delimiter: str) -> int:
    quoted = {
        index for match in _QUOTED.finditer(line) for index in range(match.start(), match.end())
    }
    return next(
        (index for index, char in enumerate(line) if char == delimiter and index not in quoted),
        len(line),
    )


def _table_header(line: str) -> tuple[str, ...] | None:
    if not line.strip().startswith("["):
        return None
    try:
        value: object = tomllib.loads(line)
    except tomllib.TOMLDecodeError:
        return None
    parts = []
    while isinstance(value, dict) and len(value) == 1:
        key, value = next(iter(value.items()))
        parts.append(str(key))
        if isinstance(value, list) and len(value) == 1:
            value = value[0]
    return tuple(parts)


@dataclass
class _TomlScope:
    section: tuple[str, ...] = ()
    key: str = ""

    def assignment(self, content: str) -> tuple[str, str]:
        assignment_at = _outside_quotes(content, "=")
        if assignment_at == len(content):
            return "", content
        key_text = content[:assignment_at].strip()
        self.key = next(iter(tomllib.loads(key_text + " = 0")))
        return content[: assignment_at + 1], content[assignment_at + 1 :]

    def active(self) -> bool:
        return (
            self.section == ("project", "scripts")
            or self.section[:2] == ("project", "entry-points")
            or (
                self.section[:2] == ("tool", "importlinter")
                and self.key not in {"layers", "exhaustive_ignores"}
            )
        )


def _toml_line(line: str, resolver: Resolver, scope: _TomlScope) -> str:
    comment_at = _outside_quotes(line, "#")
    content, comment = line[:comment_at], line[comment_at:]
    header = _table_header(content)
    if header is not None:
        scope.section, scope.key = header, ""
        return line
    prefix, content = scope.assignment(content)
    if scope.active():
        content = _QUOTED.sub(
            lambda q: _DOTTED.sub(lambda m: _dotted_target(m, resolver, prose=False), q.group()),
            content,
        )
    return prefix + content + comment


def rewrite_toml(source: str, resolver: Resolver) -> tuple[str, list[str]]:
    """Rewrite entry-point/import-linter values, preserving headers; e.g. rewrite_toml(pyproject, r)."""
    scope = _TomlScope()
    return rewrite_lines(source, lambda line: _toml_line(line, resolver, scope))


def _prose_tokens(source: str, positions: SourcePositions) -> Iterator[tokenize.TokenInfo]:
    doc_ranges = [positions.span(node) for node in docstring_nodes(ast.parse(source))]
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            yield token
            continue
        if token.type != tokenize.STRING:
            continue
        start, end = positions.offset(*token.start), positions.offset(*token.end)
        if any(first <= start and end <= last for first, last in doc_ranges):
            yield token


def rewrite_python_prose(source: str, resolver: Resolver) -> tuple[str, list[str]]:
    """Edit docstrings/comments only; e.g. rewrite_python_prose(source, resolver)."""
    positions = SourcePositions(source)
    edits: list[tuple[int, int, str]] = []
    findings: list[str] = []
    state = _ProseState()
    for token in _prose_tokens(source, positions):
        rewritten, reports = rewrite_prose(
            token.string, resolver, state=state, line_offset=token.start[0] - 1
        )
        if rewritten != token.string:
            start, end = positions.offset(*token.start), positions.offset(*token.end)
            edits.append((start, end, rewritten))
            findings.extend(reports)
    _closed(state)
    return apply_edits(source, edits), findings


def rewrite_workflow(source: str, resolver: Resolver) -> tuple[str, list[str]]:
    """Update workflow comments only; e.g. rewrite_workflow(ci_yaml, resolver)."""
    result: list[str] = []
    findings: list[str] = []
    state = _ProseState()
    for number, line in enumerate(source.splitlines(keepends=True), 1):
        comment_at = _outside_quotes(line, "#")
        rewritten, reports = rewrite_prose(
            line[comment_at:], resolver, state=state, line_offset=number - 1
        )
        result.append(line[:comment_at] + rewritten)
        findings.extend(reports)
    _closed(state)
    return "".join(result), findings


def _public_path(name: str) -> bool:
    return not any(part.startswith("_") for part in name.split("."))


def migration_section(source: str, resolver: Resolver) -> str:
    """Refresh the public module migration table; e.g. migration_section(migration, r)."""
    if not resolver.moves.modules and not resolver.moves.names:
        return source
    candidates = {move.old: compose(move.old, resolver.moves) for move in resolver.moves.modules}
    candidates.update(
        (f"{move.old}.{name}", compose(f"{move.old}.{name}", resolver.moves))
        for move in resolver.moves.names
        for name in move.names
    )
    # §7.4 N1 requires a row when a private module becomes the public toml_writer.
    rows = {old: new for old, new in candidates.items() if _public_path(old) or _public_path(new)}
    body = "\n### Module paths\n\n| Old | New |\n| --- | --- |\n" + "".join(
        f"| `{old}` | `{new}` |\n" for old, new in sorted(rows.items())
    )
    block = START + "\n" + body + "\n" + END
    if START in source:
        before, _, rest = source.partition(START)
        _, sep, after = rest.partition(END)
        if not sep:
            raise ValueError(f"Missing {END!r} in MIGRATION.md")
        return before + block + after
    return source.rstrip() + "\n\n" + block + "\n"
