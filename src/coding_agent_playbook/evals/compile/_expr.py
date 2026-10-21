"""A tiny boolean-expression interpreter over check *handle names*.

The sample config expresses a few wiring decisions as miniature boolean
expressions over *handle names* - ``[gate].expr``, ``[rubric].expr``,
``[aggregate].expr``, and ``[verdict].trial`` are strings like
``"build and (fast or sec)"`` or ``"gate and rubric"``. This module compiles such
a string into a
:mod:`coding_agent_playbook.grading.compose` check tree over a
caller-provided ``name -> Check`` map.

The pipeline is the classic three stages:

* :func:`_tokenize` - a hand-rolled scanner producing a flat
  :class:`Token` list (identifiers, the reserved keywords ``and``/``or``/``not``,
  and the ``(``/``)`` punctuation), skipping whitespace and raising
  :class:`ExprError` on any illegal character.
* :func:`parse` - a recursive-descent parser to a small immutable AST
  (:class:`Name` / :class:`And` / :class:`Or` / :class:`Not`), with precedence
  ``not`` > ``and`` > ``or`` and parentheses. Chained ``and``/``or`` are
  **flattened** into one n-ary node (so ``"a and b and c"`` is one :class:`And`
  with three children, not a nested pair).
* :func:`compile_expr` - validates every referenced :class:`Name` against the
  ``handles`` map, then folds the AST into the ``compose.py`` tree: a
  :class:`Name` becomes ``handles[name]`` itself, an :class:`And`/:class:`Or`
  becomes a single :class:`~coding_agent_playbook.grading.compose.AllOf`
  / :class:`~coding_agent_playbook.grading.compose.AnyOf`, and a
  :class:`Not` becomes
  :class:`~coding_agent_playbook.grading.compose.Not`. A bare single
  name compiles to the handle check itself (no wrapper).

:func:`names` is a parse-only helper returning the set of referenced
identifiers, so a validator can check ``idents <= bind keys`` without building
any checks.

The interpreter is deliberately self-contained: it does **not** use ``eval`` /
``exec`` / ``ast``, and it pulls in no third-party dependency. The handle builder
(:mod:`coding_agent_playbook.evals.compile._handles`) and the sample compiler
(:mod:`coding_agent_playbook.evals.compile.compiler`) consume it: the compiler builds each
layer's ``name -> Check`` map, then folds the layer ``expr`` over it via
:func:`compile_expr` (and derives the verdict via :func:`eval_bool`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from coding_agent_playbook.grading.compose import AllOf, AnyOf
from coding_agent_playbook.grading.compose import Not as NotCheck

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.grading.check import Check


class ExprError(ValueError):
    """A malformed handle-expression (bad char, syntax, or unknown handle).

    Subclasses :class:`ValueError` so callers that already catch ``ValueError``
    on config parsing keep working; the dedicated type lets the validator
    surface a precise "expression" diagnostic.
    """


# --------------------------------------------------------------------------- #
# AST
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Name:
    """A leaf referencing a handle by name (resolved against ``handles`` later)."""

    value: str


@dataclass(frozen=True)
class And:
    """An n-ary conjunction; chained ``and`` is flattened into one node."""

    children: tuple[Node, ...]


@dataclass(frozen=True)
class Or:
    """An n-ary disjunction; chained ``or`` is flattened into one node."""

    children: tuple[Node, ...]


@dataclass(frozen=True)
class Not:
    """A unary negation of one child node."""

    child: Node


#: The AST node union (a ``Name`` leaf or one of the three boolean nodes).
Node = Name | And | Or | Not


# --------------------------------------------------------------------------- #
# Tokenizer
# --------------------------------------------------------------------------- #

#: The reserved boolean keywords. An identifier equal to one of these (in any
#: case) is tokenized as that keyword, not a ``Name`` - so ``and``/``or``/``not``
#: can never be used as handle names.
_KEYWORDS = frozenset({"and", "or", "not"})


@dataclass(frozen=True)
class Token:
    """One lexical token: a ``kind`` tag plus its source ``text``.

    ``kind`` is one of ``"name"``, ``"and"``, ``"or"``, ``"not"``, ``"("``, or
    ``")"``. For a ``"name"`` token ``text`` is the identifier; for the keyword
    and punctuation tokens ``text`` mirrors ``kind`` (lowercased keyword, literal
    paren).
    """

    kind: str
    text: str


def _is_ident_start(ch: str) -> bool:
    return ch.isalpha() or ch == "_"


def _is_ident_part(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _tokenize(expr: str) -> list[Token]:
    """Scan ``expr`` into a flat token list, skipping whitespace.

    Identifiers match ``[A-Za-z_][A-Za-z0-9_]*``; an identifier equal to a
    keyword (case-insensitive) becomes that keyword token. ``(`` and ``)`` are
    single-character tokens. Any other non-whitespace character raises
    :class:`ExprError` with the offending character and its position.
    """
    tokens: list[Token] = []
    i = 0
    n = len(expr)
    while i < n:
        ch = expr[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "(":
            tokens.append(Token("(", "("))
            i += 1
            continue
        if ch == ")":
            tokens.append(Token(")", ")"))
            i += 1
            continue
        if _is_ident_start(ch):
            j = i + 1
            while j < n and _is_ident_part(expr[j]):
                j += 1
            word = expr[i:j]
            lowered = word.lower()
            if lowered in _KEYWORDS:
                tokens.append(Token(lowered, lowered))
            else:
                tokens.append(Token("name", word))
            i = j
            continue
        raise ExprError(f"illegal character {ch!r} at position {i} in {expr!r}")
    return tokens


# --------------------------------------------------------------------------- #
# Recursive-descent parser
# --------------------------------------------------------------------------- #


class _Parser:
    """A single-pass recursive-descent parser over a token list.

    Grammar (precedence ``not`` > ``and`` > ``or``)::

        or_expr  := and_expr ('or' and_expr)*
        and_expr := not_expr ('and' not_expr)*
        not_expr := 'not' not_expr | atom
        atom     := NAME | '(' or_expr ')'

    Chained ``and``/``or`` are flattened into one n-ary :class:`And`/:class:`Or`.
    The parser raises :class:`ExprError` on an empty token stream, an unexpected
    or trailing token, or an unbalanced parenthesis.
    """

    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> Token | None:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _advance(self) -> Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def parse(self) -> Node:
        """Parse the full expression and assert nothing trails."""
        if not self._tokens:
            raise ExprError("empty expression")
        node = self._or_expr()
        trailing = self._peek()
        if trailing is not None:
            raise ExprError(f"unexpected trailing token {trailing.text!r}")
        return node

    def _or_expr(self) -> Node:
        first = self._and_expr()
        operands = [first]
        while (tok := self._peek()) is not None and tok.kind == "or":
            self._advance()
            operands.append(self._and_expr())
        if len(operands) == 1:
            return first
        return Or(tuple(operands))

    def _and_expr(self) -> Node:
        first = self._not_expr()
        operands = [first]
        while (tok := self._peek()) is not None and tok.kind == "and":
            self._advance()
            operands.append(self._not_expr())
        if len(operands) == 1:
            return first
        return And(tuple(operands))

    def _not_expr(self) -> Node:
        tok = self._peek()
        if tok is not None and tok.kind == "not":
            self._advance()
            return Not(self._not_expr())
        return self._atom()

    def _atom(self) -> Node:
        tok = self._peek()
        if tok is None:
            raise ExprError("unexpected end of expression; expected a name or '('")
        if tok.kind == "name":
            self._advance()
            return Name(tok.text)
        if tok.kind == "(":
            self._advance()
            inner = self._or_expr()
            closing = self._peek()
            if closing is None or closing.kind != ")":
                raise ExprError("unbalanced '(' - missing closing ')'")
            self._advance()
            return inner
        raise ExprError(f"unexpected token {tok.text!r}; expected a name or '('")


def parse(expr: str) -> Node:
    """Tokenize then parse ``expr`` into an AST :class:`Node`.

    Raises :class:`ExprError` on an empty/whitespace-only string, an illegal
    character, a syntax error (unexpected/trailing token, dangling operator), or
    an unbalanced parenthesis.
    """
    return _Parser(_tokenize(expr)).parse()


# --------------------------------------------------------------------------- #
# Compiler + name collection
# --------------------------------------------------------------------------- #


def _collect_names(node: Node, into: set[str]) -> None:
    """Recursively gather every :class:`Name`'s value into ``into``."""
    if isinstance(node, Name):
        into.add(node.value)
    elif isinstance(node, Not):
        _collect_names(node.child, into)
    else:  # And | Or
        for child in node.children:
            _collect_names(child, into)


