"""Tests for the OpenCode adapter (SPEC.md §10.6)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import yaml

from coding_agent_playbook.adapters.claude_code_adapter import ClaudeCodeAdapter
from coding_agent_playbook.adapters.opencode_adapter import OpenCodeAdapter
from coding_agent_playbook.generated_output.sentinel import SENTINEL
from coding_agent_playbook.prompt_rule_delivery import SkillReference
from coding_agent_playbook.types import (
    Prompt,
    PromptFrontmatter,
    Rule,
    RuleFrontmatter,
    Skill,
)

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
    fm = RuleFrontmatter(
        id=rule_id,
        name=name,
        description=description,
        scope=scope,  # type: ignore[arg-type]
        globs=list(globs) if globs is not None else [],
        priority=priority,
    )
    return Rule(
        frontmatter=fm,
        body=body,
        template_body=body,
        is_templated=False,
        source_path=None,
        source_package="test",
    )


def _make_prompt(
    *,
    prompt_id: str = "generate-tests",
    name: str = "Generate tests",
    description: str = "Generate pytest tests for the provided code",
    slash: str = "generate-tests",
    input_variables: list[dict[str, str]] | None = None,
    includes_rules: list[str] | None = None,
    body: str = "Task: generate tests for {{ target }}.\n",
    write_scope: dict[str, object] | None = None,
) -> Prompt:
    fm = PromptFrontmatter(
        id=prompt_id,
        name=name,
        description=description,
        slash=slash,
        input_variables=list(input_variables) if input_variables is not None else [],
        includes_rules=list(includes_rules) if includes_rules is not None else [],
        write_scope=dict(write_scope or {}),
    )
    return Prompt(
        frontmatter=fm,
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
    body: str = "Skill body.\n",
) -> Skill:
    return Skill(
        frontmatter={
            "id": skill_id,
            "name": name,
            "description": description,
            "slash": skill_id,
        },
        body=body,
        scripts_dir=None,
        references_dir=None,
        source_package="test",
    )


def test_write_rule_returns_empty_list_and_creates_no_files(tmp_path: Path) -> None:
    """OpenCode reads AGENTS.md natively, so the adapter does not write rules."""
    rule = _make_rule()
    adapter = OpenCodeAdapter()
    written = adapter.write_rule(rule, repo_root=tmp_path)
    assert written == []
    # The adapter must not touch the .opencode tree just because a rule was offered.
    assert not (tmp_path / ".opencode").exists()
    # Nor the AGENTS.md path — that belongs to the sibling adapter.
    assert not (tmp_path / "AGENTS.md").exists()


def test_write_skill_writes_native_opencode_skill_dir(tmp_path: Path) -> None:
    """Skills land in OpenCode's native ``.opencode/skills/<id>/SKILL.md`` with
    ``name`` = id, so OpenCode no longer depends on the claude_code adapter."""
    adapter = OpenCodeAdapter()
    written = adapter.write_skill(_make_skill(skill_id="demo-skill"), repo_root=tmp_path)
    skill_md = tmp_path / ".opencode" / "skills" / "demo-skill" / "SKILL.md"
    assert written == [skill_md]
    content = skill_md.read_text(encoding="utf-8")
    assert content.startswith("---\nname: demo-skill\n")
    assert f"---\n<!-- {SENTINEL} -->" in content
    # The .claude tree belongs to the Claude Code adapter.
    assert not (tmp_path / ".claude").exists()


def test_write_skill_is_byte_identical_to_claude_code_output(tmp_path: Path) -> None:
    """Both roots come from one SkillWriter; duplicates discovered by OpenCode
    via .claude/skills/ are therefore identical (and OpenCode keys by name)."""
    skill = _make_skill(skill_id="demo-skill")
    [opencode_md] = OpenCodeAdapter().write_skill(skill, repo_root=tmp_path)
    [claude_md] = ClaudeCodeAdapter().write_skill(skill, repo_root=tmp_path)
    assert opencode_md.read_bytes() == claude_md.read_bytes()


def test_cleanup_stale_never_deletes_skill_files(tmp_path: Path) -> None:
    """Stale ``.opencode/skills/`` dirs are settled by sync's lockfile leftover
    policy (SPEC §4.2 step 9), never by the adapter's own cleanup."""
    adapter = OpenCodeAdapter()
    [gone_md] = adapter.write_skill(_make_skill(skill_id="gone"), repo_root=tmp_path)
    kept = adapter.write_skill(_make_skill(skill_id="kept"), repo_root=tmp_path)
    user_md = tmp_path / ".opencode" / "skills" / "mine" / "SKILL.md"
    user_md.parent.mkdir(parents=True)
    user_md.write_text("---\nname: mine\ndescription: d\n---\nmine\n", encoding="utf-8")

    deleted = adapter.cleanup_stale({p.resolve() for p in kept}, repo_root=tmp_path)

    assert deleted == []
    assert gone_md.is_file()
    assert kept[0].is_file()
    assert user_md.is_file()


