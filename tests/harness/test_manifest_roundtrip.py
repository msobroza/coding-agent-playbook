"""Tests for harness.manifest — .playbook/manifest.toml sidecar (Track H1)."""

from __future__ import annotations

import dataclasses
import datetime as dt
import tomllib
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.adapters.agent_harness_adapter import AgentHarnessAdapter
from coding_agent_playbook.commands.import_harness import import_harness
from coding_agent_playbook.harness.manifest import (
    ManifestEntry,
    ScriptEntry,
    _format_scalar,
    read_manifest,
    write_manifest,
)
from coding_agent_playbook.types import Rule, RuleFrontmatter, Skill
from tests.toml_equality import assert_toml_identical

if TYPE_CHECKING:
    from pathlib import Path


def _rule_entry() -> ManifestEntry:
    return ManifestEntry(
        kind="rule",
        path="rules/10-python-house-style.md",
        id="python-house-style",
        # ``name`` and the un-rendered source ``body`` are part of the canonical
        # reconstruction payload the sidecar records for every kind.
        name="Python House Style (Human)",
        body="# House style\n\nUse type hints.\n",
        is_templated=False,
        scope="always",
        priority=10,
        globs=[],
        applies_if={},
        tags=["python"],
        version=1,
    )


def _scoped_rule_entry() -> ManifestEntry:
    return ManifestEntry(
        kind="rule",
        path="references/db-conventions.md",
        id="db-conventions",
        name="DB Conventions",
        body="# DB\n\nUse snake_case.\n",
        is_templated=True,
        scope="scoped",
        priority=50,
        globs=["**/*.sql"],
        applies_if={"language": "sql"},
        tags=[],
        version=2,
    )


def _prompt_entry() -> ManifestEntry:
    return ManifestEntry(
        kind="prompt",
        path="prompts/refactor/SKILL.md",
        id="refactor",
        name="Refactor",
        body="# Refactor\n\nRefactor the code.\n",
        is_templated=True,
        slash="refactor",
        input_variables=[{"name": "target", "required": True}],
        includes_rules=["python-house-style"],
        eval_tasks=["refactor-001"],
        applies_if={},
        version=3,
    )


def _skill_entry() -> ManifestEntry:
    return ManifestEntry(
        kind="skill",
        path="skills/query-database/SKILL.md",
        id="query-database",
        name="Query database",
        body="# Query database\n\nUse the run_query script.\n",
        extra_frontmatter={"license": "MIT"},
        scripts=[
            ScriptEntry(path="skills/query-database/scripts/run_query.py", executable=True),
            ScriptEntry(path="skills/query-database/scripts/_db.py", executable=False),
        ],
    )


def _eval_entry() -> ManifestEntry:
    return ManifestEntry(
        kind="eval_task",
        path="evals/refactor-001.toml",
        id="refactor-001",
    )


def test_read_manifest_absent_returns_none(tmp_path: Path) -> None:
    assert read_manifest(tmp_path) is None


def test_write_manifest_creates_file_with_schema(tmp_path: Path) -> None:
    out = write_manifest(tmp_path, [_rule_entry()])
    assert out == tmp_path / ".playbook" / "manifest.toml"
    assert out.is_file()
    parsed = tomllib.loads(out.read_text(encoding="utf-8"))
    assert parsed["schema"] == 1


def test_roundtrip_rule(tmp_path: Path) -> None:
    write_manifest(tmp_path, [_rule_entry(), _scoped_rule_entry()])
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.entries == [_rule_entry(), _scoped_rule_entry()]


def test_roundtrip_prompt(tmp_path: Path) -> None:
    write_manifest(tmp_path, [_prompt_entry()])
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.entries == [_prompt_entry()]


def test_roundtrip_records_name_body_and_is_templated(tmp_path: Path) -> None:
    """The canonical reconstruction payload (``name`` + un-rendered source
    ``body`` + ``is_templated``) round-trips for rules, prompts and skills —
    these are what let the importer rebuild losslessly without the rendered leaf.
    """
    write_manifest(tmp_path, [_rule_entry(), _prompt_entry(), _skill_entry()])
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    index = manifest.index_by_path()

    rule = index["rules/10-python-house-style.md"]
    assert rule.name == "Python House Style (Human)"
    assert rule.body == "# House style\n\nUse type hints.\n"
    assert rule.is_templated is False

    prompt = index["prompts/refactor/SKILL.md"]
    assert prompt.name == "Refactor"
    assert prompt.body == "# Refactor\n\nRefactor the code.\n"
    # is_templated is now recorded for prompts too (defect #3).
    assert prompt.is_templated is True

    skill = index["skills/query-database/SKILL.md"]
    assert skill.name == "Query database"
    assert skill.body == "# Query database\n\nUse the run_query script.\n"


def test_roundtrip_skill_with_scripts(tmp_path: Path) -> None:
    write_manifest(tmp_path, [_skill_entry()])
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    [entry] = manifest.entries
    assert entry == _skill_entry()
    assert entry.scripts[0].executable is True
    assert entry.scripts[1].executable is False


