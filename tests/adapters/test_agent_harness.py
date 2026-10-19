"""Tests for the agent_harness output adapter (PR H Track H2).

The adapter buffers rules/prompts/skills during ``write_*`` and composes the
whole harness tree in ``finalize``. These tests mirror the
``tests/adapters/test_claude_code.py`` style and cover the golden tree shape,
``HARNESS.md`` frontmatter + sentinel placement, routing files, the
``.leaf-detectors`` vocabulary, the ``.playbook/`` sidecar (manifest + leaf
marker), script-byte/exec-bit fidelity, prompt ``includes_rules`` inlining,
``cleanup_stale`` semantics, and entry-point discoverability.
"""

from __future__ import annotations

import os
import stat
from importlib import metadata
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.adapters.agent_harness_adapter import AgentHarnessAdapter
from coding_agent_playbook.adapters.base import Adapter
from coding_agent_playbook.agent_harness.manifest import read_manifest
from coding_agent_playbook.artifacts.prompt import Prompt, PromptFrontmatter
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.generated_output.sentinel import SENTINEL
from coding_agent_playbook.rendering.prompt_rule_delivery import SkillReference

if TYPE_CHECKING:
    from pathlib import Path

# --- builders --------------------------------------------------------------


def _make_rule(
    *,
    rule_id: str = "python-house-style",
    name: str = "Python house style",
    description: str = "House style for Python",
    scope: str = "always",
    globs: list[str] | None = None,
    priority: int = 10,
    tags: list[str] | None = None,
    applies_if: dict[str, object] | None = None,
    version: int = 1,
    body: str = "# House style\n\nUse type hints.\n",
) -> Rule:
    return Rule(
        frontmatter=RuleFrontmatter(
            id=rule_id,
            name=name,
            description=description,
            scope=scope,  # type: ignore[arg-type]
            globs=globs or [],
            priority=priority,
            tags=tags or [],
            applies_if=applies_if or {},
            version=version,
        ),
        body=body,
        template_body=body,
        is_templated=False,
        source_path=None,
        source_package="test",
    )


def _make_prompt(
    *,
    prompt_id: str = "review",
    name: str = "Review",
    description: str = "Review code",
    slash: str = "review",
    body: str = "# Review\n\nReview the diff.\n",
    includes_rules: list[str] | None = None,
    input_variables: list[dict[str, object]] | None = None,
) -> Prompt:
    return Prompt(
        frontmatter=PromptFrontmatter(
            id=prompt_id,
            name=name,
            description=description,
            slash=slash,
            includes_rules=includes_rules or [],
            input_variables=input_variables or [],
        ),
        body=body,
        template_body=body,
        is_templated=False,
        source_path=None,
        source_package="test",
    )


def _make_skill(
    *,
    skill_id: str = "query-database",
    name: str = "Query database",
    description: str = "Run SQL against the warehouse",
    body: str = "# Query database\n\nUse the run_query script.\n",
    scripts_dir: Path | None = None,
    references_dir: Path | None = None,
    extra_frontmatter: dict[str, object] | None = None,
) -> Skill:
    frontmatter: dict[str, object] = {
        "id": skill_id,
        "name": name,
        "description": description,
    }
    if extra_frontmatter:
        frontmatter.update(extra_frontmatter)
    return Skill(
        frontmatter=frontmatter,
        body=body,
        scripts_dir=scripts_dir,
        references_dir=references_dir,
        source_package="test",
    )


def _populate(
    adapter: AgentHarnessAdapter,
    *artifacts: Rule | Prompt | Skill,
    repo_root: Path,
) -> None:
    """Run the sync dispatch order (write_* then finalize) for ``artifacts``."""
    for artifact in artifacts:
        if isinstance(artifact, Rule):
            adapter.write_rule(artifact, repo_root)
        elif isinstance(artifact, Prompt):
            adapter.write_prompt(artifact, repo_root)
        elif isinstance(artifact, Skill):
            adapter.write_skill(artifact, repo_root)


# --- basics ----------------------------------------------------------------


def test_agent_harness_is_adapter_subclass():
    assert issubclass(AgentHarnessAdapter, Adapter)
    assert AgentHarnessAdapter.name == "agent_harness"