def _gray_matter(text: str) -> tuple[dict[str, Any], str]:
    """Parse like OpenCode's gray-matter: frontmatter only when the file starts with ``---``."""
    if not text.startswith("---\n"):
        return {}, text
    front, _, content = text[len("---\n") :].partition("\n---\n")
    return yaml.safe_load(front) or {}, content


def test_write_prompt_creates_file_with_opencode_envelope(tmp_path: Path) -> None:
    """The prompt lands at ``.opencode/command/<slash>.md`` as
    ``---\\ndescription: ...\\n---\\n<!-- AUTOGENERATED ... -->\\n\\n<body>``.

    Regression: the sentinel used to precede the envelope, but OpenCode parses
    commands with gray-matter, which only sees frontmatter at offset 0 — the
    description was lost and the comment + envelope leaked into the prompt.
    """
    prompt = _make_prompt(
        slash="generate-tests",
        description="Generate pytest tests for the provided code",
        body="Task: generate tests.\n",
    )
    adapter = OpenCodeAdapter()
    written = adapter.write_prompt(prompt, repo_root=tmp_path)

    expected = tmp_path / ".opencode" / "command" / "generate-tests.md"
    assert written == [expected]
    assert expected.is_file()

    content = expected.read_text(encoding="utf-8")
    assert content.startswith("---\ndescription:")
    data, template = _gray_matter(content)
    assert data == {"description": "Generate pytest tests for the provided code"}
    assert SENTINEL in template.splitlines()[0]
    assert "description:" not in template
    assert "Task: generate tests." in template


def test_read_only_prompt_renders_agent_plan(tmp_path: Path) -> None:
    """specs/prK-hook-pack.md §E.3: a read-only prompt runs as OpenCode's ``plan`` agent.

    The envelope stays at offset 0 (gray-matter), the sentinel on the first body line."""
    prompt = _make_prompt(
        description="Review code", body="Review.\n", write_scope={"read_only": True}
    )

    [path] = OpenCodeAdapter().write_prompt(prompt, repo_root=tmp_path)

    assert path.read_text(encoding="utf-8").splitlines() == [
        "---",
        "description: Review code",
        "agent: plan",
        "---",
        f"<!-- {SENTINEL} -->",
        "",
        "Review.",
    ]


def test_unscoped_prompt_command_unchanged(tmp_path: Path) -> None:
    """No ``agent`` key without a read-only scope; a glob scope has no native form."""
    plain = _make_prompt(body="Write tests.\n")
    scoped = _make_prompt(body="Write tests.\n", write_scope={"globs": ["tests/**"]})

    [plain_path] = OpenCodeAdapter().write_prompt(plain, repo_root=tmp_path / "plain")
    [scoped_path] = OpenCodeAdapter().write_prompt(scoped, repo_root=tmp_path / "scoped")

    assert scoped_path.read_bytes() == plain_path.read_bytes()
    assert "agent:" not in plain_path.read_text(encoding="utf-8")