def test_roundtrip_eval_task(tmp_path: Path) -> None:
    write_manifest(tmp_path, [_eval_entry()])
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.entries == [_eval_entry()]


def test_roundtrip_full_manifest(tmp_path: Path) -> None:
    entries = [
        _rule_entry(),
        _scoped_rule_entry(),
        _prompt_entry(),
        _skill_entry(),
        _eval_entry(),
    ]
    write_manifest(tmp_path, entries)
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.entries == entries


def test_index_by_path_lookup(tmp_path: Path) -> None:
    write_manifest(tmp_path, [_rule_entry(), _skill_entry()])
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    index = manifest.index_by_path()
    assert index["rules/10-python-house-style.md"].id == "python-house-style"
    assert index["skills/query-database/SKILL.md"].kind == "skill"
    assert "missing.md" not in index


def test_written_toml_is_parseable_and_has_array_of_tables(tmp_path: Path) -> None:
    out = write_manifest(tmp_path, [_rule_entry(), _skill_entry()])
    text = out.read_text(encoding="utf-8")
    assert "[[artifact]]" in text
    assert "[[artifact.script]]" in text
    # Must be valid TOML.
    tomllib.loads(text)


def test_write_manifest_overwrites_existing(tmp_path: Path) -> None:
    write_manifest(tmp_path, [_rule_entry()])
    write_manifest(tmp_path, [_eval_entry()])
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.entries == [_eval_entry()]


def test_roundtrip_special_chars_in_strings(tmp_path: Path) -> None:
    entry = ManifestEntry(
        kind="rule",
        path="rules/weird.md",
        id="weird",
        name='weird "name" with\ttabs',
        body="line1\nline2\twith tab\n",
        is_templated=False,
        scope="always",
        priority=1,
        globs=['has"quote', "back\\slash", "tab\tchar", "line\nbreak", "ret\rurn", "ctrl\x01x"],
        applies_if={"note": 'a "quoted" value'},
        tags=[],
        version=1,
    )
    write_manifest(tmp_path, [entry])
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.entries == [entry]


def test_roundtrip_non_identifier_key_in_inline_table(tmp_path: Path) -> None:
    # A frontmatter key with a dot/space must be emitted as a quoted TOML key.
    entry = ManifestEntry(
        kind="skill",
        path="skills/x/SKILL.md",
        id="x",
        name="X",
        body="# X\n",
        extra_frontmatter={"weird key.dotted": "v"},
    )
    write_manifest(tmp_path, [entry])
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.entries == [entry]


def test_format_scalar_rejects_unsupported_type() -> None:
    with pytest.raises(TypeError):
        _format_scalar(object())


#: ``_serialize`` output for the entries below, captured before ``_toml`` gained
#: floats/dates and ASCII-only bare keys (branch ``claude/init-local-overrides``,
#: cut from ``1dd8f74``). The shared primitives changed; these bytes must not.
_GOLDEN_MANIFEST = (
    "schema = 1\n"
    "\n"
    "[[artifact]]\n"
    'kind = "rule"\n'
    'path = "rules/10-python-house-style.md"\n'
    'id = "python-house-style"\n'
    'name = "Python House Style"\n'
    'body = "# House style\\n\\nUse \\"type\\" hints.\\n"\n'
    "is_templated = false\n"
    'scope = "scoped"\n'
    "priority = 10\n"
    'globs = ["**/*.py"]\n'
    'tags = ["python"]\n'
    "version = 1\n"
    'applies_if = { language = "python", "has framework" = ["fastapi"] }\n'
    "\n"
    "[[artifact]]\n"
    'kind = "prompt"\n'
    'path = "prompts/refactor/SKILL.md"\n'
    'id = "refactor"\n'
    'name = "Refactor"\n'
    'body = "Refactor.\\n"\n'
    "is_templated = true\n"
    'slash = "refactor"\n'
    "version = 3\n"
    'input_variables = [{ name = "target", required = true }]\n'
    'includes_rules = ["python-house-style"]\n'
    'eval_tasks = ["refactor-001"]\n'
    "applies_if = {}\n"
    "\n"
    "[[artifact]]\n"
    'kind = "skill"\n'
    'path = "skills/query-database/SKILL.md"\n'
    'id = "query-database"\n'
    'name = "Query database"\n'
    'body = "# Q\\n"\n'
    'extra_frontmatter = { license = "MIT", meta = { "a.b" = 1 } }\n'
    "\n"
    "[[artifact.script]]\n"
    'path = "skills/query-database/scripts/run.py"\n'
    "executable = true\n"
    "\n"
    "[[artifact.script]]\n"
    'path = "skills/query-database/scripts/_db.py"\n'
    "executable = false\n"
    "\n"
    "[[artifact]]\n"
    'kind = "eval_task"\n'
    'path = "evals/refactor-001.toml"\n'
    'id = "refactor-001"\n'
)


