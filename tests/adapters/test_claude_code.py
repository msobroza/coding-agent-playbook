"""Tests for the Claude Code adapter (PR B Track 7).

The composed rule output (the ``.claude/CLAUDE.md`` stub and the
``.claude/rules/coding-agent-playbook.md`` rules file) and its staleness are
covered in ``test_claude_code_rules.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.adapters.claude_code.adapter import ClaudeCodeAdapter
from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.generated_output.sentinel import SENTINEL
from coding_agent_playbook.rendering.prompt_rule_delivery import SkillReference

if TYPE_CHECKING:
    from pathlib import Path


def _make_rule(
    *,
    rule_id: str = "python-typing",
    name: str = "Python typing standards",
    description: str = "Type hints everywhere",
    scope: str = "scoped",
    globs: list[str] | None = None,
    priority: int = 50,
    body: str = "# Python typing\n\nUse type hints.\n",
) -> Rule:
    return Rule(
        frontmatter=RuleFrontmatter(
            id=rule_id,
            name=name,
            description=description,
            scope=scope,  # type: ignore[arg-type]
            globs=globs or [],
            priority=priority,
        ),
        body=body,
        template_body=body,
        is_templated=False,
        source_path=None,
        source_package="test",
    )


def _make_prompt(
    *,
    prompt_id: str = "review",
    name: str = "Review",
    description: str = "Review code",
    slash: str = "review",
    body: str = "# Review\n\nReview the diff.\n",
    includes_rules: list[str] | None = None,
    input_variables: list[dict[str, object]] | None = None,
    write_scope: dict[str, object] | None = None,
) -> Prompt:
    return Prompt(
        frontmatter=PromptFrontmatter(
            id=prompt_id,
            name=name,
            description=description,
            slash=slash,
            includes_rules=includes_rules or [],
            input_variables=input_variables or [],
            write_scope=dict(write_scope or {}),
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
    name: str = "Demo skill",
    description: str = "A demo skill",
    body: str = "# Demo skill\n\nDo the thing.\n",
    scripts_dir: Path | None = None,
    references_dir: Path | None = None,
) -> Skill:
    return Skill(
        frontmatter={"id": skill_id, "name": name, "description": description},
        body=body,
        scripts_dir=scripts_dir,
        references_dir=references_dir,
        source_package="test",
    )


def test_claude_code_adapter_is_adapter_subclass():
    assert issubclass(ClaudeCodeAdapter, Adapter)
    assert ClaudeCodeAdapter.name == "claude_code"


def test_claude_code_adapter_instantiates_with_empty_buffer():
    adapter = ClaudeCodeAdapter()
    assert adapter._buffered_rules == []


def test_claude_code_write_rule_buffers_does_not_write(tmp_path):
    rule = _make_rule(rule_id="x", priority=50, globs=["**/*.py"])
    adapter = ClaudeCodeAdapter()
    written = adapter.write_rule(rule, repo_root=tmp_path)
    assert written == []
    # No .claude/ directory or files were created.
    assert not (tmp_path / ".claude").exists()
    # The rule was buffered for finalize() to compose.
    assert len(adapter._buffered_rules) == 1
    priority, rule_id, rendered_section = adapter._buffered_rules[0]
    assert priority == 50
    assert rule_id == "x"
    # Rendered section is a claude_md_section: ## heading, optional applies-to,
    # body, separator.
    assert "## Python typing standards" in rendered_section
    assert "*Applies to: `**/*.py`*" in rendered_section


def test_claude_code_write_rule_appends_to_buffer_in_call_order(tmp_path):
    adapter = ClaudeCodeAdapter()
    adapter.write_rule(_make_rule(rule_id="a", priority=10, name="A"), tmp_path)
    adapter.write_rule(_make_rule(rule_id="b", priority=20, name="B"), tmp_path)
    assert [item[:2] for item in adapter._buffered_rules] == [(10, "a"), (20, "b")]


def test_claude_code_write_prompt_creates_command_file(tmp_path):
    prompt = _make_prompt(
        slash="review",
        name="Review",
        description="Review code",
        body="# Review\n\nReview the diff.\n",
    )
    adapter = ClaudeCodeAdapter()
    written = adapter.write_prompt(prompt, repo_root=tmp_path)
    expected = tmp_path / ".claude" / "commands" / "review.md"
    assert written == [expected]
    assert expected.is_file()
    content = expected.read_text(encoding="utf-8")
    # The sentinel HTML comment is the first line so cleanup can recognise this
    # file as engine-owned. Claude Code commands are otherwise pure markdown —
    # no YAML frontmatter fence.
    lines = content.splitlines()
    assert SENTINEL in lines[0]
    assert not lines[1].startswith("---")
    # The H1 from the body is preserved (renderer doesn't double-prepend).
    assert "# Review" in content
    # Sanity: the body content is present.
    assert "Review the diff." in content


def test_claude_code_write_prompt_prepends_h1_when_body_lacks_one(tmp_path):
    prompt = _make_prompt(
        slash="audit",
        name="Audit",
        description="Audit code",
        body="Audit the diff for issues.\n",
    )
    adapter = ClaudeCodeAdapter()
    adapter.write_prompt(prompt, repo_root=tmp_path)
    content = (tmp_path / ".claude" / "commands" / "audit.md").read_text(encoding="utf-8")
    # The sentinel comment is the first line so cleanup can recognise this as
    # engine-owned; the renderer then prepends `# {name}` when the body lacks an H1.
    lines = content.splitlines()
    assert SENTINEL in lines[0]
    assert lines[1] == "# Audit"


class FakeSkillRegistry:
    """The two faces of the sync's registry: rule text and skill references (D15).

    Every rule id renders a body and lives in skill ``s`` as
    ``references/<id>.md``, so a command that inlined text would show both.
    """

    def render_for_inclusion(self, rule_id: str, context: dict[str, object]) -> str:
        del context
        return f"### Rule {rule_id}\n\nrendered body.\n"

    def reference_for(self, rule_id: str) -> SkillReference | None:
        return SkillReference("s", f"references/{rule_id}.md")


def test_claude_code_write_prompt_points_at_skills_when_registry_set(tmp_path):
    """With the sync's registry the command names the skill reference, never the rule text."""
    adapter = ClaudeCodeAdapter(rule_registry=FakeSkillRegistry())
    prompt = _make_prompt(
        prompt_id="x",
        name="X",
        description="d",
        slash="x",
        includes_rules=["foo"],
        body="body line\n",
    )
    [written_path] = adapter.write_prompt(prompt, repo_root=tmp_path)
    content = written_path.read_text(encoding="utf-8")
    assert content == (
        f"<!-- {SENTINEL} -->\n# X\n\n## Before you start\n\n"
        "1. Load skill `s` and read its reference `references/foo.md`.\n"
        "2. For each file in scope, also load any other listed skill whose description "
        "matches it.\n\nbody line\n"
    )
    assert "### " not in content


