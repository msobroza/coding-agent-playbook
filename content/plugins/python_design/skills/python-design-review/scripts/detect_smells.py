#!/usr/bin/env python3
"""List design-smell candidates in Python source, using only the standard library.

Usage:
    python3 detect_smells.py [PATH ...]

Each PATH is a file or a directory; the default is the current directory.
Directories are searched recursively for ``*.py`` files, skipping dot
directories, ``__pycache__``, ``venv``/``.venv``, ``node_modules`` and
``site-packages``.

stdout is a JSON array of ``{"smell", "file", "line", "evidence"}`` objects,
sorted by (file, line, smell). Every entry is a candidate for a reviewer to
judge, never a verdict: a boolean parameter may be a deliberate public API and
a long parameter list may mirror an external schema.

Smell ids:
    mutable-default-argument   a list/dict/set literal, comprehension or factory
                               call used as a parameter default
    isinstance-ladder          3+ isinstance() tests in one if/elif chain
    long-parameter-list        more than 5 parameters, not counting self/cls
    boolean-flag-parameter     a bool-annotated or True/False-defaulted
                               parameter that an ``if`` branches on
    bare-except                ``except:`` with no exception type
    swallowed-exception        ``except Exception``/``BaseException`` whose
                               body is only pass, ``...`` or continue
    deep-nesting               a block nested more than 3 levels in a function
                               (an elif sits beside its if, not inside it)
    long-function              more than 50 lines that start a statement
    method-could-be-function   an instance method that never uses self; skips
                               methods that override a scanned base class or
                               are overridden by a scanned subclass, every
                               method of a class with an unscanned base (it
                               might be an override), Protocols, ``Test*``
                               classes, dunders, stub bodies, and methods
                               decorated with staticmethod, classmethod,
                               property, a setter/getter/deleter,
                               abstractmethod, override or overload
    namespace-class            a class whose methods are all staticmethods and
                               that has no base, metaclass, class decorator or
                               annotated field
    type-in-name               a parameter or assigned name ending in _str,
                               _int, _list, _dict, _set, _tuple or _bool, or
                               starting with str_, list_ or dict_ (first
                               binding per scope only)
    module-level-mutable-global-rebound
                               a ``global`` statement

Exit status: 0 after a scan, with or without candidates; 2 on a usage error or
a PATH that does not exist or cannot be read. A file that fails to parse, or
that nests too deeply to analyse, is named on stderr and skipped; the other
files are still reported.

Example:
    python3 detect_smells.py src/ tests/ > smell-candidates.json
"""

from __future__ import annotations

import argparse
import ast
import builtins
import json
import os
import sys
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Sequence

MAX_PARAMETERS = 5
MAX_NESTING = 3
MAX_STATEMENT_LINES = 50
MIN_ISINSTANCE_TESTS = 3
EVIDENCE_WIDTH = 60
# ast.unparse recurses once per nesting level, so a sum of a few hundred terms exhausts the stack.
TOO_DEEP_TO_PRINT = "<expression too deep to print>"

SKIPPED_DIR_NAMES = frozenset({"__pycache__", "venv", ".venv", "node_modules", "site-packages"})
FUNCTION_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)
SCOPE_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
# ast.TryStar (3.11) and ast.Match (3.10) are looked up so the script still runs on 3.10.
BLOCK_TYPES: tuple[type[ast.AST], ...] = tuple(
    getattr(ast, name)
    for name in ("If", "For", "AsyncFor", "While", "With", "AsyncWith", "Try", "TryStar", "Match")
    if hasattr(ast, name)
)
MUTABLE_LITERALS = (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)
MUTABLE_FACTORIES = frozenset(
    {"list", "dict", "set", "bytearray", "defaultdict", "deque", "OrderedDict", "Counter"}
)
BROAD_EXCEPTIONS = frozenset({"Exception", "BaseException"})
RECEIVER_NAMES = frozenset({"self", "cls"})
TYPE_SUFFIXES = ("_str", "_int", "_list", "_dict", "_set", "_tuple", "_bool")
TYPE_PREFIXES = ("str_", "list_", "dict_")
# A method carrying one of these is a framework hook or an interface, not a helper.
SELF_EXEMPT_DECORATORS = frozenset(
    {"staticmethod", "classmethod", "property", "cached_property", "setter", "getter", "deleter"}
    | {"abstractmethod", "abstractproperty", "override", "overload"}
)
# Bases with no overridable public methods: inheriting them never makes a method an override.
NEUTRAL_BASES = frozenset(
    {"object", "ABC", "Generic", "NamedTuple", "TypedDict"}
    | {"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"}
)

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


