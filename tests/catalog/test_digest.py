"""The artifact content digest (``catalog.digest``, #281 ticket 03).

Digests are computed from artifacts loaded the way sync loads them: the body,
the behaviour-relevant frontmatter and the side files move a digest; key order,
YAML formatting and bookkeeping keys do not.
"""

from __future__ import annotations

import dataclasses
import re
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.artifacts.hook import Hook
from coding_agent_playbook.artifacts.prompt import Prompt
from coding_agent_playbook.artifacts.rule import Rule
from coding_agent_playbook.catalog.digest import artifact_digest, digest_kind
from coding_agent_playbook.catalog.source import _iter_skills
from tests._catalog import core_rules, core_skills
from tests.hook_samples import sample_hook, write_hook

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.artifacts.skill import Skill

# ADR 0010: a module that reads the shipped catalog is a catalog check as a whole.
pytestmark = pytest.mark.catalog

_RULE = """\
---
id: style
name: Style
description: How to write code.
scope: always
priority: 40
---
Use spaces.
"""

# The same rule: keys reordered, flow-style YAML, a bookkeeping version, an empty list.
_RULE_REORDERED = """\
---
{scope: always, priority: 40, description: How to write code., version: 7, tags: [],
 name: Style, id: style}
---
Use spaces.
"""


def _rule(tmp_path: Path, text: str, name: str = "style.md") -> Rule:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return Rule.from_markdown(path, "<repo-local>")


def _skill(tmp_path: Path, files: dict[str, str]) -> Skill:
    """Load ``<tmp>/skills/demo`` holding ``SKILL.md`` plus ``files`` as sync loads it."""
    skill_dir = tmp_path / "skills" / "demo"
    texts = {"SKILL.md": "---\nname: demo\ndescription: A demo.\n---\nDo it.\n", **files}
    for relative, text in texts.items():
        (skill_dir / relative).parent.mkdir(parents=True, exist_ok=True)
        (skill_dir / relative).write_text(text, encoding="utf-8")
    (skill,) = _iter_skills(tmp_path / "skills", "<repo-local>")
    return skill


def test_digest_is_a_sha256_hex_string(tmp_path: Path) -> None:
    assert re.fullmatch(r"[0-9a-f]{64}", artifact_digest(_rule(tmp_path, _RULE)))


def test_reordering_and_reformatting_frontmatter_keeps_the_digest(tmp_path: Path) -> None:
    plain = _rule(tmp_path, _RULE, "a.md")
    reordered = _rule(tmp_path, _RULE_REORDERED, "b.md")

    assert artifact_digest(plain) == artifact_digest(reordered)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("Use spaces.\n", "Use tabs.\n"),
        ("priority: 40\n", "priority: 41\n"),
        ("description: How to write code.\n", "description: How to write tests.\n"),
    ],
    ids=["body", "priority", "description"],
)
def test_changing_the_body_or_a_behaviour_key_changes_the_digest(
    tmp_path: Path, old: str, new: str
) -> None:
    before = _rule(tmp_path, _RULE, "a.md")
    after = _rule(tmp_path, _RULE.replace(old, new), "b.md")

    assert artifact_digest(before) != artifact_digest(after)


def test_the_digest_covers_the_source_body_not_the_rendered_one(tmp_path: Path) -> None:
    rule = _rule(tmp_path, _RULE)
    rendered = dataclasses.replace(rule, body="Use spaces in /repo/x.\n")

    assert artifact_digest(rendered) == artifact_digest(rule)


def test_a_prompts_eval_samples_are_bookkeeping(tmp_path: Path) -> None:
    text = "---\nid: tidy\nname: Tidy\ndescription: Tidy.\nslash: tidy\n{extra}---\nTidy it.\n"
    path_a, path_b = tmp_path / "a.md", tmp_path / "b.md"
    path_a.write_text(text.format(extra=""), encoding="utf-8")
    path_b.write_text(text.format(extra="eval_samples: [tidy-one]\n"), encoding="utf-8")

    plain = Prompt.from_markdown(path_a, "<repo-local>")
    with_samples = Prompt.from_markdown(path_b, "<repo-local>")

    assert artifact_digest(plain) == artifact_digest(with_samples)


@pytest.mark.parametrize(
    "side_file", ["rules/member.md", "scripts/run.py", "references/guide.md", "examples/a.txt"]
)
def test_editing_a_skill_side_file_changes_the_digest(tmp_path: Path, side_file: str) -> None:
    before = artifact_digest(_skill(tmp_path / "a", {side_file: "one\n"}))
    after = artifact_digest(_skill(tmp_path / "b", {side_file: "two\n"}))

    assert before != after


def test_bytecode_caches_never_move_a_skill_digest(tmp_path: Path) -> None:
    clean = _skill(tmp_path / "a", {"scripts/run.py": "print()\n"})
    cached = _skill(
        tmp_path / "b",
        {"scripts/run.py": "print()\n", "scripts/__pycache__/run.cpython-312.pyc": "junk"},
    )

    assert artifact_digest(clean) == artifact_digest(cached)


def test_the_skill_directory_location_does_not_move_the_digest(tmp_path: Path) -> None:
    files = {"scripts/run.py": "print()\n", "rules/member.md": "m\n"}

    assert artifact_digest(_skill(tmp_path / "a", files)) == artifact_digest(
        _skill(tmp_path / "deeper" / "b", files)
    )


def test_editing_a_hook_script_changes_the_digest(tmp_path: Path) -> None:
    def hook_with_script(root: Path, script: str) -> Hook:
        path = write_hook(root, scripts=True)
        (path.parent / "scripts" / "check.py").write_text(script, encoding="utf-8")
        return Hook.from_markdown(path, "<repo-local>")

    before = hook_with_script(tmp_path / "a", "print(1)\n")
    after = hook_with_script(tmp_path / "b", "print(2)\n")

    assert artifact_digest(before) != artifact_digest(after)


def test_a_hook_without_files_still_has_a_digest() -> None:
    assert artifact_digest(sample_hook()) != artifact_digest(sample_hook(name="Other"))


def test_digest_kind_names_each_artifact_kind(tmp_path: Path) -> None:
    skill = _skill(tmp_path, {})
    kinds = [digest_kind(_rule(tmp_path, _RULE)), digest_kind(skill), digest_kind(sample_hook())]

    assert kinds == ["rule", "skill", "hook"]
    assert digest_kind(skill.to_prompt()) == "prompt"


def test_digest_kind_names_the_value_it_cannot_digest() -> None:
    with pytest.raises(TypeError, match=r"cannot digest 'nope'; expected a Rule"):
        digest_kind("nope")  # type: ignore[arg-type]


def test_every_shipped_rule_and_skill_has_a_distinct_digest() -> None:
    rules = list(core_rules().values())
    skills = core_skills()
    digests = [artifact_digest(rule) for rule in rules] + [artifact_digest(s) for s in skills]

    assert len(set(digests)) == len(digests) == len(rules) + len(skills)