def test_claude_code_write_prompt_no_block_when_registry_absent(tmp_path):
    """Without a registry, ``includes_rules:`` is declarative-only: no block, no
    rule text. This is the documented default when the orchestrator has not
    built a merged-overlay registry.
    """
    adapter = ClaudeCodeAdapter()  # no rule_registry
    prompt = _make_prompt(
        prompt_id="x",
        name="X",
        description="d",
        slash="x",
        includes_rules=["foo"],
        body="body line\n",
    )
    [written_path] = adapter.write_prompt(prompt, repo_root=tmp_path)
    content = written_path.read_text(encoding="utf-8")
    assert content == f"<!-- {SENTINEL} -->\n# X\n\nbody line\n"


def test_claude_code_cleanup_round_trip_after_slash_rename(tmp_path):
    """Writing prompt A then prompt B (different slash) then cleanup_stale
    with only B in written_paths must delete A's file.

    This is a round-trip test against the renderer + adapter together. Before
    Fix 1 landed, the renderer omitted the sentinel from the Claude command
    output, so A's file had no first-line marker and cleanup would silently
    leave A behind on a slash rename.
    """
    adapter = ClaudeCodeAdapter()
    prompt_a = _make_prompt(
        prompt_id="a",
        name="A",
        description="A",
        slash="a",
        body="A body\n",
    )
    prompt_b = _make_prompt(
        prompt_id="b",
        name="B",
        description="B",
        slash="b",
        body="B body\n",
    )
    a_path = adapter.write_prompt(prompt_a, tmp_path)[0]
    b_path = adapter.write_prompt(prompt_b, tmp_path)[0]
    deleted = adapter.cleanup_stale({b_path.resolve()}, repo_root=tmp_path)
    assert a_path in deleted
    assert not a_path.exists()
    assert b_path.exists()


