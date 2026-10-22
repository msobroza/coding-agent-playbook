"""CI gates for the core skills that deliver the scoped rules in core (D4, D13; spec 6.8.12).

Core ships one skill per topic, and every scoped rule in core names the one that
owns it (ADR 0001). Each core skill's pins live in its own module under
``tests/core_skill_pins/`` (prU L0-03), so content lanes extend them in
parallel. Core also ships one plain skill, ``playbook-guardrails``, which takes
no member rules: sync composes it from the on hooks' guardrail text (D6), so it
has no ``playbook:`` block and its authored description carries its own "Use when".
The D13 static checks (description shape, 500 lines, references one level deep,
plain markdown) and the directory gates of ``tests/_core_skill_layout.py`` (a
core skill holds rules/, references/, scripts/ and examples/, and its links stay
inside it; prU L0-13) cover the core skills only: bundled plugin skills are exempt
(D24) because their vendored or distilled descriptions and bodies fail them as
written, and rewording vendored text would change upstream wording. The
skill-listing budget in ``test_context_budget.py`` still counts every plugin.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.adapters.claude_code.paths import CLAUDE_RULES_PATH
from coding_agent_playbook.adapters.skill_dirs.writer import render_skill_md
from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from coding_agent_playbook.catalog.roots import ENGINE_PACKAGE
from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.hooks.guardrails_skill import (
    GUARDRAILS_SKILL_ID,
    compose_guardrails_skill,
)
from coding_agent_playbook.skills.document import DESCRIPTION_MAX_CHARS
from coding_agent_playbook.skills.membership import compose_skills, member_rules_of
from coding_agent_playbook.skills.naming import agent_skill_issues
from tests._budget_probe import reference_probe_facts, render_core_rule
from tests._catalog import CORE_ROOT, core_rule_paths, core_rule_skill_ids, core_rules
from tests._core_skill_layout import (
    NOT_THIRD_PERSON,
    description_problems,
    inventory_problems,
    link_problems,
    nesting_problems,
    plain_markdown_problems,
)
from tests.core_skill_pins import (
    ALL_PINS,
    DOMINO_SKILL_IDS,
    PLAIN_CORE_SKILL_IDS,
    CoreSkillPins,
)
from tests.hook_runtime.handlers.pack_repo import engine_hook, engine_hook_paths
from tests.hook_samples import resolved_hook
from tests.plugins.superpowers_expectations import NATIVE_SKILL_ROOTS

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill
    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook

pytestmark = pytest.mark.catalog

#: Every core skill with member rules, one pins module each under ``tests/core_skill_pins/``.
PINS_BY_SKILL: Final[Mapping[str, CoreSkillPins]] = {pins.skill_id: pins for pins in ALL_PINS}
#: Scoped rule in core -> the core skill whose rules/ delivers it, from the pins modules.
MEMBERSHIP_FROM_PINS: Final[Mapping[str, str]] = {
    rule_id: pins.skill_id for pins in ALL_PINS for rule_id in pins.members
}
#: Core skill with member rules -> its ``playbook.files`` phrase in "Where guidance lives".
WHERE_FROM_PINS: Final[Mapping[str, str]] = {pins.skill_id: pins.where for pins in ALL_PINS}
CORE_SKILLS: Final = sorted(PINS_BY_SKILL)
#: Core skills checked on the reference probe, and on the Domino probe (prU D59, D63).
REFERENCE_PROBE_SKILLS: Final = sorted(set(PINS_BY_SKILL) - DOMINO_SKILL_IDS)
DOMINO_PROBE_SKILLS: Final = sorted(DOMINO_SKILL_IDS)
#: Core members whose gate the reference probe fails (spec 9.6.2): a reference-probe
#: skill's ``probe_inactive`` and every member of a Domino-probe skill.
PROBE_INACTIVE_MEMBERS: Final = frozenset().union(
    *(p.probe_inactive if p.probe == "reference" else p.members for p in ALL_PINS)
)
EVERY_CORE_SKILL: Final = sorted({*CORE_SKILLS, *PLAIN_CORE_SKILL_IDS})
#: (skill id, rule id) of every rule a pins module pins the frontmatter of.
PINNED_RULES: Final = sorted((p.skill_id, rule_id) for p in ALL_PINS for rule_id in p.rules)
SKILLS_ROOT: Final = CORE_ROOT / "skills"
_TRUNCATION_TAIL: Final = re.compile(r"and \d+ more")
#: A ``playbook-guardrails`` section heading, ``## <name> (`<id>`)``; group 1 is the hook id.
_GUARDRAIL_SECTION: Final = re.compile(r"^## .+ \(`([^`]+)`\)$", re.MULTILINE)
#: Continue's advisory rule file name, ``30-guardrail-<hook id>.md``, before the hook id.
_CONTINUE_GUARDRAIL_PREFIX: Final = "30-guardrail-"


def _skill_md_text(skill_id: str) -> str:
    """The authored ``SKILL.md`` of core skill ``skill_id``, as text."""
    return (SKILLS_ROOT / skill_id / "SKILL.md").read_text(encoding="utf-8")


def _authored(skill_id: str) -> tuple[dict[str, object], str]:
    """The authored ``SKILL.md`` of core skill ``skill_id``: (frontmatter, body)."""
    return split_frontmatter(_skill_md_text(skill_id))


def _loaded_skill(skill_id: str, tmp_path: Path) -> Skill:
    """Core skill ``skill_id`` as the engine's artifact source loads it."""
    skills = FileSystemArtifactSource(repo_root=tmp_path).list_skills()
    engine = {s.frontmatter.get("id"): s for s in skills if s.source_package == ENGINE_PACKAGE}
    return engine[skill_id]