def test_agent_harness_finalize_with_no_artifacts_writes_nothing(tmp_path):
    """An empty buffer must produce no harness tree."""
    adapter = AgentHarnessAdapter()
    written = adapter.finalize(tmp_path)
    assert written == []
    assert not (tmp_path / "HARNESS.md").exists()


def test_write_methods_buffer_and_return_empty(tmp_path):
    adapter = AgentHarnessAdapter()
    assert adapter.write_rule(_make_rule(), tmp_path) == []
    assert adapter.write_prompt(_make_prompt(), tmp_path) == []
    assert adapter.write_skill(_make_skill(), tmp_path) == []
    # Nothing written until finalize.
    assert not (tmp_path / "HARNESS.md").exists()
    assert not (tmp_path / "rules").exists()


# --- golden tree shape -----------------------------------------------------


def _golden_repo(tmp_path: Path) -> tuple[Path, list[Path], AgentHarnessAdapter]:
    """Build a repo with a skill (1 exec + 1 non-exec script + a reference),
    a prompt, an always-rule and a scoped-rule; run the adapter; return root.
    """
    scripts_src = tmp_path / "src_scripts"
    scripts_src.mkdir()
    exec_script = scripts_src / "run_query.py"
    exec_script.write_text("#!/usr/bin/env python\nprint('q')\n", encoding="utf-8")
    exec_script.chmod(exec_script.stat().st_mode | stat.S_IXUSR)
    helper = scripts_src / "_db.py"
    helper.write_text("DB = 'helper'\n", encoding="utf-8")
    # ensure helper is NOT executable
    helper.chmod(helper.stat().st_mode & ~0o111)

    refs_src = tmp_path / "src_refs"
    refs_src.mkdir()
    (refs_src / "schema.md").write_text("# Schema\n", encoding="utf-8")

    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = AgentHarnessAdapter()
    _populate(
        adapter,
        _make_skill(
            skill_id="query-database",
            scripts_dir=scripts_src,
            references_dir=refs_src,
            extra_frontmatter={"license": "MIT"},
        ),
        _make_prompt(slash="review", prompt_id="review"),
        _make_rule(rule_id="python-house-style", scope="always", priority=10, tags=["python"]),
        _make_rule(
            rule_id="sql-guidelines",
            name="SQL guidelines",
            description="Use parameterized queries",
            scope="scoped",
            globs=["**/*.sql"],
            priority=40,
        ),
        repo_root=repo,
    )
    written = adapter.finalize(repo)
    return repo, written, adapter


def test_golden_tree_shape(tmp_path):
    repo, written, _ = _golden_repo(tmp_path)
    expected = {
        repo / "HARNESS.md",
        repo / ".leaf-detectors",
        repo / "skills" / "SKILLS.md",
        repo / "skills" / "query-database" / "SKILL.md",
        repo / "skills" / "query-database" / "scripts" / "run_query.py",
        repo / "skills" / "query-database" / "scripts" / "_db.py",
        repo / "skills" / "query-database" / "references" / "schema.md",
        repo / "prompts" / "PROMPTS.md",
        repo / "prompts" / "review" / "SKILL.md",
        repo / "rules" / "RULES.md",
        repo / "rules" / "10-python-house-style.md",
        repo / "references" / "REFERENCES.md",
        repo / "references" / "sql-guidelines.md",
        repo / ".playbook" / "manifest.toml",
        repo / ".playbook" / ".harnessleaf",
    }
    for path in expected:
        assert path.is_file(), f"missing {path}"
    assert set(written) >= expected


def test_no_evals_directory_emitted(tmp_path):
    repo, _, _ = _golden_repo(tmp_path)
    assert not (repo / "evals").exists()


# --- HARNESS.md ------------------------------------------------------------


def test_harness_md_frontmatter_and_sentinel(tmp_path):
    repo, _, _ = _golden_repo(tmp_path)
    content = (repo / "HARNESS.md").read_text(encoding="utf-8")
    lines = content.splitlines()
    # Frontmatter must be on line 1 for the harness parser's ^---.
    assert lines[0] == "---"
    assert "name:" in content
    assert "description:" in content
    # Frontmatter name defaults to repo dir name (no config harness field).
    assert "name: repo" in content
    # Sentinel is the FIRST BODY line (cannot be line 1).
    fm_end = next(i for i in range(1, len(lines)) if lines[i] == "---")
    assert SENTINEL in lines[fm_end + 1]
    assert lines[0] != f"<!-- {SENTINEL} -->"


