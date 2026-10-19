"""Round-trip tests for the harness importer (PR H Track H3).

The key deliverable: canonical ``Rule`` / ``Prompt`` / ``Skill`` -> the
``AgentHarnessAdapter`` (write_* + finalize, which drops the ``.playbook``
sidecar) -> :func:`import_harness` -> canonical artifacts, asserting the
reconstructed objects equal the originals.

Two fidelity tiers are exercised (``specs/prH-agent-harness.md`` §C):

- **Lossless** — with the ``.playbook/manifest.toml`` sidecar present, every
  non-native field (rule ``scope``/``globs``/``priority``/..., prompt
  ``includes_rules``/``slash``/..., skill ``extra_frontmatter``) is rebuilt
  from the manifest. ``to_dict`` equality holds for the *semantic* content
  (provenance — ``source_path``/``source_package`` and, for skills, the
  side-file *paths* — legitimately changes on import; the §C note says script
  fidelity is covered by a separate file-level assertion, not ``to_dict``).
- **Best-effort** — with the sidecar removed (foreign harness), artifacts are
  inferred structurally and lossiness warnings are surfaced.
"""

from __future__ import annotations

import os
import shutil
import stat
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.agent_harness.adapter import AgentHarnessAdapter
from coding_agent_playbook.agent_harness.importer import import_harness, write_import
from coding_agent_playbook.artifacts.hook import Hook
from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import Skill
from tests.hook_samples import resolved_from_disk

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook

# --- builders --------------------------------------------------------------


def _make_always_rule() -> Rule:
    body = "# House style\n\nUse type hints.\n"
    return Rule(
        frontmatter=RuleFrontmatter(
            id="python-house-style",
            # HARD CASE: ``name != id``. Native rule frontmatter carries only
            # ``description`` (the harness has no rule ``name`` field), so the
            # un-rendered ``name`` must round-trip via the sidecar manifest, NOT
            # by defaulting to the id. A human-facing name proves it.
            name="Python House Style (Human)",
            description="House style for Python",
            scope="always",
            globs=[],
            priority=10,
            tags=["python"],
            applies_if={},
            version=1,
        ),
        body=body,
        template_body=body,
        is_templated=False,
        source_path=None,
        source_package="test",
    )


def _make_scoped_rule() -> Rule:
    body = "# SQL\n\nUse parameterized queries.\n"
    return Rule(
        frontmatter=RuleFrontmatter(
            id="sql-guidelines",
            # HARD CASE: ``name != id`` for a scoped rule too.
            name="SQL Guidelines (Human)",
            description="Use parameterized queries",
            scope="scoped",
            skill="python-coding",
            globs=["**/*.sql"],
            priority=40,
            tags=[],
            applies_if={"orm": "sqlalchemy"},
            version=2,
        ),
        body=body,
        template_body=body,
        is_templated=False,
        source_path=None,
        source_package="test",
    )


#: The ORIGINAL, un-inlined prompt source body. After emission WITH a registry
#: the harness leaf interleaves the inlined ``includes_rules`` fragment (see
#: ``_StubRegistry``), so a lossless import must recover THIS string, not the
#: rendered/inlined on-disk body.
_PROMPT_BODY = "# Review\n\nReview the diff carefully.\n"


def _make_prompt() -> Prompt:
    # HARD CASE: ``is_templated=True`` (``.md.j2`` origin) AND a populated
    # ``includes_rules`` that the adapter genuinely inlines when emitted with a
    # rule registry. The lossless tier must recover the original un-inlined body
    # and the templated flag — both via the sidecar, not the rendered leaf file.
    return Prompt(
        frontmatter=PromptFrontmatter(
            id="review",
            name="Review",
            description="Review code",
            slash="review",
            version=3,
            applies_if={},
            input_variables=[],
            includes_rules=["python-house-style"],
            eval_tasks=[],
        ),
        body=_PROMPT_BODY,
        template_body=_PROMPT_BODY,
        is_templated=True,
        source_path=None,
        source_package="test",
    )


class _StubRegistry:
    """Inlines ``includes_rules`` into the harness leaf so the emitted body is
    genuinely rendered/inlined — proving the lossless importer recovers the
    ORIGINAL source body from the sidecar rather than the on-disk leaf.
    """

    def render_for_inclusion(self, rule_id: str, context: dict[str, Any]) -> str:
        del context
        return f"### Rule {rule_id}\n\ninlined rule body that is NOT in the source.\n"


