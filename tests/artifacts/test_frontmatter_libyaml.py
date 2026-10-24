"""How frontmatter parses with libyaml and in pure Python (the libyaml loader in frontmatter.py).

split_frontmatter parses with yaml.CSafeLoader when PyYAML is built with libyaml,
and re-parses a chunk libyaml rejects with yaml.SafeLoader, so errors read the same
on every build. tests/catalog/test_frontmatter_loader.py checks the shipped content.
"""

from __future__ import annotations

import pytest
import yaml

from coding_agent_playbook.artifacts.frontmatter import _load_yaml, split_frontmatter

_NEEDS_LIBYAML = pytest.mark.skipif(
    not yaml.__with_libyaml__, reason="PyYAML is built without libyaml"
)
#: A chunk libyaml accepts and the pure-Python loader rejects (a trailing tab).
_TAB_CHUNK = "id: x\t\n"


def test_split_frontmatter_propagates_invalid_yaml_as_yaml_error() -> None:
    """Callers (Rule.from_markdown, the skill-rule walk, validation) catch
    yaml.YAMLError to name the file, whichever loader parsed it."""
    with pytest.raises(yaml.YAMLError):
        split_frontmatter("---\nid: [unclosed\n---\nbody\n")


@_NEEDS_LIBYAML
def test_invalid_frontmatter_raises_the_pure_python_error_on_a_libyaml_build() -> None:
    """libyaml's errors lack the source snippet and caret; users get the same text on every build."""
    chunk = "id: [unclosed\n"
    with pytest.raises(yaml.YAMLError) as pure:
        yaml.load(chunk, Loader=yaml.SafeLoader)

    with pytest.raises(yaml.YAMLError) as split:
        split_frontmatter(f"---\n{chunk}---\nbody\n")

    assert str(split.value) == str(pure.value)


@_NEEDS_LIBYAML
def test_libyaml_accepts_a_tab_the_pure_python_loader_rejects() -> None:
    """The known gap between builds that the loader comment states: shipped content avoids it."""
    assert _load_yaml(_TAB_CHUNK, with_libyaml=True) == {"id": "x"}
    with pytest.raises(yaml.YAMLError):
        _load_yaml(_TAB_CHUNK, with_libyaml=False)


def test_without_libyaml_the_frontmatter_parses_in_pure_python() -> None:
    assert _load_yaml("id: x\nversion: 1\n", with_libyaml=False) == {"id": "x", "version": 1}