def test_write_prompt_substitutes_single_input_variable_with_dollar_arguments(
    tmp_path: Path,
) -> None:
    """One ``input_variables`` entry becomes ``$ARGUMENTS`` in the body."""
    prompt = _make_prompt(
        slash="generate-tests",
        input_variables=[{"name": "target", "description": "path to module"}],
        body="Generate tests for {{ target }} now.\n",
    )
    adapter = OpenCodeAdapter()
    written = adapter.write_prompt(prompt, repo_root=tmp_path)

    content = written[0].read_text(encoding="utf-8")
    assert "$ARGUMENTS" in content
    assert "{{ target }}" not in content


def test_write_prompt_substitutes_multiple_input_variables_with_positional(
    tmp_path: Path,
) -> None:
    """Multiple input variables become ``$1``, ``$2``, ... in order."""
    prompt = _make_prompt(
        slash="refactor",
        input_variables=[
            {"name": "src", "description": "source file"},
            {"name": "style", "description": "style guide"},
        ],
        body="Refactor {{ src }} per {{ style }}.\n",
    )
    adapter = OpenCodeAdapter()
    written = adapter.write_prompt(prompt, repo_root=tmp_path)

    content = written[0].read_text(encoding="utf-8")
    assert "$1" in content
    assert "$2" in content
    assert "{{ src }}" not in content
    assert "{{ style }}" not in content


def test_write_prompt_yaml_escapes_description_with_special_characters(
    tmp_path: Path,
) -> None:
    """A description containing a colon must be YAML-safe in the envelope."""
    prompt = _make_prompt(
        slash="explain",
        description="Explain: be careful with colons",
        body="Body.\n",
    )
    adapter = OpenCodeAdapter()
    written = adapter.write_prompt(prompt, repo_root=tmp_path)

    content = written[0].read_text(encoding="utf-8")
    # The YAML envelope must parse — i.e. the colon is properly quoted, not raw.
    assert (
        "'Explain: be careful with colons'" in content
        or '"Explain: be careful with colons"' in content
    )
    # Sanity: the body still survives untouched.
    assert "Body." in content


class FakeSkillRegistry:
    """The two faces of the sync's registry: rule text and skill references (D15)."""

    def render_for_inclusion(self, rule_id: str, context: dict[str, object]) -> str:
        del context
        return f"### Rule {rule_id}\n\nrendered body.\n"

    def reference_for(self, rule_id: str) -> SkillReference | None:
        return SkillReference("s", f"references/{rule_id}.md")


def test_write_prompt_points_at_skills_when_registry_set(tmp_path: Path) -> None:
    """With the sync's registry the command names the skill reference, never the rule text."""
    adapter = OpenCodeAdapter(rule_registry=FakeSkillRegistry())
    prompt = _make_prompt(
        prompt_id="x",
        name="X",
        description="d",
        slash="x",
        includes_rules=["foo"],
        body="# X\n\nbody line\n",
    )
    [written_path] = adapter.write_prompt(prompt, repo_root=tmp_path)
    content = written_path.read_text(encoding="utf-8")
    assert content == (
        f"---\ndescription: d\n---\n<!-- {SENTINEL} -->\n\n# X\n\n## Before you start\n\n"
        "1. Load skill `s` and read its reference `references/foo.md`.\n"
        "2. For each file in scope, also load any other listed skill whose description "
        "matches it.\n\nbody line\n"
    )
    assert "### " not in content


def test_write_prompt_no_block_when_registry_absent(tmp_path: Path) -> None:
    """Without a registry, ``includes_rules:`` is declarative-only: no block, no rule text."""
    adapter = OpenCodeAdapter()  # no rule_registry
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
    assert content == f"---\ndescription: d\n---\n<!-- {SENTINEL} -->\n\nbody line\n"


def test_cleanup_round_trip_after_slash_rename(tmp_path: Path) -> None:
    """Writing prompt A then prompt B (different slash) then cleanup_stale
    with only B in written_paths must delete A's file.

    This is a round-trip test against the renderer + adapter together. Before
    Fix 1 landed, the renderer omitted the sentinel from the OpenCode command
    output, so A's file had no first-line marker and cleanup would silently
    leave A behind on a slash rename.
    """
    adapter = OpenCodeAdapter()
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
    deleted = adapter.cleanup_stale({b_path.resolve()}, tmp_path)
    assert a_path in deleted
    assert not a_path.exists()
    assert b_path.exists()