def test_harness_md_always_consult_section_points_at_rules(tmp_path):
    repo, _, _ = _golden_repo(tmp_path)
    content = (repo / "HARNESS.md").read_text(encoding="utf-8")
    assert "Always consult these" in content
    # Pointer to the always-rule file.
    assert "rules/10-python-house-style.md" in content


def test_harness_md_indexes_top_level_dirs(tmp_path):
    repo, _, _ = _golden_repo(tmp_path)
    content = (repo / "HARNESS.md").read_text(encoding="utf-8")
    for top in ("skills", "prompts", "rules", "references"):
        assert top in content


def test_harness_md_indexes_what_it_emits_not_what_is_on_disk(tmp_path):
    """Regression: the index listed any top-level dir present on disk, so a leftover
    (or the user's own) ``skills/`` changed HARNESS.md, and ``sync --check`` — which
    renders into an empty scratch dir — reported drift forever."""
    rendered = []
    for repo in (tmp_path / "with-dirs", tmp_path / "empty"):
        repo.mkdir()
        adapter = AgentHarnessAdapter()
        _populate(adapter, _make_rule(scope="always"), repo_root=repo)
        if repo.name == "with-dirs":
            for leftover in ("skills/old/scripts", "prompts", "references"):
                (repo / leftover).mkdir(parents=True)
        adapter.finalize(repo)
        rendered.append((repo / "HARNESS.md").read_text(encoding="utf-8").replace(repo.name, "R"))
    assert rendered[0] == rendered[1]
    assert "`rules/`" in rendered[0]
    assert "`skills/`" not in rendered[0]


# --- routing files ---------------------------------------------------------


def test_routing_files_are_description_only_with_sentinel(tmp_path):
    repo, _, _ = _golden_repo(tmp_path)
    for routing in (
        "skills/SKILLS.md",
        "rules/RULES.md",
        "references/REFERENCES.md",
        "prompts/PROMPTS.md",
    ):
        content = (repo / routing).read_text(encoding="utf-8")
        lines = content.splitlines()
        assert lines[0] == "---"
        assert "description:" in content
        # Routing files carry NO name field.
        assert "name:" not in content
        # Sentinel on first body line.
        fm_end = next(i for i in range(1, len(lines)) if lines[i] == "---")
        assert SENTINEL in lines[fm_end + 1]


# --- skills ----------------------------------------------------------------


def test_skill_md_frontmatter_only_name_and_description(tmp_path):
    repo, _, _ = _golden_repo(tmp_path)
    content = (repo / "skills" / "query-database" / "SKILL.md").read_text(encoding="utf-8")
    lines = content.splitlines()
    assert lines[0] == "---"
    assert "name: Query database" in content
    assert "description: Run SQL against the warehouse" in content
    # Extra frontmatter (license) is NOT emitted natively — sidecar only.
    assert "license:" not in content
    fm_end = next(i for i in range(1, len(lines)) if lines[i] == "---")
    assert SENTINEL in lines[fm_end + 1]
    assert "Use the run_query script." in content


def test_skill_scripts_bytes_and_exec_bits_preserved(tmp_path):
    repo, _, _ = _golden_repo(tmp_path)
    exec_path = repo / "skills" / "query-database" / "scripts" / "run_query.py"
    helper_path = repo / "skills" / "query-database" / "scripts" / "_db.py"
    assert exec_path.read_text(encoding="utf-8") == "#!/usr/bin/env python\nprint('q')\n"
    assert helper_path.read_text(encoding="utf-8") == "DB = 'helper'\n"
    if os.name == "posix":
        assert os.stat(exec_path).st_mode & 0o111, "exec script should stay executable"
        assert not (os.stat(helper_path).st_mode & 0o111), "helper should stay non-exec"


def test_skill_reference_copied(tmp_path):
    repo, _, _ = _golden_repo(tmp_path)
    ref = repo / "skills" / "query-database" / "references" / "schema.md"
    assert ref.read_text(encoding="utf-8") == "# Schema\n"


