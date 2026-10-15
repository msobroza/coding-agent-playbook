"""Tests for the Continue adapter (PR B Track 6). SPEC §10.2."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from coding_agent_playbook.adapters.continue_adapter import ContinueAdapter
from coding_agent_playbook.renderer import SENTINEL
from coding_agent_playbook.types import (
    Prompt,
    PromptFrontmatter,
    Rule,
    RuleFrontmatter,
    Skill,
)
from tests.hook_samples import resolved_hook

if TYPE_CHECKING:
    from pathlib import Path


class _StubRegistry:
    """In-memory ``RuleRegistry`` used by the Continue adapter tests."""

    def __init__(self, fragments: dict[str, str]) -> None:
        self._fragments = fragments

    def render_for_inclusion(self, rule_id: str, context: dict[str, Any]) -> str:
        return self._fragments.get(rule_id, "")


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
            globs=list(globs) if globs is not None else [],
            priority=priority,
        ),
        body=body,
        template_body=body,
        is_templated=False,
        source_path=None,
        source_package="coding_agent_playbook",
    )


# --- Task 6.2: write_rule -------------------------------------------------


def test_continue_write_rule_creates_file_with_sentinel(tmp_path: Path) -> None:
    rule = _make_rule(rule_id="x", priority=50, globs=["**/*.py"])
    adapter = ContinueAdapter()
    written = adapter.write_rule(rule, repo_root=tmp_path)
    expected = tmp_path / ".continue" / "rules" / "50-x.md"
    assert written == [expected]
    content = expected.read_text(encoding="utf-8")
    assert SENTINEL in content.split("\n", 1)[0]
    assert "name: Python typing standards" in content
    assert "alwaysApply: false" in content
    assert "**/*.py" in content


def test_continue_write_rule_zero_pads_priority(tmp_path: Path) -> None:
    """Priority must format as two-digit zero-padded for stable lex sort."""
    rule = _make_rule(rule_id="early", priority=5)
    written = ContinueAdapter().write_rule(rule, repo_root=tmp_path)
    assert written == [tmp_path / ".continue" / "rules" / "05-early.md"]


def test_continue_write_rule_creates_parent_directory(tmp_path: Path) -> None:
    """write_rule must create .continue/rules/ if it does not already exist."""
    rule = _make_rule(rule_id="x", priority=50)
    assert not (tmp_path / ".continue").exists()
    ContinueAdapter().write_rule(rule, repo_root=tmp_path)
    assert (tmp_path / ".continue" / "rules").is_dir()


def test_continue_write_rule_always_scope_drops_globs(tmp_path: Path) -> None:
    """A scope=always rule must render alwaysApply: true with no globs (renderer
    contract — Continue treats globs as meaningful only when alwaysApply=false)."""
    rule = _make_rule(rule_id="x", scope="always", globs=["**/*.py"])
    written = ContinueAdapter().write_rule(rule, repo_root=tmp_path)
    content = written[0].read_text(encoding="utf-8")
    assert "alwaysApply: true" in content
    assert "globs:" not in content


# --- Task 6.3: write_prompt -----------------------------------------------


def _make_prompt(
    *,
    prompt_id: str = "generate-tests",
    name: str = "Generate tests",
    description: str = "Generate pytest tests",
    slash: str = "generate-tests",
    includes_rules: list[str] | None = None,
    body: str = "# Generate tests\n\nWrite tests.\n",
) -> Prompt:
    return Prompt(
        frontmatter=PromptFrontmatter(
            id=prompt_id,
            name=name,
            description=description,
            slash=slash,
            includes_rules=list(includes_rules) if includes_rules is not None else [],
        ),
        body=body,
        template_body=body,
        is_templated=False,
        source_path=None,
        source_package="coding_agent_playbook",
    )


def test_continue_write_prompt_creates_file_with_sentinel(tmp_path: Path) -> None:
    prompt = _make_prompt(slash="generate-tests")
    adapter = ContinueAdapter()
    written = adapter.write_prompt(prompt, repo_root=tmp_path)
    expected = tmp_path / ".continue" / "prompts" / "generate-tests.md"
    assert written == [expected]
    content = expected.read_text(encoding="utf-8")
    assert SENTINEL in content.split("\n", 1)[0]
    assert "name: Generate tests" in content
    assert "description: Generate pytest tests" in content
    assert "invokable: true" in content


def test_continue_write_prompt_creates_parent_directory(tmp_path: Path) -> None:
    """write_prompt must create .continue/prompts/ if it does not already exist."""
    prompt = _make_prompt(slash="x")
    assert not (tmp_path / ".continue").exists()
    ContinueAdapter().write_prompt(prompt, repo_root=tmp_path)
    assert (tmp_path / ".continue" / "prompts").is_dir()


def test_continue_write_prompt_no_appendix_without_registry(tmp_path: Path) -> None:
    """When the adapter is constructed without a rule_registry, includes_rules
    is declarative-only and no '## Reference rules' appendix is appended."""
    prompt = _make_prompt(includes_rules=["x"])
    adapter = ContinueAdapter()
    written = adapter.write_prompt(prompt, repo_root=tmp_path)
    content = written[0].read_text(encoding="utf-8")
    assert "## Reference rules" not in content


def test_continue_write_prompt_renders_includes_rules_appendix(tmp_path: Path) -> None:
    """When constructed with a registry, the includes_rules appendix is emitted."""
    prompt = _make_prompt(includes_rules=["x"])
    registry = _StubRegistry({"x": "### X\n\nrule body\n"})
    adapter = ContinueAdapter(rule_registry=registry)
    written = adapter.write_prompt(prompt, repo_root=tmp_path)
    content = written[0].read_text(encoding="utf-8")
    assert "## Reference rules" in content
    assert "### X" in content
    assert "rule body" in content


# --- Task 6.4: write_skill degrades to write_prompt -----------------------


# --- Task 6.5: cleanup_stale -----------------------------------------------


def test_continue_cleanup_removes_stale_rule(tmp_path: Path) -> None:
    """A sentinel-tagged rule file not in written_paths is removed."""
    rules_dir = tmp_path / ".continue" / "rules"
    rules_dir.mkdir(parents=True)
    current = rules_dir / "01-current.md"
    current.write_text(f"<!-- {SENTINEL} -->\n---\nname: c\n---\n", encoding="utf-8")
    stale = rules_dir / "02-stale.md"
    stale.write_text(f"<!-- {SENTINEL} -->\n---\nname: s\n---\n", encoding="utf-8")

    adapter = ContinueAdapter()
    deleted = adapter.cleanup_stale({current.resolve()}, tmp_path)

    assert deleted == [stale]
    assert not stale.exists()
    assert current.exists()


def test_continue_cleanup_removes_stale_prompt(tmp_path: Path) -> None:
    """The prompts directory is also scanned by _output_directories."""
    prompts_dir = tmp_path / ".continue" / "prompts"
    prompts_dir.mkdir(parents=True)
    stale = prompts_dir / "obsolete.md"
    stale.write_text(f"<!-- {SENTINEL} -->\n---\nname: o\n---\n", encoding="utf-8")

    adapter = ContinueAdapter()
    deleted = adapter.cleanup_stale(set(), tmp_path)

    assert deleted == [stale]
    assert not stale.exists()


def test_continue_cleanup_preserves_user_authored_files(tmp_path: Path) -> None:
    """A user-authored file (no sentinel) must NEVER be removed, even if it
    is not in written_paths."""
    rules_dir = tmp_path / ".continue" / "rules"
    rules_dir.mkdir(parents=True)
    user_authored = rules_dir / "99-handwritten.md"
    user_authored.write_text(
        "---\nname: hand\nalwaysApply: false\n---\n# I wrote this by hand.\n",
        encoding="utf-8",
    )

    adapter = ContinueAdapter()
    deleted = adapter.cleanup_stale(set(), tmp_path)

    assert deleted == []
    assert user_authored.exists()


def test_continue_cleanup_skips_when_directories_missing(tmp_path: Path) -> None:
    """If neither .continue/rules nor .continue/prompts exists, cleanup is a no-op."""
    adapter = ContinueAdapter()
    assert adapter.cleanup_stale(set(), tmp_path) == []


def test_continue_output_directories_lists_rules_and_prompts(tmp_path: Path) -> None:
    """The adapter's _output_directories points at both .continue subdirs."""
    adapter = ContinueAdapter()
    dirs = list(adapter._output_directories(tmp_path))
    assert dirs == [
        tmp_path / ".continue" / "rules",
        tmp_path / ".continue" / "prompts",
    ]


