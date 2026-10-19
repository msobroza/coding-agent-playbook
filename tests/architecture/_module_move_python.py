"""AST-located edits keep Python comments, literal spelling and indentation intact."""

from __future__ import annotations

import ast
import io
import re
import tokenize
from typing import TYPE_CHECKING

from tests.architecture._module_move_common import SourcePositions, apply_edits, docstring_nodes

if TYPE_CHECKING:
    from collections.abc import Iterator

    from tests.architecture._module_move_resolve import Resolver


def literal_target(value: str, resolver: Resolver) -> str | None:
    """Resolve only whole dotted or entry-point values; e.g. literal_target('pkg.old:C', r)."""
    if not re.fullmatch(
        r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+(?::[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)?", value
    ):
        return None
    module, colon, member = value.partition(":")
    replacement = resolver.resolve(module + ("." + member if colon else ""))
    if replacement and colon:
        return replacement[: -len(member) - 1] + ":" + member
    return replacement


def _alias(name: str, local: str | None) -> str:
    return name + (f" as {local}" if local and local != name else "")


def _import_destination(module: str, alias: ast.alias, resolver: Resolver) -> tuple[str, str]:
    full = f"{module}.{alias.name}"
    target = resolver.module_object(full)
    if target:
        parent, _, leaf = target.rpartition(".")
        return parent, _alias(leaf, alias.asname or alias.name)
    parent = resolver.resolve(module) or module
    return parent, _alias(alias.name, alias.asname)


def _replace_from_module(segment: str, module: str) -> str:
    tokens = list(tokenize.generate_tokens(io.StringIO(segment).readline))
    boundary = next(index for index, token in enumerate(tokens) if token.string == "import")
    module_tokens = [
        token for token in tokens[1:boundary] if token.type in {tokenize.NAME, tokenize.OP}
    ]
    positions = SourcePositions(segment)
    first, last = module_tokens[0], module_tokens[-1]
    start = positions.offset(*first.start)
    end = positions.offset(*last.end)
    return segment[:start] + module + segment[end:]


def _commented_members(
    node: ast.ImportFrom, destinations: list[tuple[str, str]], comments: list[tokenize.TokenInfo]
) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {parent: [] for parent, _ in destinations}
    remaining = list(comments)
    for index, ((parent, name), alias) in enumerate(zip(destinations, node.names, strict=True)):
        before = [token for token in remaining if token.start[0] + node.lineno - 1 < alias.lineno]
        same_line = index + 1 == len(node.names) or node.names[index + 1].lineno != alias.lineno
        inline = [
            token
            for token in remaining
            if same_line and token.start[0] + node.lineno - 1 == alias.lineno
        ]
        groups[parent].extend(token.string for token in before)
        groups[parent].append(
            name + "," + ("  " + " ".join(token.string for token in inline) if inline else "")
        )
        remaining = [token for token in remaining if token not in before and token not in inline]
    groups[destinations[-1][0]].extend(token.string for token in remaining)
    return groups


def _split_from_import(
    node: ast.ImportFrom, segment: str, destinations: list[tuple[str, str]], indent: str
) -> str:
    comments = [
        token
        for token in tokenize.generate_tokens(io.StringIO(segment).readline)
        if token.type == tokenize.COMMENT
    ]
    groups = _commented_members(node, destinations, comments)
    statements = []
    for parent, members in groups.items():
        if comments:
            body = "\n".join(indent + "    " + member for member in members)
            statements.append(f"from {parent} import (\n{body}\n{indent})")
        else:
            statements.append(
                f"from {parent} import " + ", ".join(member.removesuffix(",") for member in members)
            )
    return ("\n" + indent).join(statements)


def _from_import(node: ast.ImportFrom, segment: str, indent: str, resolver: Resolver) -> str:
    if node.level:
        raise ValueError(
            f"line {node.lineno}: relative import {segment!r}; expected an absolute import"
        )
    module = node.module or ""
    destinations = [_import_destination(module, alias, resolver) for alias in node.names]
    names_unchanged = all(
        name == _alias(alias.name, alias.asname)
        for (_, name), alias in zip(destinations, node.names, strict=True)
    )
    parents = dict.fromkeys(parent for parent, _ in destinations)
    if names_unchanged and list(parents) == [module]:
        return segment
    if names_unchanged and len(parents) == 1:
        return _replace_from_module(segment, next(iter(parents)))
    return _split_from_import(node, segment, destinations, indent)


def _plain_import(node: ast.Import, segment: str, indent: str, resolver: Resolver) -> str:
    statements = []
    changed = False
    for alias in node.names:
        target = resolver.module_object(alias.name)
        changed |= target is not None
        if target and alias.asname and target.startswith(alias.name + "."):
            parent, _, leaf = target.rpartition(".")
            statements.append(f"from {parent} import {_alias(leaf, alias.asname)}")
        else:
            statements.append("import " + _alias(target or alias.name, alias.asname))
    return ("\n" + indent).join(statements) if changed else segment


def _rewrite_nodes(tree: ast.Module) -> Iterator[ast.Import | ast.ImportFrom | ast.Constant]:
    blocked = {
        id(child)
        for parent in ast.walk(tree)
        if isinstance(parent, ast.JoinedStr | ast.BinOp)
        for child in ast.walk(parent)
    }
    # The prose pass owns docstrings so surrounding history markers can protect them.
    blocked.update(id(node) for node in docstring_nodes(tree))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Import | ast.ImportFrom | ast.Constant) or id(node) in blocked:
            continue
        if node.end_lineno is None or node.end_col_offset is None:
            continue
        yield node