# --- leaf detectors --------------------------------------------------------


def test_leaf_detectors_content(tmp_path):
    repo, _, _ = _golden_repo(tmp_path)
    content = (repo / ".leaf-detectors").read_text(encoding="utf-8")
    assert "skill=SKILL.md" in content


def test_no_leaf_detectors_when_no_skill_or_prompt(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = AgentHarnessAdapter()
    _populate(adapter, _make_rule(scope="always"), repo_root=repo)
    adapter.finalize(repo)
    assert not (repo / ".leaf-detectors").exists()


# --- prompts ---------------------------------------------------------------


def test_prompt_leaf_is_skill_shaped(tmp_path):
    repo, _, _ = _golden_repo(tmp_path)
    content = (repo / "prompts" / "review" / "SKILL.md").read_text(encoding="utf-8")
    assert content.splitlines()[0] == "---"
    assert "name: Review" in content
    assert "description: Review code" in content


def test_read_only_prompt_leaf_has_no_claude_frontmatter(tmp_path):
    """The leaf reuses the Claude command renderer without ``write_scope``: one fence pair only."""
    prompt = _make_prompt()
    prompt.frontmatter.write_scope = {"read_only": True}
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = AgentHarnessAdapter()
    _populate(adapter, prompt, repo_root=repo)
    adapter.finalize(repo)

    content = (repo / "prompts" / "review" / "SKILL.md").read_text(encoding="utf-8")

    assert "disallowed-tools" not in content
    assert [line for line in content.splitlines() if line == "---"] == ["---", "---"]
    sidecar = read_manifest(repo)
    assert sidecar is not None
    entry = sidecar.index_by_path()["prompts/review/SKILL.md"]
    assert entry.write_scope == {"read_only": True}


def test_prompt_includes_rules_inlined_via_registry(tmp_path):
    class _StubRegistry:
        def render_for_inclusion(self, rule_id: str, context: dict[str, object]) -> str:
            del context
            return f"### Rule {rule_id}\n\ninlined body.\n"

    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = AgentHarnessAdapter(rule_registry=_StubRegistry())
    _populate(
        adapter,
        _make_prompt(slash="review", prompt_id="review", includes_rules=["foo"]),
        repo_root=repo,
    )
    adapter.finalize(repo)
    content = (repo / "prompts" / "review" / "SKILL.md").read_text(encoding="utf-8")
    assert "### Rule foo" in content
    assert "inlined body." in content


#: The leaf the engine wrote before D15 for a ``refactor``-like prompt (no title in
#: its body, two included rules, one input variable), captured from that engine.
_REFACTOR_LEAF_BEFORE_D15 = (
    "---\nname: Refactor\ndescription: Refactor code\n---\n"
    f"<!-- {SENTINEL} -->\n\n"
    "# Refactor\n\nRefactor the code without changing behaviour.\n\n"
    "## The contract\n\nKeep tests green.\n\n"
    "## Reference rules\n\n### Rule foo\n\ninlined body.\n\n### Rule bar\n\ninlined body.\n\n"
    "## Input variables\n\n- `target` — what to refactor\n"
)


class _InliningRegistry:
    """Renders every rule id as ``### Rule <id>`` and points it at skill ``s`` too.

    Implements both faces of the sync's registry, so a leaf that took the
    Claude command's pointer block would show it.
    """

    def render_for_inclusion(self, rule_id: str, context: dict[str, object]) -> str:
        del context
        return f"### Rule {rule_id}\n\ninlined body.\n"

    def reference_for(self, rule_id: str) -> SkillReference | None:
        return SkillReference("s", f"references/{rule_id}.md")


def _refactor_leaf(tmp_path: Path) -> str:
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = AgentHarnessAdapter(rule_registry=_InliningRegistry())
    body = "Refactor the code without changing behaviour.\n\n## The contract\n\nKeep tests green.\n"
    prompt = _make_prompt(
        slash="refactor",
        prompt_id="refactor",
        name="Refactor",
        description="Refactor code",
        body=body,
        includes_rules=["foo", "bar"],
        input_variables=[{"name": "target", "description": "what to refactor"}],
    )
    _populate(adapter, prompt, repo_root=repo)
    adapter.finalize(repo)
    return (repo / "prompts" / "refactor" / "SKILL.md").read_text(encoding="utf-8")


def test_prompt_leaf_bytes_unchanged_for_a_prompt_without_rule_calls(tmp_path):
    """Regression (P3-6): a prompt that never called ``rule()`` keeps its leaf byte for byte."""
    assert _refactor_leaf(tmp_path) == _REFACTOR_LEAF_BEFORE_D15


def test_prompt_leaf_has_no_pointer_block(tmp_path):
    """The harness tree's scoped rules are not skill references: the leaf stays inline."""
    leaf = _refactor_leaf(tmp_path)

    assert "## Before you start" not in leaf
    assert "Load skill" not in leaf


def test_prompt_input_variables_noted_in_body(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = AgentHarnessAdapter()
    _populate(
        adapter,
        _make_prompt(
            slash="greet",
            prompt_id="greet",
            input_variables=[{"name": "target", "description": "who to greet"}],
        ),
        repo_root=repo,
    )
    adapter.finalize(repo)
    content = (repo / "prompts" / "greet" / "SKILL.md").read_text(encoding="utf-8")
    assert "target" in content


def test_prompt_is_templated_recorded_in_manifest(tmp_path):
    """Defect #3: a ``.md.j2`` prompt must record ``is_templated=True`` so the
    importer can round-trip its templated origin (rules already did this)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    templated = _make_prompt(slash="gen", prompt_id="gen")
    templated.is_templated = True
    adapter = AgentHarnessAdapter()
    _populate(adapter, templated, repo_root=repo)
    adapter.finalize(repo)
    manifest = read_manifest(repo)
    assert manifest is not None
    entry = manifest.index_by_path()["prompts/gen/SKILL.md"]
    assert entry.is_templated is True


# --- rules -----------------------------------------------------------------


def test_always_rule_is_md_content_file_with_description(tmp_path):
    repo, _, _ = _golden_repo(tmp_path)
    content = (repo / "rules" / "10-python-house-style.md").read_text(encoding="utf-8")
    lines = content.splitlines()
    assert lines[0] == "---"
    assert "description: House style for Python" in content
    assert "name:" not in content
    fm_end = next(i for i in range(1, len(lines)) if lines[i] == "---")
    assert SENTINEL in lines[fm_end + 1]
    assert "Use type hints." in content


def test_scoped_rule_goes_to_references(tmp_path):
    repo, _, _ = _golden_repo(tmp_path)
    ref = repo / "references" / "sql-guidelines.md"
    assert ref.is_file()
    content = ref.read_text(encoding="utf-8")
    assert "description: Use parameterized queries" in content
    # Not emitted under rules/.
    assert not (repo / "rules" / "40-sql-guidelines.md").exists()


# --- manifest sidecar ------------------------------------------------------


def test_manifest_completeness(tmp_path):
    repo, _, _ = _golden_repo(tmp_path)
    manifest = read_manifest(repo)
    assert manifest is not None
    index = manifest.index_by_path()

    rule_entry = index["rules/10-python-house-style.md"]
    assert rule_entry.kind == "rule"
    assert rule_entry.id == "python-house-style"
    assert rule_entry.scope == "always"
    assert rule_entry.priority == 10
    assert rule_entry.tags == ["python"]
    assert rule_entry.is_templated is False
    # The sidecar records the un-rendered ``name`` (the harness rule file emits
    # only ``description``) and the canonical source body for reconstruction.
    assert rule_entry.name == "Python house style"
    assert rule_entry.body == "# House style\n\nUse type hints.\n"

    scoped_entry = index["references/sql-guidelines.md"]
    assert scoped_entry.kind == "rule"
    assert scoped_entry.scope == "scoped"
    assert scoped_entry.globs == ["**/*.sql"]
    assert scoped_entry.name == "SQL guidelines"

    prompt_entry = index["prompts/review/SKILL.md"]
    assert prompt_entry.kind == "prompt"
    assert prompt_entry.slash == "review"
    # Prompt name + un-inlined source body + is_templated are all recorded so a
    # lossless import reconstructs the prompt independently of the rendered leaf.
    assert prompt_entry.name == "Review"
    assert prompt_entry.body == "# Review\n\nReview the diff.\n"
    assert prompt_entry.is_templated is False

    skill_entry = index["skills/query-database/SKILL.md"]
    assert skill_entry.kind == "skill"
    assert skill_entry.id == "query-database"
    assert skill_entry.name == "Query database"
    assert skill_entry.body == "# Query database\n\nUse the run_query script.\n"
    assert skill_entry.extra_frontmatter == {"license": "MIT"}
    by_script = {s.path: s.executable for s in skill_entry.scripts}
    assert by_script["skills/query-database/scripts/run_query.py"] is True
    assert by_script["skills/query-database/scripts/_db.py"] is False


def test_harnessleaf_sidecar_marker_is_empty(tmp_path):
    repo, _, _ = _golden_repo(tmp_path)
    marker = repo / ".playbook" / ".harnessleaf"
    assert marker.is_file()
    assert marker.read_text(encoding="utf-8") == ""


# --- cleanup_stale ---------------------------------------------------------


def test_cleanup_deletes_stale_sentinel_file_preserves_user_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = AgentHarnessAdapter()
    _populate(
        adapter,
        _make_rule(rule_id="old-rule", scope="always", priority=10),
        repo_root=repo,
    )
    adapter.finalize(repo)
    stale = repo / "rules" / "10-old-rule.md"
    assert stale.is_file()

    # A user-authored (no sentinel) file under an output dir must be preserved.
    user_file = repo / "rules" / "user-notes.md"
    user_file.write_text("# My notes\n\nKeep me.\n", encoding="utf-8")

    # Re-sync with NO artifacts: old-rule becomes stale.
    adapter2 = AgentHarnessAdapter()
    written2 = adapter2.finalize(repo)
    resolved = {p.resolve() for p in written2}
    deleted = adapter2.cleanup_stale(resolved, repo)
    assert stale.resolve() in {p.resolve() for p in deleted}
    assert not stale.exists()
    assert user_file.exists()


def test_cleanup_never_deletes_inside_a_skill_dir(tmp_path):
    """Superseded: cleanup used to delete a removed skill's ``SKILL.md`` and (via the
    prior manifest) its scripts — even a user-edited script. A skill dir mixes engine
    output with user edits, so only ``playbook sync``'s lockfile leftover policy
    (pristine + untracked + listed, SPEC §4.2 step 9) deletes there; the routing
    file ``skills/SKILLS.md`` (not inside a skill dir) is still cleaned here."""
    scripts_src = tmp_path / "src_scripts"
    scripts_src.mkdir()
    (scripts_src / "run.py").write_text("print('x')\n", encoding="utf-8")

    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = AgentHarnessAdapter()
    _populate(adapter, _make_skill(skill_id="s1", scripts_dir=scripts_src), repo_root=repo)
    adapter.finalize(repo)
    script = repo / "skills" / "s1" / "scripts" / "run.py"
    script.write_text("print('edited by hand')\n", encoding="utf-8")

    adapter2 = AgentHarnessAdapter()
    _populate(adapter2, _make_rule(scope="always"), repo_root=repo)
    written2 = adapter2.finalize(repo)
    deleted = adapter2.cleanup_stale({p.resolve() for p in written2}, repo)

    assert script.read_text(encoding="utf-8") == "print('edited by hand')\n"
    assert (repo / "skills" / "s1" / "SKILL.md").is_file()
    assert deleted == [repo / "skills" / "SKILLS.md"]


def test_cleanup_keeps_fresh_output_after_a_case_only_rename(tmp_path):
    """Case-insensitive FS: ``skills/Demo/SKILL.md`` *is* the just-written
    ``skills/demo/SKILL.md`` — comparing spellings deleted it on every sync."""
    probe = tmp_path / "CaseProbe"
    probe.mkdir()
    insensitive = (tmp_path / "caseprobe").exists()
    probe.rmdir()
    if not insensitive:
        pytest.skip("needs a case-insensitive filesystem")
    repo = tmp_path / "repo"
    repo.mkdir()
    first = AgentHarnessAdapter()
    _populate(first, _make_prompt(slash="Review"), repo_root=repo)
    first.finalize(repo)

    second = AgentHarnessAdapter()
    _populate(second, _make_prompt(slash="review"), repo_root=repo)
    written = second.finalize(repo)

    assert second.cleanup_stale({p.resolve() for p in written}, repo) == []
    assert (repo / "prompts" / "review" / "SKILL.md").is_file()


def test_cleanup_preserves_user_authored_non_sentinel_script_not_in_manifest(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    # Pre-existing user file under skills/ with no sentinel and not in any manifest.
    (repo / "skills").mkdir()
    user_asset = repo / "skills" / "user_data.bin"
    user_asset.write_bytes(b"\x00\x01\x02not-sentinel")

    adapter = AgentHarnessAdapter()
    _populate(adapter, _make_rule(scope="always"), repo_root=repo)
    written = adapter.finalize(repo)
    resolved = {p.resolve() for p in written}
    deleted = adapter.cleanup_stale(resolved, repo)
    assert user_asset.resolve() not in {p.resolve() for p in deleted}
    assert user_asset.exists()


def test_cleanup_preserves_undecodable_binary_not_in_manifest(tmp_path):
    """A binary file the engine never wrote (undecodable, absent from the prior
    manifest) must be preserved — the sentinel scan swallows UnicodeDecodeError.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "references").mkdir()
    # Invalid UTF-8 (lone continuation byte) so read_text raises.
    blob = repo / "references" / "logo.bin"
    blob.write_bytes(b"\xff\xfe\x00binary")

    adapter = AgentHarnessAdapter()
    _populate(adapter, _make_rule(scope="always"), repo_root=repo)
    written = adapter.finalize(repo)
    resolved = {p.resolve() for p in written}
    deleted = adapter.cleanup_stale(resolved, repo)
    assert blob.resolve() not in {p.resolve() for p in deleted}
    assert blob.exists()