def test_write_prompt_overwrites_existing_file(tmp_path: Path) -> None:
    """Re-running write_prompt for the same slash replaces the previous file."""
    prompt = _make_prompt(slash="duplicate", body="first body\n")
    adapter = OpenCodeAdapter()
    adapter.write_prompt(prompt, repo_root=tmp_path)

    # Second write with different body re-uses the same path.
    prompt_v2 = _make_prompt(slash="duplicate", body="second body\n")
    written = adapter.write_prompt(prompt_v2, repo_root=tmp_path)

    content = written[0].read_text(encoding="utf-8")
    assert "second body" in content
    assert "first body" not in content


def _stale_sentinel_body(slug: str) -> str:
    """A command in the current layout: envelope first, sentinel as the first body line."""
    return f"---\ndescription: stale {slug}\n---\n<!-- {SENTINEL} -->\n\nstale body for {slug}\n"


def _legacy_sentinel_body(slug: str) -> str:
    """A command written by older engines: the sentinel on line 1, before the envelope."""
    return f"<!-- {SENTINEL} -->\n---\ndescription: stale {slug}\n---\nstale body for {slug}\n"


@pytest.mark.parametrize("layout", [_stale_sentinel_body, _legacy_sentinel_body])
def test_cleanup_stale_removes_sentinel_tagged_files_not_in_written_paths(
    tmp_path: Path, layout: Any
) -> None:
    """A stale OpenCode command (sentinel-tagged, not re-emitted) is deleted, in
    the current layout and in the line-1 layout older engines wrote."""
    commands = tmp_path / ".opencode" / "command"
    commands.mkdir(parents=True)
    current = commands / "current.md"
    stale = commands / "stale.md"
    current.write_text(layout("current"), encoding="utf-8")
    stale.write_text(layout("stale"), encoding="utf-8")

    adapter = OpenCodeAdapter()
    deleted = adapter.cleanup_stale(written_paths={current.resolve()}, repo_root=tmp_path)

    assert deleted == [stale]
    assert current.is_file()
    assert not stale.exists()


def test_cleanup_stale_preserves_user_authored_files_without_sentinel(
    tmp_path: Path,
) -> None:
    """A file without the sentinel marker is user-authored and never deleted."""
    commands = tmp_path / ".opencode" / "command"
    commands.mkdir(parents=True)
    user_owned = commands / "user-command.md"
    user_owned.write_text(
        "---\ndescription: I wrote this myself\n---\nHand-rolled body.\n",
        encoding="utf-8",
    )

    adapter = OpenCodeAdapter()
    deleted = adapter.cleanup_stale(written_paths=set(), repo_root=tmp_path)

    assert deleted == []
    assert user_owned.is_file()


@pytest.mark.parametrize(
    "text",
    [
        f"---\ndescription: mine\n---\nIntro line.\n<!-- {SENTINEL} -->\n",
        f"Notes about the generator:\n<!-- {SENTINEL} -->\n",
        f"---\ndescription: {SENTINEL}\n---\nHand-rolled body.\n",
        f"---\ndescription: mine\n---\nFiles saying {SENTINEL} are generated.\n",
    ],
    ids=[
        "sentinel-deeper-in-body",
        "sentinel-on-line-2-without-frontmatter",
        "sentinel-in-frontmatter",
        "first-body-line-quotes-it-in-prose",
    ],
)
def test_cleanup_stale_preserves_user_files_that_only_quote_the_sentinel(
    tmp_path: Path, text: str
) -> None:
    """Only the two engine positions count: a user file quoting the sentinel elsewhere stays."""
    commands = tmp_path / ".opencode" / "command"
    commands.mkdir(parents=True)
    user_owned = commands / "user-command.md"
    user_owned.write_text(text, encoding="utf-8")

    deleted = OpenCodeAdapter().cleanup_stale(written_paths=set(), repo_root=tmp_path)

    assert deleted == []
    assert user_owned.is_file()


