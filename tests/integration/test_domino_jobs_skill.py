"""The ``domino-jobs`` core skill follows the Domino gate (prU D51, D63; L0-20's deferred line).

Every member rule of ``domino-jobs`` gates on ``domino_project``, so sync writes
the skill only where the detector finds a reliable Domino marker or the committed
config names the platform: the Domino probe gets it, the standard reference
probe does not, and ``platforms = ["domino"]`` turns it on in a repo without
markers. Each case is one real ``playbook init`` / ``sync``, read at the
emitted skill directory and the "Where guidance lives" map. On the Domino probe
the emitted skill also lists and ships its where-outputs-go guide (D47); the
guide's own content is checked in tests/core_skills/domino_jobs/test_references.py.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.config.files import CONFIG_FILENAME
from tests._budget_probe import init_and_sync_reference_probe, write_reference_probe
from tests._catalog import core_skill_root
from tests._mapping_references import mapped_references
from tests.conftest import apply_hermetic_git_env
from tests.core_skill_pins.domino_jobs import PINS
from tests.plugins.superpowers_expectations import NATIVE_SKILL_ROOTS

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_SKILL: Final = "domino-jobs"
_WHERE_LINE: Final = "skill `domino-jobs`"
_GUIDE: Final = "references/where-outputs-go.md"


def _emitted_roots(repo: Path) -> list[str]:
    """The native skill roots of ``repo`` that hold ``domino-jobs/SKILL.md``."""
    return [root for root in NATIVE_SKILL_ROOTS if (repo / root / _SKILL / "SKILL.md").is_file()]


def _emitted_members(repo: Path) -> list[str]:
    """The member rule ids written under the first native root's ``domino-jobs/rules/``."""
    rules_dir = repo / NATIVE_SKILL_ROOTS[0] / _SKILL / "rules"
    return sorted(path.name.removesuffix(".md") for path in rules_dir.glob("*.md"))


def _agents_md(repo: Path) -> str:
    return (repo / "AGENTS.md").read_text(encoding="utf-8")


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


def test_domino_probe_emits_domino_jobs(domino_probe_repo: Path) -> None:
    assert _emitted_roots(domino_probe_repo) == list(NATIVE_SKILL_ROOTS)
    assert _WHERE_LINE in _agents_md(domino_probe_repo)


def test_standard_probe_does_not_emit_domino_jobs(reference_probe_repo: Path) -> None:
    assert _emitted_roots(reference_probe_repo) == []
    assert _WHERE_LINE not in _agents_md(reference_probe_repo)


def test_platforms_domino_emits_domino_jobs_without_markers(platforms_domino_repo: Path) -> None:
    assert not (platforms_domino_repo / ".dominoignore").exists()
    assert _emitted_roots(platforms_domino_repo) == list(NATIVE_SKILL_ROOTS)
    assert _WHERE_LINE in _agents_md(platforms_domino_repo)
    assert _emitted_members(platforms_domino_repo) == sorted(PINS.members)


def test_domino_probe_lists_the_guide_with_its_open_when(domino_probe_repo: Path) -> None:
    """D47: the emitted skill lists the mapping's reference with its open_when line."""
    skill_md = (domino_probe_repo / ".claude" / "skills" / _SKILL / "SKILL.md").read_text(
        encoding="utf-8"
    )
    listed = skill_md.partition("## References and examples\n")[2]
    lines = [line for line in listed.splitlines() if line.startswith("- [")]
    open_when = mapped_references(_SKILL)[_GUIDE].open_when
    assert lines == [f"- [{_GUIDE}]({_GUIDE}) — Open when: {open_when}"]


def test_domino_probe_ships_the_guide(domino_probe_repo: Path) -> None:
    emitted = domino_probe_repo / ".claude" / "skills" / _SKILL / _GUIDE
    assert emitted.read_bytes() == (core_skill_root(_SKILL) / _GUIDE).read_bytes()
