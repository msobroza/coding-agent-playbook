"""The twelve smell detectors behind ``detect_smells.py``; not run on its own.

Standard library only, Python 3.10 or later. Each detector takes one
:class:`ModuleScan` and yields :class:`Candidate` records; ``DETECTORS`` lists
them in the order ``detect_smells.py`` runs them. The smell ids and what each
one flags are documented in ``detect_smells.py``.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from _pyscan_common import (
    FUNCTION_TYPES,
    is_dunder,
    is_ellipsis,
    is_stub_body,
    receiver_of,
    simple_name,
    without_docstring,
)
from _smell_model import (
    Candidate,
    base_names,
    classes_in,
    decorator_names,
    defaults_by_param,
    functions_in,
    methods_of,
    own_nodes,
    snippet,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from _pyscan_common import FunctionNode
    from _smell_model import ClassIndex, ModuleScan

MAX_PARAMETERS = 5
MAX_NESTING = 3
MAX_STATEMENT_LINES = 50
MIN_ISINSTANCE_TESTS = 3
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
