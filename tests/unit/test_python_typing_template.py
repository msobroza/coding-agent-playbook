"""The core ``python-typing`` template branches on ``python_at_least``, not a string compare (D40).

A string comparison orders ``"3.9"`` after ``"3.12"``, so a 3.9 repo got the
PEP 695 branch; the numeric helper keeps it on the ``TypeVar`` branch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests._budget_probe import render_core_rule
from tests._catalog import CORE_ROOT

if TYPE_CHECKING:
    from coding_agent_playbook.detector.facts import Facts

pytestmark = pytest.mark.catalog

_PEP_695_MARKER = "PEP 695 syntax"
_SELF_MARKER = "from typing import Self"
_TEMPLATE = CORE_ROOT / "skills" / "python-coding" / "rules" / "python-typing.md.j2"


@pytest.mark.parametrize(
    ("version", "pep_695"),
    [("3.9", False), ("3.10", False), ("3.11", False), ("3.12", True), ("3.13", True)],
)
def test_python_typing_picks_the_generics_branch_numerically(version: str, pep_695: bool) -> None:
    facts: Facts = {"python_version": version}
    assert (_PEP_695_MARKER in render_core_rule("python-typing", facts)) is pep_695


def test_python_typing_renders_the_typevar_branch_without_python_version() -> None:
    assert _PEP_695_MARKER not in render_core_rule("python-typing", {})


def test_python_typing_template_never_compares_python_version_as_a_string() -> None:
    assert "python_version >=" not in _TEMPLATE.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("version", "self_type"),
    [("3.10", False), ("3.11", True), ("3.12", True), ("3.13", True)],
)
def test_python_typing_returns_self_from_311_and_a_bound_typevar_below(
    version: str, self_type: bool
) -> None:
    facts: Facts = {"python_version": version}
    assert (_SELF_MARKER in render_core_rule("python-typing", facts)) is self_type


def test_python_typing_renders_the_310_forms_without_python_version() -> None:
    body = render_core_rule("python-typing", {})
    assert _SELF_MARKER not in body
    assert 'bound="' in body


@pytest.mark.parametrize(
    ("version", "generics_import"),
    [
        ("3.10", "from typing import Generic, TypeVar"),
        ("3.12", "from collections.abc import Callable, Sequence"),
    ],
)
def test_python_typing_generics_examples_show_their_imports(
    version: str, generics_import: str
) -> None:
    facts: Facts = {"python_version": version}
    assert generics_import in render_core_rule("python-typing", facts)
