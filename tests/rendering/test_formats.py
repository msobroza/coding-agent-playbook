"""Tests for the per-format post-processing. See SPEC.md §9.7 and specs/prA-core-internals.md."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.generated_output.sentinel import SENTINEL, has_sentinel
from coding_agent_playbook.rendering.formats import (
    render_for,
    render_inline_prompt_markdown,
    with_sentinel_body,
)
from coding_agent_playbook.rendering.prompt_rule_delivery import SkillReference
from tests.fakes import FakeRuleRegistry

# --- Task B.4 step 1: continue_rule + alias resolution + unknown-format ----


def test_render_for_continue_rule(tmp_path: Path) -> None:
    frontmatter = {
        "id": "py-typing",
        "name": "Python typing",
        "description": "Always use type hints.",
        "scope": "scoped",
        "globs": ["**/*.py"],
        "version": 1,
        "priority": 50,
        "tags": ["python"],
        "applies_if": {},
    }
    body = "Use type hints everywhere.\n"
    out = render_for(
        tmp_path / "rules" / "py-typing.md",
        body,
        "continue_rule",
        frontmatter=frontmatter,
    )
    assert SENTINEL in out
    assert "alwaysApply: false" in out
    assert "name: Python typing" in out
    assert "description: Always use type hints." in out
    assert "globs:" in out
    # Continue-shaped frontmatter must NOT include canonical-only keys.
    assert "id:" not in out
    assert "version:" not in out
    assert "scope:" not in out
    assert "priority:" not in out
    assert "tags:" not in out
    assert "applies_if:" not in out
    assert out.endswith(body)


def test_continue_rule_renders_links_to_skill_references_as_plain_file_names(
    tmp_path: Path,
) -> None:
    """prU D46(9): Continue receives no skill ``references/``, so such a link would dangle."""
    body = (
        "See [the worked example](../references/worked-example.md) and\n"
        "[`layers`](../references/arch/layers.md#top), or [docs](https://example.org/a.md).\n"
    )
    out = render_for(
        tmp_path / "rule.md",
        body,
        "continue_rule",
        frontmatter={"id": "x", "name": "X", "description": "x", "scope": "scoped"},
    )
    assert out.endswith(
        "See worked-example.md and\nlayers.md, or [docs](https://example.org/a.md).\n"
    )


def test_render_for_continue_rule_drops_globs_when_always_apply(tmp_path: Path) -> None:
    """When scope=always, alwaysApply=true, globs is not emitted
    (Continue semantics — globs is meaningful only with alwaysApply=false)."""
    out = render_for(
        tmp_path / "rule.md.j2",
        "body",
        "continue_rule",
        frontmatter={
            "id": "x",
            "name": "X",
            "description": "x",
            "scope": "always",
            "globs": ["**/*.py"],
        },
    )
    assert "alwaysApply: true" in out
    assert "globs:" not in out


def test_render_for_continue_rule_scoped(tmp_path: Path) -> None:
    frontmatter = {
        "id": "fastapi-routers",
        "name": "FastAPI routers",
        "description": "Use APIRouter for grouping endpoints.",
        "scope": "scoped",
        "globs": ["src/**/routers/*.py"],
    }
    body = "Group endpoints with APIRouter.\n"
    out = render_for(
        tmp_path / "rules" / "fastapi-routers.md",
        body,
        "continue_rule",
        frontmatter=frontmatter,
    )
    assert "alwaysApply: false" in out
    assert "src/**/routers/*.py" in out


def test_format_alias_resolution(tmp_path: Path) -> None:
    frontmatter = {
        "id": "x",
        "name": "X",
        "description": "x",
        "scope": "always",
        "globs": [],
    }
    body = "body\n"
    via_alias = render_for(tmp_path / "x.md", body, "continue", frontmatter=frontmatter)
    via_full = render_for(tmp_path / "x.md", body, "continue_rule", frontmatter=frontmatter)
    assert via_alias == via_full


def test_unknown_format_raises_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="bogus"):
        render_for(
            tmp_path / "x.md",
            "body\n",
            "bogus",
            frontmatter={"id": "x", "name": "X", "description": "x", "scope": "always"},
        )


# --- Task B.4 step 2: claude_md_section + agents_md_section ----------------


def test_render_for_claude_md_section_scoped(tmp_path: Path) -> None:
    frontmatter = {
        "id": "fastapi-routers",
        "name": "FastAPI routers",
        "description": "Use APIRouter for grouping endpoints.",
        "scope": "scoped",
        "globs": ["src/**/routers/*.py"],
    }
    body = "Group endpoints with APIRouter.\n"
    out = render_for(
        tmp_path / "rules" / "fastapi-routers.md",
        body,
        "claude_md_section",
        frontmatter=frontmatter,
    )
    assert "## FastAPI routers" in out
    assert "*Applies to: `src/**/routers/*.py`*" in out
    assert "Group endpoints with APIRouter." in out
    assert out.rstrip().endswith("---")


def test_render_for_claude_md_section_always(tmp_path: Path) -> None:
    frontmatter = {
        "id": "py-typing",
        "name": "Python typing",
        "description": "Always use type hints.",
        "scope": "always",
        "globs": [],
    }
    body = "Use type hints everywhere.\n"
    out = render_for(
        tmp_path / "rules" / "py-typing.md",
        body,
        "claude_md_section",
        frontmatter=frontmatter,
    )
    assert "## Python typing" in out
    assert "Applies to:" not in out
    assert "Use type hints everywhere." in out
    assert out.rstrip().endswith("---")


def test_render_for_agents_md_section_identical_to_claude(tmp_path: Path) -> None:
    frontmatter = {
        "id": "fastapi-routers",
        "name": "FastAPI routers",
        "description": "Use APIRouter for grouping endpoints.",
        "scope": "scoped",
        "globs": ["src/**/routers/*.py"],
    }
    body = "Group endpoints with APIRouter.\n"
    claude_out = render_for(
        tmp_path / "rules" / "fastapi-routers.md",
        body,
        "claude_md_section",
        frontmatter=frontmatter,
    )
    agents_out = render_for(
        tmp_path / "rules" / "fastapi-routers.md",
        body,
        "agents_md_section",
        frontmatter=frontmatter,
    )
    assert claude_out == agents_out


# --- Task B.4 step 3: prompt_continue / prompt_claude_command /
#     prompt_opencode_command + includes_rules appendix --------------------


def test_render_for_prompt_continue_with_includes_rules_appendix(tmp_path: Path) -> None:
    frontmatter = {
        "id": "review-code",
        "name": "Review code",
        "description": "Review a diff for safety.",
        "slash": "/review",
        "includes_rules": ["x"],
    }
    body = "Review the diff.\n"
    registry = FakeRuleRegistry({"x": "### X\n\nrule body\n"})
    out = render_for(
        tmp_path / "prompts" / "review-code.md",
        body,
        "prompt_continue",
        frontmatter=frontmatter,
        rule_registry=registry,
    )
    assert "name: Review code" in out
    assert "description: Review a diff for safety." in out
    assert "invokable: true" in out
    assert "Review the diff." in out
    assert "## Reference rules" in out
    assert "### X" in out
    assert "rule body" in out
    assert SENTINEL in out


def test_render_for_prompt_opencode_command_single_arg_substitution(
    tmp_path: Path,
) -> None:
    frontmatter = {
        "id": "review",
        "name": "Review",
        "description": "Review.",
        "slash": "/review",
        "input_variables": [{"name": "target", "description": "what to review"}],
    }
    body = "Please review {{ target }} carefully.\n"
    out = render_for(
        tmp_path / "prompts" / "review.md",
        body,
        "prompt_opencode_command",
        frontmatter=frontmatter,
    )
    assert "$ARGUMENTS" in out
    assert "{{ target }}" not in out
    assert "description: Review." in out


def test_render_for_prompt_opencode_command_multi_arg_substitution(
    tmp_path: Path,
) -> None:
    frontmatter = {
        "id": "compare",
        "name": "Compare",
        "description": "Compare two things.",
        "slash": "/compare",
        "input_variables": [
            {"name": "a", "description": "first"},
            {"name": "b", "description": "second"},
        ],
    }
    body = "Compare {{ a }} with {{ b }}.\n"
    out = render_for(
        tmp_path / "prompts" / "compare.md",
        body,
        "prompt_opencode_command",
        frontmatter=frontmatter,
    )
    assert "$1" in out
    assert "$2" in out
    assert "{{ a }}" not in out
    assert "{{ b }}" not in out


def test_render_for_prompt_claude_command_emits_title_and_body(tmp_path: Path) -> None:
    frontmatter = {
        "id": "review",
        "name": "Review",
        "description": "Review a diff.",
        "slash": "/review",
    }
    body = "Step 1: read the diff.\n"
    out = render_for(
        tmp_path / "prompts" / "review.md",
        body,
        "prompt_claude_command",
        frontmatter=frontmatter,
    )
    assert "# Review" in out
    assert "Step 1: read the diff." in out


# --- D15: Claude Code and OpenCode commands point at skills -----------------


_TYPING_REFERENCE = SkillReference("python-coding", "rules/python-typing.md")
_POINTER_FRONTMATTER = {
    "name": "Review",
    "description": "Review a diff.",
    "includes_rules": ["python-typing"],
}
_POINTER_BODY = "# Review\n\nYou are reviewing code.\n\n## Tone\n\nBe kind.\n"
_POINTER_BLOCK = (
    "## Before you start\n\n"
    "1. Load skill `python-coding` and read its rule `rules/python-typing.md`.\n"
    "2. For each file in scope, also load any other listed skill whose description matches it.\n"
)


def _pointer_command(fmt: str, frontmatter: dict[str, Any] = _POINTER_FRONTMATTER) -> str:
    """The pointer prompt as ``fmt`` renders it, with a registry AND a reference index."""
    return render_for(
        Path("review.md"),
        _POINTER_BODY,
        fmt,
        frontmatter=frontmatter,
        rule_registry=FakeRuleRegistry({"python-typing": "### Typing\n\nTYPING BODY\n"}),
        skill_references=FakeRuleRegistry(references={"python-typing": _TYPING_REFERENCE}),
    )


def test_render_for_prompt_claude_command_inserts_pointer_block_and_no_rule_body() -> None:
    out = _pointer_command("prompt_claude_command")

    assert out == (
        f"<!-- {SENTINEL} -->\n# Review\n\nYou are reviewing code.\n\n"
        f"{_POINTER_BLOCK}\n## Tone\n\nBe kind.\n"
    )


def test_render_for_prompt_claude_command_read_only_keeps_disallowed_tools_with_block() -> None:
    out = _pointer_command(
        "prompt_claude_command", {**_POINTER_FRONTMATTER, "write_scope": {"read_only": True}}
    )

    assert out.startswith(
        f"---\ndisallowed-tools: Edit Write NotebookEdit\n---\n<!-- {SENTINEL} -->\n# Review\n"
    )
    assert f"\n\n{_POINTER_BLOCK}\n## Tone\n" in out
    assert "TYPING BODY" not in out


def test_render_for_prompt_opencode_command_inserts_block_after_envelope() -> None:
    out = _pointer_command("prompt_opencode_command")

    assert out == (
        f"---\ndescription: Review a diff.\n---\n<!-- {SENTINEL} -->\n\n"
        f"# Review\n\nYou are reviewing code.\n\n{_POINTER_BLOCK}\n## Tone\n\nBe kind.\n"
    )


@pytest.mark.parametrize("fmt", ["prompt_claude_command", "prompt_opencode_command"])
def test_render_for_prompt_without_skill_references_has_no_block(fmt: str) -> None:
    """Without an index ``includes_rules`` is declarative only: no block, no appendix."""
    out = render_for(
        Path("review.md"),
        _POINTER_BODY,
        fmt,
        frontmatter=_POINTER_FRONTMATTER,
        rule_registry=FakeRuleRegistry({"python-typing": "### Typing\n\nTYPING BODY\n"}),
    )

    assert "## Before you start" not in out
    assert "## Reference rules" not in out
    assert out.endswith(_POINTER_BODY)


def test_render_for_prompt_continue_appends_the_appendix_and_no_block() -> None:
    out = _pointer_command("prompt_continue")

    assert out.endswith(f"{_POINTER_BODY}\n## Reference rules\n\n### Typing\n\nTYPING BODY\n")
    assert "## Before you start" not in out


# --- render_inline_prompt_markdown (agent_harness prompt leaf) --------------


def test_render_inline_prompt_markdown_titles_the_body_and_appends_the_appendix() -> None:
    out = render_inline_prompt_markdown(
        "Tidy the code.\n",
        {"name": "Tidy", "includes_rules": ["x"]},
        FakeRuleRegistry({"x": "### X\n\nrule body\n"}),
    )

    assert out == "# Tidy\n\nTidy the code.\n\n## Reference rules\n\n### X\n\nrule body\n"


def test_render_inline_prompt_markdown_keeps_a_body_title_and_has_no_sentinel() -> None:
    out = render_inline_prompt_markdown(
        "# Own title\n\nBody.\n", {"name": "Tidy", "write_scope": {"read_only": True}}, None
    )

    assert out == "# Own title\n\nBody.\n"


def test_render_for_prompt_opencode_command_escapes_special_description(
    tmp_path: Path,
) -> None:
    """A description containing a colon or quote must produce valid YAML
    (code-quality review I4 — was using raw f-string)."""
    import yaml as _yaml

    out = render_for(
        tmp_path / "prompt.md.j2",
        "hello",
        "prompt_opencode_command",
        frontmatter={"description": 'has: colons and "quotes"'},
    )
    # Reparse and check we get the original description back
    parts = out.split("---\n", 2)
    parsed = _yaml.safe_load(parts[1])
    assert parsed["description"] == 'has: colons and "quotes"'


# --- Task B.6 / code-quality review I6: full-string equality tests --------


def test_render_for_continue_rule_exact_output(tmp_path: Path) -> None:
    """Locks the exact output shape of continue_rule to catch whitespace
    regressions (code-quality review I6)."""
    out = render_for(
        tmp_path / "rule.md.j2",
        "body line 1\nbody line 2\n",
        "continue_rule",
        frontmatter={
            "id": "py-typing",
            "name": "Py typing",
            "description": "Type hints",
            "scope": "scoped",
            "globs": ["**/*.py"],
        },
    )
    expected = (
        f"<!-- {SENTINEL} -->\n"
        "---\n"
        "name: Py typing\n"
        "description: Type hints\n"
        "alwaysApply: false\n"
        "globs:\n"
        "- '**/*.py'\n"
        "---\n"
        "body line 1\nbody line 2\n"
    )
    assert out == expected


def test_render_for_claude_md_section_exact_output(tmp_path: Path) -> None:
    """Locks the exact output shape of claude_md_section to catch whitespace
    regressions (code-quality review I6)."""
    out = render_for(
        tmp_path / "rule.md",
        "body line 1\nbody line 2\n",
        "claude_md_section",
        frontmatter={
            "id": "x",
            "name": "X",
            "description": "d",
            "scope": "scoped",
            "globs": ["**/*.py"],
        },
    )
    expected = "## X\n\n*Applies to: `**/*.py`*\n\nbody line 1\nbody line 2\n\n---\n"
    assert out == expected


def test_render_for_prompt_continue_exact_output(tmp_path: Path) -> None:
    """Locks the exact output shape of prompt_continue (no includes_rules)
    to catch whitespace regressions (code-quality review I6)."""
    out = render_for(
        tmp_path / "prompt.md.j2",
        "body line 1\nbody line 2\n",
        "prompt_continue",
        frontmatter={"name": "P", "description": "D"},
    )
    expected = (
        f"<!-- {SENTINEL} -->\n"
        "---\n"
        "name: P\n"
        "description: D\n"
        "invokable: true\n"
        "---\n"
        "body line 1\nbody line 2\n"
    )
    assert out == expected


def test_render_for_prompt_continue_no_appendix_when_all_fragments_empty(
    tmp_path: Path,
) -> None:
    """When includes_rules is set but every rule's applies_if evaluates false
    (registry returns ""), no Reference rules section is emitted
    (code-quality review M5)."""
    registry = FakeRuleRegistry({"foo": "", "bar": ""})
    out = render_for(
        tmp_path / "prompt.md.j2",
        "body",
        "prompt_continue",
        frontmatter={
            "name": "P",
            "description": "D",
            "includes_rules": ["foo", "bar"],
        },
        rule_registry=registry,
    )
    assert "## Reference rules" not in out


# --- engine-output detection (sentinel position) ----------------------------

_BODY_FIRST = with_sentinel_body("---\ndescription: d\n---", "body\n")


@pytest.mark.parametrize(
    ("text", "owned"),
    [
        (f"<!-- {SENTINEL} -->\n# Title\n", True),
        (f"<!-- {SENTINEL} -->\n---\ndescription: d\n---\nbody\n", True),
        (_BODY_FIRST, True),
        ("\ufeff" + _BODY_FIRST, True),
        (f"\ufeff<!-- {SENTINEL} -->\n# Title\n", True),
        (f"---\ndescription: d\n---\nFiles saying {SENTINEL} are generated.\n", False),
        ("---\ndescription: d\n---\nbody\n", False),
        (f"---\ndescription: d\n---\nintro\n<!-- {SENTINEL} -->\n", False),
        (f"intro\n<!-- {SENTINEL} -->\n", False),
        (f"---\ndescription: {SENTINEL}\n---\nbody\n", False),
        ("", False),
    ],
    ids=[
        "line-1",
        "legacy-line-1-before-frontmatter",
        "first-body-line",
        "bom-first-body-line",
        "bom-line-1",
        "first-body-line-quotes-it-in-prose",
        "no-sentinel",
        "deeper-in-body",
        "line-2-no-frontmatter",
        "inside-frontmatter",
        "empty",
    ],
)
def test_with_sentinel_body_output_is_engine_owned_only_at_the_anchored_positions(
    text: str, owned: bool
) -> None:
    """``with_sentinel_body`` writes the second position ``has_sentinel`` accepts.

    One detector decides ownership for every scanner (prK §P3), so the layout
    the renderer writes for OpenCode commands and skills is recognised without
    a per-adapter opt-in; a file that merely quotes the sentinel stays the user's.
    """
    assert has_sentinel(text) is owned


def test_opencode_command_starts_with_its_frontmatter(tmp_path: Path) -> None:
    """OpenCode's gray-matter needs ``---`` at offset 0; the sentinel follows the envelope."""
    out = render_for(
        tmp_path / "p.md",
        "Body\n",
        "prompt_opencode_command",
        frontmatter={"name": "P", "description": "D"},
    )
    assert out == f"---\ndescription: D\n---\n<!-- {SENTINEL} -->\n\nBody\n"
