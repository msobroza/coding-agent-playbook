"""CI gates for the core skills that deliver the scoped rules in core (D4, D13; spec 6.8.12).

Core ships one skill per topic, and every scoped rule in core names the one that
owns it (ADR 0001). The two tables below are the contract later content PRs
extend. The D13 static checks (description shape, 500 lines, references one
level deep, plain markdown) cover the core skills only: bundled plugin skills are
exempt (D24) because their vendored or distilled descriptions and bodies fail them
as written, and rewording vendored text would change upstream wording. The
skill-listing budget in ``test_context_budget.py`` still counts every plugin.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.adapters._skill_writer import agent_skill_issues, render_skill_md
from coding_agent_playbook.adapters.claude_rule_paths import CLAUDE_RULES_PATH
from coding_agent_playbook.catalog import ENGINE_PACKAGE
from coding_agent_playbook.links import extract_markdown_links
from coding_agent_playbook.skill_membership import compose_skills
from coding_agent_playbook.sources.filesystem import FileSystemArtifactSource, FileSystemStateSource
from coding_agent_playbook.types import split_frontmatter
from tests._budget_probe import reference_probe_facts, render_core_rule
from tests._catalog import CORE_ROOT, core_rules
from tests.plugins.superpowers_expectations import NATIVE_SKILL_ROOTS

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from coding_agent_playbook.types import Rule, Skill

pytestmark = pytest.mark.catalog

#: Scoped rule in core -> the core skill whose references deliver it.
EXPECTED_MEMBERSHIP: Final[Mapping[str, str]] = {
    "python-dependency-injection": "python-coding",
    "python-pure-core": "python-coding",
    "python-data-shapes": "python-coding",
    "python-typing": "python-coding",
    "python-performance-idioms": "python-coding",
    "python-async": "python-coding",
    "python-classes-and-protocols": "python-coding",
    "python-error-handling": "python-coding",
    "python-context-managers": "python-coding",
    "python-docstrings": "python-coding",
    "python-retries-and-timeouts": "python-coding",
    "python-idioms": "python-coding",
    "pytest": "python-testing",
    "pytest-test-doubles": "python-testing",
    "pytest-fixtures": "python-testing",
    "python-static-checks": "python-tooling",
    "pytest-configuration": "python-tooling",
    "python-uv-workflow": "python-tooling",
    "fastapi-app-wiring": "python-tooling",
    "fastapi-error-boundaries": "python-tooling",
    "pydantic-boundaries": "python-tooling",
    "ml-serialization-security": "ml-data",
}
#: Core skill with member rules -> its ``playbook.files`` phrase in "Where guidance lives".
EXPECTED_WHERE: Final[Mapping[str, str]] = {
    "python-coding": "Any Python file",
    "python-testing": "Test files and conftest.py",
    "python-tooling": "Tool configuration and framework wiring",
    "ml-data": "Code that loads or saves models, checkpoints or caches",
}
CORE_SKILLS: Final = sorted(EXPECTED_WHERE)
#: Core members whose gate the reference probe fails: it has no uv.lock (spec 9.6.2).
PROBE_INACTIVE_MEMBERS: Final = frozenset({"python-uv-workflow"})
#: python-coding's member count after the python-best-practices distillation (spec 9.6.2, H13).
PYTHON_CODING_MEMBER_COUNT: Final = 12
#: python-testing's members after the pytest distillation (spec 9.6.2): pytest plus two.
PYTHON_TESTING_MEMBERS: Final = ("pytest", "pytest-fixtures", "pytest-test-doubles")
#: python-tooling's members (spec 9.6.2): the two FastAPI rules plus four distilled ones.
PYTHON_TOOLING_MEMBERS: Final = (
    "fastapi-app-wiring",
    "fastapi-error-boundaries",
    "pydantic-boundaries",
    "pytest-configuration",
    "python-static-checks",
    "python-uv-workflow",
)


@dataclass(frozen=True)
class DistilledRuleRow:
    """One row of spec 9.6.1: a distilled rule's file, skill, label, gate and priority."""

    path: str
    skill: str
    name: str
    globs: tuple[str, ...]
    applies_if: Mapping[str, object]
    priority: int
    tags: tuple[str, ...]