def names(expr: str) -> set[str]:
    """The set of handle names referenced by ``expr`` (parse-only, no compile).

    Used by the validator to check that an expression's identifiers are a subset
    of the available bind keys without building any checks. Raises
    :class:`ExprError` on a malformed expression (same as :func:`parse`).
    """
    found: set[str] = set()
    _collect_names(parse(expr), found)
    return found


def _build(node: Node, handles: Mapping[str, Check], *, id: str) -> Check:
    """Fold one AST node into a ``compose.py`` check (names already validated).

    A :class:`Name` resolves to ``handles[name]`` itself (no wrapper); an
    :class:`And`/:class:`Or` becomes one flat
    :class:`~coding_agent_playbook.grading.compose.AllOf` /
    :class:`~coding_agent_playbook.grading.compose.AnyOf` over its
    compiled children; a :class:`Not` becomes
    :class:`~coding_agent_playbook.grading.compose.Not`. Every composer
    node is labeled with ``id``.
    """
    if isinstance(node, Name):
        return handles[node.value]
    if isinstance(node, Not):
        return NotCheck(_build(node.child, handles, id=id), id=id)
    if isinstance(node, And):
        return AllOf(*(_build(c, handles, id=id) for c in node.children), id=id)
    # Or
    return AnyOf(*(_build(c, handles, id=id) for c in node.children), id=id)