def test_continue_write_skill_degrades_to_prompt_path(tmp_path: Path) -> None:
    """ContinueAdapter has no native skill support — write_skill must inherit
    the ABC default, which calls Skill.to_prompt() and forwards to write_prompt.
    The resulting file lands at .continue/prompts/{slash}.md."""
    skill = Skill(
        frontmatter={
            "id": "demo-skill",
            "name": "Demo skill",
            "description": "A demo",
            "slash": "demo-skill",
        },
        body="# Demo skill body\n",
        scripts_dir=None,
        references_dir=None,
        source_package="coding_agent_playbook",
    )
    adapter = ContinueAdapter()
    written = adapter.write_skill(skill, repo_root=tmp_path)
    expected = tmp_path / ".continue" / "prompts" / "demo-skill.md"
    assert written == [expected]
    content = expected.read_text(encoding="utf-8")
    assert SENTINEL in content.split("\n", 1)[0]
    assert "name: Demo skill" in content
    assert "Demo skill body" in content
    # The Continue prompt shape ships invokable: true at the top.
    assert "invokable: true" in content


# --- K3: hooks degrade to one advisory rule (specs/prK-lifecycle-hooks.md §C.4.2, P5) ----


def test_guardrail_rule_written_as_30_guardrail_id_md(tmp_path: Path) -> None:
    adapter = ContinueAdapter()

    written = adapter.write_hook(resolved_hook(body="Never edit generated files.\n"), tmp_path)

    target = tmp_path / ".continue" / "rules" / "30-guardrail-guard-x.md"
    assert written == [target]
    assert target.read_text(encoding="utf-8") == (
        f"<!-- {SENTINEL} -->\n"
        "---\n"
        "name: 'Guardrail: Guard X'\n"
        "description: Deny x.\n"
        "alwaysApply: true\n"
        "---\n"
        "Never edit generated files.\n\n"
        "*Enforced by lifecycle hooks on: Claude Code. "
        "Everywhere else this is guidance: apply it yourself.*\n"
    )