_PY_FILES: Final = ("**/*.py",)
_TEST_FILES: Final = ("tests/**/*.py", "**/conftest.py")
_PYTEST_GATE: Final[Mapping[str, object]] = {"has_framework": ["pytest"]}
#: Distilled rule id -> its spec 9.6.1 row; ``path`` is relative to ``catalog/core/rules``.
DISTILLED_RULES: Final[Mapping[str, DistilledRuleRow]] = {
    "python-performance-idioms": DistilledRuleRow(
        "languages/python/performance-idioms.md",
        "python-coding",
        "Performance idioms",
        _PY_FILES,
        {},
        51,
        ("python", "performance"),
    ),
    "python-async": DistilledRuleRow(
        "languages/python/async.md",
        "python-coding",
        "Asyncio",
        _PY_FILES,
        {"python_version": ">=3.11"},
        53,
        ("python", "async", "concurrency"),
    ),
    "python-classes-and-protocols": DistilledRuleRow(
        "languages/python/classes-and-protocols.md",
        "python-coding",
        "Classes and protocols",
        _PY_FILES,
        {},
        53,
        ("python", "design", "oop"),
    ),
    "pytest-test-doubles": DistilledRuleRow(
        "frameworks/pytest-test-doubles.md",
        "python-testing",
        "pytest test doubles",
        _TEST_FILES,
        _PYTEST_GATE,
        61,
        ("python", "testing", "pytest", "mocking"),
    ),
    "pytest-fixtures": DistilledRuleRow(
        "frameworks/pytest-fixtures.md",
        "python-testing",
        "pytest fixtures",
        _TEST_FILES,
        _PYTEST_GATE,
        63,
        ("python", "testing", "pytest", "fixtures"),
    ),
    "python-static-checks": DistilledRuleRow(
        "languages/python/static-checks.md",
        "python-tooling",
        "Static checks",
        ("**/*.py", "pyproject.toml", "ruff.toml", ".ruff.toml", "mypy.ini", ".mypy.ini"),
        {},
        21,
        ("python", "tooling", "ruff", "mypy"),
    ),
    "pytest-configuration": DistilledRuleRow(
        "frameworks/pytest-configuration.md",
        "python-tooling",
        "pytest configuration",
        ("pyproject.toml", "pytest.ini", "tox.ini", "setup.cfg", "**/conftest.py"),
        _PYTEST_GATE,
        23,
        ("python", "tooling", "pytest"),
    ),
    "python-uv-workflow": DistilledRuleRow(
        "languages/python/uv-workflow.md",
        "python-tooling",
        "uv workflow",
        ("pyproject.toml",),
        {"package_manager": "uv"},
        28,
        ("python", "tooling", "uv"),
    ),
    "pydantic-boundaries": DistilledRuleRow(
        "frameworks/pydantic-boundaries.md",
        "python-tooling",
        "Pydantic boundaries",
        _PY_FILES,
        {"has_framework": ["pydantic"]},
        63,
        ("python", "pydantic", "validation"),
    ),
}
SKILLS_ROOT: Final = CORE_ROOT / "skills"
#: The python_design plugin's third-person regex, extended with "use" (a "Use when" opener).
_NOT_THIRD_PERSON: Final = re.compile(r"(?i)(i|you|we|use)\b")
_URL: Final = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://|\bwww\.")
_TRUNCATION_TAIL: Final = re.compile(r"and \d+ more")


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
    """The members of ``skill_id`` the reference probe activates."""
    return [r for r in _members(skill_id) if r.frontmatter.id not in PROBE_INACTIVE_MEMBERS]


def _is_core_member_reference(path: str) -> bool:
    """Whether repo-relative ``path`` is ``<root>/<core skill>/references/<file>``."""
    parts = path.split("/")
    return len(parts) >= 3 and parts[-2] == "references" and parts[-3] in EXPECTED_WHERE


def _probe_skill_md(repo: Path, skill_id: str) -> str:
    """The probe's emitted ``.claude/skills/<skill_id>/SKILL.md``."""
    return (repo / ".claude" / "skills" / skill_id / "SKILL.md").read_text(encoding="utf-8")


def test_core_ships_exactly_the_d4_skills() -> None:
    """An inventory pin: a later PR adding a hand-written reference or a skill updates it."""
    assert sorted(p.name for p in SKILLS_ROOT.iterdir()) == CORE_SKILLS
    for skill_id in CORE_SKILLS:
        entries = sorted(p.name for p in (SKILLS_ROOT / skill_id).iterdir())
        assert entries == ["SKILL.md"], f"core skill {skill_id!r} holds {entries}"


@pytest.mark.parametrize("skill_id", CORE_SKILLS)
def test_core_skill_identity_and_description_shape(skill_id: str) -> None:
    """The D13 description lint, over core skills only.

    Plugin skills are exempt (D24): their vendored or distilled descriptions fail
    it as written (most superpowers descriptions open with "Use when").
    """
    frontmatter, _ = _authored(skill_id)
    identity = (frontmatter.get("id"), frontmatter.get("name"))
    assert identity == (skill_id, skill_id), f"core skill {skill_id!r}: (id, name) is {identity}"
    description = str(frontmatter.get("description"))
    shaped = not _NOT_THIRD_PERSON.match(description) and description.endswith(".")
    assert shaped and "use when" not in description.lower(), (
        f"core skill {skill_id!r}: description {description!r} must be one third-person "
        "capability sentence without 'Use when' (the engine adds playbook.use_when)"
    )
    block = frontmatter.get("playbook")
    assert isinstance(block, dict), f"core skill {skill_id!r} needs a playbook: block"
    use_when = block.get("use_when")
    assert isinstance(use_when, str) and use_when.strip(), f"{skill_id}: playbook.use_when"
    assert not use_when.lower().startswith("use when"), f"{skill_id}: {use_when!r}"


