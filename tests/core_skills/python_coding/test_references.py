"""The python-coding skill's references and their ``playbook.references`` entries.

prU C-python-coding-refs: the mapping (specs/prU-core-python-skills/mapping-
python-coding.md, "References") names three internal decision guides, each with an
open-when line, no gate and the rule ids it routes to. D47 lists each in
``playbook.references``; D49 caps an internal decision guide at 120 lines.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Final

import pytest

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from tests._catalog import core_skill_root

pytestmark = pytest.mark.catalog

SKILL_ROOT: Final = core_skill_root("python-coding")
#: The mapping's references, in its order; none carries a gate.
MAPPED_REFERENCES: Final = (
    "references/python-version-idioms.md",
    "references/choosing-a-data-shape.md",
    "references/error-flow.md",
)
#: The mapping's "Routes to" column: the rule ids each reference must name.
ROUTES_TO: Final = {
    "references/python-version-idioms.md": [
        "python-typing",
        "python-type-aliases",
        "python-async",
        "python-async-tasks",
        "python-async-fanout",
        "python-async-generators",
        "python-enums",
        "pydantic-model-validators",
        "python-match-fallback",
        "python-match-destructuring",
        "python-pure-core",
        "python-decorators",
        "python-context-managers",
    ],
    "references/choosing-a-data-shape.md": [
        "python-data-shapes",
        "python-frozen-dataclasses",
        "python-dataclass-post-init",
        "python-enums",
        "python-type-aliases",
        "python-protocols",
        "python-properties",
        "python-hide-internal-state",
        "python-optional-keys",
        "python-match-destructuring",
        "python-error-boundaries",
        "pydantic-boundaries",
        "pydantic-typed-settings",
        "pydantic-field-constraints",
        "pydantic-model-validators",
        "pydantic-special-types",
        "pydantic-serializers",
    ],
    "references/error-flow.md": [
        "python-custom-exceptions",
        "python-error-handling",
        "python-error-boundaries",
        "python-early-return",
        "python-dataclass-post-init",
        "python-match-fallback",
        "python-optional-keys",
        "pydantic-boundaries",
        "python-context-managers",
        "python-custom-context-managers",
        "python-async",
        "python-async-tasks",
        "python-retries-and-timeouts",
        "python-decorators",
    ],
}
#: The mapping's SKILL.md See Also: plain-text skill names (D32).
SEE_ALSO_SKILLS: Final = (
    "python-testing",
    "python-tooling",
    "design-patterns",
    "python-architecture",
    "web-application",
    "ml-data",
)
#: D49: an engine-written decision guide is at most 120 lines.
INTERNAL_GUIDE_MAX_LINES: Final = 120
#: A token shaped like one of this skill's rule ids (their prefixes), not part of a
#: file name such as ``python-version-idioms.md``.
_RULE_ID_LIKE_RE: Final = re.compile(r"(?<![\w.-])(?:python|pydantic)-[a-z0-9-]*[a-z0-9](?![\w.-])")
#: Names with those prefixes that are no rule of this skill: skill names.
_NOT_THIS_SKILLS_RULES: Final = frozenset(
    {"python-coding", "python-architecture", "python-testing", "python-tooling"}
)


def _references_block() -> list[dict[str, Any]]:
    """The SKILL.md ``playbook.references`` entries, as YAML gives them."""
    frontmatter, _ = split_frontmatter((SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8"))
    entries = frontmatter["playbook"].get("references", [])
    assert isinstance(entries, list), entries
    return entries


def _reference_text(path: str) -> str:
    """The text of one of the skill's files: ``_reference_text(MAPPED_REFERENCES[0])``."""
    return (SKILL_ROOT / path).read_text(encoding="utf-8")


def _python_coding_rule_ids() -> set[str]:
    """Every rule id of the skill: the rule file names without their suffixes."""
    return {path.name.split(".")[0] for path in (SKILL_ROOT / "rules").iterdir()}


def _rule_id_like_names(text: str) -> set[str]:
    """The rule-id-shaped names ``text`` mentions, skill names left out.

    >>> sorted(_rule_id_like_names("python-version-idioms.md, python-async; python-coding"))
    ['python-async']
    """
    return set(_RULE_ID_LIKE_RE.findall(text)) - _NOT_THIS_SKILLS_RULES


def test_skill_lists_each_mapped_reference_ungated_in_mapping_order() -> None:
    entries = _references_block()

    assert [entry["path"] for entry in entries] == list(MAPPED_REFERENCES)
    assert all("applies_if" not in entry for entry in entries)
    assert all(entry["open_when"].strip() for entry in entries)


def test_hand_written_body_leaves_navigation_to_the_engine() -> None:
    """D47: no hand-written picking bullets; D32: Quick Reference and plain-text See Also."""
    _, body = split_frontmatter((SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8"))
    headings = re.findall(r"^## (.+)$", body, re.MULTILINE)

    assert headings == ["Quick Reference", "Pythonic rewrites", "See Also"]
    assert not any(path in body for path in MAPPED_REFERENCES)
    see_also = body.partition("## See Also")[2]
    for skill in SEE_ALSO_SKILLS:
        assert f"- {skill}:" in see_also, skill


@pytest.mark.parametrize("path", MAPPED_REFERENCES)
def test_reference_names_every_rule_it_routes_to(path: str) -> None:
    named = _rule_id_like_names(_reference_text(path))

    missing = [rule_id for rule_id in ROUTES_TO[path] if rule_id not in named]

    assert missing == [], f"{path} does not name {missing}"


@pytest.mark.parametrize("path", MAPPED_REFERENCES)
def test_reference_names_only_rule_ids_the_skill_ships(path: str) -> None:
    named = _rule_id_like_names(_reference_text(path))

    unknown = sorted(named - _python_coding_rule_ids())

    assert unknown == [], f"{path} names rule ids python-coding does not ship: {unknown}"


def test_rule_id_pattern_skips_file_names_and_skill_names() -> None:
    text = "see python-version-idioms.md; python-async and pydantic-boundaries; python-coding"

    assert _rule_id_like_names(text) == {"python-async", "pydantic-boundaries"}


@pytest.mark.parametrize("path", MAPPED_REFERENCES)
def test_internal_guide_stays_within_the_d49_budget(path: str) -> None:
    lines = _reference_text(path).count("\n")

    assert lines <= INTERNAL_GUIDE_MAX_LINES, f"{path} is {lines} lines"


@pytest.mark.parametrize("path", MAPPED_REFERENCES)
def test_guide_ends_naming_its_sibling_guides_by_bare_file_name(path: str) -> None:
    last_line = _reference_text(path).rstrip("\n").rsplit("\n", 1)[-1]
    siblings = [PurePosixPath(other).name for other in MAPPED_REFERENCES if other != path]

    assert all(name in last_line for name in siblings), last_line
    assert "references/" not in last_line, last_line
