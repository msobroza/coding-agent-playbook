"""CI gates for the always rules in core and the text they handed off (D17; spec 6.8.13).

The always tier rides every turn, so it keeps only the project's identity, two
working agreements, eight code-legibility principles, seven house-style bullets
and the document layout (prU D61, D73). Everything else the old house
style said moved to one of two ``python-coding`` members, ``python-data-shapes``
and ``python-idioms`` (spec 6.5.4), and its class-design items later on to
``python-classes-and-protocols`` (spec 9.8); the one-owner table below is the
"nothing silently lost" regression for those moves.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

import pytest

import coding_agent_playbook
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.config.layout import resolve_layout
from coding_agent_playbook.rendering.session import RenderSession, TemplateContext
from tests._budget_probe import reference_probe_facts, render_core_rule
from tests._catalog import core_rules, core_skill_ids

if TYPE_CHECKING:
    from collections.abc import Sequence

    from coding_agent_playbook.detector.facts import Facts

pytestmark = pytest.mark.catalog

HOUSE_STYLE: Final = "python-house-style"
PROJECT_CONTEXT: Final = "project-context"
DATA_SHAPES: Final = "python-data-shapes"
IDIOMS: Final = "python-idioms"
CLASSES: Final = "python-classes-and-protocols"
LEGIBILITY: Final = "code-legibility"
DOCUMENT_LAYOUT: Final = "document-layout"
#: The always rules that route to no skill; code-legibility names one per line (D73).
ALWAYS_RULES: Final = (PROJECT_CONTEXT, HOUSE_STYLE, DOCUMENT_LAYOUT)

#: Phrases the seven house-style bullets must keep (D17; the layout axis moved, D73). The ``None`` and ``excepted`` clauses
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
    ("layout axis", LEGIBILITY),
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


def test_house_style_has_exactly_seven_bullets() -> None:
    body = _body(HOUSE_STYLE)
    assert len(_bullets(body)) == 7, _bullets(body)
    assert "seven" in core_rules()[HOUSE_STYLE].frontmatter.description
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


# --- code-legibility (prU D73) ------------------------------------------------------

#: Each D73 principle -> the ``skill -> rule`` pointer its line ends with.
LEGIBILITY_POINTERS: Final = (
    ("small", "python-coding", "python-small-units"),
    ("one reason to change", "design-patterns", "design-single-responsibility"),
    ("nesting", "python-coding", "python-early-return"),
    ("offending value", "python-coding", "python-error-messages-with-context"),
    ("searchable names", "python-coding", "python-meaningful-names"),
    ("one home", "design-patterns", "design-dry-yagni-kiss"),
    ("predictable", "python-architecture", "arch-predictable-project-tree"),
    ("F.I.R.S.T", "python-testing", "pytest-first-properties"),
)
#: Targets whose rule a wave 7 content lane still has to ship (prU tickets
#: C-python-coding-*, C-design-patterns-*, C-python-architecture-*, C-python-testing-*).
#: Until then ``rule_active`` hides its pointer, so the rule never names it. A lane that
#: ships one removes it here; the F-02 final-state check needs this empty.
PENDING_LEGIBILITY_TARGETS: Final = frozenset(
    {
        "python-small-units",
        "python-early-return",
        "python-error-messages-with-context",
        "design-single-responsibility",
        "design-dry-yagni-kiss",
        "arch-predictable-project-tree",
        "pytest-first-properties",
    }
)
#: A pointer renders only when ``rule_active`` resolves it, so none dangles (D73).
_GUARDED_POINTER: Final = re.compile(
    r"\{% if rule_active\('([a-z0-9-]+)'\) %\} \(`([a-z0-9-]+)` -> `([a-z0-9-]+)`\)\{% endif %\}\.$"
)
_POINTER: Final = re.compile(r" \(`([a-z0-9-]+)` -> `([a-z0-9-]+)`\)\.$")


def test_code_legibility_names_eight_principles_each_with_its_skill_and_rule() -> None:
    bullets = _bullets(_body(LEGIBILITY))
    assert len(bullets) == len(LEGIBILITY_POINTERS), bullets
    for bullet, (phrase, skill, rule) in zip(bullets, LEGIBILITY_POINTERS, strict=True):
        assert phrase in bullet, f"{phrase!r} not in {bullet!r}"
        match = _GUARDED_POINTER.search(bullet)
        assert match is not None and match.groups() == (rule, skill, rule), bullet


def _legibility_target(skill_id: str, rule_id: str) -> tuple[Skill, Rule]:
    """A plain skill (always rendered) and its one ungated member ``rule_id``."""
    skill = Skill(
        frontmatter={"id": skill_id, "name": skill_id, "description": "d"},
        body="b\n",
        scripts_dir=None,
        references_dir=None,
        source_package="coding_agent_playbook",
    )
    frontmatter = RuleFrontmatter(
        id=rule_id, name=rule_id, description="d", scope="scoped", globs=["**/*.py"], skill=skill_id
    )
    return skill, Rule(frontmatter, "r\n", "r\n", False, None, "coding_agent_playbook")


def _render_legibility(targets: Sequence[tuple[str, str]]) -> list[str]:
    """code-legibility's bullets as sync renders them when exactly ``targets`` ship."""
    pairs = [_legibility_target(skill, rule) for skill, rule in targets]
    context = TemplateContext(
        facts=cast("Facts", {}),
        project_name="demo",
        engine_version=coding_agent_playbook.__version__,
    )
    session = RenderSession.open(
        [rule for _, rule in pairs],
        context,
        repo_root=Path(),
        skills=[skill for skill, _ in pairs],
    )
    return _bullets(session.render_rule(core_rules()[LEGIBILITY]).body)