def test_cleanup_stale_removes_a_stale_command_saved_with_a_bom(tmp_path: Path) -> None:
    """Some editors add a UTF-8 BOM on save; the command is still engine output."""
    commands = tmp_path / ".opencode" / "command"
    commands.mkdir(parents=True)
    stale = commands / "stale.md"
    stale.write_text("\ufeff" + _stale_sentinel_body("stale"), encoding="utf-8")

    deleted = OpenCodeAdapter().cleanup_stale(written_paths=set(), repo_root=tmp_path)

    assert deleted == [stale]


def test_cleanup_stale_returns_empty_when_directory_is_missing(
    tmp_path: Path,
) -> None:
    """First sync (no ``.opencode/command/`` yet) is a no-op, not an error."""
    adapter = OpenCodeAdapter()
    deleted = adapter.cleanup_stale(written_paths=set(), repo_root=tmp_path)

    assert deleted == []


def test_cleanup_stale_ignores_subdirectories_under_command_root(
    tmp_path: Path,
) -> None:
    """``rglob('*')`` yields directories too; the scanner must skip them.

    Without the ``is_file()`` guard the loop would try to read a directory
    as text and crash. A nested subdir is unusual for OpenCode but possible
    if the user stashes auxiliary files alongside generated commands.
    """
    commands = tmp_path / ".opencode" / "command"
    nested = commands / "subdir"
    nested.mkdir(parents=True)
    stale = commands / "stale.md"
    stale.write_text(_stale_sentinel_body("stale"), encoding="utf-8")

    adapter = OpenCodeAdapter()
    deleted = adapter.cleanup_stale(written_paths=set(), repo_root=tmp_path)

    assert deleted == [stale]
    assert nested.is_dir()


def test_cleanup_stale_skips_files_that_cannot_be_read_as_text(
    tmp_path: Path,
) -> None:
    """Binary or otherwise-unreadable files are left alone, not crashed on."""
    commands = tmp_path / ".opencode" / "command"
    commands.mkdir(parents=True)
    # Binary content with invalid UTF-8 — read_text(encoding='utf-8') raises
    # UnicodeDecodeError, which the cleanup loop must catch.
    binary = commands / "blob.md"
    binary.write_bytes(b"\xff\xfe\x00\x00not-text\n")
    stale = commands / "stale.md"
    stale.write_text(_stale_sentinel_body("stale"), encoding="utf-8")

    adapter = OpenCodeAdapter()
    deleted = adapter.cleanup_stale(written_paths=set(), repo_root=tmp_path)

    assert deleted == [stale]
    assert binary.is_file()  # binary preserved despite being unreadable


def test_cleanup_stale_does_not_touch_unrelated_directories(tmp_path: Path) -> None:
    """The OpenCode adapter must only scan ``.opencode/command/``.

    Sibling adapters own ``AGENTS.md`` and ``.claude/`` — if the OpenCode
    adapter scanned those too, it would delete files it does not own.
    """
    # A sentinel-tagged file outside the adapter's territory.
    sibling = tmp_path / ".claude" / "commands" / "leave-me-alone.md"
    sibling.parent.mkdir(parents=True)
    sibling.write_text(_stale_sentinel_body("leave-me-alone"), encoding="utf-8")
    agents_md = tmp_path / "AGENTS.md"
    agents_md.write_text(_stale_sentinel_body("agents"), encoding="utf-8")
    # A stale engine-owned Claude skill belongs to the Claude Code adapter.
    ClaudeCodeAdapter().write_skill(_make_skill(skill_id="claude-only"), repo_root=tmp_path)
    # User-owned OpenCode config (SPEC §10.6.4).
    user_owned = [
        tmp_path / ".opencode" / "agent" / "reviewer.md",
        tmp_path / ".opencode" / "plugin" / "hook.ts",
        tmp_path / "opencode.json",
    ]
    for path in user_owned:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_stale_sentinel_body(path.name), encoding="utf-8")

    adapter = OpenCodeAdapter()
    deleted = adapter.cleanup_stale(written_paths=set(), repo_root=tmp_path)

    assert deleted == []
    assert sibling.is_file()
    assert agents_md.is_file()
    assert (tmp_path / ".claude" / "skills" / "claude-only" / "SKILL.md").is_file()
    assert all(path.is_file() for path in user_owned)