def _members(skill_id: str) -> list[Rule]:
    """Every rule in core naming ``skill_id``, merged and before ``applies_if``."""
    return [rule for rule in core_rules().values() if rule.frontmatter.skill == skill_id]


def _probe_members(skill_id: str) -> list[Rule]:
    """The members of ``skill_id`` its own probe (``CoreSkillPins.probe``) activates."""
    inactive = PINS_BY_SKILL[skill_id].probe_inactive
    return [r for r in _members(skill_id) if r.frontmatter.id not in inactive]


def _is_core_member_rule(path: str, subdir: str = "rules") -> bool:
    """Whether repo-relative ``path`` is ``<root>/<core skill>/<subdir>/<file>``."""
    parts = path.split("/")
    return len(parts) >= 3 and parts[-2] == subdir and parts[-3] in WHERE_FROM_PINS


def _probe_skill_md(repo: Path, skill_id: str) -> str:
    """The probe's emitted ``.claude/skills/<skill_id>/SKILL.md``."""
    return (repo / ".claude" / "skills" / skill_id / "SKILL.md").read_text(encoding="utf-8")


def _continue_guardrail_hook_ids(repo: Path) -> list[str]:
    """The hook ids of ``repo``'s ``.continue/rules/30-guardrail-<id>.md`` files, sorted."""
    rules = (repo / ".continue" / "rules").glob(f"{_CONTINUE_GUARDRAIL_PREFIX}*.md")
    return sorted(p.stem.removeprefix(_CONTINUE_GUARDRAIL_PREFIX) for p in rules)


def test_core_ships_exactly_the_d4_skills() -> None:
    """An inventory pin: a later PR adding a skill updates the pins modules."""
    assert sorted(p.name for p in SKILLS_ROOT.iterdir()) == EVERY_CORE_SKILL


@pytest.mark.parametrize("skill_id", EVERY_CORE_SKILL)
def test_core_skill_holds_only_rules_references_scripts_and_examples(skill_id: str) -> None:
    """prU L0-13 (D2, D19, D25, D48): SKILL.md plus rules/, references/, scripts/, examples/.

    rules/ holds only rule files, references/ only .md files and the two license
    copies, one level deep, and scripts/ only .py files (tests/_core_skill_layout.py).
    """
    assert inventory_problems(SKILLS_ROOT / skill_id) == [], skill_id


