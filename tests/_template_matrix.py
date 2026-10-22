"""Render a rule template down every branch, and measure a rendering as one reference read.

prU D40 turns more core rules into ``python_at_least`` branches and many already
branch on libraries, while the reference probe (``tests/_budget_probe.py``) reaches
one branch per rule. :func:`distinct_renderings` renders a rule over its matrix:
each of :data:`MATRIX_PYTHON_VERSIONS` crossed with every on/off combination of
the libraries its template tests (:func:`fact_matrix`) and with each variant of
the project metadata it reads (:func:`metadata_matrix`). A branch the matrix
cannot switch is reported by :func:`unswitchable_branches`, a version ordered as
text by :func:`string_version_comparisons`, and :func:`ruff_formatted` is the
form the D20 caps measure.
"""

from __future__ import annotations

import itertools
import subprocess
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from jinja2 import UndefinedError, nodes
from jinja2.sandbox import SandboxedEnvironment

from coding_agent_playbook.detector.facts import Facts
from tests._budget_probe import render_rule

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from coding_agent_playbook.artifacts.rule import Rule

#: prU D40: example code targets 3.10 as the lowest branch; the matrix renders each minor.
MATRIX_PYTHON_VERSIONS: Final = ("3.10", "3.11", "3.12", "3.13")
#: Library helper -> the fact it reads in ``rendering.jinja.build_environment``;
#: ``tests/unit/test_core_rule_template_matrix.py`` pins it against that environment.
LIBRARY_HELPER_FACTS: Final[Mapping[str, str]] = {
    "has_framework": "frameworks",
    "has_ml_dep": "ml_stack",
    "has_dependency": "dependencies",
}
#: The render helpers that test no library; with :data:`LIBRARY_HELPER_FACTS`, every helper.
OTHER_HELPERS: Final = frozenset(
    {"python_at_least", "framework_skill", "skill_active", "rule_active"}
)
#: Project metadata -> the values the matrix renders a template that reads it with.
#: ``playbook init`` may record no description, so both sides of its branch render.
METADATA_VARIANTS: Final[Mapping[str, tuple[str, ...]]] = {
    "project_description": (
        "",
        "A FastAPI service that scores loan applications with a torch model.",
    ),
}
#: Library facts a template must test through a helper, so the matrix can switch them.
_LIBRARY_FACTS: Final = frozenset({*LIBRARY_HELPER_FACTS.values(), "dev_dependencies"})
#: Names a branch may test: the matrix varies each one.
_SWITCHED_NAMES: Final = frozenset({"python_version", *METADATA_VARIANTS})
_ORDERING_OPS: Final[Mapping[str, str]] = {"gt": ">", "gteq": ">=", "lt": "<", "lteq": "<="}
#: Generous: one ruff format run over one rendering takes a few milliseconds.
_RUFF_TIMEOUT_S: Final = 60


@dataclass(frozen=True)
class MatrixPoint:
    """One point of a template's matrix: the facts and project metadata it renders with.

    Example: ``render_rule(rule, point.facts, point.metadata)``.
    """

    facts: Facts
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"facts {self.facts} and metadata {dict(self.metadata)}"


def library_switches(template: str) -> tuple[tuple[str, str], ...]:
    """Every ``(helper, library)`` a template tests, sorted: its literal library-helper calls.

    Example: ``library_switches('{% if has_ml_dep("torch") %}x{% endif %}')`` ->
    ``(("has_ml_dep", "torch"),)``.
    """
    found = {
        (helper, library)
        for helper, call in _library_helper_calls(_parse(template))
        if (library := _literal_library(call)) is not None
    }
    return tuple(sorted(found))


