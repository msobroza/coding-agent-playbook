"""``playbook validate`` over skill membership and ``playbook:`` blocks (prS §6.6, V1-V14, W1-W3).

One test per row of specs/prS-skills-context.md section 6.6, each asserting the
exact ``FAIL`` (stdout) or ``warning:`` (stderr) line. V1 and V2 are the
contract step: a scoped rule without ``skill:`` fails, and an override of a
rule in core that named one is told which. The fixtures are repo-local: ``playbook/skills/<id>/SKILL.md`` and
``playbook/rules/<id>.md`` in a synthetic consumer repo. Core ships four skills
that take members, so they are the known skills every message lists, and a
repo-local ``python-coding`` overrides the core one and keeps its core members:
the tests that count members use their own skill, ``risk-models``.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import sync as _sync
from coding_agent_playbook.commands import validate as _validate
from tests._catalog import core_rule_skill_ids

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    SyntheticRepoFactory = Callable[..., Path]

_PLAYBOOK_BLOCK = "playbook:\n  use_when: editing Python code\n  files: Any Python file\n"
_PATTERN = "^[a-z0-9]+(-[a-z0-9]+)*$ (1-64 chars)"
_REPO_LOCAL = "(<repo-local>)"
_SUPERPOWERS = "coding_agent_playbook.plugins.superpowers"
#: The skills that take members in every synthetic repo: core's, as V1 and V5 list them.
_KNOWN_SKILLS = ", ".join(core_rule_skill_ids())
#: A repo-local skill no core rule names, for the tests that count members.
_OWN_SKILL = "risk-models"

_CONFIG_WITH_SUPERPOWERS = f"""\
schema_version = 1
adapters_enabled = ["claude_code"]
overlays_enabled = ["{_SUPERPOWERS}"]

[project]
name = "synthetic"
kind = "python-library"

[engine]
version = "0.1.0a0"
"""


def write_skill(
    repo: Path,
    skill_id: str,
    *,
    description: str = "Python conventions for this repo.",
    block: str = _PLAYBOOK_BLOCK,
    body: str = "# Python coding\n\nPick the reference the task needs.\n",
) -> Path:
    """Write ``playbook/skills/<skill_id>/SKILL.md``; ``block`` is raw YAML (``""`` for none)."""
    skill_dir = repo / "playbook" / "skills" / skill_id
    skill_dir.mkdir(parents=True, exist_ok=True)
    frontmatter = f"id: {skill_id}\nname: {skill_id}\ndescription: {description!r}\n{block}"
    (skill_dir / "SKILL.md").write_text(f"---\n{frontmatter}---\n{body}", encoding="utf-8")
    return skill_dir


def write_rule(
    repo: Path,
    rule_id: str,
    *,
    skill: str | None = "python-coding",
    scope: str = "scoped",
    name: str | None = None,
    priority: int = 50,
) -> Path:
    """Write ``playbook/rules/<rule_id>.md``; ``skill`` is raw YAML (``None`` leaves it out)."""
    target = repo / "playbook" / "rules" / f"{rule_id}.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    skill_line = "" if skill is None else f"skill: {skill}\n"
    target.write_text(
        f"---\nid: {rule_id}\nname: {name or rule_id!r}\ndescription: One line.\n"
        f"scope: {scope}\n{skill_line}priority: {priority}\n---\nBody\n",
        encoding="utf-8",
    )
    return target


def run_validate(repo: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    """``playbook validate`` in ``repo``: ``(exit code, stdout, stderr)``."""
    rc = _validate.run(argparse.Namespace(repo_root=str(repo)))
    captured = capsys.readouterr()
    return rc, captured.out, captured.err


def fail_lines(out: str) -> list[str]:
    """Every ``FAIL`` line of validate's stdout."""
    return [line for line in out.splitlines() if line.startswith("FAIL ")]


@pytest.fixture
def repo(tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory) -> Path:
    """A synthetic repo with one valid skill that takes members: ``python-coding``."""
    built = make_synthetic_repo(tmp_path)
    write_skill(built, "python-coding")
    return built


