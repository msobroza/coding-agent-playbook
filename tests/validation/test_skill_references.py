"""``validation._skill_references``: the D47 ``playbook.references`` checks (prU D47, D48).

Wired in through ``check_skill_sections``; each fixture produces exactly one
finding with its exact message.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.validation.section_samples import (
    SECTIONED_BLOCK,
    SECTIONLESS_BLOCK,
    SKILL_LABEL,
    errors_of,
    make_rule,
    make_skill,
)

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.artifacts.skill import Skill

_UNLISTED = (
    "is not listed in 'playbook.references'; add an entry with its path (or a parent "
    "directory) and open_when (license files are exempt)"
)


def _skill_dir(tmp_path: Path, *files: str) -> Path:
    for name in files:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("x\n", encoding="utf-8")
    return tmp_path


def _references_skill(references: object, source_dir: Path) -> Skill:
    return make_skill({**SECTIONED_BLOCK, "references": references}, source_dir=source_dir)


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

    assert errors_of([make_rule()], _references_skill(references, source_dir)) == []


def test_references_must_be_a_list(tmp_path: Path) -> None:
    assert errors_of([make_rule()], _references_skill("references/guide.md", tmp_path)) == [
        (
            SKILL_LABEL,
            "'playbook.references' must be a list of mappings with keys path, open_when and "
            "optional applies_if, got str 'references/guide.md'",
        )
    ]


def test_a_reference_entry_must_be_a_mapping(tmp_path: Path) -> None:
    assert errors_of([make_rule()], _references_skill(["references/guide.md"], tmp_path)) == [
        (
            SKILL_LABEL,
            "reference entry 1 of 'playbook.references': must be a mapping with keys path, "
            "open_when and optional applies_if, got str 'references/guide.md'",
        )
    ]


@pytest.mark.parametrize(
    ("entry", "problem"),
    [
        ({"path": "references/guide.md"}, "is missing 'open_when'"),
        (
            {"path": "references/guide.md", "open_when": "a\nb"},
            "'open_when' must be one line, got 'a\\nb'",
        ),
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

    assert errors_of([make_rule()], _references_skill([entry], source_dir)) == [
        (
            SKILL_LABEL,
            f"reference 'references/guide.md' (entry 1 of 'playbook.references'): {problem}",
        )
    ]


@pytest.mark.parametrize("key", ["any_framework", "any_ml_stack", "any_dependency"])
def test_a_list_predicate_key_given_a_bare_string_is_an_error(tmp_path: Path, key: str) -> None:
    source_dir = _skill_dir(tmp_path, "references/guide.md")
    entry = {"path": "references/guide.md", "open_when": "x", "applies_if": {key: "fastapi"}}

    assert errors_of([make_rule()], _references_skill([entry], source_dir)) == [
        (
            SKILL_LABEL,
            "reference 'references/guide.md' (entry 1 of 'playbook.references'): applies_if: "
            f"predicate {key!r} must be a list of strings; got 'fastapi'",
        )
    ]


@pytest.mark.parametrize("path", ["docs/guide.md", "/abs/references/x.md", "references/../x.md"])
def test_a_reference_path_stays_under_references_or_examples(tmp_path: Path, path: str) -> None:
    entry = {"path": path, "open_when": "x"}

    assert errors_of([make_rule()], _references_skill([entry], tmp_path)) == [
        (
            SKILL_LABEL,
            f"reference {path!r} (entry 1 of 'playbook.references'): 'path' must be a relative "
            "path under references/ or examples/, e.g. 'references/guide.md'",
        )
    ]


def test_a_reference_entry_needs_a_path(tmp_path: Path) -> None:
    assert errors_of([make_rule()], _references_skill([{"open_when": "x"}], tmp_path)) == [
        (SKILL_LABEL, "reference entry 1 of 'playbook.references': is missing 'path'")
    ]


def test_a_listed_reference_must_exist(tmp_path: Path) -> None:
    entry = {"path": "references/gone.md", "open_when": "x"}

    assert errors_of([make_rule()], _references_skill([entry], tmp_path)) == [
        (
            SKILL_LABEL,
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

    assert errors_of([make_rule()], _references_skill([entry], source_dir)) == [
        (SKILL_LABEL, f"examples/app/main.py {_UNLISTED}")
    ]


def test_only_license_files_are_exempt_from_listing(tmp_path: Path) -> None:
    # D47 exempts license files and nothing else: a dotfile needs an entry too.
    source_dir = _skill_dir(tmp_path, "references/guide.md", "references/.notes")
    entry = {"path": "references/guide.md", "open_when": "x"}

    assert errors_of([make_rule()], _references_skill([entry], source_dir)) == [
        (SKILL_LABEL, f"references/.notes {_UNLISTED}")
    ]


def test_a_sectioned_skill_without_references_lists_its_files(tmp_path: Path) -> None:
    source_dir = _skill_dir(tmp_path, "references/guide.md")
    skill = make_skill(source_dir=source_dir)

    assert [message for _, message in errors_of([make_rule()], skill)] == [
        f"references/guide.md {_UNLISTED}"
    ]


@pytest.mark.parametrize("block", [SECTIONLESS_BLOCK, {**SECTIONLESS_BLOCK, "sections": []}])
def test_a_sectionless_skill_without_references_keeps_its_files_unlisted(
    tmp_path: Path, block: dict[str, Any]
) -> None:
    source_dir = _skill_dir(tmp_path, "references/guide.md")
    skill = make_skill(block, source_dir=source_dir)

    assert errors_of([make_rule(section=None, priority=50)], skill) == []
