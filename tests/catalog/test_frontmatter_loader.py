"""Every frontmatter the catalog ships parses alike with libyaml and with pure-Python PyYAML.

``split_frontmatter`` parses with ``yaml.CSafeLoader`` when PyYAML is built with
libyaml, because a sync parses hundreds of frontmatters. The C loader and the
pure-Python ``yaml.SafeLoader`` are separate implementations, so this pins, on the
content the engine actually ships, that the faster one changes no parsed value.
Without libyaml both sides are ``yaml.SafeLoader`` and the check holds trivially.
It is a ``catalog`` check, so a skill edit runs it in the skill lane (ADR 0010).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import yaml

from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from tests._catalog import CATALOG_ROOT, MARKDOWN_SUFFIXES

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_FENCE = "---"


def _opens_with_fence(text: str) -> bool:
    lines = text.splitlines(keepends=True)
    return bool(lines) and lines[0].rstrip("\r\n") == _FENCE


def _fenced_catalog_markdown() -> dict[Path, str]:
    """Every catalog markdown source, plain or Jinja, that opens with a frontmatter fence."""
    paths = sorted(CATALOG_ROOT.rglob("*"))
    sources = [path for path in paths if path.is_file() and path.name.endswith(MARKDOWN_SUFFIXES)]
    texts = {path: path.read_text(encoding="utf-8") for path in sources}
    return {path: text for path, text in texts.items() if _opens_with_fence(text)}


def _pure_python_mapping(text: str) -> object:
    """The frontmatter as ``yaml.SafeLoader`` reads it, fenced the way split_frontmatter fences it."""
    lines = text.splitlines(keepends=True)
    closing = next(i for i in range(1, len(lines)) if lines[i].rstrip("\r\n") == _FENCE)
    return yaml.load("".join(lines[1:closing]), Loader=yaml.SafeLoader) or {}


def test_every_catalog_frontmatter_parses_alike_with_libyaml_and_pure_python() -> None:
    fenced = _fenced_catalog_markdown()
    assert fenced, f"no markdown under {CATALOG_ROOT} opens with a frontmatter fence"

    mismatched = [
        path.relative_to(CATALOG_ROOT).as_posix()
        for path, text in fenced.items()
        if split_frontmatter(text)[0] != _pure_python_mapping(text)
    ]

    assert mismatched == []