# --- skill side-file edge cases --------------------------------------------


def test_skill_without_scripts_or_references(tmp_path):
    """A skill with neither scripts_dir nor references_dir emits only SKILL.md."""
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = AgentHarnessAdapter()
    _populate(adapter, _make_skill(skill_id="bare"), repo_root=repo)
    adapter.finalize(repo)
    skill_md = repo / "skills" / "bare" / "SKILL.md"
    assert skill_md.is_file()
    assert not (repo / "skills" / "bare" / "scripts").exists()
    assert not (repo / "skills" / "bare" / "references").exists()
    manifest = read_manifest(repo)
    assert manifest is not None
    entry = manifest.index_by_path()["skills/bare/SKILL.md"]
    assert entry.scripts == []


def test_skill_nested_script_and_reference_dirs_only_copy_files(tmp_path):
    """Nested directories under scripts/ and references/ are walked; only files
    are copied (the directory entries themselves are skipped, not copied).
    """
    scripts_src = tmp_path / "scripts"
    scripts_src.mkdir()
    (scripts_src / "sub").mkdir()
    (scripts_src / "sub" / "deep.py").write_text("print('deep')\n", encoding="utf-8")

    refs_src = tmp_path / "refs"
    refs_src.mkdir()
    (refs_src / "sub").mkdir()
    (refs_src / "sub" / "deep.md").write_text("# deep ref\n", encoding="utf-8")

    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = AgentHarnessAdapter()
    _populate(
        adapter,
        _make_skill(skill_id="nested", scripts_dir=scripts_src, references_dir=refs_src),
        repo_root=repo,
    )
    adapter.finalize(repo)
    deep_script = repo / "skills" / "nested" / "scripts" / "sub" / "deep.py"
    deep_ref = repo / "skills" / "nested" / "references" / "sub" / "deep.md"
    assert deep_script.read_text(encoding="utf-8") == "print('deep')\n"
    assert deep_ref.read_text(encoding="utf-8") == "# deep ref\n"