class Candidate(NamedTuple):
    """One smell candidate inside a module (the file is attached by the caller)."""

    smell: str
    line: int
    evidence: str


@dataclass
class ClassIndex:
    """Method and base names of every scanned class, keyed by the bare class name.

    ``overridden`` maps a class to the method names some scanned subclass
    redefines: those are extension points, not helpers. Same-named classes from
    different modules are merged, which only makes the override checks more
    conservative.
    """

    methods: dict[str, set[str]] = field(default_factory=dict)
    bases: dict[str, set[str]] = field(default_factory=dict)
    overridden: dict[str, set[str]] = field(default_factory=dict)

    @classmethod
    def from_trees(cls, trees: Iterable[ast.Module]) -> ClassIndex:
        """Index every class definition found in ``trees``."""
        index = cls()
        for node in (n for tree in trees for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
            index.methods.setdefault(node.name, set()).update(m.name for m in methods_of(node))
            index.bases.setdefault(node.name, set()).update(base_names(node))
        index.mark_overrides()
        return index

    def mark_overrides(self) -> None:
        """Fill ``overridden`` from every scanned class's scanned ancestors."""
        for name, own in self.methods.items():
            for ancestor in self.scanned_ancestors(name):
                self.overridden.setdefault(ancestor, set()).update(own & self.methods[ancestor])

    def scanned_ancestors(self, name: str) -> set[str]:
        """Every ancestor of ``name`` that was itself scanned (unscanned ones are dropped)."""
        found: set[str] = set()
        pending = list(self.bases.get(name, ()))
        while pending:
            base = pending.pop()
            if base not in found and base in self.methods:
                found.add(base)
                pending.extend(self.bases[base])
        return found

    def ancestor_methods(self, bases: Iterable[str]) -> set[str] | None:
        """Method names defined by any ancestor, or None when an ancestor was not scanned.

        >>> ClassIndex({"Base": {"run"}}, {"Base": set()}).ancestor_methods(["Base"])
        {'run'}
        """
        found: set[str] = set()
        pending, seen = list(bases), set()
        while pending:
            name = pending.pop()
            if name in seen:
                continue
            seen.add(name)
            if name in self.methods:
                found |= self.methods[name]
                pending.extend(self.bases[name])
            elif not is_neutral_base(name):
                return None
        return found


@dataclass(frozen=True)
class ModuleScan:
    """What every detector receives: one parsed module plus the cross-module class index."""

    tree: ast.Module
    classes: ClassIndex


# --- shared AST helpers ------------------------------------------------------------------


def simple_name(node: ast.expr | None) -> str:
    """Last dotted component of a name: ``abc.ABC`` -> ``ABC``, ``Base[T]`` -> ``Base``.

    Anything that is not a plain or dotted name yields ``""``.
    """
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Subscript):
        node = node.value
    if isinstance(node, ast.Name):
        return node.id
    return node.attr if isinstance(node, ast.Attribute) else ""


def decorator_names(node: FunctionNode | ast.ClassDef) -> set[str]:
    """``@abc.abstractmethod`` -> ``abstractmethod``; ``@total.setter`` -> ``setter``."""
    return {simple_name(decorator) for decorator in node.decorator_list}


