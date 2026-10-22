"""The Domino core skills apply only in Domino repos (prU D51, D63; L0-20's deferred line).

Each skill whose pins check it on the Domino probe (``CoreSkillPins.probe``) is
written by sync on that probe (``tests/_budget_probe.py`` ``write_domino_probe``),
not on the standard reference probe, and a committed ``platforms = ["domino"]``
makes a real sync write it in a repo with no Domino marker yet.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.config.files import CONFIG_FILENAME
from tests._budget_probe import init_and_sync_reference_probe, write_reference_probe
from tests._catalog import core_rules
from tests.conftest import apply_hermetic_git_env
from tests.core_skill_pins import ALL_PINS, DOMINO_PROBE_SKILL_IDS
from tests.plugins.superpowers_expectations import NATIVE_SKILL_ROOTS

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

DOMINO_SKILLS: Final = sorted(DOMINO_PROBE_SKILL_IDS)
_MEMBERS: Final = {pins.skill_id: pins.members for pins in ALL_PINS}


def _emitted_roots(repo: Path, skill_id: str) -> list[str]:
    """The native skill roots of ``repo`` that hold ``<skill_id>/SKILL.md``."""
    return [root for root in NATIVE_SKILL_ROOTS if (repo / root / skill_id / "SKILL.md").is_file()]


def _emitted_members(repo: Path, skill_id: str) -> list[str]:
    """The member rule ids written under the first native root's ``<skill_id>/rules/``."""
    rules_dir = repo / NATIVE_SKILL_ROOTS[0] / skill_id / "rules"
    return sorted(path.stem for path in rules_dir.glob("*.md"))


@pytest.fixture(scope="module")
def platforms_domino_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The marker-free reference probe, then ``platforms = ["domino"]`` and a second sync."""
    repo = tmp_path_factory.mktemp("platforms-domino")
    write_reference_probe(repo)
    with pytest.MonkeyPatch.context() as patch:
        config_home = tmp_path_factory.mktemp("xdg-config")
        apply_hermetic_git_env(patch, ceiling=repo.parent, config_home=config_home)
        init_and_sync_reference_probe(repo)
        config = repo / CONFIG_FILENAME
        text = config.read_text(encoding="utf-8")
        head, sep, rest = text.partition("schema_version = 1\n")
        assert sep, f"{CONFIG_FILENAME} has no top-level schema_version line"
        config.write_text(f'{head}{sep}platforms = ["domino"]\n{rest}', encoding="utf-8")
        code = _sync.run(argparse.Namespace(repo_root=str(repo), check=False))
    assert code == 0, f"playbook sync exited {code} after platforms = ['domino']"
    return repo


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
    assert _emitted_roots(domino_probe_repo, skill_id) == list(NATIVE_SKILL_ROOTS)


@pytest.mark.parametrize("skill_id", DOMINO_SKILLS)
def test_standard_probe_does_not_write_the_skill(reference_probe_repo: Path, skill_id: str) -> None:
    assert _emitted_roots(reference_probe_repo, skill_id) == []


@pytest.mark.parametrize("skill_id", DOMINO_SKILLS)
def test_platforms_domino_writes_the_skill_in_a_marker_free_repo(
    platforms_domino_repo: Path, skill_id: str
) -> None:
    assert not (platforms_domino_repo / ".dominoignore").exists()
    assert _emitted_roots(platforms_domino_repo, skill_id) == list(NATIVE_SKILL_ROOTS)
    assert _emitted_members(platforms_domino_repo, skill_id) == sorted(_MEMBERS[skill_id])
