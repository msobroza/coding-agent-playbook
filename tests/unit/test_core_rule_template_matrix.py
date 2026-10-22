"""Every branch of every core rule template renders, within the D20 caps (prU D20, D40).

The reference probe renders one branch of each ``.md.j2`` rule. D40 turns more
rules into ``python_at_least`` branches and many already branch on libraries, so
each core template is rendered over a fact matrix: Python 3.10 to 3.13 crossed
with every on/off combination of the libraries the template tests
(``tests/_budget_probe.py``, :func:`~tests._budget_probe.fact_matrix`). Every
rendering must succeed (the environment's ``StrictUndefined`` fails an undefined
variable), and every distinct rendering must fit one reference read: 100 lines
and 750 words. A template that orders ``python_version`` or a version string as
text fails too, because ``"3.9" > "3.12"`` (D40: ``python_at_least`` instead).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest
from jinja2 import UndefinedError

from coding_agent_playbook.artifacts.rule import Rule
from coding_agent_playbook.catalog.roots import ENGINE_PACKAGE
from tests._budget_probe import (
    MATRIX_PYTHON_VERSIONS,
    distinct_renderings,
    fact_matrix,
    library_switches,
    string_version_comparisons,
)
from tests._catalog import core_rules
from tests.unit.test_core_rule_shapes import assert_fits_one_reference_read

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

CORE_TEMPLATE_IDS: Final = sorted(
    rule_id for rule_id, rule in core_rules().items() if rule.is_templated
)


def _template_rule(tmp_path: Path, body: str) -> Rule:
    """A scoped ``.md.j2`` rule named ``probe`` with ``body``, loaded as core rules are."""
    path = tmp_path / "probe.md.j2"
    path.write_text(
        "---\nid: probe\nname: Probe\ndescription: A probe.\nversion: 1\n"
        'scope: scoped\nglobs: ["**/*.py"]\npriority: 50\n---\n' + body,
        encoding="utf-8",
    )
    return Rule.from_markdown(path, ENGINE_PACKAGE)


def test_matrix_covers_python_310_to_313() -> None:
    assert MATRIX_PYTHON_VERSIONS == ("3.10", "3.11", "3.12", "3.13")


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
    assert {facts["python_version"] for facts in matrix} == set(MATRIX_PYTHON_VERSIONS)
    assert (
        sorted("fastapi" in facts.get("frameworks", {}) for facts in matrix)
        == [False] * 4 + [True] * 4
    )


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


def test_an_undefined_variable_in_any_branch_fails(tmp_path: Path) -> None:
    rule = _template_rule(
        tmp_path, '{% if has_ml_dep("torch") %}\n{{ torch_version }}\n{% endif %}\n'
    )
    with pytest.raises(UndefinedError, match="torch_version"):
        distinct_renderings(rule)


@pytest.mark.parametrize(
    "condition",
    ['python_version >= "3.11"', '"3.11" <= python_version', "python_version < minimum"],
)
def test_a_string_version_comparison_is_reported(condition: str) -> None:
    body = f"{{% if {condition} %}}x{{% endif %}}"
    assert string_version_comparisons(body) == [condition.replace('"', "'")]


def test_an_equality_or_helper_comparison_is_not_a_string_version_comparison() -> None:
    body = '{% if project_kind == "notebook" and python_at_least("3.11") %}x{% endif %}'
    assert string_version_comparisons(body) == []


@pytest.mark.parametrize("rule_id", CORE_TEMPLATE_IDS)
def test_core_template_never_compares_versions_as_strings(rule_id: str) -> None:
    found = string_version_comparisons(core_rules()[rule_id].template_body)
    assert not found, f"{rule_id}: compares versions as strings {found}; use python_at_least()"


@pytest.mark.parametrize("rule_id", CORE_TEMPLATE_IDS)
def test_every_distinct_rendering_of_a_core_template_fits_one_reference_read(
    rule_id: str,
) -> None:
    renderings = distinct_renderings(core_rules()[rule_id])
    for body, facts in renderings.items():
        assert_fits_one_reference_read(rule_id, body, f"the facts {facts}")