@pytest.mark.parametrize("skill_id", EVERY_CORE_SKILL)
def test_core_skill_links_stay_inside_the_skill(skill_id: str) -> None:
    """Every relative link in SKILL.md or a rule resolves inside the same skill dir.

    SKILL.md may link only its own references/<file>.md; a rule may link
    ../references/<file>.md (prU L0-13). A link into another skill names its path.
    """
    assert link_problems(SKILLS_ROOT / skill_id) == [], skill_id


def test_core_rules_dir_holds_only_always_rules() -> None:
    """prU L0-07 (D21, D36): core-layer scoped rules live in their skill's rules/.

    Read from disk, so adding an always rule to core edits no pin here.
    """
    files = [path for path in (CORE_ROOT / "rules").rglob("*") if path.is_file()]
    assert files
    for path in files:
        assert path.relative_to(CORE_ROOT / "rules").parts[0] == "always", path
        front, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        assert front["scope"] == "always", path


def test_core_in_skill_rules_declare_no_skill() -> None:
    """prU L0-07: the directory sets membership, so a moved rule drops its 'skill:' line.

    R1 allows a line naming the home skill; core keeps none. The file name is
    R2's, checked on the real catalog by the validate no-finding test.
    """
    for home, path in core_rule_paths():
        if home is None:
            continue
        front, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        assert "skill" not in front, f"{path} declares 'skill: {front['skill']}'"


@pytest.mark.parametrize("skill_id", CORE_SKILLS)
def test_core_skill_identity_and_description_shape(skill_id: str) -> None:
    """The D13 description lint, over core skills only.

    Plugin skills are exempt (D24): their vendored or distilled descriptions fail
    it as written (most superpowers descriptions open with "Use when").
    """
    assert description_problems(SKILLS_ROOT / skill_id) == [], skill_id


@pytest.mark.parametrize("skill_id", sorted(PLAIN_CORE_SKILL_IDS))
def test_plain_core_skill_identity_and_description_shape(skill_id: str) -> None:
    """The D13 description lint for a core skill without members (spec 8.4.3, H15).

    No ``playbook:`` block, so the engine composes nothing: the authored
    description is emitted as is and carries its one "Use when" clause itself.
    """
    frontmatter, _ = _authored(skill_id)
    identity = (frontmatter.get("id"), frontmatter.get("name"))
    assert identity == (skill_id, skill_id), f"core skill {skill_id!r}: (id, name) is {identity}"
    assert "playbook" not in frontmatter, f"core skill {skill_id!r} takes no member rules"
    description = str(frontmatter.get("description"))
    shaped = not NOT_THIRD_PERSON.match(description) and description.endswith(".")
    assert shaped and description.count(" Use when ") == 1, (
        f"core skill {skill_id!r}: description {description!r} must be third person, end "
        "with '.', and carry exactly one ' Use when ' clause"
    )
    assert len(description) <= DESCRIPTION_MAX_CHARS, f"{skill_id}: {len(description)} chars"


@pytest.mark.parametrize("skill_id", CORE_SKILLS)
def test_core_skill_declares_where_phrase(skill_id: str) -> None:
    block = _authored(skill_id)[0].get("playbook")
    files = block.get("files") if isinstance(block, dict) else None
    assert files == WHERE_FROM_PINS[skill_id], (
        f"core skill {skill_id!r} needs playbook.files {WHERE_FROM_PINS[skill_id]!r}, got {files!r}"
    )
    assert 1 <= len(files) <= 80 and not files.endswith(".")