def _make_skill(scripts_dir: Path, references_dir: Path) -> Skill:
    return Skill(
        frontmatter={
            "id": "query-database",
            "name": "Query database",
            "description": "Run SQL against the warehouse",
            "license": "MIT",
        },
        body="# Query database\n\nUse the run_query script.\n",
        scripts_dir=scripts_dir,
        references_dir=references_dir,
        source_package="test",
    )


def _build_script_dirs(tmp_path: Path) -> tuple[Path, Path]:
    scripts_src = tmp_path / "src_scripts"
    scripts_src.mkdir()
    exec_script = scripts_src / "run_query.py"
    exec_script.write_text("#!/usr/bin/env python\nprint('q')\n", encoding="utf-8")
    exec_script.chmod(exec_script.stat().st_mode | stat.S_IXUSR)
    helper = scripts_src / "_db.py"
    helper.write_text("DB = 'helper'\n", encoding="utf-8")
    helper.chmod(helper.stat().st_mode & ~0o111)

    refs_src = tmp_path / "src_refs"
    refs_src.mkdir()
    (refs_src / "schema.md").write_text("# Schema\n", encoding="utf-8")
    return scripts_src, refs_src


def _emit_harness(tmp_path: Path) -> tuple[Path, Skill]:
    """Emit a golden harness tree from canonical fixtures; return (root, skill).

    The adapter is run WITH a rule registry so the prompt's ``includes_rules``
    are genuinely inlined into ``prompts/review/SKILL.md`` — the harness leaf's
    body therefore differs from the canonical source body, forcing the lossless
    importer to reconstruct the body from the sidecar (not the rendered file).
    """
    scripts_src, refs_src = _build_script_dirs(tmp_path)
    skill = _make_skill(scripts_src, refs_src)
    repo = tmp_path / "harness"
    repo.mkdir()
    adapter = AgentHarnessAdapter(rule_registry=_StubRegistry())
    adapter.write_skill(skill, repo)
    adapter.write_prompt(_make_prompt(), repo)
    adapter.write_rule(_make_always_rule(), repo)
    adapter.write_rule(_make_scoped_rule(), repo)
    adapter.finalize(repo)
    return repo, skill


# --- comparison helpers ----------------------------------------------------


def _semantic(obj: Rule | Prompt) -> dict[str, Any]:
    """``to_dict`` minus provenance fields that change on import."""
    data = obj.to_dict()
    data.pop("source_path", None)
    data.pop("source_package", None)
    return data


def _skill_semantic(skill: Skill) -> dict[str, Any]:
    """Skill content comparable across import: frontmatter + body only.

    ``scripts_dir`` / ``references_dir`` are *paths* (they point at the imported
    tree, not the original sources) and ``source_package`` is provenance — the
    §C note says script fidelity is asserted file-level, not via ``to_dict``.
    """
    data = skill.to_dict()
    return {"frontmatter": data["frontmatter"], "body": data["body"]}


# --- lossless tier ---------------------------------------------------------


def test_lossless_rules_round_trip(tmp_path):
    repo, _ = _emit_harness(tmp_path)
    result = import_harness(repo)
    by_id = {r.frontmatter.id: r for r in result.rules}
    assert _semantic(by_id["python-house-style"]) == _semantic(_make_always_rule())
    assert _semantic(by_id["sql-guidelines"]) == _semantic(_make_scoped_rule())


def test_lossless_rule_name_round_trips_when_name_differs_from_id(tmp_path):
    """HARD CASE (defect #1): the un-rendered ``name`` (which the harness format
    drops) must be recovered from the sidecar, not defaulted to the id."""
    repo, _ = _emit_harness(tmp_path)
    result = import_harness(repo)
    by_id = {r.frontmatter.id: r for r in result.rules}
    assert by_id["python-house-style"].frontmatter.name == "Python House Style (Human)"
    assert by_id["sql-guidelines"].frontmatter.name == "SQL Guidelines (Human)"


