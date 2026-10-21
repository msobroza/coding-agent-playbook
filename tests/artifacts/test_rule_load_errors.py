"""``Rule.from_markdown`` raises :class:`RuleLoadError` naming the file (prU D21, ADR 0005).

A malformed rule used to surface as a ``TypeError`` from ``RuleFrontmatter(**data)``
(or a bare ``ValueError`` from the fence split) that named neither the file nor
the keys a rule may set, so ``playbook validate`` and ``sync`` died with a
traceback. The optional ``section`` field round-trips and, when unset, leaves
a rule's markdown byte-identical.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.artifacts.rule import Rule, RuleLoadError

if TYPE_CHECKING:
    from pathlib import Path

_ALLOWED = (
    "allowed keys: id, name, description, scope, version, globs, applies_if, "
    "priority, tags, lint_codes, skill, section"
)
_VALID_HEAD = "id: r\nname: R\ndescription: d\nscope: always\n"


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "x.md"
    path.write_text(text, encoding="utf-8")
    return path


def _load_error(path: Path) -> RuleLoadError:
    with pytest.raises(RuleLoadError) as excinfo:
        Rule.from_markdown(path, "<repo-local>")
    return excinfo.value


def test_unknown_key_names_the_path_the_key_and_the_allowed_keys(tmp_path: Path) -> None:
    path = _write(tmp_path, f"---\n{_VALID_HEAD}impact: HIGH\n---\nBody\n")

    error = _load_error(path)

    assert error.path == path
    assert str(error) == f"{path}: unknown frontmatter key 'impact'; {_ALLOWED}"


def test_several_unknown_keys_are_all_named(tmp_path: Path) -> None:
    path = _write(tmp_path, f"---\n{_VALID_HEAD}impact: HIGH\nowner: me\n---\nBody\n")

    assert _load_error(path).problem == (f"unknown frontmatter keys 'impact', 'owner'; {_ALLOWED}")


def test_missing_required_key_is_named(tmp_path: Path) -> None:
    path = _write(tmp_path, "---\nid: r\nname: R\ndescription: d\n---\nBody\n")

    assert str(_load_error(path)) == (
        f"{path}: missing required frontmatter key 'scope'; {_ALLOWED}"
    )


def test_missing_fence_is_a_load_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "# no frontmatter\n")

    error = _load_error(path)

    assert error.path == path
    assert "'---' frontmatter fence" in error.problem


def test_non_mapping_frontmatter_is_a_load_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "---\n- a\n- b\n---\nBody\n")

    assert str(_load_error(path)) == f"{path}: frontmatter must be a YAML mapping"


def test_invalid_yaml_is_a_load_error(tmp_path: Path) -> None:
    path = _write(tmp_path, "---\nid: [unclosed\n---\nBody\n")

    assert _load_error(path).problem.startswith("invalid YAML frontmatter: ")


def test_section_round_trips(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        f"---\n{_VALID_HEAD}version: 1\npriority: 50\nsection: error-handling\n---\nBody\n",
    )

    rule = Rule.from_markdown(path, "<repo-local>")

    assert rule.frontmatter.section == "error-handling"
    assert rule.to_markdown() == path.read_text(encoding="utf-8")
    assert Rule.from_dict(rule.to_dict()) == rule


def test_rule_without_section_renders_byte_identical_markdown(tmp_path: Path) -> None:
    text = f"---\n{_VALID_HEAD}version: 1\npriority: 40\ntags:\n- python\n---\n# R\n\nBody.\n"
    path = _write(tmp_path, text)

    rule = Rule.from_markdown(path, "<repo-local>")

    assert rule.frontmatter.section is None
    assert rule.to_markdown() == text
