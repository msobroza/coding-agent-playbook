"""Tests for agent_harness._emit_skills — the skill and prompt leaves (AH-2, #143).

AH-2 moved these emitters out of ``AgentHarnessAdapter`` and gave them explicit
arguments; the adapter byte tests only reach them through ``finalize``. These
pin the seam itself: the written paths and their order, the leaf text (sentinel
as first body line) and the manifest entry each leaf appends.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from coding_agent_playbook.agent_harness._emit_skills import emit_prompt_leaves, emit_skill_leaves
from coding_agent_playbook.agent_harness.manifest import ManifestEntry, ScriptEntry
from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.generated_output.sentinel import SENTINEL

if TYPE_CHECKING:
    from pathlib import Path

_SENTINEL_LINE = f"<!-- {SENTINEL} -->"


def _skill_with_side_dirs(src: Path) -> Skill:
    """A ``db`` skill with two scripts (one executable), one reference and extra frontmatter."""
    scripts = src / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "run.sh").write_text("#!/bin/sh\necho run\n", encoding="utf-8")
    (scripts / "run.sh").chmod(0o755)
    (scripts / "lib.py").write_text("X = 1\n", encoding="utf-8")
    (scripts / "lib.py").chmod(0o644)
    references = src / "references"
    references.mkdir()
    (references / "guide.md").write_text("# Guide\n", encoding="utf-8")
    frontmatter = {
        "id": "db",
        "name": "DB",
        "description": "Database work.",
        "allowed-tools": "Bash",
        "tags": ["data"],
    }
    return Skill(frontmatter, "Use the db.\n", scripts, references, "test")


def _prompt(slash: str) -> Prompt:
    frontmatter = PromptFrontmatter(
        id=f"{slash}-id",
        name=f"{slash.title()} prompt",
        description=f"Run {slash}.",
        slash=slash,
        applies_if={"language": "python"},
        input_variables=[{"name": "target"}],
        includes_rules=["style"],
        output_contract=["^DONE$"],
        write_scope={"read_only": True},
    )
    body = "Review {{ target }}.\n"
    return Prompt(frontmatter, body, body, True, None, "test")


# --- emit_skill_leaves -----------------------------------------------------


def test_emit_skill_leaves_returns_skill_md_then_scripts_then_references(tmp_path: Path) -> None:
    skill = _skill_with_side_dirs(tmp_path / "src")
    repo = tmp_path / "harness"
    leaf = repo / "skills" / "db"

    written = emit_skill_leaves([skill], repo, [])

    assert written == [
        leaf / "SKILL.md",
        leaf / "scripts" / "lib.py",
        leaf / "scripts" / "run.sh",
        leaf / "references" / "guide.md",
    ]
    assert (leaf / "scripts" / "run.sh").read_bytes() == b"#!/bin/sh\necho run\n"
    assert (leaf / "references" / "guide.md").read_bytes() == b"# Guide\n"


def test_emit_skill_leaves_writes_native_frontmatter_then_the_sentinel(tmp_path: Path) -> None:
    skill = _skill_with_side_dirs(tmp_path / "src")
    repo = tmp_path / "harness"

    emit_skill_leaves([skill], repo, [])

    text = (repo / "skills" / "db" / "SKILL.md").read_text(encoding="utf-8")
    assert text == (
        f"---\nname: DB\ndescription: Database work.\n---\n{_SENTINEL_LINE}\n\nUse the db.\n"
    )


def test_emit_skill_leaves_records_extra_frontmatter_and_script_bits(tmp_path: Path) -> None:
    skill = _skill_with_side_dirs(tmp_path / "src")
    entries: list[ManifestEntry] = []

    emit_skill_leaves([skill], tmp_path / "harness", entries)

    assert entries == [
        ManifestEntry(
            kind="skill",
            path="skills/db/SKILL.md",
            id="db",
            name="DB",
            body="Use the db.\n",
            extra_frontmatter={"allowed-tools": "Bash", "tags": ["data"]},
            scripts=[
                ScriptEntry("skills/db/scripts/lib.py", executable=False),
                ScriptEntry("skills/db/scripts/run.sh", executable=os.name == "posix"),
            ],
        )
    ]


def test_emit_skill_leaves_defaults_name_to_id_without_side_dirs(tmp_path: Path) -> None:
    skill = Skill({"id": "bare"}, "Bare body.\n", None, None, "test")
    repo = tmp_path / "harness"
    entries: list[ManifestEntry] = []

    written = emit_skill_leaves([skill], repo, entries)

    assert written == [repo / "skills" / "bare" / "SKILL.md"]
    [entry] = entries
    assert (entry.name, entry.extra_frontmatter, entry.scripts) == ("bare", {}, [])


# --- emit_prompt_leaves ----------------------------------------------------


def test_emit_prompt_leaves_writes_the_rendered_body_in_input_order(tmp_path: Path) -> None:
    repo = tmp_path / "harness"
    leaves = [(_prompt("review"), "Review src.\n"), (_prompt("audit"), "Audit src.\n")]

    written = emit_prompt_leaves(leaves, repo, [])

    review, audit = repo / "prompts" / "review", repo / "prompts" / "audit"
    assert written == [review / "SKILL.md", audit / "SKILL.md"]
    assert (review / "SKILL.md").read_text(encoding="utf-8") == (
        f"---\nname: Review prompt\ndescription: Run review.\n---\n{_SENTINEL_LINE}\n\n"
        "Review src.\n"
    )


def test_emit_prompt_leaves_records_the_template_body_not_the_leaf(tmp_path: Path) -> None:
    entries: list[ManifestEntry] = []

    emit_prompt_leaves([(_prompt("review"), "Review src.\n")], tmp_path / "harness", entries)

    assert entries == [
        ManifestEntry(
            kind="prompt",
            path="prompts/review/SKILL.md",
            id="review-id",
            name="Review prompt",
            body="Review {{ target }}.\n",
            is_templated=True,
            slash="review",
            applies_if={"language": "python"},
            input_variables=[{"name": "target"}],
            includes_rules=["style"],
            output_contract=["^DONE$"],
            write_scope={"read_only": True},
        )
    ]
