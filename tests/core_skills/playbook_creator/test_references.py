"""The playbook-creator skill's templates and their ``playbook.references`` entries.

prU C-playbook-creator-refs: the mapping (specs/prU-core-python-skills/mapping-
playbook-creator.md, "References") names six engine-written templates (D70), each
with an open-when line, no gate and the rule ids it routes to. D47 lists each in
``playbook.references``; D49 caps an internal guide at 120 lines. The rules of
C-playbook-creator-01 end their Notes with the templates the mapping names for them.
"""

from __future__ import annotations

import re
from typing import Final

import pytest

from coding_agent_playbook.rendering.jinja import RULE_CALL_RE
from tests._catalog import core_skill_root
from tests.core_skills._references import (
    INTERNAL_GUIDE_MAX_LINES,
    guide_line_count,
    reference_text,
    references_block,
    skill_md_parts,
    skill_rule_ids,
)

pytestmark = pytest.mark.catalog

SKILL_ROOT: Final = core_skill_root("playbook-creator")
#: The mapping's references, in its order: path -> its "Open when" line; none is gated.
MAPPED_OPEN_WHEN: Final = {
    "references/rule-template.md": (
        "Starting a new rule file: an in-skill member rule, a rule joining another"
        " layer's skill, or an always rule."
    ),
    "references/skill-template.md": (
        "Starting a new skill directory, or adding sections, a guide, a script or an"
        " example to an existing skill."
    ),
    "references/hook-template.md": (
        "Starting a new HOOK.md with a builtin or an external handler, or wiring a"
        " hook's guard twin into pre-commit."
    ),
    "references/prompt-template.md": (
        "Starting a new slash-command prompt with includes_rules, a write scope or an"
        " output contract."
    ),
    "references/eval-sample-template.md": (
        "Starting a new eval sample: its task file, setup/, solution/ and negatives for"
        " an edit or a review-only prompt."
    ),
    "references/plugin-template.md": (
        "Starting a bundled plugin or an overlay package, or writing its README,"
        " ATTRIBUTIONS or framework file."
    ),
}
MAPPED_REFERENCES: Final = tuple(MAPPED_OPEN_WHEN)
#: The mapping's "Routes to" column: the rule ids each template must name.
ROUTES_TO: Final = {
    "references/rule-template.md": [
        "playbook-rule-frontmatter",
        "playbook-rule-ids",
        "playbook-rule-gates",
        "playbook-rule-templates",
        "playbook-rule-body",
        "playbook-skill-sections",
        "playbook-layer-placement",
    ],
    "references/skill-template.md": [
        "playbook-skill-sections",
        "playbook-skill-md",
        "playbook-skill-files",
    ],
    "references/hook-template.md": [
        "playbook-hook-definition",
        "playbook-hook-guardrails",
        "playbook-override-by-id",
    ],
    "references/prompt-template.md": [
        "playbook-prompt-frontmatter",
        "playbook-eval-samples",
    ],
    "references/eval-sample-template.md": [
        "playbook-eval-samples",
        "playbook-prompt-frontmatter",
    ],
    "references/plugin-template.md": [
        "playbook-plugin-layout",
        "playbook-third-party-content",
        "playbook-layer-placement",
    ],
}
#: C-playbook-creator-01's rules -> the templates their last Note names (ticket row).
SEE_LINES: Final = {
    "playbook-ask-for-missing-inputs": tuple(
        path.removeprefix("references/") for path in MAPPED_REFERENCES
    ),
    "playbook-layer-placement": ("rule-template.md", "plugin-template.md"),
    "playbook-rule-frontmatter": ("rule-template.md",),
    "playbook-rule-gates": ("rule-template.md",),
    "playbook-rule-templates": ("rule-template.md",),
    "playbook-rule-body": ("rule-template.md",),
}
#: A token shaped like one of this skill's rule ids, not part of a file name.
_RULE_ID_LIKE_RE: Final = re.compile(r"(?<![\w./-])playbook-[a-z0-9-]*[a-z0-9](?![\w./-])")
#: Names with that prefix that are no rule of this skill: skill names.
_NOT_THIS_SKILLS_RULES: Final = frozenset({"playbook-creator", "playbook-guardrails"})


def _rule_id_like_names(text: str) -> set[str]:
    """The rule-id-shaped names ``text`` mentions, skill names left out.

    >>> sorted(_rule_id_like_names("rule-template.md, `playbook-rule-ids`; playbook-creator"))
    ['playbook-rule-ids']
    """
    return set(_RULE_ID_LIKE_RE.findall(text)) - _NOT_THIS_SKILLS_RULES


def _last_note(rule_id: str) -> str:
    """The last line of the rule's source file: the end of its Notes."""
    path = next((SKILL_ROOT / "rules").glob(f"{rule_id}.md*"))
    return path.read_text(encoding="utf-8").rstrip("\n").rsplit("\n", 1)[-1]


def test_skill_lists_each_mapped_reference_ungated_in_mapping_order() -> None:
    entries = references_block(SKILL_ROOT)

    assert [entry["path"] for entry in entries] == list(MAPPED_REFERENCES)
    assert all("applies_if" not in entry for entry in entries)
    assert {entry["path"]: entry["open_when"] for entry in entries} == MAPPED_OPEN_WHEN


def test_hand_written_body_leaves_navigation_to_the_engine() -> None:
    """D47: no hand-written picking bullets; the engine lists the templates."""
    _, body = skill_md_parts(SKILL_ROOT)

    assert not any(path.removeprefix("references/") in body for path in MAPPED_REFERENCES)


@pytest.mark.parametrize("path", MAPPED_REFERENCES)
def test_template_names_every_rule_it_routes_to(path: str) -> None:
    named = _rule_id_like_names(reference_text(SKILL_ROOT, path))

    missing = [rule_id for rule_id in ROUTES_TO[path] if rule_id not in named]

    assert missing == [], f"{path} does not name {missing}"


@pytest.mark.parametrize("path", MAPPED_REFERENCES)
def test_template_names_only_rule_ids_the_skill_ships(path: str) -> None:
    named = _rule_id_like_names(reference_text(SKILL_ROOT, path))

    unknown = sorted(named - skill_rule_ids(SKILL_ROOT))

    assert unknown == [], f"{path} names rule ids playbook-creator does not ship: {unknown}"


@pytest.mark.parametrize("path", MAPPED_REFERENCES)
def test_template_stays_within_the_d49_budget(path: str) -> None:
    lines = guide_line_count(SKILL_ROOT, path)

    assert lines <= INTERNAL_GUIDE_MAX_LINES, f"{path} is {lines} lines"


@pytest.mark.parametrize("path", MAPPED_REFERENCES)
def test_template_never_writes_the_rule_inclusion_call(path: str) -> None:
    assert not RULE_CALL_RE.search(reference_text(SKILL_ROOT, path)), path


@pytest.mark.parametrize(("rule_id", "templates"), sorted(SEE_LINES.items()))
def test_rule_notes_end_with_its_template_see_line(
    rule_id: str, templates: tuple[str, ...]
) -> None:
    last = _last_note(rule_id)

    assert last.startswith("- "), last
    assert all(name in last for name in templates), last
    assert "references/" not in last, last