@pytest.mark.parametrize("skill_id", EVERY_CORE_SKILL)
def test_core_skill_md_is_plain_markdown(skill_id: str) -> None:
    """The D13 body hygiene (no Jinja, URLs or rule ids), over core skills only.

    Plugin skills are exempt (D24): they take no member rules, and vendored text
    keeps its upstream wording.
    """
    # Links to its own references/*.md are allowed; test_core_skill_links_stay_inside_the_skill
    # checks them (prU L0-13).
    assert plain_markdown_problems(SKILLS_ROOT / skill_id) == [], skill_id
    # The description may say "pytest" (also a rule id); only the body must not name ids.
    body, rule_ids = _authored(skill_id)[1], sorted(core_rules())
    for number, line in enumerate(body.splitlines(), start=1):
        for rule_id in rule_ids:
            assert not re.search(rf"(?<![\w-]){re.escape(rule_id)}(?![\w-])", line), (
                f"core skill {skill_id!r}: SKILL.md body line {number} names rule id "
                f"{rule_id!r}; bodies name topics, the generated index names ids"
            )


@pytest.mark.parametrize("skill_id", CORE_SKILLS)
def test_core_skill_md_within_500_lines_with_every_member(skill_id: str, tmp_path: Path) -> None:
    """The D13 500-line limit, composed with every member, over core skills only.

    Plugin skills are exempt (D24): two vendored superpowers skills have 569 and
    682 lines, and shortening them would change upstream text.
    """
    facts = reference_probe_facts(tmp_path)
    members = _members(skill_id)
    rendered = [replace(r, body=render_core_rule(r.frontmatter.id, facts)) for r in members]
    (composed,) = compose_skills([_loaded_skill(skill_id, tmp_path)], members, rendered)
    lines = render_skill_md(composed).count("\n")
    assert lines <= 500, f"core skill {skill_id!r}: SKILL.md is {lines} lines; the limit is 500"


def _every_core_guardrail() -> list[ResolvedHook]:
    """Every core hook with a body, ungated, as a hook whose guardrail text is that body."""
    hooks = (engine_hook(hook_id) for hook_id in engine_hook_paths())
    return [
        resolved_hook(hook.frontmatter.id, name=hook.frontmatter.name, body=hook.body)
        for hook in hooks
        if hook.body.strip()
    ]


def test_guardrails_skill_md_within_500_lines_with_every_core_hook(tmp_path: Path) -> None:
    """The D13 500-line limit for ``playbook-guardrails``, every opt-in hook on too (8.4.3)."""
    hooks = _every_core_guardrail()
    composed = compose_guardrails_skill(_loaded_skill(GUARDRAILS_SKILL_ID, tmp_path), hooks)
    assert composed is not None
    text = render_skill_md(composed)
    assert text.count("\n## ") == len(hooks), "one section per core hook with a body"
    lines = text.count("\n")
    assert lines <= 500, f"playbook-guardrails is {lines} lines with every core hook; limit 500"


@pytest.mark.parametrize("skill_id", EVERY_CORE_SKILL)
def test_core_skill_references_are_one_level_deep(skill_id: str) -> None:
    """The D13 one-level reference check, over core skills only.

    No directory under references/, and no SKILL.md, rule or reference text
    naming one; a drawn skill tree's bare ``references/`` passes (D78(16)).
    Plugin skills are exempt (D24): their references are vendored as written.
    """
    assert nesting_problems(SKILLS_ROOT / skill_id) == [], skill_id


@pytest.mark.parametrize("skill_id", EVERY_CORE_SKILL)
def test_core_skills_pass_agent_skill_issues(skill_id: str, tmp_path: Path) -> None:
    assert agent_skill_issues(_loaded_skill(skill_id, tmp_path)) == []


@pytest.mark.parametrize("rule_id", sorted(MEMBERSHIP_FROM_PINS))
def test_scoped_core_rule_names_its_skill(rule_id: str) -> None:
    skill = core_rules()[rule_id].frontmatter.skill
    assert skill == MEMBERSHIP_FROM_PINS[rule_id], (
        f"core rule {rule_id!r} names skill {skill!r}; tests/core_skill_pins expects "
        f"{MEMBERSHIP_FROM_PINS[rule_id]!r} (scoped rules in core must name one of: "
        f"{', '.join(CORE_SKILLS)})"
    )


