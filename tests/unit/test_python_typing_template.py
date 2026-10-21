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

_PEP_695_MARKER = "use **PEP 695** generic syntax"
_TEMPLATE = CORE_ROOT / "rules" / "languages" / "python" / "typing.md.j2"


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