def unswitchable_branches(template: str) -> list[str]:
    """What ``template`` branches on that the matrix cannot switch, so a branch would go unrendered.

    A library fact read directly (``"torch" in ml_stack``), a library helper called
    with anything but one string literal, and a name an ``if`` tests that is
    neither a helper, ``python_version``, a :data:`METADATA_VARIANTS` key nor set
    in the template.

    Example: ``unswitchable_branches('{% if "torch" in ml_stack %}x{% endif %}')`` ->
    ``["reads the library fact 'ml_stack' directly"]``.
    """
    tree = _parse(template)
    found: list[str] = []
    loaded = {name.name for name in tree.find_all(nodes.Name) if name.ctx == "load"}
    found += [
        f"reads the library fact {fact!r} directly" for fact in sorted(loaded & _LIBRARY_FACTS)
    ]
    found += [
        f"calls {helper}() without one string literal"
        for helper, call in _library_helper_calls(tree)
        if _literal_library(call) is None
    ]
    stored = {name.name for name in tree.find_all(nodes.Name) if name.ctx in ("store", "param")}
    helpers = {*LIBRARY_HELPER_FACTS, *OTHER_HELPERS}
    tested = {name.name for test in _branch_tests(tree) for name in _names_in(test)}
    unknown = tested - helpers - _SWITCHED_NAMES - _LIBRARY_FACTS - stored
    found += [f"branches on {name!r}, which the matrix does not vary" for name in sorted(unknown)]
    return found


def fact_matrix(template: str) -> list[Facts]:
    """The facts a template renders with: each matrix Python crossed with its libraries on/off.

    Every on/off combination of :func:`library_switches` (each in the fact its
    helper reads) for each of :data:`MATRIX_PYTHON_VERSIONS`. No other fact is
    set beyond ``project_kind``, which ``detect`` always reports, so a template
    that reads an undetected fact without a guard fails to render.

    Example: ``len(fact_matrix('{% if has_framework("fastapi") %}x{% endif %}'))`` -> 8.
    """
    libraries = library_switches(template)
    matrix: list[Facts] = []
    for version in MATRIX_PYTHON_VERSIONS:
        for switches in itertools.product((False, True), repeat=len(libraries)):
            held: dict[str, dict[str, str]] = {}
            for (helper, library), on in zip(libraries, switches, strict=True):
                if on:
                    held.setdefault(LIBRARY_HELPER_FACTS[helper], {})[library] = "1.0"
            matrix.append(_facts(version, held))
    return matrix


def metadata_matrix(template: str) -> list[dict[str, str]]:
    """Every combination of :data:`METADATA_VARIANTS` for the metadata ``template`` reads.

    Example: ``metadata_matrix("{{ project_description }}")`` ->
    ``[{"project_description": ""}, {"project_description": "A FastAPI service ..."}]``.
    """
    loaded = {name.name for name in _parse(template).find_all(nodes.Name) if name.ctx == "load"}
    read = sorted(loaded & METADATA_VARIANTS.keys())
    return [
        dict(zip(read, values, strict=True))
        for values in itertools.product(*(METADATA_VARIANTS[name] for name in read))
    ]


def matrix_points(template: str) -> Iterator[MatrixPoint]:
    """:func:`fact_matrix` crossed with :func:`metadata_matrix`.

    Example: ``len(list(matrix_points("{{ project_description }}")))`` -> 8.
    """
    for facts, metadata in itertools.product(fact_matrix(template), metadata_matrix(template)):
        yield MatrixPoint(facts, metadata)


def distinct_renderings(rule: Rule) -> dict[str, MatrixPoint]:
    """Each distinct body ``rule`` renders over its :func:`matrix_points`, with the first point behind it.

    Raises ``jinja2.UndefinedError`` naming the rule, the undefined variable and
    the point that reached it.

    Example: ``len(distinct_renderings(core_rules()["python-typing"]))`` -> 3.
    """
    renderings: dict[str, MatrixPoint] = {}
    for point in matrix_points(rule.template_body):
        try:
            body = render_rule(rule, point.facts, point.metadata)
        except UndefinedError as error:
            raise UndefinedError(
                f"{rule.frontmatter.id}: {error.message} when rendered with {point}"
            ) from error
        renderings.setdefault(body, point)
    return renderings