def test_each_scoped_core_rule_is_pinned_by_exactly_its_skill() -> None:
    """Regression: a scoped rule in core appears in exactly one pins module, its skill's."""
    rules = core_rules()
    scoped = sorted(rule_id for rule_id, r in rules.items() if r.frontmatter.scope == "scoped")
    for rule_id in scoped:
        owners = [pins.skill_id for pins in ALL_PINS if rule_id in pins.members]
        assert owners == [rules[rule_id].frontmatter.skill], (
            f"scoped core rule {rule_id!r} is pinned by {owners}; expected only the pins "
            f"module of its skill {rules[rule_id].frontmatter.skill!r}"
        )
    pinned = [rule_id for pins in ALL_PINS for rule_id in pins.members]
    extra = sorted(set(pinned) - set(scoped))
    assert not extra, f"pins name rules that are not scoped core rules: {extra}"
    dupes = sorted({rule_id for rule_id in pinned if pinned.count(rule_id) > 1})
    assert not dupes, f"pins list these member rules more than once: {dupes}"


@pytest.mark.parametrize("pins", ALL_PINS, ids=lambda pins: pins.skill_id)
def test_core_skill_members_in_index_order(pins: CoreSkillPins) -> None:
    """Spec 9.6.2: each skill's members, in the order its rules index lists them."""
    members = [
        rule.frontmatter.id for rule in member_rules_of(pins.skill_id, list(core_rules().values()))
    ]
    assert tuple(members) == pins.members, (
        f"{pins.skill_id} members are {members}; expected {list(pins.members)}"
    )


@pytest.mark.parametrize(("skill_id", "rule_id"), PINNED_RULES)
def test_pinned_rule_frontmatter(skill_id: str, rule_id: str) -> None:
    """Spec 9.4.1 / 9.6.1: the pinned frontmatter; distilled rules have no ``lint_codes`` (D23)."""
    pin, front = PINS_BY_SKILL[skill_id].rules[rule_id], core_rules()[rule_id].frontmatter
    actual = (front.skill, front.scope, front.version, front.name, tuple(front.globs))
    assert actual == (skill_id, "scoped", pin.version, pin.name, pin.globs), f"{rule_id}: {actual}"
    assert (front.applies_if, front.priority) == (pin.applies_if, pin.priority), rule_id
    assert tuple(front.tags) == pin.tags, f"{rule_id}: tags {front.tags}"
    assert front.lint_codes == pin.lint_codes, f"{rule_id} carries lint_codes {front.lint_codes}"
    assert front.section == pin.section, (
        f"{rule_id}: section {front.section!r}; expected {pin.section!r}"
    )
    assert front.description.endswith("."), f"{rule_id}: one-sentence description"


@pytest.mark.parametrize("pins", ALL_PINS, ids=lambda pins: pins.skill_id)
def test_pinned_rules_are_members_and_probe_inactive_are_members(pins: CoreSkillPins) -> None:
    stray = sorted((set(pins.rules) | pins.probe_inactive) - set(pins.members))
    assert not stray, f"{pins.skill_id} pins non-members {stray}"


def test_always_core_rules_name_no_skill() -> None:
    always = {
        i: r.frontmatter.skill for i, r in core_rules().items() if r.frontmatter.scope == "always"
    }
    assert always == {
        "project-context": None,
        "code-legibility": None,
        "python-house-style": None,
        "document-layout": None,
    }


def test_every_core_member_skill_has_a_core_member() -> None:
    assert set(MEMBERSHIP_FROM_PINS.values()) == set(WHERE_FROM_PINS)


def test_pins_modules_cover_exactly_the_core_skills_with_a_playbook_block() -> None:
    assert core_rule_skill_ids() == CORE_SKILLS, "one tests/core_skill_pins module per such skill"


