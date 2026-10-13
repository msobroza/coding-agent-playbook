"""Tests for the shared-skills adapter (SPEC.md §10.8)."""

from __future__ import annotations

from importlib import metadata
from typing import TYPE_CHECKING

from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.adapters.claude_code_adapter import ClaudeCodeAdapter
from coding_agent_playbook.adapters.shared_skills_adapter import (
    SHARED_SKILLS_ROOT,
    SharedSkillsAdapter,
)
from coding_agent_playbook.config import Config, ProjectMeta
from coding_agent_playbook.orchestrator import discover_adapters
from coding_agent_playbook.renderer import SENTINEL
from coding_agent_playbook.types import (
    Prompt,
    PromptFrontmatter,
    Rule,
    RuleFrontmatter,
    Skill,
)

if TYPE_CHECKING:
    from pathlib import Path


def _make_rule() -> Rule:
    return Rule(
        frontmatter=RuleFrontmatter(id="r", name="R", description="d", scope="always"),
        body="Body\n",
        template_body="Body\n",
        is_templated=False,
        source_path=None,
        source_package="test",
    )


def _make_prompt() -> Prompt:
    return Prompt(
        frontmatter=PromptFrontmatter(id="p", name="P", description="d", slash="p"),
        body="Body\n",
        template_body="Body\n",
        is_templated=False,
        source_path=None,
        source_package="test",
    )


def _make_skill(*, skill_id: str = "demo-skill", scripts_dir: Path | None = None) -> Skill:
    return Skill(
        frontmatter={"id": skill_id, "name": "Demo", "description": "A demo skill"},
        body="# Demo\n\nDo the thing.\n",
        scripts_dir=scripts_dir,
        references_dir=None,
        source_package="test",
    )


def test_shared_skills_adapter_identity() -> None:
    assert issubclass(SharedSkillsAdapter, Adapter)
    assert SharedSkillsAdapter.name == "shared_skills"
    assert str(SHARED_SKILLS_ROOT) == "shared_skills"


def test_shared_skills_entry_point_is_registered() -> None:
    eps = metadata.entry_points(group="coding_agent_playbook.adapters")
    [ep] = [ep for ep in eps if ep.name == "shared_skills"]
    assert ep.load() is SharedSkillsAdapter


def test_write_rule_and_prompt_are_noops(tmp_path: Path) -> None:
    adapter = SharedSkillsAdapter()
    assert adapter.write_rule(_make_rule(), tmp_path) == []
    assert adapter.write_prompt(_make_prompt(), tmp_path) == []
    assert adapter.finalize(tmp_path) == []
    assert list(tmp_path.iterdir()) == []


def test_write_skill_writes_shared_skills_dir(tmp_path: Path) -> None:
    scripts = tmp_path / "src_scripts"
    scripts.mkdir()
    (scripts / "run.py").write_text("print('x')\n", encoding="utf-8")
    repo = tmp_path / "repo"

    written = SharedSkillsAdapter().write_skill(_make_skill(scripts_dir=scripts), repo)

    skill_dir = repo / "shared_skills" / "demo-skill"
    assert written == [skill_dir / "SKILL.md", skill_dir / "scripts" / "run.py"]
    content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert content.startswith("---\nname: demo-skill\n")
    assert f"<!-- {SENTINEL} -->" in content


def test_write_skill_is_byte_identical_to_claude_code(tmp_path: Path) -> None:
    skill = _make_skill()
    [shared_md] = SharedSkillsAdapter().write_skill(skill, tmp_path)
    [claude_md] = ClaudeCodeAdapter().write_skill(skill, tmp_path)
    assert shared_md.read_bytes() == claude_md.read_bytes()


def test_cleanup_stale_removes_deleted_skill_and_keeps_user_skill(tmp_path: Path) -> None:
    adapter = SharedSkillsAdapter()
    adapter.write_skill(_make_skill(skill_id="gone"), tmp_path)
    kept = adapter.write_skill(_make_skill(skill_id="kept"), tmp_path)
    user_md = tmp_path / "shared_skills" / "hand-written" / "SKILL.md"
    user_md.parent.mkdir(parents=True)
    user_md.write_text("---\nname: hand-written\n---\nmine\n", encoding="utf-8")

    deleted = adapter.cleanup_stale({p.resolve() for p in kept}, tmp_path)

    assert deleted == [tmp_path / "shared_skills" / "gone" / "SKILL.md"]
    assert not (tmp_path / "shared_skills" / "gone").exists()
    assert kept[0].is_file()
    assert user_md.is_file()


def test_discover_adapters_builds_shared_skills_without_rule_registry() -> None:
    """``discover_adapters`` passes ``rule_registry``; the adapter takes none,
    so the orchestrator's no-arg fallback constructs it (like ``agents_md``)."""

    class _StubRegistry:
        def render_for_inclusion(self, rule_id: str, context: dict[str, object]) -> str:
            del context
            return rule_id

    config = Config(
        schema_version=1,
        project=ProjectMeta(name="x", kind="python-library"),
        engine_version="0.1.0a0",
        adapters_enabled=["shared_skills"],
    )
    adapters = discover_adapters(config, rule_registry=_StubRegistry())
    assert isinstance(adapters["shared_skills"], SharedSkillsAdapter)
    assert set(adapters) == {"shared_skills", "agents_md"}