def ruff_formatted(markdown: str) -> str:
    """``markdown`` with its Python code blocks as ``ruff format`` writes them (default settings).

    The D20 caps count lines after ruff format, which a consumer's editor or hook
    applies to copied examples. ``--isolated`` keeps this checkout's settings out.
    A block that does not parse as Python is left as it is. Raises
    ``RuntimeError`` naming the command when ruff fails.

    Example: ``ruff_formatted("```python\\nx=1\\n```\\n")`` -> ``"```python\\nx = 1\\n```\\n"``.
    """
    command = [sys.executable, "-m", "ruff", "format", "--isolated", "--no-cache"]
    command += ["--stdin-filename", "rendering.md", "-"]
    done = subprocess.run(
        command,
        input=markdown,
        capture_output=True,
        encoding="utf-8",
        timeout=_RUFF_TIMEOUT_S,
        check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(f"{' '.join(command)} exited {done.returncode}: {done.stderr.strip()}")
    return done.stdout


def string_version_comparisons(template: str) -> list[str]:
    """Each ordering comparison of ``python_version`` or a string literal in ``template``.

    Strings order character by character (``"3.9" > "3.12"``), so a version
    branch goes through ``python_at_least`` (prU D40). A finding spells names and
    string literals (single-quoted) as the template does; any other operand shows
    as its Jinja node type in angle brackets, e.g. ``python_version < <Getattr>``.

    Example: ``string_version_comparisons('{% if python_version >= "3.11" %}{% endif %}')``
    -> ``["python_version >= '3.11'"]``.
    """
    found: list[str] = []
    for compare in _parse(template).find_all(nodes.Compare):
        operands = [compare.expr, *(operand.expr for operand in compare.ops)]
        ordering = any(operand.op in _ORDERING_OPS for operand in compare.ops)
        if ordering and any(_is_version_text(operand) for operand in operands):
            parts = [_describe(compare.expr)]
            for operand in compare.ops:
                parts += [_ORDERING_OPS.get(operand.op, operand.op), _describe(operand.expr)]
            found.append(" ".join(parts))
    return found


def _facts(version: str, held: Mapping[str, dict[str, str]]) -> Facts:
    facts = Facts(python_version=version, project_kind="python-unknown")
    if "frameworks" in held:
        facts["frameworks"] = held["frameworks"]
    if "ml_stack" in held:
        facts["ml_stack"] = held["ml_stack"]
    if "dependencies" in held:
        facts["dependencies"] = held["dependencies"]
    return facts


def _parse(template: str) -> nodes.Template:
    return SandboxedEnvironment().parse(template)


def _library_helper_calls(tree: nodes.Template) -> Iterator[tuple[str, nodes.Call]]:
    for call in tree.find_all(nodes.Call):
        if isinstance(call.node, nodes.Name) and call.node.name in LIBRARY_HELPER_FACTS:
            yield call.node.name, call


def _literal_library(call: nodes.Call) -> str | None:
    if len(call.args) != 1 or call.kwargs or call.dyn_args or call.dyn_kwargs:
        return None
    argument = call.args[0]
    if isinstance(argument, nodes.Const) and isinstance(argument.value, str):
        return argument.value
    return None


def _branch_tests(tree: nodes.Template) -> Iterator[nodes.Node]:
    for statement in tree.find_all(nodes.If):
        yield statement.test
    for expression in tree.find_all(nodes.CondExpr):
        yield expression.test


def _names_in(expr: nodes.Node) -> Iterator[nodes.Name]:
    # find_all yields descendants only, so a bare ``{% if name %}`` test needs its own check.
    if isinstance(expr, nodes.Name):
        yield expr
    yield from expr.find_all(nodes.Name)


def _is_version_text(node: nodes.Node) -> bool:
    if isinstance(node, nodes.Name):
        return node.name == "python_version"
    return isinstance(node, nodes.Const) and isinstance(node.value, str)


def _describe(node: nodes.Node) -> str:
    if isinstance(node, nodes.Name):
        return node.name
    if isinstance(node, nodes.Const):
        return repr(node.value)
    return f"<{type(node).__name__}>"
