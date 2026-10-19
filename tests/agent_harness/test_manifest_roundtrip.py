"""Tests for agent_harness.manifest — .playbook/manifest.toml sidecar (Track H1)."""

from __future__ import annotations

import dataclasses
import datetime as dt
import tomllib
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.agent_harness.adapter import AgentHarnessAdapter
from coding_agent_playbook.agent_harness.importer import import_harness
from coding_agent_playbook.agent_harness.manifest import (
    ManifestEntry,
    ScriptEntry,
    _format_scalar,
    read_manifest,
    write_manifest,
)
from coding_agent_playbook.artifacts.hook_frontmatter import HookFrontmatter
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import Skill
from tests.hook_samples import hook_frontmatter
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


VERDICT = r"(?im)^\W*(verdict\W*)?(approve with comments|approve|request changes)\W*$"


def test_roundtrip_prompt_output_contract(tmp_path: Path) -> None:
    """Regex backslashes survive the TOML sidecar (specs/prK-hook-pack.md §E.2)."""
    entry = _prompt_entry()
    entry.output_contract = [VERDICT, r"(?i)\bCWE-\d+\b|no (reachable|exploitable)"]
    write_manifest(tmp_path, [entry])

    manifest = read_manifest(tmp_path)

    assert manifest is not None
    assert manifest.entries == [entry]
    assert _tables(tmp_path)[0]["output_contract"][0] == VERDICT


def test_prompt_without_output_contract_emits_no_key(tmp_path: Path) -> None:
    """Existing manifests stay byte-identical: no empty ``output_contract`` key."""
    write_manifest(tmp_path, [_prompt_entry()])

    text = (tmp_path / ".playbook" / "manifest.toml").read_text(encoding="utf-8")

    assert "output_contract" not in text


@pytest.mark.parametrize("scope", [{"read_only": True}, {"globs": ["tests/**", "**/conftest.py"]}])
def test_roundtrip_prompt_write_scope(tmp_path: Path, scope: dict[str, Any]) -> None:
    """specs/prK-lifecycle-hooks.md §A.7: the sidecar carries ``write_scope`` as an inline table."""
    entry = _prompt_entry()
    entry.write_scope = scope

    write_manifest(tmp_path, [entry])

    manifest = read_manifest(tmp_path)
    assert manifest is not None and manifest.entries == [entry]
    assert _tables(tmp_path)[0]["write_scope"] == scope


def test_prompt_without_write_scope_emits_no_key(tmp_path: Path) -> None:
    """Existing sidecars stay byte-identical: an unscoped prompt writes no ``write_scope`` line."""
    write_manifest(tmp_path, [_prompt_entry(), _rule_entry()])

    text = (tmp_path / ".playbook" / "manifest.toml").read_text(encoding="utf-8")

    assert "write_scope" not in text
    assert all("write_scope" not in table for table in _tables(tmp_path))


def test_roundtrip_rule_lint_codes_inline_table(tmp_path: Path) -> None:
    """specs/prK-lifecycle-hooks.md §A.7: ``lint_codes`` rides the sidecar as one inline table.

    A rule without it writes no ``lint_codes`` line (existing sidecars stay byte-identical).
    """
    entry = _scoped_rule_entry()
    entry.lint_codes = {
        "warn": ["ANN001", "B006"],
        "when": [{"applies_if": {"python_version": ">=3.12"}, "warn": ["UP046"]}],
    }

    write_manifest(tmp_path, [entry, _rule_entry()])

    manifest = read_manifest(tmp_path)
    text = (tmp_path / ".playbook" / "manifest.toml").read_text(encoding="utf-8")
    assert manifest is not None and manifest.entries == [entry, _rule_entry()]
    assert text.count("lint_codes = {") == 1
    assert _tables(tmp_path)[0]["lint_codes"] == entry.lint_codes
    assert "lint_codes" not in _tables(tmp_path)[1]


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


# --- kind "hook" (specs/prK-lifecycle-hooks.md §C.6) -------------------------


def _hook_entry(**frontmatter: object) -> ManifestEntry:
    return ManifestEntry(
        kind="hook",
        path=".playbook/hooks/guard-x/HOOK.md",
        id="guard-x",
        name="Guard X",
        body="Advice for {{ project.name }}.\n",
        is_templated=True,
        hook_frontmatter=hook_frontmatter(**frontmatter).to_mapping(),
        scripts=[ScriptEntry(path=".playbook/hooks/guard-x/scripts/check.sh", executable=True)],
    )


def test_hook_kind_roundtrip(tmp_path: Path) -> None:
    write_manifest(tmp_path, [_rule_entry(), _hook_entry()])

    manifest = read_manifest(tmp_path)

    assert manifest is not None
    assert manifest.entries == [_rule_entry(), _hook_entry()]
    [table] = [t for t in _tables(tmp_path) if t["kind"] == "hook"]
    assert table["hook_frontmatter"]["handler"] == {"builtin": "guard_x"}
    assert "hook_frontmatter" not in next(t for t in _tables(tmp_path) if t["kind"] == "rule")


def test_hook_float_timeout_and_config_roundtrip(tmp_path: Path) -> None:
    handler = {"builtin": "guard_x", "config": {"threshold": 0.75, "limits": {"max": 3}}}
    entry = _hook_entry(timeout=2.5, handler=handler)
    write_manifest(tmp_path, [entry])

    manifest = read_manifest(tmp_path)

    assert manifest is not None
    [read] = manifest.entries
    rebuilt = HookFrontmatter.from_mapping(read.hook_frontmatter, where="manifest")
    assert rebuilt == hook_frontmatter(timeout=2.5, handler=handler)
    assert repr(read.hook_frontmatter["timeout"]) == "2.5"
    assert repr(read.hook_frontmatter["handler"]["config"]["threshold"]) == "0.75"


def test_old_engine_unknown_kind_warns_and_skips(tmp_path: Path) -> None:
    """A newer engine's kind reads fine and is skipped with a warning (no schema bump)."""
    (tmp_path / "HARNESS.md").write_text("---\nname: h\ndescription: d\n---\n", "utf-8")
    sidecar = tmp_path / ".playbook"
    sidecar.mkdir()
    (sidecar / "manifest.toml").write_text(
        'schema = 1\n\n[[artifact]]\nkind = "widget"\npath = "HARNESS.md"\nid = "w"\n'
        "widget_fields = { a = 1 }\n",
        "utf-8",
    )

    result = import_harness(tmp_path)

    assert (result.rules, result.prompts, result.skills, result.hooks) == ([], [], [], [])
    assert result.warnings == ["manifest entry 'HARNESS.md' has unsupported kind 'widget'; skipped"]


def _tables(root: Path) -> list[dict[str, Any]]:
    with (root / ".playbook" / "manifest.toml").open("rb") as handle:
        tables: list[dict[str, Any]] = tomllib.load(handle)["artifact"]
    return tables


#: ``_serialize`` output for the entries below, captured before the shared TOML
#: writer (``toml_writer``, then named ``_toml``) gained floats/dates and
#: ASCII-only bare keys (branch ``claude/init-local-overrides``, cut from
#: ``1dd8f74``). The shared primitives changed; these bytes must not.
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
