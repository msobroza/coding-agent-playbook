"""Tests for the shared-skills adapter (SPEC.md §10.8).

The adapter writes the shared skill root ``.agents/skills/`` and declares the
pre-v0.21 root ``shared_skills/`` as a retired output location
(specs/prS-skills-context.md section 5.4.1). Of the prompts it writes only the
review prompt, as the ``review-core`` skill Codex reads (#274).
"""

from __future__ import annotations

from importlib import metadata
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.adapters.claude_code.adapter import ClaudeCodeAdapter
from coding_agent_playbook.adapters.opencode import OpenCodeAdapter
from coding_agent_playbook.adapters.registry import discover_adapters, installed_output_locations
from coding_agent_playbook.adapters.shared_skills import (
    REVIEW_PROMPT_ID,
    REVIEW_SKILL_ID,
    SHARED_SKILLS_ROOT,
    SharedSkillsAdapter,
)
from coding_agent_playbook.agent_harness.adapter import AgentHarnessAdapter
from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.config.model import Config, ProjectMeta
from coding_agent_playbook.generated_output.sentinel import SENTINEL
from coding_agent_playbook.sync._hook_outputs import _generated_locations
from tests.engine_version import ENGINE_VERSION
from tests.fakes import FakeRuleRegistry

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.adapters.skill_dirs.writer import SkillWriter

#: The adapters that write a native skills root through the shared ``SkillWriter``.
_SKILL_ROOT_ADAPTERS: tuple[type[Adapter], ...] = (
    ClaudeCodeAdapter,
    OpenCodeAdapter,
    SharedSkillsAdapter,
)


def _make_rule() -> Rule:
    return Rule(
        frontmatter=RuleFrontmatter(id="r", name="R", description="d", scope="always"),
        body="Body\n",
        template_body="Body\n",
        is_templated=False,
        source_path=None,
        source_package="test",
    )


def _make_prompt(
    prompt_id: str = "p", *, slash: str = "p", includes_rules: list[str] | None = None
) -> Prompt:
    body = "Review the diff.\n\n## Output format\n\nEnd with the verdict.\n"
    return Prompt(
        frontmatter=PromptFrontmatter(
            id=prompt_id,
            name="Review",
            description="Review the provided code or diff.",
            slash=slash,
            includes_rules=list(includes_rules or []),
            input_variables=[{"name": "target", "description": "what to review"}],
        ),
        body=body,
        template_body=body,
        is_templated=False,
        source_path=None,
        source_package="test",
    )


def _make_skill(
    *,
    skill_id: str = "demo-skill",
    scripts_dir: Path | None = None,
    references_dir: Path | None = None,
) -> Skill:
    return Skill(
        frontmatter={"id": skill_id, "name": "Demo", "description": "A demo skill"},
        body="# Demo\n\nDo the thing.\n",
        scripts_dir=scripts_dir,
        references_dir=references_dir,
        source_package="test",
    )


def _write_tree(base: Path, files: dict[str, str]) -> Path:
    """Write ``files`` (POSIX path -> text) under ``base`` and return ``base``."""
    for rel, text in files.items():
        target = base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return base


def _skill_writer_of(adapter_class: type[Adapter]) -> SkillWriter | None:
    writer: SkillWriter | None = getattr(adapter_class, "_SKILL_WRITER", None)
    return writer


def test_shared_skills_adapter_identity() -> None:
    assert issubclass(SharedSkillsAdapter, Adapter)
    assert SharedSkillsAdapter.name == "shared_skills"
    assert SHARED_SKILLS_ROOT.as_posix() == ".agents/skills"
    assert SharedSkillsAdapter.output_locations == (".agents/skills/",)
    assert SharedSkillsAdapter.retired_output_locations == ("shared_skills/",)


def test_adapter_abc_declares_no_retired_location_by_default() -> None:
    """Every other adapter inherits the empty default (SPEC §10.1)."""
    assert Adapter.retired_output_locations == ()
    assert ClaudeCodeAdapter.retired_output_locations == ()


