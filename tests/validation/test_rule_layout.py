"""``check_rule_layout``: the rules/ layout of every layer (prU D21, D5, ADR 0005).

Each check has a passing and a failing fixture; a failing one yields exactly one
finding whose path is the file and whose message names the offending value and
the fix, asserted verbatim.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.artifacts.rule import Rule
from coding_agent_playbook.catalog.roots import ENGINE_PACKAGE
from coding_agent_playbook.catalog.source import ArtifactSource, FileSystemArtifactSource
from coding_agent_playbook.validation._rule_layout import _layer_root, check_rule_layout

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.skill import Skill
    from coding_agent_playbook.evals.sample import EvalSample
    from coding_agent_playbook.validation.findings import ValidationError

_RULE = "---\nid: {id}\nname: {id}\ndescription: d\nscope: {scope}\n{extra}---\nBody\n"
_SKILL = "---\nid: {id}\nname: {id}\ndescription: d\n{block}---\nBody\n"
_BLOCK = "playbook:\n  files: f\n"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _skill(layer: Path, skill_id: str, *, block: str = _BLOCK) -> Path:
    skill_dir = layer / "skills" / skill_id
    _write(skill_dir / "SKILL.md", _SKILL.format(id=skill_id, block=block))
    return skill_dir


def _rule(path: Path, rule_id: str, *, scope: str = "scoped", extra: str = "") -> Path:
    return _write(path, _RULE.format(id=rule_id, scope=scope, extra=extra))


@pytest.fixture
def engine(make_package: Callable[..., str]) -> str:
    """A throwaway engine package, so the real catalog stays out of these fixtures."""
    return make_package("layout_engine", resources=True)


def _engine_layer(engine: str) -> Path:
    module = importlib.import_module(engine)
    assert module.__file__ is not None
    return Path(module.__file__).parent / "resources"


def _check(repo: Path, engine: str) -> list[ValidationError]:
    source = FileSystemArtifactSource(repo_root=repo, engine_package=engine)
    rules, _ = source.collect_rules()
    return check_rule_layout(rules, source)


def _messages(errors: list[ValidationError]) -> list[tuple[str, str]]:
    return [(e.path, e.message) for e in errors]


# R1: a rule inside skills/x/rules/ must not declare another skill.


def test_r1_an_in_skill_rule_naming_its_own_skill_passes(tmp_path: Path, engine: str) -> None:
    _rule(_skill(tmp_path / "playbook", "s") / "rules" / "r.md", "r", extra="skill: s\n")

    assert _check(tmp_path, engine) == []


def test_r1_an_in_skill_rule_naming_another_skill_fails(tmp_path: Path, engine: str) -> None:
    path = _rule(_skill(tmp_path / "playbook", "s") / "rules" / "r.md", "r", extra="skill: t\n")

    assert _messages(_check(tmp_path, engine)) == [
        (
            str(path),
            "declares 'skill: t' but lies in the rules/ directory of skill 's', which sets "
            "its membership; remove the 'skill:' line, or move the file to "
            f"{tmp_path / 'playbook' / 'skills' / 't' / 'rules' / 'r.md'}",
        )
    ]


# R2: the file name is the id, inside a skill's rules/ and in the engine layer.


def test_r2_in_skill_and_engine_names_equal_to_the_id_pass(tmp_path: Path, engine: str) -> None:
    _rule(_skill(tmp_path / "playbook", "s") / "rules" / "nested" / "r.md.j2", "r")
    layer = _engine_layer(engine)
    _rule(_skill(layer, "core") / "rules" / "core-r.md", "core-r")
    _rule(layer / "rules" / "always" / "10-house.md", "house", scope="always")
    _rule(layer / "rules" / "always" / "context.md.j2", "context", scope="always")

    assert _check(tmp_path, engine) == []


def test_r2_overlay_and_local_layer_rules_dirs_keep_free_names(tmp_path: Path, engine: str) -> None:
    _rule(tmp_path / "playbook" / "rules" / "anything.md", "r", extra="skill: s\n")
    _skill(tmp_path / "playbook", "s")

    assert _check(tmp_path, engine) == []


def test_r2_an_in_skill_file_named_otherwise_fails(tmp_path: Path, engine: str) -> None:
    path = _rule(_skill(tmp_path / "playbook", "s") / "rules" / "typing.md.j2", "python-typing")

    assert _messages(_check(tmp_path, engine)) == [
        (
            str(path),
            "file name 'typing.md.j2' does not match rule id 'python-typing'; rename the "
            "file to python-typing.md.j2",
        )
    ]


def test_r2_an_engine_always_rule_named_otherwise_fails(tmp_path: Path, engine: str) -> None:
    path = _rule(_engine_layer(engine) / "rules" / "always" / "1-house.md", "house", scope="always")

    assert _messages(_check(tmp_path, engine)) == [
        (
            str(path),
            "file name '1-house.md' does not match rule id 'house'; rename the file to "
            "house.md (an always rule may keep a two-digit priority prefix, e.g. 10-house.md)",
        )
    ]


def test_r2_leaves_an_engine_scoped_rule_outside_a_skill_to_r5(tmp_path: Path, engine: str) -> None:
    """R5's move hint already names <id>.md; a rename hint would only repeat it."""
    layer = _engine_layer(engine)
    _skill(layer, "s")
    path = _rule(layer / "rules" / "typing.md.j2", "python-typing", extra="skill: s\n")

    errors = _check(tmp_path, engine)

    assert [e.path for e in errors] == [str(path)]
    assert errors[0].message.startswith("scoped rule 'python-typing' lies in the engine's")
    assert "rename the file" not in errors[0].message