@pytest.mark.parametrize("skill_id", REFERENCE_PROBE_SKILLS)
def test_reference_probe_emits_each_core_skill_within_budget(
    reference_probe_repo: Path, skill_id: str
) -> None:
    _assert_emitted_within_budget(reference_probe_repo, skill_id)


@pytest.mark.parametrize("skill_id", DOMINO_PROBE_SKILLS)
def test_domino_probe_emits_each_domino_skill_within_budget(
    domino_probe_repo: Path, skill_id: str
) -> None:
    """prU D63: the Domino skills are checked on the probe that activates them."""
    _assert_emitted_within_budget(domino_probe_repo, skill_id)


def _assert_emitted_within_budget(repo: Path, skill_id: str) -> None:
    """``repo``'s emitted ``skill_id``: description shape and budget, index of its probe members."""
    frontmatter, body = split_frontmatter(_probe_skill_md(repo, skill_id))
    authored = _authored(skill_id)[0]
    block = authored["playbook"]
    assert isinstance(block, dict)
    description = str(frontmatter["description"])
    assert len(description) <= 300, f"{skill_id}: {len(description)} chars"
    assert description.startswith(str(authored["description"]))
    # The generated clause follows the authored sentence: "<sentence> Covers <names>."
    assert description.startswith(f"{authored['description']} Covers "), description
    assert description.count(" Covers ") == 1, description
    assert description.endswith(f"Use when {block['use_when']}.")
    assert description.count(" Use when ") == 1
    assert not _TRUNCATION_TAIL.search(description), f"{skill_id} truncates: {description!r}"
    members = _probe_members(skill_id)
    if block.get("sections"):
        # A sectioned skill's Covers clause names its active sections, not its members (D17).
        covers = description.partition(" Covers ")[2].partition(". Use when ")[0].lower()
        # Only declared sections are named: a member in D42's Other adds no name. A title
        # may hold commas ("Names, types, docs"), so each title is looked up, not counted.
        declared = {section["id"] for section in block["sections"]}
        active = {rule.frontmatter.section for rule in members} & declared
        named = {s["id"] for s in block["sections"] if str(s["title"]).lower() in covers}
        assert named == active, f"{skill_id} covers {covers!r}"
    else:
        for rule in members:
            name = rule.frontmatter.name
            assert name in description, f"{skill_id} omits {name!r}"
    assert sorted(frontmatter) == ["description", "id", "name"]
    index = body.partition("## Rules\n")[2].partition("## References and examples")[0]
    # A flat index lists one "- [" line per member, a sectioned one one "| [" table row.
    lines = [line for line in index.splitlines() if line.startswith(("- [", "| ["))]
    assert len(lines) == len(members), f"{skill_id} index: {lines}"


def test_reference_probe_where_section_lists_every_core_skill(reference_probe_repo: Path) -> None:
    _assert_where_section_lists(reference_probe_repo, REFERENCE_PROBE_SKILLS)


def test_domino_probe_where_section_lists_every_core_skill(domino_probe_repo: Path) -> None:
    """prU D63: the Domino probe is the reference probe plus markers, so it lists them all."""
    _assert_where_section_lists(domino_probe_repo, CORE_SKILLS)


def _assert_where_section_lists(repo: Path, skill_ids: list[str]) -> None:
    for relative in ("AGENTS.md", CLAUDE_RULES_PATH):
        text = (repo / relative).read_text(encoding="utf-8")
        assert text.count("## Where guidance lives") == 1, relative
        for skill_id in skill_ids:
            files = WHERE_FROM_PINS[skill_id]
            assert f"- {files}: skill `{skill_id}`" in text, f"{relative} lacks {skill_id}"
        assert "Lint feedback names a rule id" in text, relative