def base_names(node: ast.ClassDef) -> list[str]:
    """Bare names of the explicit bases (see :func:`simple_name`)."""
    return [simple_name(base) for base in node.bases]


def is_neutral_base(name: str) -> bool:
    """True for bases that contribute no method a subclass would override."""
    candidate = getattr(builtins, name, None)
    is_exception = isinstance(candidate, type) and issubclass(candidate, BaseException)
    return name in NEUTRAL_BASES or is_exception


def methods_of(node: ast.ClassDef) -> list[FunctionNode]:
    """Functions defined directly in the class body, in source order."""
    return [child for child in node.body if isinstance(child, FUNCTION_TYPES)]


def functions_in(tree: ast.AST) -> Iterator[FunctionNode]:
    """Every function and method anywhere in ``tree``."""
    return (node for node in ast.walk(tree) if isinstance(node, FUNCTION_TYPES))


def classes_in(tree: ast.AST) -> Iterator[ast.ClassDef]:
    """Every class anywhere in ``tree``."""
    return (node for node in ast.walk(tree) if isinstance(node, ast.ClassDef))


def own_nodes(scope: ast.AST) -> Iterator[ast.AST]:
    """Nodes inside ``scope``, not descending into nested functions, classes or lambdas."""
    stack = list(ast.iter_child_nodes(scope))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, SCOPE_TYPES):
            stack.extend(ast.iter_child_nodes(node))


def without_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    """``body`` minus a leading docstring expression."""
    return body[1:] if body and is_string_statement(body[0]) else body


def is_string_statement(stmt: ast.stmt) -> bool:
    """True for a statement that is only a string literal (a docstring)."""
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def is_ellipsis(stmt: ast.stmt) -> bool:
    """True for a bare ``...`` statement."""
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and stmt.value.value is Ellipsis
    )


def is_stub_statement(stmt: ast.stmt) -> bool:
    """``pass``, ``...`` or ``raise NotImplementedError``: a placeholder, not behaviour."""
    if isinstance(stmt, ast.Raise):
        return simple_name(stmt.exc) == "NotImplementedError"
    return isinstance(stmt, ast.Pass) or is_ellipsis(stmt)


def is_stub_body(body: list[ast.stmt]) -> bool:
    """True when a body only documents or refuses (docstring, pass, ..., NotImplementedError)."""
    return all(is_stub_statement(stmt) for stmt in without_docstring(body))


def receiver_of(fn: FunctionNode) -> str | None:
    """Name of the first positional parameter (``self`` by convention), if any."""
    positional = fn.args.posonlyargs + fn.args.args
    return positional[0].arg if positional else None


def is_dunder(name: str) -> bool:
    """True for ``__name__``-style names."""
    return len(name) > 4 and name.startswith("__") and name.endswith("__")


def snippet(node: ast.AST) -> str:
    """Source text of ``node``, cut to EVIDENCE_WIDTH characters.

    An expression too deep for ``ast.unparse`` yields TOO_DEEP_TO_PRINT, so the
    candidate is still reported.
    """
    try:
        text = ast.unparse(node)
    except RecursionError:
        return TOO_DEEP_TO_PRINT
    return text if len(text) <= EVIDENCE_WIDTH else text[: EVIDENCE_WIDTH - 3] + "..."


def defaults_by_param(args: ast.arguments) -> Iterator[tuple[ast.arg, ast.expr]]:
    """Pair each parameter that has a default with that default."""
    positional = args.posonlyargs + args.args
    with_default = positional[len(positional) - len(args.defaults) :]
    yield from zip(with_default, args.defaults, strict=True)
    for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=True):
        if default is not None:
            yield arg, default


# --- detectors ---------------------------------------------------------------------------


