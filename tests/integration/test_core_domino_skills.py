"""The Domino core skills apply only in Domino repos (prU D51, D63; L0-20's deferred line).

Each skill whose pins mark it ``domino_only`` is written by sync on the Domino
probe (``tests/_budget_probe.py`` ``write_domino_probe``), not on the standard
reference probe, and a committed ``platforms = ["domino"]`` turns its members on
in a repo with no Domino marker yet.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.config.files import CONFIG_FILENAME
from coding_agent_playbook.detector.facts import detect
from coding_agent_playbook.detector.predicate import evaluate_predicate
from tests._budget_probe import write_reference_probe
from tests._catalog import core_rules
from tests.core_skill_pins import ALL_PINS

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.detector.facts import Facts

pytestmark = pytest.mark.catalog

#: The ids of the core skills whose every member gates on ``domino_project``.
DOMINO_SKILLS: Final = sorted(pins.skill_id for pins in ALL_PINS if pins.domino_only)
_MEMBERS: Final = {pins.skill_id: pins.members for pins in ALL_PINS}


def _skill_md(repo: Path, skill_id: str) -> Path:
    return repo / ".claude" / "skills" / skill_id / "SKILL.md"


def test_a_domino_skill_ships() -> None:
    assert "domino-agents" in DOMINO_SKILLS


@pytest.mark.parametrize("skill_id", DOMINO_SKILLS)
def test_every_member_gates_on_domino_project(skill_id: str) -> None:
    rules = core_rules()
    ungated = [
        rule_id
        for rule_id in _MEMBERS[skill_id]
        if rules[rule_id].frontmatter.applies_if.get("domino_project") is not True
    ]
    assert ungated == [], f"{skill_id}: members without the domino_project gate: {ungated}"


@pytest.mark.parametrize("skill_id", DOMINO_SKILLS)
def test_domino_probe_writes_the_skill(domino_probe_repo: Path, skill_id: str) -> None:
    assert _skill_md(domino_probe_repo, skill_id).is_file()


@pytest.mark.parametrize("skill_id", DOMINO_SKILLS)
def test_standard_probe_does_not_write_the_skill(reference_probe_repo: Path, skill_id: str) -> None:
    assert not _skill_md(reference_probe_repo, skill_id).exists()


@pytest.mark.parametrize("skill_id", DOMINO_SKILLS)
def test_platforms_domino_activates_the_skill_in_a_marker_free_repo(
    tmp_path: Path, skill_id: str
) -> None:
    write_reference_probe(tmp_path)
    before = detect(tmp_path)
    (tmp_path / CONFIG_FILENAME).write_text(
        'schema_version = 1\nplatforms = ["domino"]\n', encoding="utf-8"
    )
    after = detect(tmp_path)
    rules = core_rules()

    def active(facts: Facts) -> list[str]:
        return [
            rule_id
            for rule_id in _MEMBERS[skill_id]
            if evaluate_predicate(rules[rule_id].frontmatter.applies_if, facts)
        ]

    assert active(before) == []
    assert active(after) == list(_MEMBERS[skill_id])