def test_lossless_prompt_round_trips_including_includes_rules(tmp_path):
    repo, _ = _emit_harness(tmp_path)
    result = import_harness(repo)
    assert len(result.prompts) == 1
    prompt = result.prompts[0]
    assert _semantic(prompt) == _semantic(_make_prompt())
    # The non-native field is rebuilt from the sidecar, not from the body.
    assert prompt.frontmatter.includes_rules == ["python-house-style"]
    assert prompt.frontmatter.version == 3
    assert prompt.frontmatter.slash == "review"


def test_lossless_prompt_output_contract_survives_emit_then_import(tmp_path):
    """``output_contract`` rides the sidecar: emit -> import gives the same regexes."""
    contract = [r"(?i)\bCWE-\d+\b|no (reachable|exploitable)"]
    prompt = _make_prompt()
    prompt.frontmatter.output_contract = list(contract)
    repo = tmp_path / "harness"
    repo.mkdir()
    adapter = AgentHarnessAdapter(rule_registry=_StubRegistry())
    adapter.write_prompt(prompt, repo)
    adapter.finalize(repo)

    [imported] = import_harness(repo).prompts

    assert imported.frontmatter.output_contract == contract
    assert _semantic(imported) == _semantic(prompt)


def test_lossless_prompt_write_scope_round_trips(tmp_path):
    """specs/prK-lifecycle-hooks.md §A.7: ``write_scope`` survives emit -> sidecar -> import."""
    scoped = [_make_prompt(), _make_prompt()]
    scoped[0].frontmatter.write_scope = {"read_only": True}
    scoped[1].frontmatter.id = scoped[1].frontmatter.slash = "generate-tests"
    scoped[1].frontmatter.write_scope = {"globs": ["tests/**", "**/conftest.py"]}
    repo = tmp_path / "harness"
    repo.mkdir()
    adapter = AgentHarnessAdapter(rule_registry=_StubRegistry())
    for prompt in scoped:
        adapter.write_prompt(prompt, repo)
    adapter.finalize(repo)

    result = import_harness(repo)

    by_id = {prompt.frontmatter.id: prompt for prompt in result.prompts}
    assert [_semantic(by_id[p.frontmatter.id]) for p in scoped] == [_semantic(p) for p in scoped]


def test_lossless_rule_lint_codes_round_trip(tmp_path):
    """specs/prK-lifecycle-hooks.md §A.7: ``lint_codes`` survives emit -> sidecar -> import.

    Both rule placements (an always rule's ``rules/`` leaf, a scoped rule's
    ``references/`` leaf) record it.
    """
    linked = [_make_always_rule(), _make_scoped_rule()]
    linked[0].frontmatter.lint_codes = {"warn": ["E722", "BLE001"]}
    linked[1].frontmatter.lint_codes = {
        "warn": ["ANN001"],
        "when": [{"applies_if": {"python_version": ">=3.12"}, "warn": ["UP046"]}],
    }
    repo = tmp_path / "harness"
    repo.mkdir()
    adapter = AgentHarnessAdapter(rule_registry=_StubRegistry())
    for rule in linked:
        adapter.write_rule(rule, repo)
    adapter.finalize(repo)

    result = import_harness(repo)

    by_id = {rule.frontmatter.id: rule for rule in result.rules}
    assert [_semantic(by_id[r.frontmatter.id]) for r in linked] == [_semantic(r) for r in linked]


def test_lossless_prompt_body_recovers_original_uninlined_body(tmp_path):
    """HARD CASE (defect #2): the harness leaf inlines ``includes_rules`` (the
    registry fragment is genuinely written into ``prompts/review/SKILL.md``), so
    the reconstructed body must be the ORIGINAL source body, not the rendered
    leaf — proving the importer reconstructs from the sidecar, not the file."""
    repo, _ = _emit_harness(tmp_path)
    # The on-disk leaf really IS inlined (sanity check that the test exercises
    # the hard case rather than passing trivially).
    leaf = (repo / "prompts" / "review" / "SKILL.md").read_text(encoding="utf-8")
    assert "inlined rule body that is NOT in the source." in leaf

    result = import_harness(repo)
    prompt = result.prompts[0]
    assert prompt.body == _PROMPT_BODY
    assert prompt.template_body == _PROMPT_BODY
    assert "inlined rule body that is NOT in the source." not in prompt.body