@pytest.mark.parametrize("skill_id", CORE_SKILLS)
def test_core_skill_declares_where_phrase(skill_id: str) -> None:
    block = _authored(skill_id)[0].get("playbook")
    files = block.get("files") if isinstance(block, dict) else None
    assert files == EXPECTED_WHERE[skill_id], (
        f"core skill {skill_id!r} needs playbook.files {EXPECTED_WHERE[skill_id]!r}, got {files!r}"
    )
    assert 1 <= len(files) <= 80 and not files.endswith(".")


@pytest.mark.parametrize("skill_id", CORE_SKILLS)
def test_core_skill_md_is_plain_markdown(skill_id: str) -> None:
    """The D13 body hygiene (no Jinja, links, URLs or rule ids), over core skills only.

    Plugin skills are exempt (D24): they take no member rules, and vendored text
    keeps its upstream wording.
    """
    text = _skill_md_text(skill_id)
    assert "{{" not in text and "{%" not in text, f"core skill {skill_id!r} contains Jinja"
    links = extract_markdown_links(text)
    assert links == [], f"core skill {skill_id!r} contains a markdown link: {links}"
    assert not _URL.search(text), f"core skill {skill_id!r} contains a URL"
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


@pytest.mark.parametrize("skill_id", CORE_SKILLS)
def test_core_skill_references_are_one_level_deep(skill_id: str) -> None:
    """The D13 one-level reference check, over core skills only.

    Plugin skills are exempt (D24): their references are vendored as written.
    """
    references = SKILLS_ROOT / skill_id / "references"
    nested = (
        sorted(p.name for p in references.iterdir() if p.is_dir()) if references.is_dir() else []
    )
    assert nested == [], f"core skill {skill_id!r} nests references: {nested}"
    handwritten = sorted(references.glob("*.md")) if references.is_dir() else []
    texts = [p.read_text(encoding="utf-8") for p in handwritten]
    texts += [rule.body for rule in _members(skill_id)]
    nesting = [text.split("\n", 1)[0] for text in texts if "references/" in text]
    assert not nesting, (
        f"core skill {skill_id!r}: text naming references/ (one level only): {nesting}"
    )


@pytest.mark.parametrize("skill_id", CORE_SKILLS)
def test_core_skills_pass_agent_skill_issues(skill_id: str, tmp_path: Path) -> None:
    assert agent_skill_issues(_loaded_skill(skill_id, tmp_path)) == []


@pytest.mark.parametrize("rule_id", sorted(EXPECTED_MEMBERSHIP))
def test_scoped_core_rule_names_its_skill(rule_id: str) -> None:
    skill = core_rules()[rule_id].frontmatter.skill
    assert skill == EXPECTED_MEMBERSHIP[rule_id], (
        f"core rule {rule_id!r} names skill {skill!r}; EXPECTED_MEMBERSHIP expects "
        f"{EXPECTED_MEMBERSHIP[rule_id]!r} (scoped rules in core must name one of: "
        f"{', '.join(CORE_SKILLS)})"
    )


def test_membership_table_covers_every_scoped_core_rule() -> None:
    """Regression: a new scoped rule in core cannot ship without an owning skill."""
    scoped = {rule_id for rule_id, r in core_rules().items() if r.frontmatter.scope == "scoped"}
    missing = sorted(scoped - set(EXPECTED_MEMBERSHIP))
    assert not missing, f"scoped rules {missing} in core are missing from EXPECTED_MEMBERSHIP"
    assert scoped == set(EXPECTED_MEMBERSHIP)


def test_python_coding_members() -> None:
    """The twelve members of spec 9.6.2: nine from the always-text move, three distilled."""
    members = sorted(i for i, r in core_rules().items() if r.frontmatter.skill == "python-coding")
    expected = sorted(i for i, skill in EXPECTED_MEMBERSHIP.items() if skill == "python-coding")
    assert members == expected, f"python-coding members are {members}; expected {expected}"
    assert len(members) == PYTHON_CODING_MEMBER_COUNT, (
        f"python-coding has {len(members)} members; expected {PYTHON_CODING_MEMBER_COUNT}"
    )


