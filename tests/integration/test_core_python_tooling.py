"""python-tooling on the reference probe (specs/prS-skills-context.md 11 intro, 11.3, H20).

``python-static-checks`` is ungated, so ``python-tooling`` is written in every Python
repo and its authored texts are generic, while the Covers clause follows the gates.
The skill declares sections (prU D17, L0-15), so the Covers clause names the
sections whose members are active: the probe has no ``uv.lock``, so its
description names linting, type checking, formatting and test configuration; the
same probe with a ``uv.lock`` also names package management. The FastAPI rules moved to
web-application and the Pydantic rule to python-coding (D24). The authored
body's picker bullets name each member by the display name the index shows.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from tests._catalog import CORE_ROOT, core_rules
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
_UV_PROBE_RULES: Final = [
    "mypy-type-checking.md",
    "pytest-configuration.md",
    "python-pyproject-dependencies.md",
    "python-static-checks.md",
    "python-uv-workflow.md",
    "ruff-format.md",
    "ruff-lint.md",
]


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


#: Member display name -> the picker label the body uses instead. ``pytest`` is also
#: a rule id, which a SKILL.md body may not name (spec 6.5.5), so this one label is
#: a phrase; python-testing drops its ``pytest`` prefixes for the same reason.
_BODY_LABEL_FOR: Final = {"pytest configuration": "the test runner's configuration"}


def _picker_labels(body: str) -> list[str]:
    """The reference labels of ``body``'s picker bullets: the text after each bullet's ": "."""
    tails = (line.rsplit(": ", 1)[-1].rstrip(".") for line in body.splitlines() if line[:2] == "- ")
    return [label for tail in tails for label in re.split(r", | and ", tail)]


def test_python_tooling_pickers_use_member_display_names() -> None:
    """Each picker bullet names a member by its index label, and every member is named.

    A descriptive phrase ("the package manager's workflow") leaves the agent to
    guess which index line it means (review of ticket 21); only a name holding a
    rule id gets a phrase, from ``_BODY_LABEL_FOR``.
    """
    skill_md = CORE_ROOT / "skills" / "python-tooling" / "SKILL.md"
    _, body = split_frontmatter(skill_md.read_text(encoding="utf-8"))
    rules = core_rules().values()
    names = {r.frontmatter.name.lower() for r in rules if r.frontmatter.skill == "python-tooling"}
    expected = sorted(_BODY_LABEL_FOR.get(name, name) for name in names)
    labels = [label.lower() for label in _picker_labels(body)]
    assert sorted(set(labels)) == expected, f"picker labels {labels}; expected {expected}"