def test_manifest_bytes_are_unchanged_by_the_shared_toml_primitives(tmp_path: Path) -> None:
    entries = [
        ManifestEntry(
            kind="rule",
            path="rules/10-python-house-style.md",
            id="python-house-style",
            name="Python House Style",
            body='# House style\n\nUse "type" hints.\n',
            is_templated=False,
            scope="scoped",
            priority=10,
            globs=["**/*.py"],
            applies_if={"language": "python", "has framework": ["fastapi"]},
            tags=["python"],
            version=1,
        ),
        ManifestEntry(
            kind="prompt",
            path="prompts/refactor/SKILL.md",
            id="refactor",
            name="Refactor",
            body="Refactor.\n",
            is_templated=True,
            slash="refactor",
            input_variables=[{"name": "target", "required": True}],
            includes_rules=["python-house-style"],
            eval_tasks=["refactor-001"],
            applies_if={},
            version=3,
        ),
        ManifestEntry(
            kind="skill",
            path="skills/query-database/SKILL.md",
            id="query-database",
            name="Query database",
            body="# Q\n",
            extra_frontmatter={"license": "MIT", "meta": {"a.b": 1}},
            scripts=[
                ScriptEntry(path="skills/query-database/scripts/run.py", executable=True),
                ScriptEntry(path="skills/query-database/scripts/_db.py", executable=False),
            ],
        ),
        ManifestEntry(kind="eval_task", path="evals/refactor-001.toml", id="refactor-001"),
    ]
    written = write_manifest(tmp_path, entries)
    assert written.read_text(encoding="utf-8") == _GOLDEN_MANIFEST
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert manifest.entries == entries


# --- floats and dates: YAML frontmatter yields them; the manifest used to refuse --

_PLUS_0530 = dt.timezone(dt.timedelta(hours=5, minutes=30))
#: What ``yaml.safe_load`` gives for ``{ratio: 1.5, weight: 1.0, released: 2024-01-02,
#: at: 2024-01-02T10:00:00+05:30}`` — floats (integral too), a date, an aware datetime.
_YAML_TYPED_VALUES: dict[str, object] = {
    "ratio": 1.5,
    "weight": 1.0,
    "released": dt.date(2024, 1, 2),
    "at": dt.datetime(2024, 1, 2, 10, 0, tzinfo=_PLUS_0530),
}


def test_manifest_round_trips_floats_and_dates_with_their_types(tmp_path: Path) -> None:
    """Regression (behaviour change, v0.18): ``_toml.format_scalar`` refused floats
    and dates, so such a frontmatter value stopped ``sync`` with ``TypeError:
    manifest TOML does not support value of type float``. Compared type-strictly:
    ``1.0`` must not come back as ``1``, nor the datetime at another offset."""
    entries = [
        dataclasses.replace(_scoped_rule_entry(), applies_if=dict(_YAML_TYPED_VALUES)),
        dataclasses.replace(
            _prompt_entry(), input_variables=[{"name": "budget", **_YAML_TYPED_VALUES}]
        ),
        dataclasses.replace(
            _skill_entry(), extra_frontmatter={"metadata": dict(_YAML_TYPED_VALUES)}
        ),
    ]
    write_manifest(tmp_path, entries)
    manifest = read_manifest(tmp_path)
    assert manifest is not None
    assert_toml_identical(
        [dataclasses.asdict(entry) for entry in manifest.entries],
        [dataclasses.asdict(entry) for entry in entries],
    )


def test_import_harness_rebuilds_float_and_date_frontmatter(tmp_path: Path) -> None:
    """End to end: the ``agent_harness`` adapter writes the sidecar, and
    ``import-harness`` rebuilds the same typed values from it."""
    rule = Rule(
        frontmatter=RuleFrontmatter(
            id="typed",
            name="Typed",
            description="Typed applies_if",
            scope="scoped",
            globs=["**/*.py"],
            applies_if=dict(_YAML_TYPED_VALUES),
        ),
        body="# Typed\n",
        template_body="# Typed\n",
        is_templated=False,
        source_path=None,
        source_package="test",
    )
    skill = Skill(
        frontmatter={
            "id": "typed-skill",
            "name": "Typed skill",
            "description": "Typed metadata",
            "metadata": dict(_YAML_TYPED_VALUES),
        },
        body="# Typed skill\n",
        scripts_dir=None,
        references_dir=None,
        source_package="test",
    )
    adapter = AgentHarnessAdapter()
    adapter.write_rule(rule, tmp_path)
    adapter.write_skill(skill, tmp_path)
    adapter.finalize(tmp_path)

    result = import_harness(tmp_path)
    [imported_rule] = result.rules
    [imported_skill] = result.skills
    assert_toml_identical(imported_rule.frontmatter.applies_if, _YAML_TYPED_VALUES)
    assert_toml_identical(imported_skill.frontmatter["metadata"], _YAML_TYPED_VALUES)
