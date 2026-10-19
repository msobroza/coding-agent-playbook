"""Tests for agent_harness.lint — the validate-harness checks behind lint_harness (AH-2, #143)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.agent_harness.lint import HarnessFinding, HarnessFindings, lint_harness
from coding_agent_playbook.agent_harness.parser import parse_harness

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.agent_harness.models import HarnessTree

_ROOT_FILES = {
    "HARNESS.md": "---\nname: probe\ndescription: A probe harness.\n---\nbody\n",
    ".leaf-detectors": "skill=SKILL.md\n",
}
_SKILLS_ROUTING = "---\ndescription: Skills.\n---\nindex\n"


def _tree(root: Path, files: dict[str, str]) -> HarnessTree:
    """Write the root files plus ``files`` (harness-relative path -> text) and parse them."""
    for relative, text in {**_ROOT_FILES, **files}.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return parse_harness(root)


def test_skill_leaf_without_name_or_description_is_an_error(tmp_path: Path) -> None:
    tree = _tree(
        tmp_path,
        {
            "skills/SKILLS.md": _SKILLS_ROUTING,
            "skills/blank/SKILL.md": '---\nname: ""\ndescription: ""\n---\nbody\n',
            "skills/half/SKILL.md": '---\nname: half\ndescription: ""\n---\nbody\n',
            "skills/whole/SKILL.md": "---\nname: whole\ndescription: Whole.\n---\nbody\n",
        },
    )

    findings = lint_harness(tree)

    blank, half = str(tmp_path / "skills" / "blank"), str(tmp_path / "skills" / "half")
    assert findings.errors == (
        HarnessFinding(blank, "skill leaf has empty 'name'"),
        HarnessFinding(blank, "skill leaf has empty 'description'"),
        HarnessFinding(half, "skill leaf has empty 'description'"),
    )
    assert findings.warnings == ()


def test_missing_routing_file_and_undescribed_content_are_warnings(tmp_path: Path) -> None:
    tree = _tree(
        tmp_path,
        {
            "docs/DOCS.md": "---\ndescription: Docs.\n---\nindex\n",
            "docs/described.md": "---\ndescription: Described.\n---\ntext\n",
            "docs/nested/plain.md": "---\ndescription: Plain.\n---\ntext\n",
            "docs/undescribed.md": "no frontmatter at all\n",
        },
    )

    findings = lint_harness(tree)

    docs = tmp_path / "docs"
    assert findings.warnings == (
        HarnessFinding(str(docs / "undescribed.md"), "content '.md' lacks a 'description'"),
        HarnessFinding(str(docs / "nested"), "grouping directory lacks its routing file 'DOCS.md'"),
    )
    assert findings.errors == ()


def test_opaque_leaf_directory_is_never_inspected(tmp_path: Path) -> None:
    # A top-level evals/ and a nested skills/vendor/ both carry .harnessleaf: neither has a
    # routing file, and the content inside them would be a warning or an error elsewhere.
    tree = _tree(
        tmp_path,
        {
            "evals/.harnessleaf": "",
            "evals/undescribed.md": "no frontmatter\n",
            "evals/inner/plain.md": "no frontmatter\n",
            "skills/SKILLS.md": _SKILLS_ROUTING,
            "skills/vendor/.harnessleaf": "",
            "skills/vendor/broken/SKILL.md": '---\nname: ""\ndescription: ""\n---\nbody\n',
        },
    )

    assert lint_harness(tree) == HarnessFindings()


def test_strict_fails_on_warnings_only() -> None:
    finding = HarnessFinding("docs/plain.md", "content '.md' lacks a 'description'")
    warnings_only = HarnessFindings(warnings=(finding,))

    assert warnings_only.failed(strict=False) is False
    assert warnings_only.failed(strict=True) is True


def test_errors_fail_with_or_without_strict_and_a_clean_lint_never_fails() -> None:
    errors = HarnessFindings(errors=(HarnessFinding("skills/x", "skill leaf has empty 'name'"),))

    assert (errors.failed(strict=False), errors.failed(strict=True)) == (True, True)
    assert (HarnessFindings().failed(strict=False), HarnessFindings().failed(strict=True)) == (
        False,
        False,
    )