def test_lossless_prompt_is_templated_round_trips(tmp_path):
    """HARD CASE (defect #3): a ``.md.j2`` prompt (``is_templated=True``) must
    round-trip as templated, not be hardcoded to ``False``."""
    repo, _ = _emit_harness(tmp_path)
    result = import_harness(repo)
    assert result.prompts[0].is_templated is True


def test_lossless_skill_frontmatter_and_body_round_trip(tmp_path):
    repo, skill = _emit_harness(tmp_path)
    result = import_harness(repo)
    assert len(result.skills) == 1
    imported = result.skills[0]
    assert _skill_semantic(imported) == _skill_semantic(skill)
    # extra_frontmatter (license) is rebuilt from the sidecar.
    assert imported.frontmatter["license"] == "MIT"


def test_lossless_no_warnings(tmp_path):
    repo, _ = _emit_harness(tmp_path)
    result = import_harness(repo)
    assert result.warnings == []


def test_lossless_scripts_round_trip_byte_for_byte_with_exec_bit(tmp_path):
    """§C note: ``to_dict`` does NOT cover script bytes/modes — assert file-level."""
    repo, _ = _emit_harness(tmp_path)
    result = import_harness(repo)
    skill = result.skills[0]
    assert skill.scripts_dir is not None
    exec_script = skill.scripts_dir / "run_query.py"
    helper = skill.scripts_dir / "_db.py"
    assert exec_script.read_text(encoding="utf-8") == "#!/usr/bin/env python\nprint('q')\n"
    assert helper.read_text(encoding="utf-8") == "DB = 'helper'\n"
    if os.name == "posix":
        assert os.stat(exec_script).st_mode & 0o111, "exec script must be restored executable"
        assert not (os.stat(helper).st_mode & 0o111), "helper must stay non-exec"


def test_lossless_reference_round_trips(tmp_path):
    repo, _ = _emit_harness(tmp_path)
    result = import_harness(repo)
    skill = result.skills[0]
    assert skill.references_dir is not None
    assert (skill.references_dir / "schema.md").read_text(encoding="utf-8") == "# Schema\n"


# --- best-effort tier (no sidecar) -----------------------------------------


def _strip_sidecar(repo: Path) -> None:
    shutil.rmtree(repo / ".playbook")  # a foreign harness: no sidecar, no hook copies


def test_best_effort_infers_structure_and_warns(tmp_path):
    repo, _ = _emit_harness(tmp_path)
    _strip_sidecar(repo)
    result = import_harness(repo)

    # Structurally correct kinds: rules/ -> always Rule, references/ -> scoped
    # Rule, prompts/ -> Prompt, skill leaf -> Skill.
    rule_ids = {r.frontmatter.id for r in result.rules}
    assert "python-house-style" in rule_ids  # from rules/
    assert "sql-guidelines" in rule_ids  # from references/
    always = next(r for r in result.rules if r.frontmatter.id == "python-house-style")
    scoped = next(r for r in result.rules if r.frontmatter.id == "sql-guidelines")
    assert always.frontmatter.scope == "always"
    assert scoped.frontmatter.scope == "scoped"

    assert {p.frontmatter.slash for p in result.prompts} == {"review"}
    assert {s.frontmatter["id"] for s in result.skills} == {"query-database"}

    # Lossiness is surfaced, not silently applied.
    assert result.warnings, "best-effort import must surface lossiness warnings"


def test_best_effort_scripts_present_on_disk(tmp_path):
    repo, _ = _emit_harness(tmp_path)
    _strip_sidecar(repo)
    result = import_harness(repo)
    skill = result.skills[0]
    assert skill.scripts_dir is not None
    assert (skill.scripts_dir / "run_query.py").read_text(encoding="utf-8") == (
        "#!/usr/bin/env python\nprint('q')\n"
    )


