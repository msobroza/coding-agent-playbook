"""python-tooling on the reference probe (specs/prS-skills-context.md 11 intro, 11.3, H20).

``python-static-checks`` is ungated, so ``python-tooling`` is written in every Python
repo and its authored texts are generic, while the Covers clause follows the gates.
The probe has no ``uv.lock``, so its description names five members (223
characters); the same probe with a ``uv.lock`` also names the uv workflow (236).
Both texts are the spec's, pinned verbatim.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.types import split_frontmatter
from tests.plugins.superpowers_expectations import NATIVE_SKILL_ROOTS

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_SENTENCE: Final = "Conventions tied to a named tool or framework."
_USE_WHEN: Final = "Use when editing tool configuration or code wired to a framework."
#: The spec 11 intro text: the five members the probe activates, in (priority, id) order.
PROBE_DESCRIPTION: Final = (
    f"{_SENTENCE} Covers Static checks, pytest configuration, FastAPI app wiring, "
    f"FastAPI error boundaries, Pydantic boundaries. {_USE_WHEN}"
)
#: With a ``uv.lock`` the uv workflow (priority 28) joins after pytest configuration (23).
UV_PROBE_DESCRIPTION: Final = (
    f"{_SENTENCE} Covers Static checks, pytest configuration, uv workflow, FastAPI app "
    f"wiring, FastAPI error boundaries, Pydantic boundaries. {_USE_WHEN}"
)
_UV_PROBE_REFERENCES: Final = [
    "fastapi-app-wiring.md",
    "fastapi-error-boundaries.md",
    "pydantic-boundaries.md",
    "pytest-configuration.md",
    "python-static-checks.md",
    "python-uv-workflow.md",
]


def _tooling_description(repo: Path) -> str:
    """The emitted description of ``repo``'s ``.claude/skills/python-tooling/SKILL.md``."""
    skill_md = repo / ".claude" / "skills" / "python-tooling" / "SKILL.md"
    frontmatter, _ = split_frontmatter(skill_md.read_text(encoding="utf-8"))
    return str(frontmatter["description"])


def test_reference_probe_python_tooling_names_its_five_active_members(
    reference_probe_repo: Path,
) -> None:
    assert _tooling_description(reference_probe_repo) == PROBE_DESCRIPTION


def test_uv_lock_adds_the_uv_workflow_to_python_tooling(uv_reference_probe_repo: Path) -> None:
    description = _tooling_description(uv_reference_probe_repo)
    assert description == UV_PROBE_DESCRIPTION
    assert len(description) <= 300, f"{len(description)} chars; the cap is 300"
    for root in NATIVE_SKILL_ROOTS:
        references = uv_reference_probe_repo / root / "python-tooling" / "references"
        assert sorted(p.name for p in references.iterdir()) == _UV_PROBE_REFERENCES, root
