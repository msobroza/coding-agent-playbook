"""Docs-consistency guard: SPEC describes rules inside skills (prU D-01; D5, D17, D21, ADR 0005).

Member rules live in their skill's ``rules/`` directory, in the catalog and in every
rendered skill root, and a sectioned skill ranks them by impact band. The SPEC body may
no longer describe the earlier ``references/<rule-id>.md`` delivery or the kind-based
priority bands (the changelogs keep that history), and §12.6 must quote, for each
layout check R1-R6 and section check S1-S7, the message the engine prints. Messages are
produced by the validation code itself, so a reworded message fails here until the
SPEC row follows. Prose-only on the SPEC side: these tests never change engine state.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from coding_agent_playbook.validation._rule_layout import check_rule_layout
from tests.unit.test_docs_lifecycle_hooks_spec import _spec_section
from tests.validation.section_samples import (
    FIXTURES,
    MOCKING,
    SECTIONLESS_BLOCK,
    check,
    make_rule,
    make_skill,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill

#: The phrases of the pre-D5 delivery and priority policy (the ticket's acceptance grep).
_STALE_PHRASES = (
    "references/<rule-id>",
    "references/python-typing.md",
    "kind bands",
    "40-59 language",
)

_RULE = "---\nid: {id}\nname: {id}\ndescription: d\nscope: {scope}\n{extra}---\nBody\n"
_SKILL = "---\nid: {id}\nname: {id}\ndescription: d\n{block}---\nBody\n"
_BLOCK = "playbook:\n  files: f\n"


def _validate_section() -> str:
    return _spec_section("### 12.6 `playbook validate`", "### 12.7 ")


def _row(check_id: str) -> str:
    """The one §12.6 table row of ``check_id`` (``R1``, ``S4``, ...)."""
    rows = [line for line in _validate_section().splitlines() if line.startswith(f"| {check_id} |")]
    assert len(rows) == 1, f"SPEC §12.6 needs exactly one row for {check_id}, found {rows}"
    return rows[0]


@pytest.mark.parametrize("phrase", _STALE_PHRASES)
def test_spec_body_no_longer_describes_the_old_delivery(phrase: str) -> None:
    body = _spec_section("## 1. Context", "## Changelog")
    stale = [line[:80] for line in body.splitlines() if phrase in line]
    assert not stale, f"SPEC body still says {phrase!r} (only the changelogs may): {stale}"


def test_section_10_2_1_states_the_impact_bands() -> None:
    policy = _spec_section("#### 10.2.1 Numbering scheme", "### 10.3 Claude Code adapter")
    for band in ("`00`-`19`", "`20`-`39`", "`40`-`59`", "`60`-`79`", "`80`-`99`"):
        assert f"| {band} |" in policy, f"SPEC §10.2.1 lacks the {band} row"


def test_section_12_6_retires_v12_and_quotes_the_rules_heading() -> None:
    assert "| V12 |" not in _validate_section(), "V12 was retired by prU D5"
    assert "'## Rules' heading" in _row("V13")


# --- S1-S7 and the D42 warning: the engine's own messages ----------------------------------


def _messages(rules: list[Rule], skill: Skill) -> list[str]:
    """Every error and warning message the section checks report, errors first."""
    findings = check(rules, skill)
    return [f.message for f in (*findings.errors, *findings.warnings)]


_SECTION_CASES = {
    "S1": lambda: _messages([], make_skill({"sections": [{**MOCKING, "impact": "URGENT"}]})),
    "S2": lambda: _messages([], make_skill({"sections": [FIXTURES, MOCKING]})),
    "S3": lambda: _messages([make_rule(section="mokcing")], make_skill()),
    "S4": lambda: _messages([make_rule(section=None)], make_skill()),
    "S5": lambda: [
        *_messages([make_rule(section="mocking", priority=50)], make_skill(SECTIONLESS_BLOCK)),
        *_messages([make_rule(skill=None, scope="always")], make_skill()),
    ],
    "S6": lambda: _messages([make_rule(priority=45)], make_skill()),
    "S7": lambda: _messages([make_rule(body="# Use fakes [HIGH]\n")], make_skill()),
    "W4": lambda: _messages([make_rule(section=None, package="other")], make_skill()),
}


@pytest.mark.parametrize("check_id", sorted(_SECTION_CASES))
def test_section_12_6_row_quotes_the_section_check_message(check_id: str) -> None:
    messages = _SECTION_CASES[check_id]()
    assert messages, f"the {check_id} fixture produced no finding"
    row = _row(check_id)
    missing = [message for message in messages if message not in row]
    assert not missing, f"SPEC §12.6 row {check_id} must quote {missing}"


# --- R1-R6: the rules/ layout messages, paths relative to the repo ------------------------


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _skill(layer: Path, skill_id: str, *, block: str = _BLOCK) -> Path:
    skill_dir = layer / "skills" / skill_id
    _write(skill_dir / "SKILL.md", _SKILL.format(id=skill_id, block=block))
    return skill_dir


def _rule(path: Path, rule_id: str, *, scope: str = "scoped", extra: str = "") -> None:
    _write(path, _RULE.format(id=rule_id, scope=scope, extra=extra))


def _r1(repo: Path) -> None:
    _rule(_skill(repo / "playbook", "s") / "rules" / "r.md", "r", extra="skill: t\n")


def _r2(repo: Path) -> None:
    _rule(_skill(repo / "playbook", "s") / "rules" / "typing.md.j2", "python-typing")


def _r3(repo: Path) -> None:
    _rule(repo / "playbook" / "rules" / "r-old.md", "r", extra="skill: s\n")
    _rule(_skill(repo / "playbook", "s") / "rules" / "r.md", "r")


def _r4(repo: Path) -> None:
    _rule(repo / "playbook" / "skills" / "orphan" / "rules" / "r.md", "r")
    (_skill(repo / "playbook", "plain", block="") / "rules").mkdir()


def _r6(repo: Path) -> None:
    _rule(_skill(repo / "playbook", "s") / "rules" / "house.md", "house", scope="always")


_LAYOUT_CASES = {"R1": _r1, "R2": _r2, "R3": _r3, "R4": _r4, "R6": _r6}


@pytest.fixture
def engine(make_package: Callable[..., str]) -> str:
    """A throwaway engine package, so the real catalog stays out of these fixtures."""
    return make_package("docs_layout_engine", resources=True)


def _layout_messages(repo: Path, engine: str) -> list[str]:
    source = FileSystemArtifactSource(repo_root=repo, engine_package=engine)
    rules, _ = source.collect_rules()
    prefix = f"{repo}/"
    return [
        f"{error.path.removeprefix(prefix)}: {error.message.replace(prefix, '')}"
        for error in check_rule_layout(rules, source)
    ]


@pytest.mark.parametrize("check_id", sorted(_LAYOUT_CASES))
def test_section_12_6_row_quotes_the_layout_check_message(
    check_id: str, tmp_path: Path, engine: str
) -> None:
    _LAYOUT_CASES[check_id](tmp_path)
    messages = _layout_messages(tmp_path, engine)
    assert messages, f"the {check_id} fixture produced no finding"
    row = _row(check_id)
    missing = [message for message in messages if f"`FAIL {message}`" not in row]
    assert not missing, f"SPEC §12.6 row {check_id} must quote {missing}"


def test_section_12_6_row_quotes_the_r5_move_hint(tmp_path: Path, engine: str) -> None:
    """R5's paths name the engine package, so the row is checked around them."""
    layer = Path(importlib.import_module(engine).__file__ or "").parent / "resources"
    _skill(layer, "python-coding")
    _rule(layer / "rules" / "typing.md.j2", "python-typing", extra="skill: python-coding\n")
    [message] = _layout_messages(tmp_path, engine)
    row = _row("R5")
    for fragment in (
        "scoped rule 'python-typing' lies in the engine's rules/ directory ",
        ", which holds only always rules; move it to ",
        "/skills/python-coding/rules/python-typing.md.j2 and remove its 'skill:' line",
    ):
        assert fragment in message, f"the engine's R5 message changed: {message!r}"
        assert fragment in row, f"SPEC §12.6 row R5 must quote {fragment!r}"