# R3: two files with one id in one layer.


def test_r3_one_id_in_two_layers_is_an_override_not_a_duplicate(
    tmp_path: Path, engine: str
) -> None:
    layer = _engine_layer(engine)
    _rule(_skill(layer, "s") / "rules" / "r.md", "r")
    _rule(_skill(tmp_path / "playbook", "s") / "rules" / "r.md", "r")

    assert _check(tmp_path, engine) == []


def test_r3_one_id_twice_in_one_layer_names_both_paths(tmp_path: Path, engine: str) -> None:
    first = _rule(tmp_path / "playbook" / "rules" / "r-old.md", "r", extra="skill: s\n")
    second = _rule(_skill(tmp_path / "playbook", "s") / "rules" / "r.md", "r")

    assert _messages(_check(tmp_path, engine)) == [
        (
            str(first),
            f"rule id 'r' is defined by 2 files in layer <repo-local>: {first} and {second}; "
            "the later one silently replaces the earlier, so give one file another id or "
            "delete it",
        )
    ]


# R4: a skill's rules/ needs a SKILL.md with a playbook: block.


def test_r4_a_rules_dir_without_skill_md_fails(tmp_path: Path, engine: str) -> None:
    rules_dir = tmp_path / "playbook" / "skills" / "orphan" / "rules"
    _rule(rules_dir / "r.md", "r")

    assert _messages(_check(tmp_path, engine)) == [
        (
            str(rules_dir),
            "a rules/ directory in a skill directory without SKILL.md is never loaded; add "
            "SKILL.md with an 'id' and a 'playbook:' block, or move its files to "
            f"{tmp_path / 'playbook' / 'rules'}/ with 'skill: <skill-id>'",
        )
    ]


def test_r4_a_rules_dir_in_a_skill_without_a_playbook_block_fails(
    tmp_path: Path, engine: str
) -> None:
    skill_dir = _skill(tmp_path / "playbook", "plain", block="")
    rules_dir = skill_dir / "rules"
    rules_dir.mkdir()

    assert _messages(_check(tmp_path, engine)) == [
        (
            str(rules_dir),
            "skill 'plain' has a rules/ directory but its SKILL.md declares no 'playbook:' "
            "block, so it cannot take member rules; add a 'playbook:' block (e.g. "
            "'playbook: {files: <which files this skill covers>}') to "
            f"{skill_dir / 'SKILL.md'}, or move the rules out",
        )
    ]


def test_r4_a_skill_dir_without_rules_needs_neither(tmp_path: Path, engine: str) -> None:
    _skill(tmp_path / "playbook", "plain", block="")
    (tmp_path / "playbook" / "skills" / "notes").mkdir()

    assert _check(tmp_path, engine) == []


# R6: an always rule inside a skill's rules/ is told where to move.


def test_r6_an_always_rule_in_the_layer_rules_dir_passes(tmp_path: Path, engine: str) -> None:
    _skill(tmp_path / "playbook", "s")
    _rule(tmp_path / "playbook" / "rules" / "house.md", "house", scope="always")

    assert _check(tmp_path, engine) == []


