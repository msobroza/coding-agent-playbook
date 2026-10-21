"""``validation._sections``: S1-S7, the D42 warning and the D47 references checks.

One fixture per check, each producing exactly one finding with its exact message;
a sectionless skill reports nothing new (prU D17, D42, D46.8, D47).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.detector.predicate import evaluate_predicate
from coding_agent_playbook.validation._sections import check_skill_sections

if TYPE_CHECKING:
    from coding_agent_playbook.validation.findings import ValidationFindings

_SKILL = "python-testing"
_LABEL = f"skills/{_SKILL} (pkg)"
_MOCKING = {
    "id": "mocking",
    "title": "Mocking",
    "impact": "CRITICAL",
    "summary": "Fakes at the boundary.",
    "open_when": "Replacing a collaborator in a test.",
}
_FIXTURES = {
    "id": "fixtures",
    "title": "Fixtures",
    "impact": "MEDIUM",
    "summary": "Shared setup.",
    "open_when": "Adding or sharing test setup.",
}
_SECTIONS = [_MOCKING, _FIXTURES]
_BLOCK: dict[str, Any] = {"use_when": "writing tests", "sections": _SECTIONS}


def _rule(
    rule_id: str = "pytest-fakes",
    *,
    skill: str | None = _SKILL,
    section: str | None = "mocking",
    priority: int = 20,
    scope: str = "scoped",
    package: str = "pkg",
    body: str = "# Use fakes\n\nBody\n",
) -> Rule:
    frontmatter = RuleFrontmatter(
        id=rule_id,
        name=rule_id,
        description="One line.",
        scope=scope,  # type: ignore[arg-type]
        priority=priority,
        skill=skill,
        section=section,
    )
    path = Path(package) / "rules" / f"{rule_id}.md"
    return Rule(frontmatter, body, body, False, path, package)


def _skill(block: Any = None, *, source_dir: Path | None = None) -> Skill:
    frontmatter: dict[str, Any] = {"id": _SKILL, "description": "Tests."}
    frontmatter["playbook"] = _BLOCK if block is None else block
    return Skill(frontmatter, "# Body\n", None, None, "pkg", source_dir=source_dir)


def _check_predicate(predicate: dict[str, Any]) -> None:
    evaluate_predicate(predicate, {}, repo_root=Path())


def _check(rules: list[Rule], skill: Skill) -> ValidationFindings:
    return check_skill_sections(rules, [skill], check_predicate=_check_predicate)


def _errors(rules: list[Rule], skill: Skill) -> list[tuple[str, str]]:
    findings = _check(rules, skill)
    assert findings.warnings == []
    return [(error.path, error.message) for error in findings.errors]


def test_a_sound_sectioned_skill_reports_nothing() -> None:
    rules = [_rule(), _rule("pytest-fixtures", section="fixtures", priority=60)]

    findings = _check(rules, _skill())

    assert (findings.errors, findings.warnings) == ([], [])


def test_a_sectionless_skill_reports_nothing_new() -> None:
    rules = [_rule(section=None, priority=50)]

    findings = _check(rules, _skill({"use_when": "writing tests"}))

    assert (findings.errors, findings.warnings) == ([], [])


# --- S1: shape -------------------------------------------------------------------------------


def test_s1_sections_must_be_a_non_empty_list() -> None:
    assert _errors([], _skill({"sections": "mocking"})) == [
        (
            _LABEL,
            "'playbook.sections' must be a non-empty list of mappings with keys id, title, "
            "impact, summary, open_when, got str 'mocking'",
        )
    ]


@pytest.mark.parametrize(
    ("entry", "problem"),
    [
        (
            {**_MOCKING, "impact": "URGENT"},
            "'impact' 'URGENT' must be one of CRITICAL, HIGH, MEDIUM, LOW",
        ),
        (
            {**_MOCKING, "level": 1},
            "has unknown key 'level'; allowed keys: id, title, impact, summary, open_when",
        ),
        (
            {**_MOCKING, "title": "T" * 41},
            f"'title' '{'T' * 41}' is 41 chars; keep it to at most 40",
        ),
        ({**_MOCKING, "summary": "a\nb"}, "'summary' must be one line, got 'a\\nb'"),
    ],
)
def test_s1_reports_each_malformed_entry(entry: dict[str, Any], problem: str) -> None:
    assert _errors([], _skill({"sections": [entry]})) == [
        (_LABEL, f"section 'mocking' (entry 1 of 'playbook.sections'): {problem}")
    ]


def test_s1_a_section_id_must_be_kebab_case() -> None:
    assert _errors([], _skill({"sections": [{**_MOCKING, "id": "Mocking"}]})) == [
        (
            _LABEL,
            "section 'Mocking' (entry 1 of 'playbook.sections'): 'id' 'Mocking' must be "
            "kebab-case, e.g. 'error-handling'",
        )
    ]


def test_s1_section_ids_are_unique() -> None:
    assert _errors([], _skill({"sections": [_MOCKING, {**_FIXTURES, "id": "mocking"}]})) == [
        (_LABEL, "'playbook.sections' declares section 'mocking' more than once; ids are unique")
    ]


@pytest.mark.parametrize("open_when", [None, "", "  "])
def test_s1_every_section_declares_a_one_line_open_when(open_when: str | None) -> None:
    entry = {**_MOCKING, "open_when": open_when}
    if open_when is None:
        del entry["open_when"]
        problem = "is missing 'open_when'"
    else:
        problem = f"'open_when' must be a non-empty string, got str {open_when!r}"

    assert _errors([], _skill({"sections": [entry]})) == [
        (_LABEL, f"section 'mocking' (entry 1 of 'playbook.sections'): {problem}")
    ]


def test_s1_a_malformed_list_skips_the_member_checks() -> None:
    rules = [_rule(section="nope", priority=99)]

    errors = _errors(rules, _skill({"sections": [{**_MOCKING, "impact": "URGENT"}]}))

    assert [path for path, _ in errors] == [_LABEL]


# --- S2: order -------------------------------------------------------------------------------


def test_s2_sections_run_from_critical_to_low() -> None:
    rules = [_rule(), _rule("pytest-fixtures", section="fixtures", priority=60)]

    assert _errors(rules, _skill({"sections": [_FIXTURES, _MOCKING]})) == [
        (
            _LABEL,
            "'playbook.sections' must run from CRITICAL to LOW: section 'mocking' (CRITICAL) "
            "comes after 'fixtures' (MEDIUM)",
        )
    ]


# --- S3: the section exists ------------------------------------------------------------------


def test_s3_a_member_names_a_declared_section() -> None:
    assert _errors([_rule(section="mokcing")], _skill()) == [
        (
            "pkg/rules/pytest-fakes.md",
            "section 'mokcing' is not declared by skill 'python-testing'; declared sections: "
            "mocking, fixtures",
        )
    ]


# --- S4: a member of a sectioned skill names its section --------------------------------------


def test_s4_a_member_of_the_skills_own_layer_needs_a_section() -> None:
    assert _errors([_rule(section=None)], _skill()) == [
        (
            "pkg/rules/pytest-fakes.md",
            "skill 'python-testing' declares sections, so its member rule needs 'section:'; "
            "declared sections: mocking, fixtures",
        )
    ]


def test_d42_a_member_from_another_layer_without_section_only_warns() -> None:
    rule = _rule(section=None, priority=50, package="<repo-local>")

    findings = _check([rule], _skill())

    assert findings.errors == []
    assert [(w.path, w.message) for w in findings.warnings] == [
        (
            "<repo-local>/rules/pytest-fakes.md",
            "joins skill 'python-testing' (pkg) from another layer without 'section:'; it is "
            "listed under 'Other', after the declared sections: mocking, fixtures",
        )
    ]


def test_a_member_from_another_layer_with_a_section_is_checked_like_any_member() -> None:
    rule = _rule(priority=45, package="<repo-local>")

    assert [message for _, message in _errors([rule], _skill())] == [
        "priority 45 is outside the band of section 'mocking' (CRITICAL): expected 20-39"
    ]


# --- S5: section: without sections -----------------------------------------------------------


def test_s5_an_always_rule_takes_no_section() -> None:
    rule = _rule("house-style", skill=None, scope="always")

    assert _errors([rule], _skill()) == [
        (
            "pkg/rules/house-style.md",
            "'section: mocking' is not allowed on an always rule (sections group a skill's "
            "member rules); remove 'section'",
        )
    ]


def test_s5_a_member_of_a_sectionless_skill_takes_no_section() -> None:
    assert _errors([_rule(priority=50)], _skill({"use_when": "writing tests"})) == [
        (
            "pkg/rules/pytest-fakes.md",
            "'section: mocking' is not allowed: skill 'python-testing' declares no "
            "'playbook.sections'; remove 'section', or declare the section in that skill",
        )
    ]


# --- S6: priority band -----------------------------------------------------------------------


@pytest.mark.parametrize(("section", "priority"), [("mocking", 19), ("fixtures", 80)])
def test_s6_a_members_priority_lies_in_its_sections_band(section: str, priority: int) -> None:
    band = "20-39" if section == "mocking" else "60-79"
    impact = "CRITICAL" if section == "mocking" else "MEDIUM"

    assert _errors([_rule(section=section, priority=priority)], _skill()) == [
        (
            "pkg/rules/pytest-fakes.md",
            f"priority {priority} is outside the band of section {section!r} ({impact}): "
            f"expected {band}",
        )
    ]


def test_s6_bands_apply_only_to_sectioned_skills() -> None:
    rules = [_rule(section=None, priority=5)]

    assert _errors(rules, _skill({"use_when": "writing tests"})) == []


# --- S7: no authored impact tag --------------------------------------------------------------


def test_s7_the_first_heading_carries_no_authored_impact_tag() -> None:
    rule = _rule(body="```\n# not a heading [LOW]\n```\n# Use fakes [HIGH]\n\nBody\n")

    assert _errors([rule], _skill()) == [
        (
            "pkg/rules/pytest-fakes.md",
            "the first heading '# Use fakes [HIGH]' carries an impact tag; remove '[HIGH]' "
            "(the engine renders it from the rule's section)",
        )
    ]


def test_s7_a_tag_after_the_first_heading_is_left_alone() -> None:
    rule = _rule(body="# Use fakes\n\n## Why [HIGH]\n")

    assert _errors([rule], _skill()) == []


def test_s7_applies_to_members_of_sectionless_skills_too() -> None:
    rule = _rule(section=None, priority=50, body="# Use fakes [LOW]\n")

    errors = _errors([rule], _skill({"use_when": "writing tests"}))

    assert [message.split(";")[0] for _, message in errors] == [
        "the first heading '# Use fakes [LOW]' carries an impact tag"
    ]


# --- D47: playbook.references ----------------------------------------------------------------


def _skill_dir(tmp_path: Path, *files: str) -> Path:
    for name in files:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x\n", encoding="utf-8")
    return tmp_path


def _references_skill(references: object, source_dir: Path) -> Skill:
    return _skill({**_BLOCK, "references": references}, source_dir=source_dir)


def test_listed_references_and_examples_validate(tmp_path: Path) -> None:
    source_dir = _skill_dir(
        tmp_path,
        "references/guide.md",
        "references/LICENSE.python-best-practices",
        "examples/app/README.md",
        "examples/app/src/main.py",
    )
    references = [
        {"path": "references/guide.md", "open_when": "Choosing a test double."},
        {
            "path": "examples/app",
            "open_when": "Wiring an app.",
            "applies_if": {"has_framework": ["fastapi"]},
        },
    ]

    assert _errors([_rule()], _references_skill(references, source_dir)) == []


def test_references_must_be_a_list(tmp_path: Path) -> None:
    assert _errors([_rule()], _references_skill("references/guide.md", tmp_path)) == [
        (
            _LABEL,
            "'playbook.references' must be a list of mappings with keys path, open_when and "
            "optional applies_if, got str 'references/guide.md'",
        )
    ]


@pytest.mark.parametrize(
    ("entry", "problem"),
    [
        ({"path": "references/guide.md"}, "is missing 'open_when'"),
        (
            {"path": "references/guide.md", "open_when": "x", "gate": 1},
            "has unknown key 'gate'; allowed keys: path, open_when, applies_if",
        ),
        (
            {"path": "references/guide.md", "open_when": "x", "applies_if": "fastapi"},
            "'applies_if' must be a mapping of predicate keys, got str 'fastapi'",
        ),
        (
            {"path": "references/guide.md", "open_when": "x", "applies_if": {"wat": True}},
            "applies_if: unknown predicate key: 'wat'",
        ),
    ],
)
def test_references_report_each_malformed_entry(
    tmp_path: Path, entry: dict[str, Any], problem: str
) -> None:
    source_dir = _skill_dir(tmp_path, "references/guide.md")

    assert _errors([_rule()], _references_skill([entry], source_dir)) == [
        (_LABEL, f"reference 'references/guide.md' (entry 1 of 'playbook.references'): {problem}")
    ]


@pytest.mark.parametrize("key", ["any_framework", "any_ml_stack", "any_dependency"])
def test_a_list_predicate_key_given_a_bare_string_is_an_error(tmp_path: Path, key: str) -> None:
    source_dir = _skill_dir(tmp_path, "references/guide.md")
    entry = {"path": "references/guide.md", "open_when": "x", "applies_if": {key: "fastapi"}}

    assert _errors([_rule()], _references_skill([entry], source_dir)) == [
        (
            _LABEL,
            "reference 'references/guide.md' (entry 1 of 'playbook.references'): applies_if: "
            f"predicate {key!r} must be a list of strings; got 'fastapi'",
        )
    ]


@pytest.mark.parametrize("path", ["docs/guide.md", "/abs/references/x.md", "references/../x.md"])
def test_a_reference_path_stays_under_references_or_examples(tmp_path: Path, path: str) -> None:
    entry = {"path": path, "open_when": "x"}

    assert _errors([_rule()], _references_skill([entry], tmp_path)) == [
        (
            _LABEL,
            f"reference {path!r} (entry 1 of 'playbook.references'): 'path' must be a relative "
            "path under references/ or examples/, e.g. 'references/guide.md'",
        )
    ]


def test_a_listed_reference_must_exist(tmp_path: Path) -> None:
    entry = {"path": "references/gone.md", "open_when": "x"}

    assert _errors([_rule()], _references_skill([entry], tmp_path)) == [
        (
            _LABEL,
            "reference 'references/gone.md' (entry 1 of 'playbook.references'): "
            "references/gone.md does not exist in the skill directory",
        )
    ]


def test_every_reference_and_example_file_is_listed(tmp_path: Path) -> None:
    source_dir = _skill_dir(
        tmp_path,
        "references/guide.md",
        "references/LICENSE.python-best-practices",
        "examples/app/main.py",
    )
    entry = {"path": "references/guide.md", "open_when": "x"}

    assert _errors([_rule()], _references_skill([entry], source_dir)) == [
        (
            _LABEL,
            "examples/app/main.py is not listed in 'playbook.references'; add an entry with its "
            "path (or a parent directory) and open_when (license files are exempt)",
        )
    ]


def test_a_sectioned_skill_without_references_lists_its_files(tmp_path: Path) -> None:
    source_dir = _skill_dir(tmp_path, "references/guide.md")

    assert [message for _, message in _errors([_rule()], _skill(source_dir=source_dir))] == [
        "references/guide.md is not listed in 'playbook.references'; add an entry with its "
        "path (or a parent directory) and open_when (license files are exempt)"
    ]


def test_a_sectionless_skill_without_references_keeps_its_files_unlisted(tmp_path: Path) -> None:
    source_dir = _skill_dir(tmp_path, "references/guide.md")
    skill = _skill({"use_when": "writing tests"}, source_dir=source_dir)

    assert _errors([_rule(section=None, priority=50)], skill) == []