def detect_mutable_defaults(scan: ModuleScan) -> Iterator[Candidate]:
    """mutable-default-argument: the default object is shared by every call."""
    for fn in functions_in(scan.tree):
        pairs = [(a, d) for a, d in defaults_by_param(fn.args) if is_mutable_value(d)]
        yield from (
            Candidate(
                "mutable-default-argument",
                default.lineno,
                f"parameter '{arg.arg}' of '{fn.name}' defaults to {snippet(default)}",
            )
            for arg, default in pairs
        )


def is_mutable_value(node: ast.expr) -> bool:
    """A literal, comprehension or factory call that builds a mutable container."""
    if isinstance(node, MUTABLE_LITERALS):
        return True
    return isinstance(node, ast.Call) and simple_name(node.func) in MUTABLE_FACTORIES


def detect_isinstance_ladders(scan: ModuleScan) -> Iterator[Candidate]:
    """isinstance-ladder: type-switching that a dispatch table or method could replace."""
    continuations: set[int] = set()
    for node in ast.walk(scan.tree):  # breadth-first: an if is seen before its elifs
        if not isinstance(node, ast.If) or id(node) in continuations:
            continue
        chain = if_chain(node)
        continuations.update(id(branch) for branch in chain[1:])
        calls = [call for branch in chain for call in isinstance_calls(branch.test)]
        if len(calls) >= MIN_ISINSTANCE_TESTS:
            yield Candidate("isinstance-ladder", node.lineno, ladder_evidence(calls))


def if_chain(node: ast.If) -> list[ast.If]:
    """The ``if`` followed by each ``elif`` it continues into."""
    chain = [node]
    while len(chain[-1].orelse) == 1 and isinstance(chain[-1].orelse[0], ast.If):
        chain.append(chain[-1].orelse[0])
    return chain


def isinstance_calls(test: ast.expr) -> list[ast.Call]:
    """Every ``isinstance(...)`` call inside a branch condition."""
    return [
        node
        for node in ast.walk(test)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "isinstance"
    ]


def ladder_evidence(calls: list[ast.Call]) -> str:
    """Describe a ladder by its size and the subjects being tested."""
    subjects = dict.fromkeys(snippet(call.args[0]) for call in calls if call.args)
    return f"{len(calls)} isinstance() tests in one if/elif chain on {', '.join(subjects)}"


def detect_long_parameter_lists(scan: ModuleScan) -> Iterator[Candidate]:
    """long-parameter-list: callers must remember too much; a parameter object may help."""
    for fn in functions_in(scan.tree):
        count = len(counted_parameters(fn.args))
        if count > MAX_PARAMETERS:
            evidence = f"'{fn.name}' takes {count} parameters (more than {MAX_PARAMETERS})"
            yield Candidate("long-parameter-list", fn.lineno, evidence)


def counted_parameters(args: ast.arguments) -> list[ast.arg]:
    """Named parameters, minus a leading self/cls and the *args/**kwargs catch-alls."""
    positional = args.posonlyargs + args.args
    if positional and positional[0].arg in RECEIVER_NAMES:
        positional = positional[1:]
    return positional + args.kwonlyargs


def detect_boolean_flags(scan: ModuleScan) -> Iterator[Candidate]:
    """boolean-flag-parameter: the function likely does two jobs selected by a flag."""
    for fn in functions_in(scan.tree):
        if "setter" in decorator_names(fn):
            continue
        tested = branch_tested_names(fn)
        yield from (
            Candidate(
                "boolean-flag-parameter", arg.lineno, f"'{fn.name}' branches on flag '{arg.arg}'"
            )
            for arg in flag_parameters(fn.args)
            if arg.arg in tested
        )


def flag_parameters(args: ast.arguments) -> list[ast.arg]:
    """Parameters annotated ``bool`` or defaulting to True/False."""
    defaults = dict(defaults_by_param(args))
    params = args.posonlyargs + args.args + args.kwonlyargs
    return [
        arg
        for arg in params
        if is_bool_annotation(arg.annotation) or is_bool_constant(defaults.get(arg))
    ]