def _literal_replacement(node: ast.Constant, segment: str, resolver: Resolver) -> str:
    if not isinstance(node.value, str):
        return segment
    tokens = [
        token
        for token in tokenize.generate_tokens(io.StringIO(segment).readline)
        if token.type == tokenize.STRING
    ]
    target = literal_target(node.value, resolver) if len(tokens) == 1 else None
    if not target:
        return segment
    return segment.replace(node.value, target) if node.value in segment else repr(target)


def _node_replacement(
    node: ast.Import | ast.ImportFrom | ast.Constant, segment: str, indent: str, resolver: Resolver
) -> str:
    if isinstance(node, ast.ImportFrom):
        return _from_import(node, segment, indent, resolver)
    if isinstance(node, ast.Import):
        return _plain_import(node, segment, indent, resolver)
    return _literal_replacement(node, segment, resolver)


def _node_edit(
    node: ast.Import | ast.ImportFrom | ast.Constant,
    source: str,
    positions: SourcePositions,
    resolver: Resolver,
) -> tuple[int, int, str] | None:
    start, end = positions.span(node)
    segment = source[start:end]
    line = positions.lines[node.lineno - 1]
    indent = line[: len(line) - len(line.lstrip())]
    replacement = _node_replacement(node, segment, indent, resolver)
    if replacement == segment:
        return None
    # Splitting a simple suite must not move its later imports outside the condition.
    prefix = source[positions.offset(node.lineno, 0) : start]
    if isinstance(node, ast.Import | ast.ImportFrom) and prefix.strip():
        replacement = replacement.replace("\n" + indent + "from ", "; from ").replace(
            "\n" + indent + "import ", "; import "
        )
    return start, end, replacement


def _report_spelling(node: ast.Import | ast.ImportFrom | ast.Constant, spelling: str) -> str:
    if isinstance(node, ast.Import) and len(node.names) == 1:
        spelling = spelling.removeprefix("import ").split(" as ")[0]
    return " ".join(spelling.split())


def rewrite_python(source: str, resolver: Resolver) -> tuple[str, list[str]]:
    """Rewrite import and literal spans; e.g. rewrite_python(source, Resolver(moves, repo))."""
    positions = SourcePositions(source)
    edits: list[tuple[int, int, str]] = []
    findings: list[str] = []
    for node in _rewrite_nodes(ast.parse(source)):
        edit = _node_edit(node, source, positions, resolver)
        if edit is None:
            continue
        start, end, replacement = edit
        edits.append(edit)
        old = _report_spelling(node, source[start:end])
        new = _report_spelling(node, replacement)
        findings.append(f"{node.lineno}: {old} -> {new}")
    return apply_edits(source, edits), findings
