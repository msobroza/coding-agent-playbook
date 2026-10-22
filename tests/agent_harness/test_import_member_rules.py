"""Member rules round-trip through the harness inside their skill (prU D22, D5).

Source files -> the catalog loader -> ``AgentHarnessAdapter`` -> lossless
``import_harness`` + ``write_import`` -> the same source files, byte for byte:
an in-skill rule goes back to ``playbook/skills/<skill>/rules/<id>.md`` without
a ``skill:`` line, a ``playbook/rules`` rule that joins by ``skill:`` goes back
there with it, and ``section`` survives both. A best-effort import reads a
skill leaf's ``rules/*.md`` as members of that skill.
Split from ``test_import_roundtrip.py``, which is already over 500 lines.
"""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

from coding_agent_playbook.agent_harness.adapter import AgentHarnessAdapter
from coding_agent_playbook.agent_harness.importer import import_harness, write_import
from coding_agent_playbook.catalog.layers import REPO_LOCAL_SOURCE
from coding_agent_playbook.catalog.source import FileSystemArtifactSource

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.artifacts.skill import Skill

_SKILL_MD = (
    "---\nid: risk\nname: Risk\ndescription: Risk model conventions.\n"
    "playbook:\n  use_when: editing risk models\n  files: Risk model code\n---\n# Risk\n"
)
# Both rules are in the canonical form ``Rule.to_markdown`` writes (key order,
# ``version`` spelled out), the form a byte-identical round trip can promise.
_IN_SKILL_RULE = (
    "---\nid: risk-limits\nname: Limits\ndescription: Cap the exposure.\nscope: scoped\n"
    "version: 1\nglobs:\n- risk/**/*.py\npriority: 40\nsection: limits\n---\n# Limits\n\nCap it.\n"
)
_JOINING_RULE = (
    "---\nid: risk-joined\nname: Joined\ndescription: Joins by skill.\nscope: scoped\n"
    "version: 1\npriority: 50\nskill: risk\nsection: other\n---\n# Joined\n\nJoin it.\n"
)
_IN_SKILL = "skills/risk/rules/risk-limits.md"
_JOINING = "rules/risk-joined.md"


def _write_sources(playbook: Path) -> None:
    for rel, text in (
        ("skills/risk/SKILL.md", _SKILL_MD),
        (_IN_SKILL, _IN_SKILL_RULE),
        (_JOINING, _JOINING_RULE),
    ):
        path = playbook / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def _repo_local(repo: Path) -> tuple[list[Rule], list[Skill]]:
    source = FileSystemArtifactSource(repo_root=repo)
    rules = [r for r in source.list_rules() if r.source_package == REPO_LOCAL_SOURCE]
    skills = [s for s in source.list_skills() if s.source_package == REPO_LOCAL_SOURCE]
    return rules, skills


def _emit_from_sources(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    _write_sources(src / "playbook")
    rules, skills = _repo_local(src)
    harness = tmp_path / "harness"
    harness.mkdir()
    adapter = AgentHarnessAdapter()
    for skill in skills:
        adapter.write_skill(skill, harness)
    for rule in rules:
        adapter.write_rule(rule, harness)
    adapter.finalize(harness)
    return harness


def test_emitted_tree_puts_both_members_inside_the_skill(tmp_path: Path) -> None:
    harness = _emit_from_sources(tmp_path)

    rules_dir = harness / "skills" / "risk" / "rules"
    assert sorted(p.name for p in rules_dir.iterdir()) == ["risk-joined.md", "risk-limits.md"]
    assert not (harness / "references").exists()


def test_lossless_import_writes_byte_identical_rule_sources(tmp_path: Path) -> None:
    harness = _emit_from_sources(tmp_path)
    out = tmp_path / "out" / "playbook"

    result = import_harness(harness)
    write_import(result, out)

    assert result.warnings == []
    assert (out / _IN_SKILL).read_text(encoding="utf-8") == _IN_SKILL_RULE
    assert (out / _JOINING).read_text(encoding="utf-8") == _JOINING_RULE


def test_reimported_rules_load_as_the_originals(tmp_path: Path) -> None:
    harness = _emit_from_sources(tmp_path)
    write_import(import_harness(harness), tmp_path / "out" / "playbook")

    before, _ = _repo_local(tmp_path / "src")
    after, _ = _repo_local(tmp_path / "out")

    def semantic(rules: list[Rule]) -> list[dict[str, object]]:
        dicts = [r.to_dict() for r in rules]
        for data in dicts:
            data.pop("source_path")
        return sorted(dicts, key=lambda d: str(d["frontmatter"]))

    assert semantic(after) == semantic(before)


def test_member_of_a_skill_from_another_harness_goes_to_playbook_rules(tmp_path: Path) -> None:
    """The home skill is not in this harness: the rule keeps a ``skill:`` line instead."""
    harness = _emit_from_sources(tmp_path)
    result = import_harness(harness)
    result.skills.clear()
    out = tmp_path / "out" / "playbook"

    write_import(result, out)

    written = (out / "rules" / "risk-limits.md").read_text(encoding="utf-8")
    assert "skill: risk\n" in written
    assert not (out / "skills").exists()


def test_best_effort_reads_skill_rules_as_members(tmp_path: Path) -> None:
    harness = _emit_from_sources(tmp_path)
    shutil.rmtree(harness / ".playbook")  # no sidecar: a foreign harness
    out = tmp_path / "out" / "playbook"

    result = import_harness(harness)
    write_import(result, out)

    by_id = {r.frontmatter.id: r for r in result.rules}
    assert {rule_id: r.frontmatter.skill for rule_id, r in by_id.items()} == {
        "risk-joined": "risk",
        "risk-limits": "risk",
    }
    assert all(r.frontmatter.scope == "scoped" for r in by_id.values())
    assert sorted(p.name for p in (out / "skills" / "risk" / "rules").iterdir()) == [
        "risk-joined.md",
        "risk-limits.md",
    ]
    assert not any("needs 'skill: <skill-id>'" in w for w in result.warnings)