def test_native_skill_roots_are_claude_opencode_and_agents() -> None:
    """D10: claude_code and opencode keep their roots; shared_skills writes .agents/skills."""
    roots: dict[str, list[str]] = {}
    for ep in metadata.entry_points(group="coding_agent_playbook.adapters"):
        adapter_class = ep.load()
        if _skill_writer_of(adapter_class) is not None:
            locations = adapter_class.output_locations
            roots[ep.name] = [loc for loc in locations if loc.endswith("skills/")]
    assert roots == {
        "claude_code": [".claude/skills/"],
        "opencode": [".opencode/skills/"],
        "shared_skills": [".agents/skills/"],
    }


@pytest.mark.parametrize(
    "adapter_class", _SKILL_ROOT_ADAPTERS, ids=[cls.name for cls in _SKILL_ROOT_ADAPTERS]
)
def test_no_adapter_writes_a_file_directly_in_its_skills_root(
    adapter_class: type[Adapter], tmp_path: Path
) -> None:
    """OpenCode v2 loads any root-level ``*.md`` in a skill root as a skill (section 5.4.5)."""
    scripts = _write_tree(tmp_path / "src_scripts", {"run.py": "print('x')\n"})
    references = _write_tree(
        tmp_path / "src_references", {"README.md": "readme\n", "api/v1.md": "v1\n"}
    )
    skill = _make_skill(scripts_dir=scripts, references_dir=references)
    repo = tmp_path / "repo"
    writer = _skill_writer_of(adapter_class)
    assert writer is not None
    skills_root = writer.skills_root(repo)

    written = adapter_class().write_skill(skill, repo)

    relative = [path.relative_to(skills_root).parts for path in written]
    assert len(relative) == 4
    assert all(len(parts) >= 2 and parts[0] == "demo-skill" for parts in relative)
    assert [child.is_dir() for child in skills_root.iterdir()] == [True]


def test_installed_output_locations_include_the_retired_root() -> None:
    """The leftover policy bounds deletion by current and retired locations alike."""
    locations = installed_output_locations()
    assert "shared_skills/" in locations
    assert ".agents/skills/" in locations


def test_generated_path_class_omits_the_retired_root() -> None:
    """guard_config.json's ``generated`` class lists current output only (P1-2)."""
    generated = _generated_locations({"shared_skills": SharedSkillsAdapter()})
    assert ".agents/skills/" in generated
    assert "shared_skills/" not in generated


def test_shared_skills_entry_point_is_registered() -> None:
    eps = metadata.entry_points(group="coding_agent_playbook.adapters")
    [ep] = [ep for ep in eps if ep.name == "shared_skills"]
    assert ep.load() is SharedSkillsAdapter


def test_write_rule_and_every_prompt_but_review_are_noops(tmp_path: Path) -> None:
    """#274: only the review prompt reaches this root; a prompt with its slash but not its id does not."""
    adapter = SharedSkillsAdapter()
    assert adapter.write_rule(_make_rule(), tmp_path) == []
    assert adapter.write_prompt(_make_prompt(), tmp_path) == []
    assert adapter.write_prompt(_make_prompt("tidy", slash=REVIEW_SKILL_ID), tmp_path) == []
    assert adapter.finalize(tmp_path) == []
    assert list(tmp_path.iterdir()) == []


_REVIEW_REGISTRY = FakeRuleRegistry({"python-typing": "### Typing\n\nAnnotate every function.\n"})


def _write_review(tmp_path: Path) -> list[Path]:
    review = _make_prompt(REVIEW_PROMPT_ID, slash="review-core", includes_rules=["python-typing"])
    return SharedSkillsAdapter(rule_registry=_REVIEW_REGISTRY).write_prompt(review, tmp_path)


def test_write_prompt_writes_the_review_prompt_as_the_review_core_skill(tmp_path: Path) -> None:
    """#274: Codex gets the review as ``$review-core``: a skill, not a command, rules inlined."""
    written = _write_review(tmp_path)

    skill_md = tmp_path / ".agents" / "skills" / "review-core" / "SKILL.md"
    assert written == [skill_md]
    frontmatter, body = split_frontmatter(skill_md.read_text(encoding="utf-8"))
    assert frontmatter == {
        "name": "review-core",
        "id": "review-core",
        "description": "Review the provided code or diff.",
    }
    assert body.startswith(f"<!-- {SENTINEL} -->\n\n# Review\n")
    assert "## Reference rules" in body
    assert "Annotate every function." in body
    assert "## Input variables" in body
    assert "## Before you start" not in body