def _hand_built_foreign_harness(tmp_path: Path) -> Path:
    """A foreign harness (no sidecar) with a raw asset and a .harnessleaf dir."""
    root = tmp_path / "foreign"
    root.mkdir()
    (root / "HARNESS.md").write_text(
        "---\nname: foreign\ndescription: a foreign harness\n---\nRole.\n",
        encoding="utf-8",
    )
    refs = root / "references"
    refs.mkdir()
    # A markdown content rule with no sentinel.
    (refs / "schema-notes.md").write_text(
        "---\ndescription: schema notes\n---\nUse snake_case columns.\n", encoding="utf-8"
    )
    # A raw (binary) asset — no canonical home.
    (refs / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\nbinary")
    # An opaque, .harnessleaf-terminated directory.
    evals = root / "evals"
    evals.mkdir()
    (evals / ".harnessleaf").write_text("", encoding="utf-8")
    (evals / "case.md").write_text("# a case\n", encoding="utf-8")
    return root


def test_best_effort_raw_asset_and_opaque_leaf_warn(tmp_path):
    root = _hand_built_foreign_harness(tmp_path)
    result = import_harness(root)

    # The scoped rule (references/*.md) is reconstructed.
    assert {r.frontmatter.id for r in result.rules} == {"schema-notes"}
    assert result.rules[0].frontmatter.scope == "scoped"
    # The raw asset is tracked as an opaque passthrough.
    assert [p.name for p in result.raw_assets] == ["logo.png"]
    # Both the raw asset and the opaque .harnessleaf dir surface warnings.
    joined = "\n".join(result.warnings)
    assert "logo.png" in joined
    assert "opaque" in joined


# --- hooks (specs/prK-lifecycle-hooks.md §C.6) -------------------------------


def _emit_hook_harness(tmp_path: Path) -> tuple[Path, ResolvedHook]:
    hook = resolved_from_disk(tmp_path / "src", body="Advice {{ x }}.\n", templated=True)
    repo = tmp_path / "harness"
    adapter = AgentHarnessAdapter()
    adapter.write_hook(hook, repo)
    adapter.finalize(repo)
    return repo, hook


def test_lossless_hook_import_restores_frontmatter_body_exec_bits(tmp_path):
    repo, hook = _emit_hook_harness(tmp_path)
    copied = repo / ".playbook" / "hooks" / "guard-x" / "scripts" / "check.sh"
    copied.chmod(0o644)  # a transport (zip, Windows checkout) that drops exec bits

    result = import_harness(repo)

    assert result.warnings == []
    [imported] = result.hooks
    source = hook.definition
    assert source is not None
    assert imported.frontmatter == source.frontmatter
    assert (imported.template_body, imported.is_templated) == (source.template_body, True)
    if os.name == "posix":
        assert copied.stat().st_mode & stat.S_IXUSR
    into = tmp_path / "playbook"
    write_import(result, into)
    written = into / "hooks" / "guard-x" / "HOOK.md.j2"
    reread = Hook.from_markdown(written, "<repo-local>")
    assert (reread.frontmatter, reread.template_body) == (source.frontmatter, source.template_body)
    script = into / "hooks" / "guard-x" / "scripts" / "check.sh"
    assert script.read_bytes() == b"#!/bin/sh\nexit 0\n"
    assert (into / "hooks" / "guard-x" / "scripts" / "lib" / "data.txt").is_file()
    if os.name == "posix":
        assert script.stat().st_mode & stat.S_IXUSR


def test_guardrail_file_not_imported_as_rule_in_lossless_mode(tmp_path):
    repo, _ = _emit_hook_harness(tmp_path)
    assert (repo / "rules" / "30-guardrail-guard-x.md").is_file()

    result = import_harness(repo)

    assert result.rules == []
    assert [hook.frontmatter.id for hook in result.hooks] == ["guard-x"]


def test_best_effort_guardrail_warns_lossy(tmp_path):
    repo, _ = _emit_hook_harness(tmp_path)
    _strip_sidecar(repo)

    result = import_harness(repo)

    assert result.hooks == []
    assert [rule.frontmatter.id for rule in result.rules] == ["guardrail-guard-x"]
    assert (
        "rule 'guardrail-guard-x': looks like a degraded hook advisory; the canonical hook "
        "cannot be reconstructed without .playbook/manifest.toml"
    ) in result.warnings


def test_lossless_import_skips_a_hook_entry_that_no_longer_parses(tmp_path):
    repo, _ = _emit_hook_harness(tmp_path)
    manifest = repo / ".playbook" / "manifest.toml"
    manifest.write_text(manifest.read_text("utf-8").replace("timeout = 2.0", 'timeout = "2s"'))

    result = import_harness(repo)

    assert result.hooks == []
    [warning] = result.warnings
    assert warning.startswith("manifest entry '.playbook/hooks/guard-x/HOOK.md': ")
    assert warning.endswith("; skipped")
