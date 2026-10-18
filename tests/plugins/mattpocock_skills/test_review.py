"""T05: the vendored two-axis-review, pr-body and tdd skills (A.T05).

specs/prT-mattpocock-skills.md section 9.6 and appendix A.T05. Each new text of
A.T05 is asserted as an exact substring, each replaced upstream text as absent;
the shared gate (``test_gates.py``) covers URLs, imposed tools, Claude-only
names, layout, licence copies and the load-target ids. Upstream line numbers in
the comments are lines of tag v1.3.1.
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING

import pytest

from tests.plugins.mattpocock_skills._expectations import (
    LOAD_RE,
    PLUGIN_ROOT,
    SKILLS_ROOT,
    present_skill_ids,
    skill_files,
    split_skill,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_T05_IDS = ("pr-body", "tdd", "two-axis-review")
_SKILLS = present_skill_ids()
#: A.T05.2 rename propagation: catches `code-review` and `/code-review`, not
#: names such as `requesting-code-review`.
_OLD_REVIEW_ID_RE = re.compile(r"(?<![\w-])code-review(?![\w-])")
#: A.T05.3 rename propagation: the code spans `pr` and `/pr`.
_OLD_PR_SPAN_RE = re.compile(r"`/?pr`")
_TWO_AXIS_DESCRIPTION = (
    "Review the changes since a fixed point (commit, branch, tag, or merge-base) along two"
    " axes: Standards (does the code follow this repo's documented coding standards?) and Spec"
    " (does the code match what the originating issue/spec asked for?). Runs both reviews in"
    " parallel sub-agents and reports them side by side. Use when the user wants to review a"
    ' branch, a PR, work-in-progress changes, or asks to "review since X".'
)
_TWO_AXIS_L11 = (
    "If your harness can run subagents, both axes run as **parallel sub-agents** so they don't"
    " pollute each other's context, then this skill aggregates their findings; otherwise you"
    " run the two reviews yourself, one after the other, as step 4 describes, and aggregate"
    " them the same way."
)
_TWO_AXIS_STEP4 = (
    "If your harness cannot run subagents, run the two reviews yourself, one after the other."
    " First run the Standards review from the Standards brief below, judged only against the"
    " standards sources and the smell baseline from step 3, with any spec contents step 2"
    " fetched set aside, and write its report in full. Then run the Spec review from the Spec"
    ' brief below; if no spec is available, skip it and report "no spec available". Do not'
    " revise the Standards report afterwards."
)
_MIT_PERMISSION = (
    "The above copyright notice and this permission notice shall be included in all copies or"
    " substantial portions of the Software."
)


def _text(skill_id: str, relative: str = "SKILL.md") -> str:
    return (SKILLS_ROOT / skill_id / relative).read_text(encoding="utf-8")


def _lines(skill_id: str, relative: str = "SKILL.md") -> list[str]:
    return _text(skill_id, relative).split("\n")


def _layout(skill_id: str) -> list[str]:
    return [p.relative_to(SKILLS_ROOT / skill_id).as_posix() for p in skill_files(skill_id)]


def _load_targets(skill_id: str) -> set[str]:
    return {m.group(1) for m in LOAD_RE.finditer(split_skill(skill_id)[1])}


def _section(text: str, start: str, end: str) -> str:
    """The text from the heading ``start`` up to (not including) ``end``."""
    head = text.index(start)
    return text[head : text.index(end, head)]


# --- shared to the three skills -------------------------------------------------


@pytest.mark.parametrize("skill_id", _T05_IDS)
def test_t05_skill_is_model_invoked_with_id_equal_name_equal_dir(skill_id: str) -> None:
    frontmatter, body = split_skill(skill_id)
    assert frontmatter["id"] == frontmatter["name"] == skill_id
    assert "disable-model-invocation" not in frontmatter, "a load target stays model-invoked"
    assert "Run this only when the user asked for it by name" not in body


@pytest.mark.parametrize("skill_id", _T05_IDS)
def test_t05_skill_files_end_with_one_newline_and_lf(skill_id: str) -> None:
    for path in skill_files(skill_id):
        data = path.read_bytes()
        assert b"\r" not in data, f"{path}: CRLF"
        assert data.endswith(b"\n") and not data.endswith(b"\n\n"), f"{path}: trailing newline"


@pytest.mark.parametrize("skill_id", _T05_IDS)
def test_t05_attributions_section_opens_with_the_upstream_and_synced_paths(skill_id: str) -> None:
    upstream = {"pr-body": "pr", "tdd": "tdd", "two-axis-review": "code-review"}[skill_id]
    text = (PLUGIN_ROOT / "ATTRIBUTIONS.md").read_text(encoding="utf-8")
    section = text.split(f"\n### {skill_id}\n", 1)[1].split("\n### ", 1)[0]
    expected = f"Upstream `skills/engineering/{upstream}/`; synced as `.agents/skills/{skill_id}/`."
    assert section.lstrip("\n").startswith(expected)
    assert "Continue:" in section, "each section records its Continue degradation (D29)"


# --- rename propagation (D8), over every skill present ----------------------------


def _skill_tree_files(skill_id: str) -> list[Path]:
    return [p for p in skill_files(skill_id) if p.suffix in {".md", ".py"}]


@pytest.mark.parametrize("skill_id", _SKILLS)
def test_no_skill_names_the_old_code_review_id(skill_id: str) -> None:
    hits = [
        f"{p.name}:{n}: {line.strip()}"
        for p in _skill_tree_files(skill_id)
        for n, line in enumerate(p.read_text(encoding="utf-8").split("\n"), 1)
        if _OLD_REVIEW_ID_RE.search(line)
    ]
    assert hits == [], "code-review is two-axis-review in this plugin (D8)"


@pytest.mark.parametrize("skill_id", _SKILLS)
def test_no_skill_carries_the_old_pr_code_span(skill_id: str) -> None:
    hits = [
        f"{p.name}:{n}: {line.strip()}"
        for p in _skill_tree_files(skill_id)
        for n, line in enumerate(p.read_text(encoding="utf-8").split("\n"), 1)
        if _OLD_PR_SPAN_RE.search(line)
    ]
    assert hits == [], "pr is pr-body in this plugin (D8)"


# --- tdd (A.T05.1) --------------------------------------------------------------


def test_tdd_layout_and_moved_references_are_byte_identical() -> None:
    assert _layout("tdd") == [
        "SKILL.md",
        "references/LICENSE",
        "references/mocking.md",
        "references/tests.md",
    ]
    digests = {
        "references/tests.md": "859f9e592c188fda4fc7277dd180e4ce9c7a2e13f6efe1f6f29eccc9d28c106a",
        "references/mocking.md": "3ceb807fdf4a47d6a93d4d9a891e5ba6d362a6247bd08adc451feebfc17361ef",
    }
    for relative, digest in digests.items():
        data = (SKILLS_ROOT / "tdd" / relative).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest, f"{relative} changed (D10)"


def test_tdd_frontmatter_is_upstream_plus_id() -> None:
    assert _lines("tdd")[:5] == [
        "---",
        "id: tdd",
        "name: tdd",
        "description: Test-driven development. Use when the user wants to build features or fix"
        ' bugs test-first, mentions "red-green-refactor", or wants integration tests.',
        "---",
    ]
    assert len(_lines("tdd")) == 40, "39 lines plus the empty string after the last newline"


def test_tdd_glossary_line_carries_the_context_fallback() -> None:
    text = _text("tdd")
    assert (
        "When exploring the codebase, read `GLOSSARY.md` (or `CONTEXT.md` if the repo already"
        " has one) (if it exists) so test names and interface vocabulary match the project's"
        " domain language, and respect ADRs in the area you're touching.\n"
    ) in text
    assert "read `GLOSSARY.md` (if it exists)" not in text


def test_tdd_links_point_into_references() -> None:
    text = _text("tdd")
    assert (
        "See [tests.md](references/tests.md) for examples and"
        " [mocking.md](references/mocking.md) for mocking guidelines.\n"
    ) in text
    assert "](tests.md)" not in text and "](mocking.md)" not in text


def test_tdd_loads_codebase_design_and_names_two_axis_review() -> None:
    text = _text("tdd")
    assert (
        "(how deep the module is, where the seam belongs, what the interface should expose),"
        " load the `codebase-design` skill for the vocabulary. It is the shared source of the"
        " module, interface, depth, seam, adapter, leverage and locality terms, and it is a"
        " reference to consult, not a session to run.\n"
    ) in text
    assert 'call the Skill tool with "codebase-design"' not in text
    assert _load_targets("tdd") == {"codebase-design"}
    assert (
        "- **Refactoring is not part of the loop.** It belongs to the review stage (see the"
        " `two-axis-review` skill), not the red → green implementation cycle.\n"
    ) in text
    assert "(see the `code-review` skill)" not in text


def test_tdd_keeps_the_typescript_and_jest_examples_verbatim() -> None:
    assert "`expect(add(a, b)).toBe(a + b)`" in _text("tdd")
    assert "const mockPayment = jest.mock(paymentService);" in _text("tdd", "references/tests.md")
    assert "process.env.STRIPE_KEY" in _text("tdd", "references/mocking.md")


# --- two-axis-review (A.T05.2) --------------------------------------------------


def test_two_axis_review_layout() -> None:
    assert _layout("two-axis-review") == ["SKILL.md", "references/LICENSE"]


def test_two_axis_review_frontmatter_keeps_the_419_char_description_verbatim() -> None:
    lines = _lines("two-axis-review")
    assert lines[:3] == ["---", "id: two-axis-review", "name: two-axis-review"]
    raw = lines[3].removeprefix('description: "').removesuffix('"')
    assert lines[3] == f'description: "{raw}"' and len(raw) == 419, "D28: verbatim, quoted"
    assert '\\"review since X\\"' in raw
    frontmatter, _ = split_skill("two-axis-review")
    assert frontmatter["description"] == _TWO_AXIS_DESCRIPTION
    assert len(_TWO_AXIS_DESCRIPTION) == 417
    assert len(lines) == 91, "90 lines plus the empty string after the last newline"


def test_two_axis_review_line_11_is_a_capability_with_a_fallback() -> None:
    lines = _lines("two-axis-review")
    assert lines[11] == _TWO_AXIS_L11, "upstream L11, one line lower after the id line"
    assert lines[11].startswith("If your harness can run subagents")
    old = (
        "Both axes run as **parallel sub-agents** so they don't pollute each other's context,"
        " then this skill aggregates their findings."
    )
    assert old not in lines


def test_two_axis_review_step_4_runs_standards_then_spec_without_subagents() -> None:
    text = _text("two-axis-review")
    step4 = _section(text, "### 4. Spawn both sub-agents in parallel", "### 5. Aggregate")
    assert (
        f"### 4. Spawn both sub-agents in parallel\n\n{_TWO_AXIS_STEP4}\n\n"
        "**Standards sub-agent prompt** should include:\n"
    ) in step4
    for phrase in (
        "If your harness cannot run subagents",
        "set aside",
        "no spec available",
        "Do not revise the Standards report afterwards",
    ):
        assert phrase in step4


def test_two_axis_review_keeps_its_sub_agent_sentences_verbatim() -> None:
    text = _text("two-axis-review")
    for kept in (
        "A bad ref or empty diff should fail here, not inside two parallel sub-agents.",
        'the **Spec** sub-agent will skip and report "no spec available".',
        "(the sub-agent has no other access to it)",
        "**Spec sub-agent prompt** should include:",
        "- The path or fetched contents of the spec.",
        "If the spec is missing, skip the Spec sub-agent and note this in the final report.",
    ):
        assert kept in text


def test_two_axis_review_keeps_the_gitlab_example_and_setup_label() -> None:
    text = _text("two-axis-review")
    assert "(`#123`, `Closes #45`, GitLab `!67`, etc.)" in text, "D18.7"
    assert (
        "If `docs/agents/issue-tracker.md` is missing, tell the user to run"
        " `/setup-matt-pocock-skills`."
    ) in text, "D17 keeps the human-facing slash"
    assert _load_targets("two-axis-review") == set()


# --- pr-body (A.T05.3) ----------------------------------------------------------


def test_pr_body_layout() -> None:
    assert _layout("pr-body") == [
        "SKILL.md",
        "references/CREDITS.md",
        "references/LICENSE",
        "references/LICENSE-show-me",
    ]
    assert not (SKILLS_ROOT / "pr-body" / "CREDITS.md").exists()


def test_pr_body_frontmatter_drops_only_the_credits_url() -> None:
    lines = _lines("pr-body")
    assert lines[:10] == [
        "---",
        "id: pr-body",
        "name: pr-body",
        'description: "Use when writing a PR body."',
        "metadata:",
        "  credits:",
        "    skill: show-me",
        "    author: Dex Horthy",
        "    organisation: Humanlayer",
        "---",
    ]
    frontmatter, _ = split_skill("pr-body")
    assert frontmatter["metadata"] == {
        "credits": {"skill": "show-me", "author": "Dex Horthy", "organisation": "Humanlayer"}
    }
    assert "url:" not in "\n".join(lines[:10])
    assert len(lines) == 171, "170 lines plus the empty string after the last newline"


def test_pr_body_glossary_line_carries_the_context_fallback() -> None:
    text = _text("pr-body")
    assert (
        "Skip all preambles and keep prose brief. Use the user's domain language from"
        " `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one).\n"
    ) in text
    assert "domain language from `GLOSSARY.md`.\n" not in text
    assert _load_targets("pr-body") == set()


def test_pr_body_keeps_the_frontend_examples_verbatim() -> None:
    text = _text("pr-body")
    assert "apps/example/src/routes/session.tsx" in text
    assert "show-me.ts" in text
    assert "layout shift, breakages for consumers, mobile responsiveness" in text


def test_pr_body_credits_keep_link_text_without_urls_and_name_pr_body() -> None:
    lines = _lines("pr-body", "references/CREDITS.md")
    assert lines[:2] == ["# Credits", ""]
    assert "come from Dex Horthy's `show-me` skill, reproduced almost word for word" in lines[2]
    assert lines[2].startswith(
        "The **Summary** section's menu of visuals (pseudocode, call trees, component trees,"
        " file trees, Mermaid, diffs) and its placement guidance come from"
    )
    assert (
        "`pr-body` does not depend on `show-me` as a skill (it isn't part of this repo, and a"
        " hard dependency would break standalone installs)"
    ) in lines[2]
    for removed in ("[Dex Horthy](", "[`show-me`](", "`pr` does not depend"):
        assert removed not in lines[2]


def test_pr_body_ships_the_humanlayer_mit_notice() -> None:
    notice = _lines("pr-body", "references/LICENSE-show-me")
    plugin = (PLUGIN_ROOT / "LICENSE").read_text(encoding="utf-8").split("\n")
    assert notice[:3] == ["MIT License", "", "Copyright (c) 2026 HumanLayer"]
    assert notice[3:] == plugin[3:], "lines 4-21 equal the plugin LICENSE's (D6)"
    normalized = " ".join(" ".join(notice).split())
    assert "Copyright (c) 2026 HumanLayer" in normalized
    assert _MIT_PERMISSION in normalized


def test_attributions_third_party_content_names_show_me_provenance() -> None:
    text = (PLUGIN_ROOT / "ATTRIBUTIONS.md").read_text(encoding="utf-8")
    section = text.split("\n## Third-party content\n", 1)[1].split("\n## ", 1)[0]
    for needle in ("humanlayer/skills", "653b6411c1f70c275a18e37673b042ff99f67ceb"):
        assert needle in section
    assert "LICENSE-show-me" in section