def test_rule_joining_a_repo_local_skill_validates(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_rule(repo, "python-typing", name="Typing")

    rc, out, err = run_validate(repo, capsys)

    assert rc == 0, out
    assert "warning:" not in err


def test_repo_local_rule_may_join_a_core_skill(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """D2: naming the core ``python-coding`` is enough; membership is resolved after the merge."""
    repo = make_synthetic_repo(tmp_path)
    write_rule(repo, "risk-naming", name="Risk naming")

    rc, out, err = run_validate(repo, capsys)
    assert rc == 0, out
    assert "warning:" not in err

    assert _sync.run(argparse.Namespace(repo_root=str(repo), check=False)) == 0
    skill_dir = repo / ".claude" / "skills" / "python-coding"
    assert (skill_dir / "references" / "risk-naming.md").is_file()
    skill_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "- [risk-naming](references/risk-naming.md) — Risk naming: One line." in skill_md
    assert "Risk naming" in skill_md.partition("\n---\n")[0], "the Covers clause names it"


def test_scoped_rule_without_skill_fails_naming_known_skills(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rule = write_rule(repo, "risk-naming", skill=None)

    rc, out, _ = run_validate(repo, capsys)

    assert rc == 1
    assert fail_lines(out) == [
        f"FAIL {rule}: scope 'scoped' needs a skill: put the file in that skill's rules/ "
        "directory (skills/<skill-id>/rules/), or add 'skill: <skill-id>' when the skill "
        f"comes from another layer; known skills: {_KNOWN_SKILLS}"
    ]


def test_scoped_override_without_skill_suggests_the_overridden_rules_skill(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """V2: the override of core's ``python-typing`` drops the ``skill`` core gave it."""
    rule = write_rule(repo, "python-typing", skill=None, name="Typing")

    rc, out, _ = run_validate(repo, capsys)

    assert rc == 1
    assert fail_lines(out) == [
        f"FAIL {rule}: scope 'scoped' needs a skill: put the file in that skill's rules/ "
        "directory (skills/<skill-id>/rules/), or add 'skill: <skill-id>' when the skill "
        f"comes from another layer; known skills: {_KNOWN_SKILLS}; the rule it overrides "
        "(coding_agent_playbook) names 'python-coding'"
    ]


def test_always_rule_with_skill_fails(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rule = write_rule(repo, "house-style", scope="always")

    rc, out, _ = run_validate(repo, capsys)

    assert rc == 1
    assert fail_lines(out) == [
        f"FAIL {rule}: 'skill: python-coding' is not allowed on an always rule (always rules "
        "stay in always-loaded context); remove 'skill', or set 'scope: scoped' to deliver "
        "the rule through that skill"
    ]


@pytest.mark.parametrize(
    ("raw", "shown"),
    [("42", "42"), ("'Python Coding'", "'Python Coding'"), ("'" + "a" * 65 + "'", repr("a" * 65))],
    ids=["int", "not-a-name", "too-long"],
)
def test_skill_value_must_be_an_id_string(
    repo: Path, capsys: pytest.CaptureFixture[str], raw: str, shown: str
) -> None:
    rule = write_rule(repo, "python-typing", skill=raw)

    rc, out, _ = run_validate(repo, capsys)

    assert rc == 1
    assert fail_lines(out) == [
        f"FAIL {rule}: skill {shown} must be a skill id string matching {_PATTERN}, "
        "e.g. 'python-coding'"
    ]


def test_skill_must_exist_after_the_merge(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rule = write_rule(repo, "python-typing", skill="python-codng")

    rc, out, _ = run_validate(repo, capsys)

    assert rc == 1
    assert fail_lines(out) == [
        f"FAIL {rule}: skill 'python-codng' does not exist after merging every layer; "
        f"expected one of: {_KNOWN_SKILLS} (or enable the overlay that ships it)"
    ]


def test_member_rule_id_must_be_a_skill_safe_name(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rule = write_rule(repo, "Py_Typing")

    rc, out, _ = run_validate(repo, capsys)

    assert rc == 1
    assert fail_lines(out) == [
        f"FAIL {rule}: rule id 'Py_Typing' cannot be a member of skill 'python-coding': its "
        f"reference is written as references/<id>.md, so the id must match {_PATTERN}"
    ]


def test_playbook_block_must_be_a_mapping(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_skill(repo, "python-coding", block="playbook: 'yes'\n")
    write_rule(repo, "python-typing")

    rc, out, _ = run_validate(repo, capsys)

    assert rc == 1
    assert fail_lines(out) == [
        f"FAIL skills/python-coding {_REPO_LOCAL}: 'playbook' must be a mapping with optional "
        "keys files and use_when, got str 'yes'"
    ]


def test_playbook_block_rejects_unknown_keys(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_skill(repo, "python-coding", block=_PLAYBOOK_BLOCK + "  when: always\n")
    write_rule(repo, "python-typing")

    rc, out, _ = run_validate(repo, capsys)

    assert rc == 1
    assert fail_lines(out) == [
        f"FAIL skills/python-coding {_REPO_LOCAL}: 'playbook' has unknown key 'when'; "
        "allowed keys: files, use_when"
    ]


_FILES_SHAPE = (
    "keep it to one line of at most 80 chars without a trailing period "
    "(it becomes one line of 'Where guidance lives')"
)


@pytest.mark.parametrize(
    ("files_yaml", "problem"),
    [
        ("'" + "f" * 112 + "'", "is 112 chars"),
        ("'Any Python file.'", "ends with a period ('Any Python file.')"),
        ('"Python files\\nand notebooks"', "spans 2 lines ('Python files\\nand notebooks')"),
        ("42", "is int 42"),
        ("'  '", "is blank"),
    ],
    ids=["too-long", "trailing-period", "two-lines", "not-a-string", "blank"],
)
def test_playbook_files_must_be_one_short_line(
    repo: Path, capsys: pytest.CaptureFixture[str], files_yaml: str, problem: str
) -> None:
    block = f"playbook:\n  use_when: editing Python code\n  files: {files_yaml}\n"
    write_skill(repo, "python-coding", block=block)
    write_rule(repo, "python-typing")

    rc, out, _ = run_validate(repo, capsys)

    assert rc == 1
    assert fail_lines(out) == [
        f"FAIL skills/python-coding {_REPO_LOCAL}: 'playbook.files' {problem}; {_FILES_SHAPE}"
    ]


def test_playbook_use_when_must_be_one_line(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_skill(repo, "python-coding", block="playbook:\n  use_when: 7\n  files: Any Python file\n")
    write_rule(repo, "python-typing")

    rc, out, _ = run_validate(repo, capsys)

    assert rc == 1
    assert fail_lines(out) == [
        f"FAIL skills/python-coding {_REPO_LOCAL}: 'playbook.use_when' is int 7; keep it to one "
        "non-empty line (the engine writes it as 'Use when <use_when>.' in the composed "
        "description)"
    ]


def test_use_when_must_not_repeat_use_when(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    block = "playbook:\n  use_when: Use when editing Python code\n  files: Any Python file\n"
    write_skill(repo, "python-coding", block=block)
    write_rule(repo, "python-typing")

    rc, out, _ = run_validate(repo, capsys)

    assert rc == 1
    assert fail_lines(out) == [
        f"FAIL skills/python-coding {_REPO_LOCAL}: 'playbook.use_when' starts with 'Use when'; "
        "write only the condition (the engine adds 'Use when'), e.g. 'editing a Python module'"
    ]


_LONG_DESCRIPTION = (
    "Python conventions that this description spells out at a length chosen to leave no "
    "room for even one member name in the clause."
)
_LONG_USE_WHEN = (
    "editing, reviewing or generating any Python module, script, notebook export or test "
    "helper in this repository today"
)


def test_description_that_cannot_fit_one_member_name_fails_with_length_and_text(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The worst case names the longest member with the ``and N-1 more`` tail (E7).

    The first member by priority (``Typing``) would fit; the longest one decides.
    """
    block = f"playbook:\n  use_when: {_LONG_USE_WHEN!r}\n  files: Any Python file\n"
    write_skill(repo, _OWN_SKILL, description=_LONG_DESCRIPTION, block=block)
    write_rule(repo, "risk-typing", skill=_OWN_SKILL, name="Typing", priority=40)
    write_rule(repo, "risk-errors", skill=_OWN_SKILL, name="Error handling and logging conventions")

    rc, out, _ = run_validate(repo, capsys)

    worst = (
        f"{_LONG_DESCRIPTION} Covers Error handling and logging conventions and 1 more. "
        f"Use when {_LONG_USE_WHEN}."
    )
    assert rc == 1
    assert fail_lines(out) == [
        f"FAIL skills/{_OWN_SKILL} {_REPO_LOCAL}: the composed description cannot fit 300 "
        f"chars even when the Covers clause names one member: '{worst}' is 311 chars; shorten "
        "'description' (127 chars), 'playbook.use_when' (115 chars) or the longest member "
        "name (risk-errors: 'Error handling and logging conventions')"
    ]


def test_handwritten_reference_colliding_with_a_member_fails(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    references = repo / "playbook" / "skills" / "python-coding" / "references"
    references.mkdir()
    (references / "python-typing.md").write_text("# Notes\n", encoding="utf-8")
    write_rule(repo, "python-typing")

    rc, out, _ = run_validate(repo, capsys)

    assert rc == 1
    assert fail_lines(out) == [
        f"FAIL skills/python-coding {_REPO_LOCAL}: references/python-typing.md is hand-written "
        "in this skill but is also the rendered reference of member rule 'python-typing'; "
        "rename the hand-written file"
    ]


def test_authored_references_heading_fails(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_skill(repo, "python-coding", body="# Python coding\n\n## References\n\n- notes\n")
    write_rule(repo, "python-typing")

    rc, out, _ = run_validate(repo, capsys)

    assert rc == 1
    assert fail_lines(out) == [
        f"FAIL skills/python-coding {_REPO_LOCAL}: the body has its own '## References' "
        "heading; the engine appends that section for member rules, so rename yours "
        "(e.g. '## Further reading')"
    ]


def test_references_heading_in_a_plain_skill_is_allowed(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """V13 guards only a skill that takes members: nothing is appended to a plain one."""
    write_skill(repo, "query-db", block="", body="# Query\n\n## References\n")

    rc, out, _ = run_validate(repo, capsys)

    assert rc == 0, out


def _v14_line(rule: Path, skill_id: str, source: str) -> str:
    return (
        f"FAIL {rule}: skill '{skill_id}' ({source}) declares no 'playbook:' block, so it "
        f"cannot take member rules; name one that does ({_KNOWN_SKILLS}), or add a "
        "'playbook:' block to a skill of your own (an override of a core skill must keep one)"
    )


def test_rule_naming_a_skill_without_a_playbook_block_fails(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """V14 over a superpowers skill (D3: a bundled plugin skill owns no members) and
    over a repo-local plain skill."""
    built = make_synthetic_repo(tmp_path, config_text=_CONFIG_WITH_SUPERPOWERS)
    write_skill(built, "python-coding")
    write_skill(built, "query-db", block="")
    plugin_rule = write_rule(built, "tdd-cycle", skill="test-driven-development")
    local_rule = write_rule(built, "db-queries", skill="query-db")

    rc, out, _ = run_validate(built, capsys)

    assert rc == 1
    assert fail_lines(out) == [
        _v14_line(local_rule, "query-db", "<repo-local>"),
        _v14_line(plugin_rule, "test-driven-development", _SUPERPOWERS),
    ]


def test_playbook_block_without_members_warns(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The fixture's python-coding keeps core's members; a skill of its own has none."""
    write_skill(repo, _OWN_SKILL)

    rc, out, err = run_validate(repo, capsys)

    assert rc == 0, out
    assert err.splitlines() == [
        f"warning: skills/{_OWN_SKILL} {_REPO_LOCAL}: declares 'playbook' but has no member "
        "rule (none in its rules/ directory, none naming it in 'skill:'); it is never written"
    ]


def test_member_skill_without_files_warns(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_skill(repo, "python-coding", block="playbook:\n  use_when: editing Python code\n")
    write_rule(repo, "python-typing")

    rc, out, err = run_validate(repo, capsys)

    assert rc == 0, out
    assert err.splitlines() == [
        f"warning: skills/python-coding {_REPO_LOCAL}: has member rules but no "
        "'playbook.files'; it is left out of the 'Where guidance lives' section"
    ]


def test_truncated_member_list_warns_with_counts(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Four 67-69 char names: all four make 348 chars, three make 290 (D21)."""
    tail = "conventions with a display name long enough to crowd the list"
    write_skill(repo, _OWN_SKILL)
    for priority, word in enumerate(["Alpha", "Bravo", "Charlie", "Delta"], start=40):
        rule_id, name = f"risk-{word.lower()}", f"{word} {tail}"
        write_rule(repo, rule_id, skill=_OWN_SKILL, name=name, priority=priority)

    rc, out, err = run_validate(repo, capsys)

    assert rc == 0, out
    assert err.splitlines() == [
        f"warning: skills/{_OWN_SKILL} {_REPO_LOCAL}: the composed description names 3 of 4 "
        "member rules within 300 chars ('... and 1 more'); shorten member names or the "
        "authored parts to list them all"
    ]