def eval_bool(node: Node, env: Mapping[str, bool]) -> bool:
    """Evaluate the AST ``node`` over a ``name -> bool`` environment.

    The boolean dual of :func:`compile_expr`: where ``compile_expr`` folds names
    into a ``compose.py`` :class:`Check` tree, this folds them into a single
    ``bool`` over an already-decided environment - a :class:`Name` resolves to
    ``env[name]`` (an absent name raises :class:`ExprError`), :class:`And` is
    ``all(...)``, :class:`Or` is ``any(...)``, :class:`Not` is ``not ...``. The
    sample compiler uses it to derive the per-trial verdict from the two layers'
    ``passed`` results without re-running them.
    """
    if isinstance(node, Name):
        try:
            return env[node.value]
        except KeyError:
            raise ExprError(f"unknown handle {node.value!r}; known: {sorted(env)}") from None
    if isinstance(node, Not):
        return not eval_bool(node.child, env)
    if isinstance(node, And):
        return all(eval_bool(child, env) for child in node.children)
    # Or
    return any(eval_bool(child, env) for child in node.children)


def compile_expr(expr: str, handles: Mapping[str, Check], *, id: str) -> Check:
    """Compile ``expr`` into a ``compose.py`` check tree over ``handles``.

    Parses ``expr``, validates that **every** referenced name exists in
    ``handles`` (raising :class:`ExprError` otherwise), then builds the tree: a
    bare single name compiles to the handle check itself; ``and``/``or`` fold
    into a single flat :class:`AllOf`/:class:`AnyOf` (chained operators are *not*
    nested); ``not`` folds into :class:`NotCheck`. The ``id`` argument labels
    every composer node produced (e.g. ``"gate"`` / ``"rubric"``).
    """
    ast = parse(expr)
    referenced: set[str] = set()
    _collect_names(ast, referenced)
    unknown = referenced - set(handles)
    if unknown:
        name = sorted(unknown)[0]
        raise ExprError(f"unknown handle {name!r}; known: {sorted(handles)}")
    return _build(ast, handles, id=id)


__all__ = [
    "And",
    "ExprError",
    "Name",
    "Node",
    "Not",
    "Or",
    "Token",
    "compile_expr",
    "eval_bool",
    "names",
    "parse",
]
