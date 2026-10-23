"""``validation._sections``: S1-S7 and the D42 warning.

One fixture per check, each producing exactly one finding with its exact message;
a sectionless skill reports nothing new (prU D17, D42, D46.8). The D47
``playbook.references`` checks are in ``test_skill_references.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.validation.section_samples import (
    FIXTURES,
    MOCKING,
    SECTIONLESS_BLOCK,
    SKILL_LABEL,
    check,
    errors_of,
    make_rule,
    make_skill,
)


def test_a_sound_sectioned_skill_reports_nothing() -> None:
    rules = [make_rule(), make_rule("pytest-fixtures", section="fixtures", priority=60)]

    findings = check(rules, make_skill())

    assert (findings.errors, findings.warnings) == ([], [])


def test_a_sectionless_skill_reports_nothing_new() -> None:
    rules = [make_rule(section=None, priority=50)]

    findings = check(rules, make_skill(SECTIONLESS_BLOCK))

    assert (findings.errors, findings.warnings) == ([], [])


# --- S1: shape -------------------------------------------------------------------------------


def test_s1_sections_must_be_a_list() -> None:
    assert errors_of([], make_skill({"sections": "mocking"})) == [
        (
            SKILL_LABEL,
            "'playbook.sections' must be a list of mappings with keys id, title, "
            "impact, summary, open_when, got str 'mocking'",
        )
    ]


def test_s1_an_empty_sections_list_declares_no_sections() -> None:
    rules = [make_rule(section=None, priority=5, body="# Use fakes [LOW]\n")]

    assert errors_of(rules, make_skill({"sections": []})) == []


def test_s5_holds_for_a_member_of_a_skill_with_an_empty_sections_list() -> None:
    errors = errors_of([make_rule(priority=50)], make_skill({"sections": []}))

    assert [message for _, message in errors] == [
        "'section: mocking' is not allowed: skill 'python-testing' declares no "
        "'playbook.sections'; remove 'section', or declare the section in that skill"
    ]


@pytest.mark.parametrize(
    ("entry", "problem"),
    [
        (
            {**MOCKING, "impact": "URGENT"},
            "'impact' 'URGENT' must be one of CRITICAL, HIGH, MEDIUM, LOW",
        ),
        (
            {**MOCKING, "level": 1},
            "has unknown key 'level'; allowed keys: id, title, impact, summary, open_when",
        ),
        (
            {**MOCKING, "title": "T" * 41},
            f"'title' '{'T' * 41}' is 41 chars; keep it to at most 40",
        ),
        ({**MOCKING, "summary": "a\nb"}, "'summary' must be one line, got 'a\\nb'"),
    ],
)
def test_s1_reports_each_malformed_entry(entry: dict[str, Any], problem: str) -> None:
    assert errors_of([], make_skill({"sections": [entry]})) == [
        (SKILL_LABEL, f"section 'mocking' (entry 1 of 'playbook.sections'): {problem}")
    ]


def test_s1_a_section_id_must_be_kebab_case() -> None:
    assert errors_of([], make_skill({"sections": [{**MOCKING, "id": "Mocking"}]})) == [
        (
            SKILL_LABEL,
            "section 'Mocking' (entry 1 of 'playbook.sections'): 'id' 'Mocking' must be "
            "kebab-case, e.g. 'error-handling'",
        )
    ]


def test_s1_section_ids_are_unique() -> None:
    skill = make_skill({"sections": [MOCKING, {**FIXTURES, "id": "mocking"}]})

    assert errors_of([], skill) == [
        (
            SKILL_LABEL,
            "'playbook.sections' declares section 'mocking' more than once; ids are unique",
        )
    ]


@pytest.mark.parametrize("open_when", [None, "", "  "])
def test_s1_every_section_declares_a_one_line_open_when(open_when: str | None) -> None:
    entry = {**MOCKING, "open_when": open_when}
    if open_when is None:
        del entry["open_when"]
        problem = "is missing 'open_when'"
    else:
        problem = f"'open_when' must be a non-empty string, got str {open_when!r}"

    assert errors_of([], make_skill({"sections": [entry]})) == [
        (SKILL_LABEL, f"section 'mocking' (entry 1 of 'playbook.sections'): {problem}")
    ]


def test_s1_a_malformed_list_skips_the_member_checks() -> None:
    rules = [make_rule(section="nope", priority=99)]

    errors = errors_of(rules, make_skill({"sections": [{**MOCKING, "impact": "URGENT"}]}))

    assert [path for path, _ in errors] == [SKILL_LABEL]


# --- S2: order -------------------------------------------------------------------------------


def test_s2_sections_run_from_critical_to_low() -> None:
    rules = [make_rule(), make_rule("pytest-fixtures", section="fixtures", priority=60)]

    assert errors_of(rules, make_skill({"sections": [FIXTURES, MOCKING]})) == [
        (
            SKILL_LABEL,
            "'playbook.sections' must run from CRITICAL to LOW: section 'mocking' (CRITICAL) "
            "comes after 'fixtures' (MEDIUM)",
        )
    ]


# --- S3: the section exists ------------------------------------------------------------------


def test_s3_a_member_names_a_declared_section() -> None:
    assert errors_of([make_rule(section="mokcing")], make_skill()) == [
        (
            "pkg/rules/pytest-fakes.md",
            "section 'mokcing' is not declared by skill 'python-testing'; declared sections: "
            "mocking, fixtures",
        )
    ]


# --- S4: a member of a sectioned skill names its section --------------------------------------

_S4_MESSAGE = (
    "skill 'python-testing' declares sections, so its member rule needs 'section:'; "
    "declared sections: mocking, fixtures"
)


def test_s4_a_member_of_the_skills_own_layer_needs_a_section() -> None:
    assert errors_of([make_rule(section=None)], make_skill()) == [
        ("pkg/rules/pytest-fakes.md", _S4_MESSAGE)
    ]


def test_s4_a_repo_local_rule_joining_another_layers_skill_needs_a_section() -> None:
    rule = make_rule(section=None, priority=50, package="<repo-local>")

    assert errors_of([rule], make_skill()) == [("<repo-local>/rules/pytest-fakes.md", _S4_MESSAGE)]


def test_d42_a_member_from_another_overlay_layer_without_section_only_warns() -> None:
    rule = make_rule(section=None, priority=50, package="overlay_pkg")

    findings = check([rule], make_skill())

    assert findings.errors == []
    assert [(w.path, w.message) for w in findings.warnings] == [
        (
            "overlay_pkg/rules/pytest-fakes.md",
            "joins skill 'python-testing' (pkg) from another layer without 'section:'; it is "
            "listed under 'Other', after the declared sections: mocking, fixtures",
        )
    ]


def test_d42_a_replaced_skills_members_from_the_replaced_layer_only_warn() -> None:
    # An overlay replaces the core skill and declares sections: the core members'
    # authors never saw those sections, so they land in "Other" instead of failing.
    core_member = make_rule(section=None, priority=50, package="coding_agent_playbook")

    findings = check([core_member], make_skill(package="overlay_pkg"))

    assert findings.errors == []
    assert [w.path for w in findings.warnings] == ["coding_agent_playbook/rules/pytest-fakes.md"]


def test_a_member_from_another_layer_with_a_section_is_checked_like_any_member() -> None:
    rule = make_rule(priority=45, package="overlay_pkg")

    assert [message for _, message in errors_of([rule], make_skill())] == [
        "priority 45 is outside the band of section 'mocking' (CRITICAL): expected 20-39"
    ]


# --- S5: section: without sections -----------------------------------------------------------


def test_s5_an_always_rule_takes_no_section() -> None:
    rule = make_rule("house-style", skill=None, scope="always")

    assert errors_of([rule], make_skill()) == [
        (
            "pkg/rules/house-style.md",
            "'section: mocking' is not allowed on an always rule (sections group a skill's "
            "member rules); remove 'section'",
        )
    ]


def test_s5_a_member_of_a_sectionless_skill_takes_no_section() -> None:
    assert errors_of([make_rule(priority=50)], make_skill(SECTIONLESS_BLOCK)) == [
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

    assert errors_of([make_rule(section=section, priority=priority)], make_skill()) == [
        (
            "pkg/rules/pytest-fakes.md",
            f"priority {priority} is outside the band of section {section!r} ({impact}): "
            f"expected {band}",
        )
    ]


def test_s6_bands_apply_only_to_sectioned_skills() -> None:
    rules = [make_rule(section=None, priority=5)]

    assert errors_of(rules, make_skill(SECTIONLESS_BLOCK)) == []


# --- S7: no authored impact tag --------------------------------------------------------------


def test_s7_the_first_heading_carries_no_authored_impact_tag() -> None:
    rule = make_rule(body="```\n# not a heading [LOW]\n```\n# Use fakes [HIGH]\n\nBody\n")

    assert errors_of([rule], make_skill()) == [
        (
            "pkg/rules/pytest-fakes.md",
            "the first heading '# Use fakes [HIGH]' carries an impact tag; remove '[HIGH]' "
            "(the engine renders it from the rule's section)",
        )
    ]


def test_s7_a_tag_after_the_first_heading_is_left_alone() -> None:
    rule = make_rule(body="# Use fakes\n\n## Why [HIGH]\n")

    assert errors_of([rule], make_skill()) == []


def test_s7_leaves_members_of_sectionless_skills_as_they_are_today() -> None:
    rule = make_rule(section=None, priority=50, body="# Use fakes [LOW]\n")

    assert errors_of([rule], make_skill(SECTIONLESS_BLOCK)) == []
