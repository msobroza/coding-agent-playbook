"""Tests for the artifact identity leaf (specs/prT-package-layout.md 4.19, H11).

- :func:`template_source` — how an artifact's template is named in error messages.
- :func:`artifact_id_of` — the id collision tracking and provenance lookups key on.
"""

from __future__ import annotations

import dataclasses

import pytest

from coding_agent_playbook.artifacts.identity import (
    artifact_id_of,
    source_package_of,
    template_source,
)
from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import Skill
from tests.engine_modules import engine_module
from tests.import_probe import new_modules_after


def _make_rule(rule_id: str, source: str, name: str = "Rule", body: str = "body\n") -> Rule:
    return Rule(
        frontmatter=RuleFrontmatter(
            id=rule_id,
            name=name,
            description="desc",
            scope="always",
            priority=50,
        ),
        body=body,
        template_body=body,
        is_templated=False,
        source_path=None,
        source_package=source,
    )


def _make_prompt(prompt_id: str, source: str) -> Prompt:
    return Prompt(
        frontmatter=PromptFrontmatter(
            id=prompt_id,
            name="Prompt",
            description="desc",
            slash=prompt_id,
        ),
        body="body\n",
        template_body="body\n",
        is_templated=False,
        source_path=None,
        source_package=source,
    )


# --- template_source -------------------------------------------------------


def test_template_source_names_the_source_path_else_the_artifact_id(tmp_path):
    source = tmp_path / "playbook" / "rules" / "gated.md.j2"
    rule = dataclasses.replace(_make_rule("gated", "<repo-local>"), source_path=source)

    assert template_source(rule) == str(source)
    assert template_source(dataclasses.replace(rule, source_path=None)) == "gated"
    assert template_source(_make_prompt("review", "engine")) == "review"


# --- artifact_id_of --------------------------------------------------------


def test_artifact_id_of_reads_the_frontmatter_id_or_the_skill_dict_key() -> None:
    skill = Skill(
        frontmatter={"id": "tdd"},
        body="",
        scripts_dir=None,
        references_dir=None,
        source_package="engine",
    )
    nameless = dataclasses.replace(skill, frontmatter={"name": "no id"})

    assert artifact_id_of(_make_rule("a", "engine")) == "a"
    assert artifact_id_of(skill) == "tdd"
    assert artifact_id_of(nameless) == "skill"


def test_artifact_id_of_refuses_an_artifact_without_an_id() -> None:
    class _Bare:
        frontmatter = ("not", "a", "mapping")

    with pytest.raises(TypeError, match="cannot extract id from artifact"):
        artifact_id_of(_Bare())


# --- source_package_of ------------------------------------------------------


def test_source_package_of_names_the_layer_or_unknown() -> None:
    class _Unsourced:
        source_package = None

    assert source_package_of(_make_rule("a", "<repo-local>")) == "<repo-local>"
    assert source_package_of(_Unsourced()) == "<unknown>"
    assert source_package_of(object()) == "<unknown>"


def test_identity_is_a_leaf_that_loads_no_other_engine_module() -> None:
    """``rendering`` imports ``template_source`` from here (H11), so it stays a stdlib leaf."""
    loaded = new_modules_after("import coding_agent_playbook.artifacts.identity")

    assert [name for name in loaded if name.startswith("coding_agent_playbook.")] == [
        engine_module("coding_agent_playbook.artifacts"),
        engine_module("coding_agent_playbook.artifacts.identity"),
    ]