# --- write_scope: native read-only constraint (specs/prK-lifecycle-hooks.md §C.4.3) ---


def test_read_only_prompt_renders_disallowed_tools_frontmatter(tmp_path):
    prompt = _make_prompt(write_scope={"read_only": True})

    [path] = ClaudeCodeAdapter().write_prompt(prompt, repo_root=tmp_path)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[:4] == [
        "---",
        "disallowed-tools: Edit Write NotebookEdit",
        "---",
        f"<!-- {SENTINEL} -->",
    ]
    assert lines[4] == "# Review"
    assert Adapter._carries_sentinel(path)


def test_read_only_command_is_cleaned_when_stale(tmp_path):
    adapter = ClaudeCodeAdapter()
    stale = adapter.write_prompt(_make_prompt(write_scope={"read_only": True}), tmp_path)[0]
    kept = adapter.write_prompt(_make_prompt(prompt_id="b", slash="b"), tmp_path)[0]

    deleted = adapter.cleanup_stale({kept.resolve()}, repo_root=tmp_path)

    assert stale in deleted
    assert not stale.exists()
    assert kept.exists()


@pytest.mark.parametrize("scope", [None, {"globs": ["tests/**"]}])
def test_unscoped_and_glob_scoped_prompts_render_byte_identically(
    tmp_path: Path, scope: dict[str, object] | None
) -> None:
    """Only ``read_only`` has a native form; every other prompt renders exactly as before."""
    plain = ClaudeCodeAdapter().write_prompt(_make_prompt(), tmp_path / "plain")[0]
    scoped = ClaudeCodeAdapter().write_prompt(_make_prompt(write_scope=scope), tmp_path / "s")[0]

    assert scoped.read_bytes() == plain.read_bytes()
    assert (
        plain.read_text(encoding="utf-8") == f"<!-- {SENTINEL} -->\n# Review\n\nReview the diff.\n"
    )


def test_claude_code_write_skill_writes_skill_md_only(tmp_path):
    """A skill with no scripts/references writes just SKILL.md."""
    skill = _make_skill(
        skill_id="demo",
        name="Demo skill",
        description="Demo skill description",
        body="# Demo\n\nDo the thing.\n",
    )
    adapter = ClaudeCodeAdapter()
    written = adapter.write_skill(skill, repo_root=tmp_path)
    expected = tmp_path / ".claude" / "skills" / "demo" / "SKILL.md"
    assert expected in written
    assert expected.is_file()
    content = expected.read_text(encoding="utf-8")
    # SKILL.md keeps the skill's frontmatter + body, but the Agent Skills
    # standard requires ``name`` == the directory name, so name is the id.
    assert content.startswith("---")
    assert "id: demo" in content
    assert "name: demo" in content
    assert "name: Demo skill" not in content
    assert "description: Demo skill description" in content
    assert "Do the thing." in content