def test_reference_probe_writes_the_guardrails_skill_to_opencode_and_agents_roots_only(
    reference_probe_repo: Path,
) -> None:
    """D6: Claude Code runs every probe hook natively, so its skill listing pays for nothing."""
    relative = f"{GUARDRAILS_SKILL_ID}/SKILL.md"
    copies = [reference_probe_repo / root / relative for root in NATIVE_SKILL_ROOTS[1:]]
    assert copies[0].read_bytes() == copies[1].read_bytes(), "the copies must be byte-identical"
    assert not (reference_probe_repo / NATIVE_SKILL_ROOTS[0] / GUARDRAILS_SKILL_ID).exists()
    prompt = reference_probe_repo / ".continue" / "prompts" / f"{GUARDRAILS_SKILL_ID}.md"
    assert not prompt.exists(), "Continue keeps its 30-guardrail rule files instead"
    frontmatter, body = split_frontmatter(copies[0].read_text(encoding="utf-8"))
    assert frontmatter == _authored(GUARDRAILS_SKILL_ID)[0]
    # Counted against Continue's rule files, which D6 keeps as they are, not against
    # AGENTS.md's Guardrails section, which holds one line per hook (D6).
    advised = _continue_guardrail_hook_ids(reference_probe_repo)
    assert advised, "the probe enables continue, so each on hook with an advisory has a file"
    assert _GUARDRAIL_SECTION.findall(body) == advised, "one skill section per advised hook"
    assert body.count("\n## ") == len(advised), "no section beyond the advised hooks"


def test_reference_probe_member_reference_is_byte_identical_in_every_skill_root(
    reference_probe_repo: Path,
) -> None:
    relative = "python-coding/rules/python-typing.md"
    copies = {
        root: (reference_probe_repo / root / relative).read_bytes() for root in NATIVE_SKILL_ROOTS
    }
    assert len(set(copies.values())) == 1, sorted(copies)


def test_reference_probe_lockfile_records_member_references_as_rules(
    reference_probe_repo: Path,
) -> None:
    """E9: ``kind = "rule"`` and the rule id, so guard-generated-outputs names the real source."""
    lockfile = FileSystemStateSource(repo_root=reference_probe_repo).load_lockfile()
    assert lockfile is not None
    rows = {
        entry.path: (entry.kind, entry.artifact_id)
        for entry in lockfile.entries
        if _is_core_member_rule(entry.path)
    }
    expected = {
        f"{root}/{skill_id}/rules/{rule_id}.md": ("rule", rule_id)
        for root in NATIVE_SKILL_ROOTS
        for rule_id, skill_id in MEMBERSHIP_FROM_PINS.items()
        if rule_id not in PROBE_INACTIVE_MEMBERS
    }
    assert rows == expected
    # prU D5: no member is written under references/ any more.
    assert not [e.path for e in lockfile.entries if _is_core_member_rule(e.path, "references")]


def test_reference_probe_writes_no_continue_prompt_for_a_member_skill(
    reference_probe_repo: Path,
) -> None:
    """Regression for E4: a skill with member rules is never degraded to a Continue prompt."""
    prompts = reference_probe_repo / ".continue" / "prompts"
    assert prompts.is_dir(), "the probe enables continue, so plugin skills are degraded there"
    assert [s for s in CORE_SKILLS if (prompts / f"{s}.md").exists()] == []


@pytest.mark.parametrize("file_name", ["60-python-data-shapes.md", "72-python-idioms.md"])
def test_reference_probe_continue_gets_the_two_new_rule_files(
    reference_probe_repo: Path, file_name: str
) -> None:
    """Continue keeps one rule file per rule, so the two new members get theirs (D11)."""
    target = reference_probe_repo / ".continue" / "rules" / file_name
    assert target.is_file(), f"the probe enables continue but wrote no {target.name}"
    # The file opens with the AUTOGENERATED sentinel line, then the frontmatter fence.
    sentinel, _, rest = target.read_text(encoding="utf-8").partition("\n")
    assert "AUTOGENERATED" in sentinel, sentinel
    frontmatter, _ = split_frontmatter(rest)
    assert frontmatter.get("alwaysApply") is False, frontmatter
    assert frontmatter.get("globs") == ["**/*.py"], frontmatter
