"""CI gates for the two always rules in core and the text they handed off (D17; spec 6.8.13).

The always tier rides every turn, so it keeps only the project's identity, two
working agreements and eight house-style bullets. Everything else the old house
style said moved to one of two ``python-coding`` members, ``python-data-shapes``
and ``python-idioms`` (spec 6.5.4), and its class-design items later on to
``python-classes-and-protocols`` (spec 9.8); the one-owner table below is the
"nothing silently lost" regression for those moves.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

import pytest

from tests._budget_probe import reference_probe_facts, render_core_rule
from tests._catalog import core_rules, core_skill_ids

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

HOUSE_STYLE: Final = "python-house-style"
PROJECT_CONTEXT: Final = "project-context"
DATA_SHAPES: Final = "python-data-shapes"
IDIOMS: Final = "python-idioms"
CLASSES: Final = "python-classes-and-protocols"
ALWAYS_RULES: Final = (PROJECT_CONTEXT, HOUSE_STYLE)

#: Phrases the eight D17 bullets must keep. The ``None`` and ``excepted`` clauses
#: are regressions for repos where no scoped copy of them is active (spec 6.5.3).
D17_HOUSE_STYLE_PHRASES: Final = (
    "Type-hint every function signature",
    "pathlib.Path",
    'encoding="utf-8"',
    "dict[str, Any]",
    "mutable default argument",
    "default to `None`",
    "default_factory",
    "keyword-only",
    "Literal",
    "Decimal",
    "# noqa",
    "# type: ignore",
    "Wrap a third-party class",
    "framework base classes excepted",
    "layout axis",
)
#: Each item that left the house style (spec 6.5.4) -> the one member rule that owns it now.
#: The two class-design items moved on from python-idioms to python-classes-and-protocols
#: with the python-best-practices distillation (spec 9.8).
MOVED_ITEM_OWNERS: Final = (
    ("three or more fields", DATA_SHAPES),
    ("parallel lists", DATA_SHAPES),
    ("NamedTuple", DATA_SHAPES),
    ("@property", DATA_SHAPES),
    ("frozenset", DATA_SHAPES),
    ("builder", DATA_SHAPES),
    ("Final", DATA_SHAPES),
    ("settings object", DATA_SHAPES),
    ("match the file", IDIOMS),
    ("os.path", IDIOMS),
    ("count_lines", IDIOMS),
    ("split the function", IDIOMS),
    ("composition over inheritance", CLASSES),
    ("DeclarativeBase", CLASSES),
    ("f-strings", IDIOMS),
    ("single quotes", IDIOMS),
    ("first-party", IDIOMS),
    ("import *", IDIOMS),
    ("shadow builtins", IDIOMS),
    ("early `return`", IDIOMS),
)
#: Owned by always bullet 2 and project-context reminder 2, so python-idioms must not restate them.
ALWAYS_TIER_PHRASES: Final = ("pathlib.Path", 'encoding="utf-8"', "mention the difference")
#: The project-context reminders D17 cut.
CUT_REMINDERS: Final = (
    "Read existing code",
    "Prefer clarity over cleverness",
    "Keep changes minimal",
)
_FENCED_BLOCK: Final = re.compile(r"^```.*?^```[ \t]*$", re.MULTILINE | re.DOTALL)
_DEMO_METADATA: Final = {
    "project_name": "demo",
    "project_kind": "python-library",
    "project_description": "",
}


def _body(rule_id: str) -> str:
    """The source body of core rule ``rule_id`` (Jinja unrendered)."""
    return core_rules()[rule_id].body


def _prose(text: str) -> str:
    """``text`` without its fenced code blocks."""
    return _FENCED_BLOCK.sub("", text)


def _bullets(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("- ")]


def _render_project_context(tmp_path: Path, description: str) -> str:
    metadata = {**_DEMO_METADATA, "project_description": description}
    return render_core_rule(PROJECT_CONTEXT, reference_probe_facts(tmp_path), metadata)


def test_house_style_has_exactly_eight_bullets() -> None:
    body = _body(HOUSE_STYLE)
    assert len(_bullets(body)) == 8, _bullets(body)
    headings = [line for line in body.splitlines() if line.startswith("#")]
    assert headings == [], f"{HOUSE_STYLE} body has headings {headings}; the adapter adds one"


@pytest.mark.parametrize("phrase", D17_HOUSE_STYLE_PHRASES)
def test_house_style_keeps_the_d17_items(phrase: str) -> None:
    assert phrase in _body(HOUSE_STYLE), f"{HOUSE_STYLE} lost the D17 item {phrase!r}"


@pytest.mark.parametrize("phrase", ALWAYS_TIER_PHRASES)
def test_python_idioms_does_not_restate_the_always_tier(phrase: str) -> None:
    """The ``count_lines`` example keeps its ``encoding="utf-8"`` call; only prose is checked."""
    assert phrase not in _prose(_body(IDIOMS)), f"{IDIOMS} restates {phrase!r}"


def test_project_context_renders_exactly_two_reminders(tmp_path: Path) -> None:
    rendered = _render_project_context(tmp_path, "")
    bullets = _bullets(rendered)
    assert len(bullets) == 2, bullets
    assert bullets[0].startswith("- Ask before writing code"), bullets[0]
    assert bullets[1].startswith("- Report a problem"), bullets[1]
    assert rendered.lstrip("\n").startswith(
        "You are working on **demo** (project kind: `python-library`)."
    )


def test_project_context_renders_the_description_only_when_set(tmp_path: Path) -> None:
    """Regression for the ``{% if %}`` layout: one blank line either way, never two."""
    without = _render_project_context(tmp_path, "")
    with_description = _render_project_context(tmp_path, "A demo service.")
    assert "`python-library`).\n\n- Ask" in without, repr(without)
    assert "`python-library`).\n\nA demo service.\n\n- Ask" in with_description
    assert "\n\n\n" not in without and "\n\n\n" not in with_description


@pytest.mark.parametrize("phrase", CUT_REMINDERS)
def test_always_rules_drop_the_cut_reminders(phrase: str) -> None:
    holders = [rule_id for rule_id in ALWAYS_RULES if phrase in _body(rule_id)]
    assert holders == [], f"D17 cut {phrase!r}, but {holders} still say it"


@pytest.mark.parametrize("rule_id", ALWAYS_RULES)
def test_always_rule_bodies_name_no_skill(rule_id: str) -> None:
    """C7: only the generated map routes to skills, and it lists only skills that are written."""
    named = sorted(skill for skill in core_skill_ids() if skill in _body(rule_id))
    assert named == [], f"always rule {rule_id!r} names skills {named}"


@pytest.mark.parametrize(("phrase", "owner"), MOVED_ITEM_OWNERS)
def test_moved_house_style_item_has_one_owner(phrase: str, owner: str) -> None:
    assert phrase in _body(owner), f"{phrase!r} left {HOUSE_STYLE} but {owner} lacks it"
    assert phrase not in _body(HOUSE_STYLE), f"{phrase!r} is in both {HOUSE_STYLE} and {owner}"