def test_code_legibility_renders_every_pointer_once_its_rule_ships() -> None:
    bullets = _render_legibility([(skill, rule) for _, skill, rule in LEGIBILITY_POINTERS])

    pointers = [_POINTER.search(bullet) for bullet in bullets]
    assert [m.groups() if m else None for m in pointers] == [
        (skill, rule) for _, skill, rule in LEGIBILITY_POINTERS
    ], bullets


def test_code_legibility_names_no_pointer_to_a_missing_rule() -> None:
    """D73 "the names never dangle": a target not yet shipped keeps its principle only."""
    bullets = _render_legibility([])

    assert len(bullets) == len(LEGIBILITY_POINTERS), bullets
    assert not any("->" in bullet for bullet in bullets), bullets
    assert all(bullet.endswith(".") for bullet in bullets), bullets


@pytest.mark.parametrize(("skill", "rule_id"), [(s, r) for _, s, r in LEGIBILITY_POINTERS])
def test_every_code_legibility_target_exists_ungated(skill: str, rule_id: str) -> None:
    rules = core_rules()
    if rule_id not in rules:
        assert rule_id in PENDING_LEGIBILITY_TARGETS, f"{LEGIBILITY} names missing rule {rule_id}"
        return
    assert rule_id not in PENDING_LEGIBILITY_TARGETS, (
        f"{rule_id} ships now: remove it from PENDING_LEGIBILITY_TARGETS"
    )
    frontmatter = rules[rule_id].frontmatter
    assert frontmatter.skill == skill, f"{rule_id} lives in {frontmatter.skill}, not {skill}"
    assert not frontmatter.applies_if, f"{rule_id} is gated by {frontmatter.applies_if}"


def test_code_legibility_follows_project_context() -> None:
    order = (PROJECT_CONTEXT, LEGIBILITY, HOUSE_STYLE, DOCUMENT_LAYOUT)
    priorities = {rule_id: core_rules()[rule_id].frontmatter.priority for rule_id in order}
    assert tuple(sorted(order, key=priorities.__getitem__)) == order, priorities


# --- document-layout (prU D60, D61, D71) -----------------------------------------------

_DEFAULT_LAYOUT_PATHS: Final = (
    "`CONTEXT.md`",
    "`docs/adr/NNNN-slug.md`",
    "`docs/specs/YYYY-MM-DD-<slug>.md`",
    "`docs/plans/YYYY-MM-DD-<slug>.md`",
    "`.scratch/`",
)


def _render_layout(tmp_path: Path, explicit: dict[str, str]) -> str:
    metadata = {**_DEMO_METADATA, "layout": resolve_layout(explicit)}
    return render_core_rule(DOCUMENT_LAYOUT, reference_probe_facts(tmp_path), metadata)


def test_document_layout_renders_the_d60_defaults(tmp_path: Path) -> None:
    rendered = _render_layout(tmp_path, {})

    missing = [path for path in _DEFAULT_LAYOUT_PATHS if path not in rendered]
    assert missing == [], rendered
    assert len(_bullets(rendered)) == 3, rendered


def test_document_layout_renders_the_configured_layout(tmp_path: Path) -> None:
    rendered = _render_layout(tmp_path, {"specs": "specs", "plans": "work/plans"})

    assert "`specs/YYYY-MM-DD-<slug>.md`" in rendered
    assert "`work/plans/YYYY-MM-DD-<slug>.md`" in rendered
    assert "docs/specs" not in rendered and "docs/plans" not in rendered


# --- project-context asks through the framework's clarify skill (prU D75) --------------

_FRAMEWORK: Final = "acme.framework"


def _clarify_skill(skill_id: str) -> Skill:
    return Skill(
        frontmatter={
            "id": skill_id,
            "name": skill_id,
            "description": "d",
            "capabilities": ["clarify"],
        },
        body="b\n",
        scripts_dir=None,
        references_dir=None,
        source_package=_FRAMEWORK,
    )


def _render_with_framework(clarify: str | None) -> str:
    """project-context as sync renders it with a framework whose clarify skill is ``clarify``."""
    skills = [] if clarify is None else [_clarify_skill(clarify)]
    context = TemplateContext(
        facts=cast("Facts", {}),
        project_name="demo",
        engine_version=coding_agent_playbook.__version__,
        overrides=dict(_DEMO_METADATA),
    )
    framework = None if clarify is None else _FRAMEWORK
    session = RenderSession.open((), context, repo_root=Path(), skills=skills, framework=framework)
    return session.render_rule(core_rules()[PROJECT_CONTEXT]).body


@pytest.mark.parametrize("clarify", ["grill-me", "brainstorming"])
def test_project_context_asks_through_the_framework_clarify_skill(clarify: str) -> None:
    ask = _bullets(_render_with_framework(clarify))[0]

    assert f"use the {clarify} skill" in ask, ask


def test_project_context_ask_line_is_unchanged_without_a_framework() -> None:
    ask = _bullets(_render_with_framework(None))[0]

    assert ask == (
        "- Ask before writing code when the scope or the approach is unclear: "
        "a short question costs less than the wrong change."
    )
