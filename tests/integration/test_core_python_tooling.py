"""python-tooling on the reference probe (specs/prS-skills-context.md 11 intro, 11.3, H20).

``python-static-checks`` is ungated, so ``python-tooling`` is written in every Python
repo and its authored texts are generic, while the Covers clause follows the gates.
The skill declares sections (prU D17, L0-15), so the Covers clause names the
sections whose members are active: the probe has no ``uv.lock``, so its
description names linting, type checking, formatting and test configuration; the
same probe with a ``uv.lock`` also names package management. The FastAPI rules moved to
web-application and the Pydantic rule to python-coding (D24). The authored body
has no picker bullets (D47): the generated index routes to rules, and "References
and examples" lists check-failures.md in every repo and uv-dependency-failures.md
only in a uv project (C-python-tooling-refs).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from tests._catalog import CORE_ROOT
from tests.core_skill_pins.python_tooling import PINS
from tests.plugins.superpowers_expectations import NATIVE_SKILL_ROOTS

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_SENTENCE: Final = "Conventions for the developer tools the repo already runs."
_USE_WHEN: Final = (
    "Use when fixing lint or type-check findings, editing tool settings, or changing dependencies."
)
_PROBE_SECTIONS: Final = "linting, type checking, formatting, test configuration"
#: The probe activates every section but package management, in declared order.
PROBE_DESCRIPTION: Final = f"{_SENTENCE} Covers {_PROBE_SECTIONS}. {_USE_WHEN}"
#: With a ``uv.lock`` the two uv rules' package-management section joins last.
UV_PROBE_DESCRIPTION: Final = (
    f"{_SENTENCE} Covers {_PROBE_SECTIONS}, package management. {_USE_WHEN}"
)
#: With a ``uv.lock`` the probe activates every member.
_UV_PROBE_RULES: Final = sorted(f"{rule_id}.md" for rule_id in PINS.members)


def _tooling_description(repo: Path) -> str:
    """The emitted description of ``repo``'s ``.claude/skills/python-tooling/SKILL.md``."""
    skill_md = repo / ".claude" / "skills" / "python-tooling" / "SKILL.md"
    frontmatter, _ = split_frontmatter(skill_md.read_text(encoding="utf-8"))
    return str(frontmatter["description"])


def test_reference_probe_python_tooling_names_its_active_sections(
    reference_probe_repo: Path,
) -> None:
    assert _tooling_description(reference_probe_repo) == PROBE_DESCRIPTION


def test_uv_lock_adds_the_uv_workflow_to_python_tooling(uv_reference_probe_repo: Path) -> None:
    description = _tooling_description(uv_reference_probe_repo)
    assert description == UV_PROBE_DESCRIPTION
    assert len(description) <= 300, f"{len(description)} chars; the cap is 300"
    for root in NATIVE_SKILL_ROOTS:
        rules = uv_reference_probe_repo / root / "python-tooling" / "rules"
        assert sorted(p.name for p in rules.iterdir()) == _UV_PROBE_RULES, root


_CHECK_FAILURES: Final = "check-failures.md"
_UV_FAILURES: Final = "uv-dependency-failures.md"


def _written_references(repo: Path, root: str) -> list[str]:
    """The reference file names ``repo``'s python-tooling skill holds under ``root``."""
    references = repo / root / "python-tooling" / "references"
    return sorted(p.name for p in references.iterdir() if p.suffix == ".md")


def _listed_references(repo: Path) -> list[str]:
    """The reference file names the emitted SKILL.md lists under "References and examples"."""
    skill_md = repo / ".claude" / "skills" / "python-tooling" / "SKILL.md"
    listing = skill_md.read_text(encoding="utf-8").partition("## References and examples")[2]
    return re.findall(r"\[references/([a-z0-9-]+\.md)\]", listing)


def test_reference_probe_ships_only_the_ungated_check_failures_guide(
    reference_probe_repo: Path,
) -> None:
    """Without a ``uv.lock`` the uv guide is neither written nor listed (D29, D58(2))."""
    for root in NATIVE_SKILL_ROOTS:
        assert _written_references(reference_probe_repo, root) == [_CHECK_FAILURES], root
    assert _listed_references(reference_probe_repo) == [_CHECK_FAILURES]


def test_uv_lock_adds_the_uv_dependency_failures_guide(uv_reference_probe_repo: Path) -> None:
    for root in NATIVE_SKILL_ROOTS:
        written = _written_references(uv_reference_probe_repo, root)
        assert written == [_CHECK_FAILURES, _UV_FAILURES], root
    assert _listed_references(uv_reference_probe_repo) == [_CHECK_FAILURES, _UV_FAILURES]


def test_python_tooling_body_leaves_rule_picking_to_the_generated_index() -> None:
    """D47: the hand-written picker bullets go; the generated parts route to rules."""
    skill_md = CORE_ROOT / "skills" / "python-tooling" / "SKILL.md"
    _, body = split_frontmatter(skill_md.read_text(encoding="utf-8"))
    assert "## Picking rules" not in body
    assert "rules index" not in body