def test_review_core_body_is_the_agent_harness_prompt_leaf_body(tmp_path: Path) -> None:
    """The prompt-as-skill pattern is shared: only the frontmatter differs from the harness leaf."""
    [skill_md] = _write_review(tmp_path / "shared")
    harness = AgentHarnessAdapter(rule_registry=_REVIEW_REGISTRY)
    review = _make_prompt(REVIEW_PROMPT_ID, slash="review-core", includes_rules=["python-typing"])
    harness.write_prompt(review, tmp_path / "harness")
    harness.finalize(tmp_path / "harness")
    leaf = tmp_path / "harness" / "prompts" / "review-core" / "SKILL.md"

    shared_body = split_frontmatter(skill_md.read_text(encoding="utf-8"))[1]
    assert shared_body == split_frontmatter(leaf.read_text(encoding="utf-8"))[1]


def test_write_prompt_never_overwrites_a_hand_written_review_core(tmp_path: Path) -> None:
    """The skill goes through the ``SkillWriter``, so a user's own ``review-core`` dir wins."""
    user_md = tmp_path / ".agents" / "skills" / "review-core" / "SKILL.md"
    user_md.parent.mkdir(parents=True)
    user_md.write_text("---\nname: review-core\ndescription: mine\n---\nmine\n", encoding="utf-8")

    assert _write_review(tmp_path) == []
    assert user_md.read_text(encoding="utf-8").endswith("mine\n")


def test_write_skill_writes_agents_skills_dir(tmp_path: Path) -> None:
    scripts = tmp_path / "src_scripts"
    scripts.mkdir()
    (scripts / "run.py").write_text("print('x')\n", encoding="utf-8")
    repo = tmp_path / "repo"

    written = SharedSkillsAdapter().write_skill(_make_skill(scripts_dir=scripts), repo)

    skill_dir = repo / ".agents" / "skills" / "demo-skill"
    assert written == [skill_dir / "SKILL.md", skill_dir / "scripts" / "run.py"]
    content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert content.startswith("---\nname: demo-skill\n")
    assert f"<!-- {SENTINEL} -->" in content


def test_write_skill_is_byte_identical_to_claude_code(tmp_path: Path) -> None:
    skill = _make_skill()
    [shared_md] = SharedSkillsAdapter().write_skill(skill, tmp_path)
    [claude_md] = ClaudeCodeAdapter().write_skill(skill, tmp_path)
    assert shared_md.read_bytes() == claude_md.read_bytes()


def test_cleanup_stale_never_deletes_skill_files(tmp_path: Path) -> None:
    """Stale skill dirs are settled by sync's lockfile leftover policy, not here."""
    adapter = SharedSkillsAdapter()
    [gone_md] = adapter.write_skill(_make_skill(skill_id="gone"), tmp_path)
    kept = adapter.write_skill(_make_skill(skill_id="kept"), tmp_path)
    user_md = tmp_path / ".agents" / "skills" / "hand-written" / "SKILL.md"
    user_md.parent.mkdir(parents=True)
    user_md.write_text("---\nname: hand-written\n---\nmine\n", encoding="utf-8")

    deleted = adapter.cleanup_stale({p.resolve() for p in kept}, tmp_path)

    assert deleted == []
    assert gone_md.is_file()
    assert kept[0].is_file()
    assert user_md.is_file()


def test_discover_adapters_hands_shared_skills_the_rule_registry() -> None:
    """#274: the registry inlines the ``review-core`` skill's rules, so the adapter takes it."""

    config = Config(
        schema_version=1,
        project=ProjectMeta(name="x", kind="python-library"),
        engine_version=ENGINE_VERSION,
        adapters_enabled=["shared_skills"],
    )
    registry = FakeRuleRegistry()
    adapters = discover_adapters(config, rule_registry=registry)
    assert isinstance(adapters["shared_skills"], SharedSkillsAdapter)
    assert adapters["shared_skills"]._rule_registry is registry
    assert set(adapters) == {"shared_skills", "agents_md"}
