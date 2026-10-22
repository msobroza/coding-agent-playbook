"""Every branch of every core rule template renders (prU D20, D40).

The reference probe renders one branch of each ``.md.j2`` rule. D40 turns more
rules into ``python_at_least`` branches and many already branch on libraries, so
each core template is rendered over its matrix (``tests/_template_matrix.py``):
Python 3.10 to 3.13 crossed with every on/off combination of the libraries the
template tests and with each project metadata variant it reads. Every rendering
must succeed (the environment's ``StrictUndefined`` fails an undefined variable),
and a branch the matrix cannot switch fails, so no branch goes unrendered. A
template that orders ``python_version`` or a version string as text fails too,
because ``"3.9" > "3.12"`` (D40: ``python_at_least`` instead). The D20 size cap
over every distinct rendering lives in ``tests/unit/test_core_rule_shapes.py``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

import pytest
from jinja2 import UndefinedError
from jinja2.defaults import DEFAULT_NAMESPACE

from coding_agent_playbook.artifacts.rule import Rule
from coding_agent_playbook.catalog.roots import ENGINE_PACKAGE
from coding_agent_playbook.rendering.jinja import build_environment
from tests._catalog import core_rules
from tests._template_matrix import (
    LIBRARY_HELPER_FACTS,
    MATRIX_PYTHON_VERSIONS,
    METADATA_VARIANTS,
    OTHER_HELPERS,
    distinct_renderings,
    fact_matrix,
    library_switches,
    metadata_matrix,
    ruff_formatted,
    string_version_comparisons,
    unswitchable_branches,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

CORE_TEMPLATE_IDS: Final = sorted(
    rule_id for rule_id, rule in core_rules().items() if rule.is_templated
)
#: D48: rules point into the FastAPI example app only inside this branch.
_FASTAPI_BRANCH: Final = re.compile(r"""has_framework\(\s*["']fastapi["']\s*\)""")
#: The canonical example app's directory (D48), the target of a pointer branch.
_FASTAPI_EXAMPLE: Final = "fastapi-hotel-api"


def _template_rule(tmp_path: Path, body: str) -> Rule:
    """A scoped ``.md.j2`` rule named ``probe`` with ``body``, loaded as core rules are."""
    path = tmp_path / "probe.md.j2"
    path.write_text(
        "---\nid: probe\nname: Probe\ndescription: A probe.\nversion: 1\n"
        'scope: scoped\nglobs: ["**/*.py"]\npriority: 50\n---\n' + body,
        encoding="utf-8",
    )
    return Rule.from_markdown(path, ENGINE_PACKAGE)


def test_library_helper_facts_match_the_render_environment() -> None:
    env = build_environment([])
    helpers = set(env.globals) - set(DEFAULT_NAMESPACE)
    assert helpers == {*LIBRARY_HELPER_FACTS, *OTHER_HELPERS}, (
        "a render helper was added or renamed; list it in tests/_template_matrix.py "
        "LIBRARY_HELPER_FACTS (it tests a library) or OTHER_HELPERS"
    )
    for helper, fact in LIBRARY_HELPER_FACTS.items():
        tests_library = env.globals[helper]
        assert callable(tests_library)
        env.globals["_facts"] = {fact: {"somelib": "1.0"}}
        assert tests_library("somelib"), f"{helper} no longer reads facts[{fact!r}]"
        env.globals["_facts"] = {}
        assert not tests_library("somelib")


def test_library_switches_reads_every_library_helper_call() -> None:
    body = (
        '{% if has_framework("fastapi") %}a{% endif %}'
        "{% if has_ml_dep('torch') or has_dependency(\"pandera\") %}b{% endif %}"
        '{% if python_at_least("3.11") %}c{% endif %}'
    )
    assert library_switches(body) == (
        ("has_dependency", "pandera"),
        ("has_framework", "fastapi"),
        ("has_ml_dep", "torch"),
    )


def test_fact_matrix_crosses_versions_with_each_library_on_and_off() -> None:
    matrix = fact_matrix('{% if has_framework("fastapi") %}x{% endif %}')
    assert len(matrix) == 8
    assert sorted(facts["python_version"] for facts in matrix) == sorted(
        [*MATRIX_PYTHON_VERSIONS, *MATRIX_PYTHON_VERSIONS]
    )
    assert MATRIX_PYTHON_VERSIONS[0] == "3.10", "D40: 3.10 is the lowest branch"
    assert (
        sorted("fastapi" in facts.get("frameworks", {}) for facts in matrix)
        == [False] * 4 + [True] * 4
    )


def test_metadata_matrix_varies_only_the_metadata_a_template_reads() -> None:
    assert metadata_matrix("Plain text.") == [{}]
    assert metadata_matrix("{% if project_description %}x{% endif %}") == [
        {"project_description": value} for value in METADATA_VARIANTS["project_description"]
    ]


def test_a_fastapi_pointer_branch_renders_with_fastapi_on_and_off(tmp_path: Path) -> None:
    rule = _template_rule(
        tmp_path, 'Body.\n{% if has_framework("fastapi") %}\nSee the FastAPI rule.\n{% endif %}\n'
    )
    assert sorted(distinct_renderings(rule)) == ["Body.\n", "Body.\nSee the FastAPI rule.\n"]


def test_a_python_version_branch_renders_both_sides(tmp_path: Path) -> None:
    rule = _template_rule(
        tmp_path, '{% if python_at_least("3.12") %}\nnew\n{% else %}\nold\n{% endif %}\n'
    )
    assert sorted(distinct_renderings(rule)) == ["new\n", "old\n"]


def test_a_project_description_branch_renders_both_sides(tmp_path: Path) -> None:
    rule = _template_rule(
        tmp_path, "Intro.\n{% if project_description %}\n{{ project_description }}\n{% endif %}\n"
    )
    described = METADATA_VARIANTS["project_description"][1]
    assert sorted(distinct_renderings(rule)) == ["Intro.\n", f"Intro.\n{described}\n"]


def test_an_undefined_variable_in_any_branch_fails_naming_the_matrix_point(
    tmp_path: Path,
) -> None:
    rule = _template_rule(
        tmp_path, '{% if has_ml_dep("torch") %}\n{{ torch_version }}\n{% endif %}\n'
    )
    with pytest.raises(UndefinedError, match=r"probe: .*torch_version.*'ml_stack': \{'torch'"):
        distinct_renderings(rule)


@pytest.mark.parametrize(
    ("body", "finding"),
    [
        ('{% if "torch" in ml_stack %}x{% endif %}', "reads the library fact 'ml_stack' directly"),
        ("{% if has_framework(name) %}x{% endif %}", "calls has_framework() without one string"),
        ("{% if has_notebooks %}x{% endif %}", "branches on 'has_notebooks'"),
        ('{{ "x" if project_kind == "notebook" else "y" }}', "branches on 'project_kind'"),
    ],
)
def test_a_branch_the_matrix_cannot_switch_is_reported(body: str, finding: str) -> None:
    assert any(found.startswith(finding) for found in unswitchable_branches(body))


def test_branches_the_matrix_switches_are_not_reported() -> None:
    body = (
        '{% set lib = "torch" %}{% if has_ml_dep("torch") and lib %}a{% endif %}'
        '{% if python_at_least("3.11") or project_description %}b{% endif %}'
        '{% if framework_skill("clarify") %}c{% elif skill_active("x") %}d{% endif %}'
    )
    assert unswitchable_branches(body) == []


@pytest.mark.parametrize(
    "condition",
    ['python_version >= "3.11"', '"3.11" <= python_version', "python_version < minimum"],
)
def test_a_string_version_comparison_is_reported(condition: str) -> None:
    body = f"{{% if {condition} %}}x{{% endif %}}"
    assert string_version_comparisons(body) == [condition.replace('"', "'")]


def test_a_non_name_operand_of_a_string_version_comparison_shows_its_node_type() -> None:
    body = "{% if python_version < config.minimum %}x{% endif %}"
    assert string_version_comparisons(body) == ["python_version < <Getattr>"]


def test_an_equality_or_helper_comparison_is_not_a_string_version_comparison() -> None:
    body = '{% if project_kind == "notebook" and python_at_least("3.11") %}x{% endif %}'
    assert string_version_comparisons(body) == []


def test_ruff_formatted_lays_out_python_blocks_and_keeps_the_rest() -> None:
    body = "Prose  stays.\n\n```python\nx={'a':1}\n```\n\n```python\nnot python ...\n```\n"
    assert ruff_formatted(body) == (
        'Prose  stays.\n\n```python\nx = {"a": 1}\n```\n\n```python\nnot python ...\n```\n'
    )


@pytest.mark.parametrize("rule_id", CORE_TEMPLATE_IDS)
def test_core_template_never_compares_versions_as_strings(rule_id: str) -> None:
    found = string_version_comparisons(core_rules()[rule_id].template_body)
    assert not found, f"{rule_id}: compares versions as strings {found}; use python_at_least()"


@pytest.mark.parametrize("rule_id", CORE_TEMPLATE_IDS)
def test_the_matrix_switches_every_branch_of_a_core_template(rule_id: str) -> None:
    found = unswitchable_branches(core_rules()[rule_id].template_body)
    assert not found, (
        f"{rule_id}: {found}; test libraries through a helper with a string literal, "
        "or teach tests/_template_matrix.py to vary the name"
    )


@pytest.mark.parametrize("rule_id", CORE_TEMPLATE_IDS)
def test_every_branch_of_a_core_template_renders(rule_id: str) -> None:
    assert distinct_renderings(core_rules()[rule_id])


def test_every_fastapi_pointer_branch_renders_with_fastapi_on_and_off() -> None:
    """D48 pointer rules: each one's FastAPI switch is reached, and both sides render apart."""
    pointer_ids = [
        rule_id
        for rule_id in CORE_TEMPLATE_IDS
        if _FASTAPI_BRANCH.search(core_rules()[rule_id].template_body)
        or _FASTAPI_EXAMPLE in core_rules()[rule_id].template_body
    ]
    for rule_id in pointer_ids:
        rule = core_rules()[rule_id]
        assert ("has_framework", "fastapi") in library_switches(rule.template_body), (
            f"{rule_id}: points at FastAPI outside a literal has_framework('fastapi') branch"
        )
        sides = {
            "fastapi" in point.facts.get("frameworks", {})
            for point in distinct_renderings(rule).values()
        }
        assert sides == {False, True}, f"{rule_id}: FastAPI on and off render the same body"