def test_claude_code_write_skill_places_sentinel_on_first_body_line(tmp_path):
    """Frontmatter stays on line 1 (agent parsers need ``^---``); the sentinel
    is the first body line so cleanup can recognise the dir as engine-owned."""
    adapter = ClaudeCodeAdapter()
    [skill_md] = adapter.write_skill(_make_skill(skill_id="demo"), repo_root=tmp_path)
    lines = skill_md.read_text(encoding="utf-8").splitlines()
    closing = lines.index("---", 1)
    assert lines[0] == "---"
    assert lines[closing + 1] == f"<!-- {SENTINEL} -->"


def test_claude_code_write_skill_rejects_path_traversal_id(tmp_path):
    adapter = ClaudeCodeAdapter()
    with pytest.raises(ValueError, match="not path-safe"):
        adapter.write_skill(_make_skill(skill_id="../escape"), repo_root=tmp_path)
    assert not (tmp_path / ".claude").exists()


def test_claude_code_write_skill_copies_scripts_directory(tmp_path):
    """Scripts in the source dir get mirrored to .claude/skills/<id>/scripts/."""
    scripts_src = tmp_path / "src_scripts"
    scripts_src.mkdir()
    (scripts_src / "helper.sh").write_text("#!/bin/sh\necho hi\n", encoding="utf-8")
    (scripts_src / "nested").mkdir()
    (scripts_src / "nested" / "deep.py").write_text("print('deep')\n", encoding="utf-8")

    skill = _make_skill(skill_id="with-scripts", scripts_dir=scripts_src)
    repo_root = tmp_path / "repo"
    adapter = ClaudeCodeAdapter()
    written = adapter.write_skill(skill, repo_root=repo_root)

    helper = repo_root / ".claude" / "skills" / "with-scripts" / "scripts" / "helper.sh"
    deep = repo_root / ".claude" / "skills" / "with-scripts" / "scripts" / "nested" / "deep.py"
    skill_md = repo_root / ".claude" / "skills" / "with-scripts" / "SKILL.md"

    assert helper.is_file()
    assert helper.read_text(encoding="utf-8") == "#!/bin/sh\necho hi\n"
    assert deep.is_file()
    assert deep.read_text(encoding="utf-8") == "print('deep')\n"
    # All three paths are in the written list.
    assert skill_md in written
    assert helper in written
    assert deep in written


def test_claude_code_write_skill_copies_references_directory(tmp_path):
    """References in the source dir get mirrored to .claude/skills/<id>/references/."""
    refs_src = tmp_path / "src_refs"
    refs_src.mkdir()
    (refs_src / "guide.md").write_text("# Reference guide\n", encoding="utf-8")

    skill = _make_skill(skill_id="with-refs", references_dir=refs_src)
    repo_root = tmp_path / "repo"
    adapter = ClaudeCodeAdapter()
    written = adapter.write_skill(skill, repo_root=repo_root)

    guide = repo_root / ".claude" / "skills" / "with-refs" / "references" / "guide.md"
    assert guide.is_file()
    assert guide.read_text(encoding="utf-8") == "# Reference guide\n"
    assert guide in written


def test_claude_code_write_skill_does_not_degrade_to_prompt(tmp_path):
    """write_skill must bypass the ABC's default Skill->Prompt degrade."""
    skill = _make_skill(skill_id="native")
    adapter = ClaudeCodeAdapter()
    adapter.write_skill(skill, repo_root=tmp_path)
    # Skills land under .claude/skills/, not under .claude/commands/.
    assert (tmp_path / ".claude" / "skills" / "native" / "SKILL.md").is_file()
    assert not (tmp_path / ".claude" / "commands").exists()


def test_claude_code_output_directories(tmp_path):
    """Output directories advertise where cleanup can scan for stale files."""
    adapter = ClaudeCodeAdapter()
    dirs = list(adapter._output_directories(tmp_path))
    # .claude/skills/ is never scanned: stale skill output is settled by sync's
    # lockfile leftover policy (SPEC §4.2 step 9). The hook launcher's dir is
    # (prK §C.0); settings.json never is (co-owned, edited in place).
    assert dirs == [tmp_path / ".claude" / "commands", tmp_path / ".claude" / "hooks" / "playbook"]