def _seed_files(root: Path, files: dict[str, bytes]) -> Path:
    for rel, content in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(content)
    return root


def test_skill_bytecode_caches_are_never_copied_or_recorded(tmp_path: Path) -> None:
    """Regression (review finding 8): ``scripts/__pycache__`` (``pip install`` byte-compiles
    pack scripts; an in-process import writes one) and stray ``*.pyc``/``*.pyo`` files are
    neither copied, returned as written, nor recorded as manifest script entries."""
    scripts_src = _seed_files(
        tmp_path / "scripts",
        {
            "run.py": b"print('x')\n",
            "__pycache__/run.cpython-312.pyc": b"\x00pyc",
            "sub/__pycache__/deep.cpython-313.pyc": b"\x00pyc",
            "stray.pyo": b"\x00pyo",
        },
    )
    refs_src = _seed_files(
        tmp_path / "refs",
        {"guide.md": b"# guide\n", "__pycache__/x.cpython-312.pyc": b"\x00", "old.pyc": b"\x00"},
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = AgentHarnessAdapter()
    skill = _make_skill(skill_id="cached", scripts_dir=scripts_src, references_dir=refs_src)
    _populate(adapter, skill, repo_root=repo)

    written = adapter.finalize(repo)

    skill_dir = repo / "skills" / "cached"
    on_disk = sorted(p.relative_to(skill_dir).as_posix() for p in skill_dir.rglob("*"))
    assert on_disk == ["SKILL.md", "references", "references/guide.md", "scripts", "scripts/run.py"]
    assert [p for p in written if "__pycache__" in p.parts or p.suffix in {".pyc", ".pyo"}] == []
    manifest = read_manifest(repo)
    assert manifest is not None
    entry = manifest.index_by_path()["skills/cached/SKILL.md"]
    assert [script.path for script in entry.scripts] == ["skills/cached/scripts/run.py"]


# --- entry-point discoverability -------------------------------------------


def test_entry_point_discoverable():
    eps = metadata.entry_points(group="coding_agent_playbook.adapters")
    by_name = {ep.name: ep for ep in eps}
    assert "agent_harness" in by_name
    cls = by_name["agent_harness"].load()
    assert cls is AgentHarnessAdapter
    assert cls.name == "agent_harness"


def test_entry_point_not_in_defaults():
    # Opt-in adapter: registered via its entry point but absent from the
    # default-adapter set, so a plain `init` never enables it.
    from coding_agent_playbook.commands._init_adapters import DEFAULT_ADAPTERS

    assert "agent_harness" not in DEFAULT_ADAPTERS

    # Complementary check: it IS discoverable via its entry point. Together these
    # prove "registered but opt-in" — this test fails if anyone adds
    # agent_harness to the default set.
    eps = metadata.entry_points(group="coding_agent_playbook.adapters")
    assert "agent_harness" in {ep.name for ep in eps}


# --- secrets in skill sources ----------------------------------------------


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlinks")
def test_skill_secrets_and_escaping_links_are_never_copied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: ``_copy_scripts``/``_copy_references`` copied a skill's ``.env``
    and a ``references/`` link out of the skill into the harness tree."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    skill_src = tmp_path / "src_skill"
    scripts_src = skill_src / "scripts"
    scripts_src.mkdir(parents=True)
    (scripts_src / "run.py").write_text("print('x')\n", encoding="utf-8")
    (scripts_src / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
    refs_src = skill_src / "references"
    refs_src.mkdir()
    (refs_src / "api.md").write_text("# API\n", encoding="utf-8")
    outside = tmp_path / "outside.md"
    outside.write_text("not the skill's\n", encoding="utf-8")
    (refs_src / "notes.md").symlink_to(outside)
    repo = tmp_path / "repo"
    repo.mkdir()
    adapter = AgentHarnessAdapter()
    skill = _make_skill(skill_id="s1", scripts_dir=scripts_src, references_dir=refs_src)

    _populate(adapter, skill, repo_root=repo)
    written = adapter.finalize(repo)

    skill_out = repo / "skills" / "s1"
    assert sorted(p.name for p in (skill_out / "scripts").iterdir()) == ["run.py"]
    assert sorted(p.name for p in (skill_out / "references").iterdir()) == ["api.md"]
    assert not any(p.name in {".env", "notes.md"} for p in written)
    manifest = read_manifest(repo)
    assert manifest is not None
    [entry] = [e for e in manifest.entries if e.kind == "skill"]
    assert [s.path for s in entry.scripts] == ["skills/s1/scripts/run.py"]
    err = capsys.readouterr().err
    assert ".env" in err
    assert "notes.md" in err