def test_r6_an_always_rule_in_a_skill_rules_dir_gets_a_move_hint(
    tmp_path: Path, engine: str
) -> None:
    rules_dir = _skill(tmp_path / "playbook", "s") / "rules"
    path = _rule(rules_dir / "nested" / "house.md", "house", scope="always")

    assert _messages(_check(tmp_path, engine)) == [
        (
            str(path),
            "always rule 'house' lies in the rules/ directory of skill 's', but always rules "
            "are never skill members; move it to "
            f"{tmp_path / 'playbook' / 'rules' / 'house.md'}, or set 'scope: scoped' to keep "
            "it in the skill",
        )
    ]


def test_r6_is_the_only_finding_for_a_misnamed_foreign_always_rule_in_a_skill(
    tmp_path: Path, engine: str
) -> None:
    """R1's "move to skills/t" and R2's "rename" would contradict R6's move hint."""
    rules_dir = _skill(tmp_path / "playbook", "s") / "rules"
    path = _rule(rules_dir / "1-house.md", "house", scope="always", extra="skill: t\n")

    assert _messages(_check(tmp_path, engine)) == [
        (
            str(path),
            "always rule 'house' lies in the rules/ directory of skill 's', but always rules "
            "are never skill members; move it to "
            f"{tmp_path / 'playbook' / 'rules' / '1-house.md'}, or set 'scope: scoped' to "
            "keep it in the skill",
        )
    ]


# R5 (D36): an engine scoped rule lives in its skill's rules/.


def test_r5_engine_scoped_rules_in_a_skill_and_overlay_scoped_rules_pass(
    tmp_path: Path, engine: str
) -> None:
    layer = _engine_layer(engine)
    _rule(_skill(layer, "s") / "rules" / "r.md", "r")
    _rule(layer / "rules" / "always" / "house.md", "house", scope="always")
    _rule(tmp_path / "playbook" / "rules" / "mine.md", "mine", extra="skill: s\n")

    assert _check(tmp_path, engine) == []


def test_r5_an_engine_scoped_rule_outside_a_skill_gets_a_move_hint(
    tmp_path: Path, engine: str
) -> None:
    layer = _engine_layer(engine)
    _skill(layer, "s")
    path = _rule(
        layer / "rules" / "languages" / "typing.md.j2", "python-typing", extra="skill: s\n"
    )

    assert _messages(_check(tmp_path, engine)) == [
        (
            str(path),
            "scoped rule 'python-typing' lies in the engine's rules/ directory "
            f"{path.parent}, which holds only always rules; move it to "
            f"{engine}/resources/skills/s/rules/python-typing.md.j2 and remove its "
            "'skill:' line",
        )
    ]


def test_r5_names_a_placeholder_skill_for_an_engine_scoped_rule_without_one(
    tmp_path: Path, engine: str
) -> None:
    """With no 'skill:' line there is nothing to remove, so the hint asks for none."""
    layer = _engine_layer(engine)
    path = _rule(layer / "rules" / "r.md", "r")

    assert (
        str(path),
        (
            f"scoped rule 'r' lies in the engine's rules/ directory {path.parent}, which holds "
            f"only always rules; move it to {engine}/resources/skills/<skill>/rules/r.md"
        ),
    ) in _messages(_check(tmp_path, engine))


class _RulesOnlySource(ArtifactSource):
    """A non-filesystem source: it has no layers, so R4 and R5 have no directory to read."""

    name = "rules-only"

    def __init__(self, rules: list[Rule]) -> None:
        self._rules = rules

    def list_rules(self) -> list[Rule]:
        return self._rules

    def list_prompts(self) -> list[Prompt]:
        return []

    def list_skills(self) -> list[Skill]:
        return []

    def list_eval_samples(self) -> list[EvalSample]:
        return []


def test_r5_is_silent_for_a_non_filesystem_source(tmp_path: Path) -> None:
    """Without layer roots there is no engine rules/ directory to place a rule outside of."""
    path = _rule(tmp_path / "rules" / "typing.md", "python-typing", extra="skill: s\n")
    rule = Rule.from_markdown(path, ENGINE_PACKAGE)

    assert check_rule_layout([rule], _RulesOnlySource([rule])) == []


def test_the_layer_of_an_in_skill_rule_outside_a_skill_rules_dir_is_an_error() -> None:
    """A home skill only comes from <layer>/skills/<dir>/rules/; any other path is a bug."""
    with pytest.raises(ValueError, match=r"x\.md is not under <layer>/skills/<dir>/rules/"):
        _layer_root(Path("playbook/rules/x.md"))