def test_claude_code_cleanup_stale_removes_stale_command(tmp_path):
    """A sentinel-tagged command file not in written_paths is deleted."""
    commands = tmp_path / ".claude" / "commands"
    commands.mkdir(parents=True)
    current = commands / "current.md"
    stale = commands / "stale.md"
    current.write_text(f"<!-- {SENTINEL} -->\n# current\n", encoding="utf-8")
    stale.write_text(f"<!-- {SENTINEL} -->\n# stale\n", encoding="utf-8")

    adapter = ClaudeCodeAdapter()
    deleted = adapter.cleanup_stale({current.resolve()}, repo_root=tmp_path)

    assert stale.resolve() in {p.resolve() for p in deleted}
    assert not stale.exists()
    assert current.is_file()


def test_claude_code_cleanup_stale_preserves_user_authored_files(tmp_path):
    """A file without the sentinel is never deleted, even if not in written_paths."""
    commands = tmp_path / ".claude" / "commands"
    commands.mkdir(parents=True)
    user_file = commands / "user.md"
    user_file.write_text("# User-authored, no sentinel\n", encoding="utf-8")

    adapter = ClaudeCodeAdapter()
    deleted = adapter.cleanup_stale(set(), repo_root=tmp_path)

    assert user_file.resolve() not in {p.resolve() for p in deleted}
    assert user_file.is_file()


def test_claude_code_cleanup_stale_never_deletes_skill_files(tmp_path):
    """A removed skill's ``.claude/skills/<id>/`` is NOT cleaned here: stale skill
    output is settled by ``playbook sync``'s lockfile leftover policy (pristine +
    untracked + listed), which also protects user-edited and user-added files
    (SPEC §4.2 step 9, §10.8). The end-to-end removal is in tests/cli/."""
    scripts = tmp_path / "src_scripts"
    scripts.mkdir()
    (scripts / "helper.sh").write_text("echo hi\n", encoding="utf-8")
    repo_root = tmp_path / "repo"
    adapter = ClaudeCodeAdapter()
    gone = adapter.write_skill(_make_skill(skill_id="gone", scripts_dir=scripts), repo_root)
    kept = adapter.write_skill(_make_skill(skill_id="kept"), repo_root)

    deleted = adapter.cleanup_stale({p.resolve() for p in kept}, repo_root=repo_root)

    assert deleted == []
    assert all(path.is_file() for path in [*gone, *kept])


def test_claude_code_cleanup_stale_preserves_user_authored_skill_dir(tmp_path):
    """A skill dir whose SKILL.md lacks the sentinel is user-authored: no file
    in it is touched, even one whose first line carries the sentinel."""
    skill_dir = tmp_path / ".claude" / "skills" / "my-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("---\nname: my-skill\n---\nmine\n", encoding="utf-8")
    helper = skill_dir / "helper.md"
    helper.write_text(f"# {SENTINEL}\nhelper\n", encoding="utf-8")

    deleted = ClaudeCodeAdapter().cleanup_stale(set(), repo_root=tmp_path)

    assert deleted == []
    assert (skill_dir / "SKILL.md").is_file()
    assert helper.is_file()


def test_claude_code_cleanup_stale_skips_binary_files(tmp_path):
    """A non-UTF-8 file in an output directory must not crash the scan."""
    commands = tmp_path / ".claude" / "commands"
    commands.mkdir(parents=True)
    binary = commands / "image.bin"
    # Write bytes that are not valid UTF-8.
    binary.write_bytes(b"\x80\x81\x82\x83\xff\xfe")

    adapter = ClaudeCodeAdapter()
    deleted = adapter.cleanup_stale(set(), repo_root=tmp_path)

    # Binary file is neither deleted nor crashes the scan.
    assert binary.resolve() not in {p.resolve() for p in deleted}
    assert binary.exists()