def test_python_testing_members() -> None:
    """Spec 9.6.2: pytest plus the two distilled members, test doubles and fixtures."""
    members = sorted(i for i, r in core_rules().items() if r.frontmatter.skill == "python-testing")
    assert tuple(members) == PYTHON_TESTING_MEMBERS, (
        f"python-testing members are {members}; expected {list(PYTHON_TESTING_MEMBERS)}"
    )


def test_python_tooling_members() -> None:
    """Spec 9.6.2: the two FastAPI rules plus the four distilled tooling members."""
    members = sorted(i for i, r in core_rules().items() if r.frontmatter.skill == "python-tooling")
    assert tuple(members) == PYTHON_TOOLING_MEMBERS, (
        f"python-tooling members are {members}; expected {list(PYTHON_TOOLING_MEMBERS)}"
    )


@pytest.mark.parametrize("rule_id", sorted(DISTILLED_RULES))
def test_distilled_rule_frontmatter(rule_id: str) -> None:
    """Spec 9.4.1 / 9.6.1: the row's file and frontmatter, version 1 and no ``lint_codes`` (D23)."""
    row, rule = DISTILLED_RULES[rule_id], core_rules()[rule_id]
    front = rule.frontmatter
    assert rule.source_path == CORE_ROOT / "rules" / row.path, rule.source_path
    actual = (front.skill, front.scope, front.version, front.name, tuple(front.globs))
    assert actual == (row.skill, "scoped", 1, row.name, row.globs), f"{rule_id}: {actual}"
    assert (front.applies_if, front.priority) == (row.applies_if, row.priority), rule_id
    assert tuple(front.tags) == row.tags, f"{rule_id}: tags {front.tags}"
    assert front.lint_codes == {}, f"{rule_id} carries lint_codes {front.lint_codes} (D23)"
    assert front.description.endswith("."), f"{rule_id}: one-sentence description"


def test_always_core_rules_name_no_skill() -> None:
    always = {
        i: r.frontmatter.skill for i, r in core_rules().items() if r.frontmatter.scope == "always"
    }
    assert always == {"project-context": None, "python-house-style": None}


def test_every_core_member_skill_has_a_core_member() -> None:
    assert set(EXPECTED_MEMBERSHIP.values()) == set(EXPECTED_WHERE)


@pytest.mark.parametrize("skill_id", CORE_SKILLS)
def test_reference_probe_emits_each_core_skill_within_budget(
    reference_probe_repo: Path, skill_id: str
) -> None:
    frontmatter, body = split_frontmatter(_probe_skill_md(reference_probe_repo, skill_id))
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
    for rule in _probe_members(skill_id):
        assert rule.frontmatter.name in description, f"{skill_id} omits {rule.frontmatter.name!r}"
    assert sorted(frontmatter) == ["description", "id", "name"]
    index = body.partition("## References\n")[2]
    lines = [line for line in index.splitlines() if line.startswith("- [")]
    assert len(lines) == len(_probe_members(skill_id)), f"{skill_id} index: {lines}"


def test_reference_probe_where_section_lists_every_core_skill(reference_probe_repo: Path) -> None:
    for relative in ("AGENTS.md", CLAUDE_RULES_PATH):
        text = (reference_probe_repo / relative).read_text(encoding="utf-8")
        assert text.count("## Where guidance lives") == 1, relative
        for skill_id, files in EXPECTED_WHERE.items():
            assert f"- {files}: skill `{skill_id}`" in text, f"{relative} lacks {skill_id}"
        assert "Lint feedback names a rule id" in text, relative


def test_reference_probe_member_reference_is_byte_identical_in_every_skill_root(
    reference_probe_repo: Path,
) -> None:
    relative = "python-coding/references/python-typing.md"
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
        if _is_core_member_reference(entry.path)
    }
    expected = {
        f"{root}/{skill_id}/references/{rule_id}.md": ("rule", rule_id)
        for root in NATIVE_SKILL_ROOTS
        for rule_id, skill_id in EXPECTED_MEMBERSHIP.items()
        if rule_id not in PROBE_INACTIVE_MEMBERS
    }
    assert rows == expected


def test_reference_probe_writes_no_continue_prompt_for_a_member_skill(
    reference_probe_repo: Path,
) -> None:
    """Regression for E4: a skill with member rules is never degraded to a Continue prompt."""
    prompts = reference_probe_repo / ".continue" / "prompts"
    assert prompts.is_dir(), "the probe enables continue, so plugin skills are degraded there"
    assert [s for s in CORE_SKILLS if (prompts / f"{s}.md").exists()] == []


@pytest.mark.parametrize("file_name", ["44-python-data-shapes.md", "58-python-idioms.md"])
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