def test_guardrail_rule_scoped_to_the_hook_paths(tmp_path: Path) -> None:
    hook = resolved_hook(matcher={"pre_tool_use": {"tools": ["edit"], "paths": ["src/**"]}})

    (target,) = ContinueAdapter().write_hook(hook, tmp_path)

    text = target.read_text(encoding="utf-8")
    assert "alwaysApply: false\n" in text
    assert "globs:\n- src/**\n" in text


def test_empty_body_hook_writes_no_continue_rule(tmp_path: Path) -> None:
    assert ContinueAdapter().write_hook(resolved_hook(body=" \n"), tmp_path) == []
    assert not (tmp_path / ".continue").exists()


def test_hooks_never_write_continue_hook_config(tmp_path: Path) -> None:
    """P5: Continue has no wired hook mechanism, so hooks only ever become rule files."""
    adapter = ContinueAdapter()
    hooks = [
        resolved_hook("guard-a", events=("pre_tool_use", "stop"), supports=("claude_code",)),
        resolved_hook("guard-b", events=("session_start",), supports=("opencode",)),
    ]

    written = [path for hook in hooks for path in adapter.write_hook(hook, tmp_path)]
    written += adapter.finalize(tmp_path)

    on_disk = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*") if p.is_file())
    assert on_disk == [
        ".continue/rules/30-guardrail-guard-a.md",
        ".continue/rules/30-guardrail-guard-b.md",
    ]
    assert sorted(p.relative_to(tmp_path).as_posix() for p in written) == on_disk
    assert dict(ContinueAdapter.hook_support) == {}
