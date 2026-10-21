"""Member rules discovered in ``<layer>/skills/<skill>/rules/`` (prU D5, ADR 0005).

The directory sets membership: a rule under a skill's ``rules/`` is a member of
that skill without ``skill:``. Layer order stays engine, overlays, extra
``resources/`` roots, repo-local; inside a layer ``rules/`` comes first, then
``skills/*/rules/``, so override-by-id keeps its meaning.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from coding_agent_playbook.artifacts.rule import Rule
from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE, REPO_LOCAL_SOURCE
from coding_agent_playbook.catalog.resolve import Collision, OverlayResolver
from coding_agent_playbook.catalog.source import FileSystemArtifactSource
from tests._catalog import KEPT_RULE_IDS

if TYPE_CHECKING:
    from pathlib import Path

_RULE = "---\nid: {id}\nname: {id}\ndescription: d\nscope: scoped\n{extra}---\nBody of {id}\n"
_SKILL = "---\nid: {id}\nname: {id}\ndescription: d\nplaybook:\n  files: f\n---\nBody\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _skill(layer: Path, dir_name: str, skill_id: str | None = None) -> Path:
    """``<layer>/skills/<dir_name>/`` holding a SKILL.md with id ``skill_id`` (default: dir)."""
    skill_dir = layer / "skills" / dir_name
    _write(skill_dir / "SKILL.md", _SKILL.format(id=skill_id or dir_name))
    return skill_dir


def _rule_file(path: Path, rule_id: str, extra: str = "") -> None:
    _write(path, _RULE.format(id=rule_id, extra=extra))


def _by_label(rules: list[Rule], label: str) -> dict[str, Rule]:
    return {rule.frontmatter.id: rule for rule in rules if rule.source_package == label}


def test_in_skill_rule_without_skill_key_is_a_member_of_its_skill(tmp_path: Path) -> None:
    skill_dir = _skill(tmp_path / "playbook", "s")
    _rule_file(skill_dir / "rules" / "r.md", "r")

    rules = FileSystemArtifactSource(repo_root=tmp_path).list_rules()

    rule = _by_label(rules, REPO_LOCAL_SOURCE)["r"]
    assert rule.frontmatter.skill == "s"
    assert rule.home_skill == "s"
    assert rule.source_path == skill_dir / "rules" / "r.md"


def test_home_skill_is_the_skill_md_id_not_the_directory_name(tmp_path: Path) -> None:
    skill_dir = _skill(tmp_path / "playbook", "dir-name", skill_id="declared-id")
    _rule_file(skill_dir / "rules" / "nested" / "r.md.j2", "r")

    rule = _by_label(FileSystemArtifactSource(repo_root=tmp_path).list_rules(), REPO_LOCAL_SOURCE)[
        "r"
    ]

    assert rule.frontmatter.skill == "declared-id"
    assert rule.is_templated


def test_explicit_skill_key_inside_a_skill_dir_is_kept(tmp_path: Path) -> None:
    """R1 (L0-06) reports the mismatch; the loader keeps what the author wrote."""
    skill_dir = _skill(tmp_path / "playbook", "s")
    _rule_file(skill_dir / "rules" / "r.md", "r", extra="skill: other\n")

    rule = _by_label(FileSystemArtifactSource(repo_root=tmp_path).list_rules(), REPO_LOCAL_SOURCE)[
        "r"
    ]

    assert (rule.frontmatter.skill, rule.home_skill) == ("other", "s")


def test_skill_dir_without_skill_md_contributes_no_rule(tmp_path: Path) -> None:
    """R4 (L0-06) reports such a directory; discovery skips it."""
    _rule_file(tmp_path / "playbook" / "skills" / "orphan" / "rules" / "r.md", "r")

    rules = FileSystemArtifactSource(repo_root=tmp_path).list_rules()

    assert "r" not in _by_label(rules, REPO_LOCAL_SOURCE)


def test_dot_dirs_under_a_skill_rules_dir_are_skipped(tmp_path: Path) -> None:
    skill_dir = _skill(tmp_path / "playbook", "s")
    _rule_file(skill_dir / "rules" / ".hidden" / "r.md", "r")

    rules = FileSystemArtifactSource(repo_root=tmp_path).list_rules()

    assert "r" not in _by_label(rules, REPO_LOCAL_SOURCE)


def test_layer_order_is_rules_dir_then_skill_rules_per_layer(tmp_path: Path) -> None:
    """Each layer's ``rules/`` first, then its ``skills/*/rules/``, layers in resolution order."""
    checkout = tmp_path / "src" / "acme" / "resources"
    _rule_file(checkout / "rules" / "a.md", "a", extra="skill: s\n")
    _rule_file(_skill(checkout, "s") / "rules" / "b.md", "b")
    playbook = tmp_path / "playbook"
    _rule_file(playbook / "rules" / "c.md", "c", extra="skill: t\n")
    _rule_file(_skill(playbook, "t") / "rules" / "d.md", "d")
    source = FileSystemArtifactSource(repo_root=tmp_path, extra_resource_roots=[checkout])

    rules = source.list_rules()

    tail = [
        (r.source_package, r.frontmatter.id)
        for r in rules
        if r.source_package != "coding_agent_playbook"
    ]
    assert tail == [
        ("acme", "a"),
        ("acme", "b"),
        (REPO_LOCAL_SOURCE, "c"),
        (REPO_LOCAL_SOURCE, "d"),
    ]