def is_bool_annotation(annotation: ast.expr | None) -> bool:
    """``bool``, ``builtins.bool`` or the string ``"bool"``."""
    if isinstance(annotation, ast.Constant):
        return annotation.value == "bool"
    return isinstance(annotation, (ast.Name, ast.Attribute)) and simple_name(annotation) == "bool"


def is_bool_constant(node: ast.expr | None) -> bool:
    """``True`` or ``False`` literal."""
    return isinstance(node, ast.Constant) and isinstance(node.value, bool)


def branch_tested_names(fn: FunctionNode) -> set[str]:
    """Names read by any ``if`` statement or conditional expression in the body."""
    tests = [
        node.test
        for stmt in fn.body
        for node in ast.walk(stmt)
        if isinstance(node, (ast.If, ast.IfExp))
    ]
    return {node.id for test in tests for node in ast.walk(test) if isinstance(node, ast.Name)}


def detect_bare_excepts(scan: ModuleScan) -> Iterator[Candidate]:
    """bare-except: also traps KeyboardInterrupt and SystemExit."""
    for node in ast.walk(scan.tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            evidence = "bare 'except:' also catches KeyboardInterrupt and SystemExit"
            yield Candidate("bare-except", node.lineno, evidence)


def detect_swallowed_exceptions(scan: ModuleScan) -> Iterator[Candidate]:
    """swallowed-exception: a broad handler that silently discards the error."""
    for node in ast.walk(scan.tree):
        if not isinstance(node, ast.ExceptHandler) or node.type is None:
            continue
        if is_broad(node.type) and is_silent(node.body):
            body = "; ".join(ast.unparse(stmt) for stmt in node.body)
            evidence = f"'except {snippet(node.type)}' discards the error (body: {body})"
            yield Candidate("swallowed-exception", node.lineno, evidence)


def is_broad(handler_type: ast.expr) -> bool:
    """``Exception`` or ``BaseException``, alone or inside a tuple."""
    if isinstance(handler_type, ast.Tuple):
        return any(is_broad(element) for element in handler_type.elts)
    return simple_name(handler_type) in BROAD_EXCEPTIONS


def is_silent(body: list[ast.stmt]) -> bool:
    """True when a handler body is only pass, ``...`` or continue."""
    return all(isinstance(stmt, (ast.Pass, ast.Continue)) or is_ellipsis(stmt) for stmt in body)


def detect_deep_nesting(scan: ModuleScan) -> Iterator[Candidate]:
    """deep-nesting: guard clauses or an extracted helper would flatten the function."""
    for fn in functions_in(scan.tree):
        levels = list(block_levels(fn.body, 0))
        too_deep = sorted(stmt.lineno for level, stmt in levels if level > MAX_NESTING)
        if too_deep:
            deepest = max(level for level, _ in levels)
            evidence = f"'{fn.name}' nests blocks {deepest} levels deep (more than {MAX_NESTING})"
            yield Candidate("deep-nesting", too_deep[0], evidence)


def block_levels(body: list[ast.stmt], depth: int) -> Iterator[tuple[int, ast.stmt]]:
    """Yield (nesting level, block) for each block below ``body``, which sits ``depth`` deep.

    Nested functions and classes are skipped: each function is measured on its own.
    Iterative, not recursive: every ``elif`` is one more nested ``If`` node, and a
    generated dispatch chain of ~1000 branches would exhaust the call stack.
    """
    pending = [(body, depth)]
    while pending:
        statements, level = pending.pop()
        for stmt in (s for s in statements if isinstance(s, BLOCK_TYPES)):
            yield level + 1, stmt
            pending.extend(child_bodies(stmt, level + 1))


def child_bodies(stmt: ast.stmt, level: int) -> Iterator[tuple[list[ast.stmt], int]]:
    """Each statement list directly inside a block, with the depth its statements sit at."""
    if isinstance(stmt, ast.If) and len(stmt.orelse) == 1 and isinstance(stmt.orelse[0], ast.If):
        yield stmt.body, level
        yield stmt.orelse, level - 1  # an elif continues the chain at the if's own level
        return
    for name in ("body", "orelse", "finalbody"):
        yield getattr(stmt, name, []), level
    for nested in getattr(stmt, "handlers", []) + getattr(stmt, "cases", []):
        yield nested.body, level


def detect_long_functions(scan: ModuleScan) -> Iterator[Candidate]:
    """long-function: too much to hold in one read; look for steps to extract."""
    for fn in functions_in(scan.tree):
        lines = statement_lines(fn)
        if len(lines) > MAX_STATEMENT_LINES:
            evidence = (
                f"'{fn.name}' spans {len(lines)} statement lines (more than {MAX_STATEMENT_LINES})"
            )
            yield Candidate("long-function", fn.lineno, evidence)


def statement_lines(fn: FunctionNode) -> set[int]:
    """Distinct lines on which a statement of the body starts (docstring excluded)."""
    body = without_docstring(fn.body)
    return {node.lineno for stmt in body for node in ast.walk(stmt) if isinstance(node, ast.stmt)}


def detect_selfless_methods(scan: ModuleScan) -> Iterator[Candidate]:
    """method-could-be-function: the method needs nothing from its instance."""
    for cls in classes_in(scan.tree):
        exempt = exempt_method_names(cls, scan.classes)
        if exempt is None:
            continue
        yield from (
            Candidate(
                "method-could-be-function",
                fn.lineno,
                f"'{cls.name}.{fn.name}' never uses '{receiver_of(fn)}'",
            )
            for fn in methods_of(cls)
            if could_be_function(fn, exempt)
        )


def exempt_method_names(cls: ast.ClassDef, index: ClassIndex) -> set[str] | None:
    """Method names of ``cls`` that override or are overridden; None leaves the class alone.

    Protocols declare interfaces, ``Test*`` classes hold pytest methods, and a base
    outside the scanned files could define any name.
    """
    bases = base_names(cls)
    if "Protocol" in bases or cls.name.startswith("Test"):
        return None
    inherited = index.ancestor_methods(bases)
    return None if inherited is None else inherited | index.overridden.get(cls.name, set())


def could_be_function(fn: FunctionNode, exempt: set[str]) -> bool:
    """True for an ordinary, non-override method whose body never touches its receiver."""
    receiver = receiver_of(fn)
    if receiver is None or is_dunder(fn.name) or fn.name in exempt:
        return False
    if decorator_names(fn) & SELF_EXEMPT_DECORATORS or is_stub_body(fn.body):
        return False
    return not uses_receiver(fn, receiver)


def uses_receiver(fn: FunctionNode, receiver: str) -> bool:
    """True when the body reads the receiver or calls zero-argument ``super()``."""
    names = (node for stmt in fn.body for node in ast.walk(stmt) if isinstance(node, ast.Name))
    return any(name.id in (receiver, "super") for name in names)


def detect_namespace_classes(scan: ModuleScan) -> Iterator[Candidate]:
    """namespace-class: a module of plain functions does the same job."""
    for cls in classes_in(scan.tree):
        if is_namespace_class(cls):
            evidence = f"class '{cls.name}' only holds staticmethods ({len(methods_of(cls))})"
            yield Candidate("namespace-class", cls.lineno, evidence)


def is_namespace_class(cls: ast.ClassDef) -> bool:
    """Only staticmethods, and no bases, metaclass, class decorator or annotated fields.

    A decorated class or one with annotated fields (a dataclass, a model) holds
    data, so a staticmethod on it is a helper, not a namespace.
    """
    methods = methods_of(cls)
    if not methods or cls.decorator_list or cls.keywords:
        return False
    if any(name != "object" for name in base_names(cls)) or has_fields(cls):
        return False
    return all("staticmethod" in decorator_names(method) for method in methods)


def has_fields(cls: ast.ClassDef) -> bool:
    """True when the class body declares annotated attributes."""
    return any(isinstance(stmt, ast.AnnAssign) for stmt in cls.body)


def detect_type_in_names(scan: ModuleScan) -> Iterator[Candidate]:
    """type-in-name: the name repeats the type instead of saying what the value means."""
    scopes: list[ast.AST] = [scan.tree, *functions_in(scan.tree), *classes_in(scan.tree)]
    for scope in scopes:
        yield from (
            Candidate("type-in-name", line, f"'{name}' spells its type in its name")
            for name, line in sorted(scope_bindings(scope).items())
            if has_type_affix(name)
        )


def has_type_affix(name: str) -> bool:
    """``price_str``, ``ids_list``, ``dict_of_codes`` -> True; ``__dict__``, ``price`` -> False."""
    core = name.strip("_").lower()
    return core.endswith(TYPE_SUFFIXES) or core.startswith(TYPE_PREFIXES)


def scope_bindings(scope: ast.AST) -> dict[str, int]:
    """First line on which each parameter or assigned name of ``scope`` is bound."""
    pairs = list(parameter_bindings(scope))
    pairs += [
        pair
        for node in own_nodes(scope)
        for target in assigned_targets(node)
        for pair in bound_names(target)
    ]
    first: dict[str, int] = {}
    for name, line in pairs:
        first[name] = min(line, first.get(name, line))
    return first


def parameter_bindings(scope: ast.AST) -> Iterator[tuple[str, int]]:
    """Every parameter of a function scope except self/cls."""
    if not isinstance(scope, FUNCTION_TYPES):
        return
    args = scope.args
    params = (
        args.posonlyargs + args.args + args.kwonlyargs + [a for a in (args.vararg, args.kwarg) if a]
    )
    yield from ((arg.arg, arg.lineno) for arg in params if arg.arg not in RECEIVER_NAMES)


def assigned_targets(node: ast.AST) -> list[ast.expr]:
    """Targets bound by an assignment, annotated assignment, walrus or for loop."""
    if isinstance(node, ast.Assign):
        return node.targets
    if isinstance(node, (ast.AnnAssign, ast.NamedExpr, ast.For, ast.AsyncFor)):
        return [node.target]
    return []


def bound_names(target: ast.expr) -> Iterator[tuple[str, int]]:
    """Names bound by one target: plain names, unpacked names, and ``self.<attr>``."""
    match target:
        case ast.Name(id=name):
            yield name, target.lineno
        case ast.Tuple(elts=elements) | ast.List(elts=elements):
            yield from (pair for element in elements for pair in bound_names(element))
        case ast.Starred(value=inner):
            yield from bound_names(inner)
        case ast.Attribute(value=ast.Name(id=owner), attr=attr) if owner in RECEIVER_NAMES:
            yield attr, target.lineno


def detect_global_statements(scan: ModuleScan) -> Iterator[Candidate]:
    """module-level-mutable-global-rebound: hidden shared state rebound from a function."""
    scopes: list[ast.AST] = [scan.tree, *functions_in(scan.tree)]
    for scope in scopes:
        owner = f"'{scope.name}'" if isinstance(scope, FUNCTION_TYPES) else "module level"
        yield from (
            Candidate(
                "module-level-mutable-global-rebound",
                node.lineno,
                f"{owner} rebinds module global {', '.join(node.names)}",
            )
            for node in own_nodes(scope)
            if isinstance(node, ast.Global)
        )


DETECTORS: tuple[Callable[[ModuleScan], Iterator[Candidate]], ...] = (
    detect_mutable_defaults,
    detect_isinstance_ladders,
    detect_long_parameter_lists,
    detect_boolean_flags,
    detect_bare_excepts,
    detect_swallowed_exceptions,
    detect_deep_nesting,
    detect_long_functions,
    detect_selfless_methods,
    detect_namespace_classes,
    detect_type_in_names,
    detect_global_statements,
)


# --- files and CLI -----------------------------------------------------------------------
# Kept in step with the file walk in lcom4_clusters.py: each script must run standalone.


def iter_python_files(paths: Sequence[Path]) -> Iterator[Path]:
    """Files named explicitly, plus every ``*.py`` under each directory."""
    for path in paths:
        if path.is_dir():
            yield from walk_python_files(path)
        else:
            yield path


def walk_python_files(root: Path) -> Iterator[Path]:
    """``*.py`` files under ``root`` in sorted order, skipping tool and vendor directories."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if not d.startswith(".") and d not in SKIPPED_DIR_NAMES
        )
        yield from (Path(dirpath) / name for name in sorted(filenames) if name.endswith(".py"))


def parse_module(path: Path) -> ast.Module | None:
    """Parse one file, or report it on stderr and return None."""
    try:
        source = path.read_bytes()
        with warnings.catch_warnings():  # the scanned code's own warnings are not ours to print
            warnings.simplefilter("ignore")
            return ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, ValueError, RecursionError) as error:
        print(f"detect_smells.py: skipped {path}: {error}", file=sys.stderr)
        return None


def load_modules(paths: Sequence[Path]) -> list[tuple[str, ast.Module]]:
    """(display path, tree) for every parseable file, de-duplicated and sorted."""
    files = sorted({path.as_posix(): path for path in iter_python_files(paths)}.items())
    parsed = [(name, parse_module(path)) for name, path in files]
    return [(name, tree) for name, tree in parsed if tree is not None]


def module_candidates(
    name: str,
    module: ModuleScan,
    detectors: Sequence[Callable[[ModuleScan], Iterator[Candidate]]],
) -> list[Candidate]:
    """Every detector's candidates for one module, or none when it nests too deeply.

    A module that exhausts the call stack is named on stderr and skipped, like an
    unparseable one, so it cannot abort the scan of every other file.
    """
    try:
        return [candidate for detector in detectors for candidate in detector(module)]
    except RecursionError as error:
        print(f"detect_smells.py: skipped {name}: {error}", file=sys.stderr)
        return []


def scan(
    paths: Sequence[Path],
    detectors: Sequence[Callable[[ModuleScan], Iterator[Candidate]]] = DETECTORS,
) -> list[dict[str, object]]:
    """Run ``detectors`` over ``paths`` and return the sorted JSON-ready candidates.

    >>> scan([Path("pkg")])  # doctest: +SKIP
    [{'smell': 'bare-except', 'file': 'pkg/io.py', 'line': 12, 'evidence': "bare 'except:' ..."}]
    """
    modules = load_modules(paths)
    index = ClassIndex.from_trees(tree for _, tree in modules)
    found = {
        (name, candidate.line, candidate.smell, candidate.evidence)
        for name, tree in modules
        for candidate in module_candidates(name, ModuleScan(tree, index), detectors)
    }
    return [
        {"smell": smell, "file": name, "line": line, "evidence": text}
        for name, line, smell, text in sorted(found)
    ]


def path_problem(path: Path) -> str | None:
    """Why ``path`` cannot be scanned, or None when it can."""
    if not path.exists():
        return f"no such file or directory: {path}"
    mode = os.R_OK | (os.X_OK if path.is_dir() else 0)
    return None if os.access(path, mode) else f"cannot read: {path}"


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Command-line interface; argparse exits with status 2 on a usage error."""
    parser = argparse.ArgumentParser(
        prog="detect_smells.py",
        description="Print design-smell candidates in Python files as a JSON array.",
    )
    parser.add_argument(
        "paths", nargs="*", default=["."], metavar="PATH", help="file or directory (default: .)"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: scan the given paths and print JSON; returns the exit status."""
    paths = [Path(raw) for raw in parse_args(argv).paths]
    problems = [problem for problem in map(path_problem, paths) if problem]
    if problems:
        print(f"detect_smells.py: error: {problems[0]}", file=sys.stderr)
        return 2
    print(json.dumps(scan(paths), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