def test_repo_local_in_skill_rule_overrides_a_core_rule_of_the_same_id(tmp_path: Path) -> None:
    core_id = next(iter(KEPT_RULE_IDS))
    _rule_file(_skill(tmp_path / "playbook", "mine") / "rules" / f"{core_id}.md", core_id)
    rules = FileSystemArtifactSource(repo_root=tmp_path).list_rules()
    engine = [r for r in rules if r.source_package == ENGINE_PACKAGE]
    local = [r for r in rules if r.source_package == REPO_LOCAL_SOURCE]
    resolver = OverlayResolver()

    resolved = resolver.resolve_rules(engine, [], local)

    winner = next(r for r in resolved if r.frontmatter.id == core_id)
    assert (winner.source_package, winner.frontmatter.skill) == (REPO_LOCAL_SOURCE, "mine")
    assert Collision("rule", core_id, REPO_LOCAL_SOURCE, (ENGINE_PACKAGE,)) in resolver.collisions


def test_collect_rules_reports_a_malformed_in_skill_rule(tmp_path: Path) -> None:
    skill_dir = _skill(tmp_path / "playbook", "s")
    _write(skill_dir / "rules" / "bad.md", "no frontmatter here\n")

    _rules, errors = FileSystemArtifactSource(repo_root=tmp_path).collect_rules()

    assert [error.path for error in errors] == [skill_dir / "rules" / "bad.md"]


def test_to_markdown_does_not_write_the_injected_skill(tmp_path: Path) -> None:
    skill_dir = _skill(tmp_path / "playbook", "s")
    _rule_file(skill_dir / "rules" / "r.md", "r")
    rule = _by_label(FileSystemArtifactSource(repo_root=tmp_path).list_rules(), REPO_LOCAL_SOURCE)[
        "r"
    ]

    assert "skill:" not in rule.to_markdown()
    assert Rule.from_dict(rule.to_dict()) == rule


def test_a_malformed_skill_md_is_reported_against_each_of_its_rules(tmp_path: Path) -> None:
    skill_dir = tmp_path / "playbook" / "skills" / "s"
    _write(skill_dir / "SKILL.md", "no frontmatter\n")
    _rule_file(skill_dir / "rules" / "r.md", "r")

    rules, errors = FileSystemArtifactSource(repo_root=tmp_path).collect_rules()

    assert "r" not in _by_label(rules, REPO_LOCAL_SOURCE)
    assert [error.path for error in errors] == [skill_dir / "rules" / "r.md"]
    assert "its skill's SKILL.md:" in errors[0].problem
